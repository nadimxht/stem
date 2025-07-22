import redis
from rq import SimpleWorker, Queue
from rq import Connection
import os
from utils.yt_download import download_audio
from utils.demucs import separate_stems
import logging
import time
from loguru import logger

logging.basicConfig(filename='worker.log', level=logging.ERROR)

# Add loguru logger for profiling
logger.add("worker_profile.log", rotation="1 week", retention="4 weeks", level="INFO")

# Check for GPU availability (for Demucs)
try:
    import torch
    GPU_AVAILABLE = torch.cuda.is_available()
    logger.info(f"GPU available: {GPU_AVAILABLE}")
except ImportError:
    GPU_AVAILABLE = False
    logger.info("PyTorch not installed, cannot check GPU availability.")

# To process jobs in parallel, run multiple worker.py processes (e.g., in separate terminals or with a process manager)

redis_conn = redis.Redis()
with Connection(redis_conn):
    q = Queue(connection=redis_conn)
    worker = SimpleWorker([q])
    worker.work()

def process_job(youtube_url, job_id):
    start = time.time()
    print(f"Processing job: {job_id} for URL: {youtube_url}")
    redis_conn = redis.Redis()
    job_key = f"job:{job_id}"
    try:
        # Set job as pending
        redis_conn.hset(job_key, "status", "pending")
        # Prepare directories
        base_dir = os.path.join("jobs", job_id)
        os.makedirs(base_dir, exist_ok=True)
        # Download audio
        audio_download_start = time.time()
        audio_path = download_audio(youtube_url, base_dir)
        audio_download_end = time.time()
        logger.info(f"Job {job_id}: Audio download took {audio_download_end - audio_download_start:.2f} seconds")
        # Separate stems
        stems_start = time.time()
        # If Demucs supports device selection, pass device
        demucs_kwargs = {}
        if GPU_AVAILABLE:
            demucs_kwargs['device'] = 'cuda'
        stems_dir = separate_stems(audio_path, base_dir, **demucs_kwargs) if demucs_kwargs else separate_stems(audio_path, base_dir)
        stems_end = time.time()
        logger.info(f"Job {job_id}: Stem separation took {stems_end - stems_start:.2f} seconds")
        logger.info(f"Job {job_id}: Total job time: {stems_end - start:.2f} seconds")
        # List stems
        stems = [f[:-4] for f in os.listdir(stems_dir) if f.endswith('.wav')]
        # Update Redis with completion
        redis_conn.hset(job_key, mapping={
            "status": "completed",
            "stems": ",".join(stems),
            "stems_dir": stems_dir
        })
        redis_conn.hset(f"url_cache:{youtube_url}", mapping={
            "stems": ",".join(stems),
            "stems_dir": stems_dir
        })
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        redis_conn.hset(job_key, mapping={
            "status": "error",
            "error": str(e)
        })