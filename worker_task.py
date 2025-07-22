import redis
from rq import get_current_job
import os
import time
import logging
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from config import settings
from database import update_job_status, Job
from utils.yt_download import download_audio
from utils.demucs import separate_stems

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup for worker
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Redis connection
redis_conn = redis.from_url(settings.redis_url)

def process_job(youtube_url: str, job_id: str):
    """Process audio separation job"""
    start_time = time.time()
    logger.info(f"Starting job {job_id} for URL: {youtube_url}")
    
    db = SessionLocal()
    
    try:
        # Update job status to processing
        update_job_status(db, job_id, "processing", progress=10)
        
        # Create job directory
        job_dir = os.path.join(settings.jobs_base_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Download audio
        logger.info(f"Job {job_id}: Starting audio download")
        download_start = time.time()
        
        update_job_status(db, job_id, "processing", progress=20)
        audio_path = download_audio(youtube_url, job_dir)
        
        download_time = time.time() - download_start
        logger.info(f"Job {job_id}: Audio download completed in {download_time:.2f}s")
        
        update_job_status(db, job_id, "processing", progress=50)
        
        # Separate stems
        logger.info(f"Job {job_id}: Starting stem separation")
        separation_start = time.time()
        
        # Check for GPU availability
        device = None
        try:
            import torch
            if torch.cuda.is_available():
                device = 'cuda'
                logger.info(f"Job {job_id}: Using GPU for processing")
            else:
                logger.info(f"Job {job_id}: Using CPU for processing")
        except ImportError:
            logger.info(f"Job {job_id}: PyTorch not available, using CPU")
        
        # Process with device if available
        if device:
            stems_dir = separate_stems(audio_path, job_dir, device=device)
        else:
            stems_dir = separate_stems(audio_path, job_dir)
        
        separation_time = time.time() - separation_start
        logger.info(f"Job {job_id}: Stem separation completed in {separation_time:.2f}s")
        
        update_job_status(db, job_id, "processing", progress=90)
        
        # List generated stems
        stem_files = []
        if os.path.exists(stems_dir):
            stem_files = [
                f[:-4] for f in os.listdir(stems_dir) 
                if f.endswith('.wav')
            ]
        
        if not stem_files:
            raise Exception("No stems were generated")
        
        total_time = time.time() - start_time
        
        # Update job as completed
        update_job_status(
            db, 
            job_id, 
            "completed", 
            progress=100,
            stems=",".join(stem_files),
            stems_dir=stems_dir,
            processing_time=int(total_time)
        )
        
        # Cache the result
        cache_key = f"url_cache:{youtube_url}"
        cache_data = {
            "stems": ",".join(stem_files),
            "stems_dir": stems_dir,
            "cached_at": datetime.utcnow().isoformat()
        }
        redis_conn.hset(cache_key, mapping=cache_data)
        redis_conn.expire(cache_key, 86400 * 7)  # Cache for 7 days
        
        logger.info(f"Job {job_id}: Completed successfully in {total_time:.2f}s")
        
        # Cleanup temporary files (keep only stems)
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception as e:
            logger.warning(f"Job {job_id}: Failed to cleanup temp files: {e}")
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id} failed: {error_msg}", exc_info=True)
        
        # Update job as failed
        update_job_status(
            db, 
            job_id, 
            "error", 
            error=error_msg,
            processing_time=int(time.time() - start_time)
        )
        
        # Cleanup on error
        try:
            job_dir = os.path.join(settings.jobs_base_dir, job_id)
            if os.path.exists(job_dir):
                import shutil
                shutil.rmtree(job_dir)
        except Exception as cleanup_error:
            logger.error(f"Job {job_id}: Cleanup failed: {cleanup_error}")
        
        raise  # Re-raise for RQ to handle
        
    finally:
        db.close()

def cleanup_old_jobs():
    """Cleanup old job files and database records"""
    logger.info("Starting cleanup of old jobs")
    
    db = SessionLocal()
    try:
        # Find jobs older than 7 days
        cutoff_date = datetime.utcnow() - timedelta(days=7)
        old_jobs = db.query(Job).filter(Job.created_at < cutoff_date).all()
        
        for job in old_jobs:
            try:
                # Remove files
                if job.stems_dir and os.path.exists(job.stems_dir):
                    import shutil
                    shutil.rmtree(os.path.dirname(job.stems_dir))
                
                # Remove database record
                db.delete(job)
                
                logger.info(f"Cleaned up job {job.id}")
                
            except Exception as e:
                logger.error(f"Failed to cleanup job {job.id}: {e}")
        
        db.commit()
        logger.info(f"Cleanup completed, removed {len(old_jobs)} old jobs")
        
    except Exception as e:
        logger.error(f"Cleanup process failed: {e}")
        db.rollback()
    finally:
        db.close()