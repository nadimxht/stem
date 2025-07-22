import redis
from rq import Worker, Queue, Connection
import os
import logging
from config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('worker.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Main worker function"""
    logger.info("Starting RQ Worker...")
    
    # Connect to Redis
    redis_conn = redis.from_url(settings.redis_url)
    
    try:
        redis_conn.ping()
        logger.info("Connected to Redis successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return
    
    # Create job directories
    os.makedirs(settings.jobs_base_dir, exist_ok=True)
    
    # Setup worker
    with Connection(redis_conn):
        worker = Worker(
            [Queue()],
            connection=redis_conn,
            name=f"worker-{os.getpid()}"
        )
        
        logger.info(f"Worker {worker.name} started")
        worker.work(with_scheduler=True)

if __name__ == "__main__":
    main()