from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session
import uuid
import os
import logging
from datetime import datetime, timedelta
import redis
from rq import Queue
from contextlib import asynccontextmanager

# Local imports
from config import settings
from database import get_db, create_tables, Job, update_job_status, get_job_by_id, get_active_jobs_count
from security import security_manager
from worker_tasks import process_job
from rate_limiter import setup_rate_limiting
from health import health_router
from monitoring import setup_monitoring

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(settings.log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Redis connection
redis_conn = redis.from_url(settings.redis_url)
job_queue = Queue(connection=redis_conn, default_timeout=settings.job_timeout)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    try:
        create_tables()
        logger.info("Application started successfully")
        
        # Test Redis connection
        redis_conn.ping()
        logger.info("Redis connection established")
        
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Application shutting down")

# Create FastAPI app
app = FastAPI(
    title="Audio Stem Separation API",
    description="API for separating audio stems from YouTube videos",
    version="2.0.0",
    lifespan=lifespan
)

# Security middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["*"]  # Configure properly for production
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup rate limiting
setup_rate_limiting(app, redis_conn)

# Setup monitoring
setup_monitoring(app)

# Include health check router
app.include_router(health_router, prefix="/health", tags=["health"])

# Request/Response models
class SeparateRequest(BaseModel):
    url: HttpUrl
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            }
        }

class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str

class StatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int = 0
    stems: list = []
    error: str = None
    created_at: datetime
    estimated_completion: datetime = None

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_id": str(uuid.uuid4())}
    )

@app.post("/separate", response_model=JobResponse)
async def separate_audio(
    request: SeparateRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: str = Depends(security_manager.get_api_key)
):
    """Submit audio separation job"""
    
    client_ip = security_manager.get_client_ip(http_request)
    url = str(request.url)
    
    # Validate YouTube URL
    if not security_manager.validate_youtube_url(url):
        raise HTTPException(
            status_code=400,
            detail="Invalid YouTube URL"
        )
    
    # Check concurrent job limits
    active_jobs = get_active_jobs_count(db, client_ip)
    if active_jobs >= settings.max_concurrent_jobs:
        raise HTTPException(
            status_code=429,
            detail=f"Too many concurrent jobs. Limit: {settings.max_concurrent_jobs}"
        )
    
    # Check for cached results
    cache_key = f"url_cache:{url}"
    cached_result = redis_conn.hgetall(cache_key)
    
    if cached_result:
        logger.info(f"Cache hit for URL: {url}")
        job_id = str(uuid.uuid4())
        
        # Create completed job record
        job = Job(
            id=job_id,
            url=url,
            status="completed",
            stems=cached_result.get(b'stems', b'').decode(),
            stems_dir=cached_result.get(b'stems_dir', b'').decode(),
            client_ip=client_ip,
            progress=100,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(job)
        db.commit()
        
        return JobResponse(
            job_id=job_id,
            status="completed",
            message="Job completed (cached result)"
        )
    
    # Create new job
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        url=url,
        status="pending",
        client_ip=client_ip,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(job)
    db.commit()
    
    # Enqueue job
    try:
        job_queue.enqueue(
            process_job,
            url,
            job_id,
            retry=True,
            job_timeout=settings.job_timeout
        )
        
        logger.info(f"Job {job_id} enqueued for URL: {url}")
        
        return JobResponse(
            job_id=job_id,
            status="pending",
            message="Job submitted successfully"
        )
        
    except Exception as e:
        logger.error(f"Error enqueueing job {job_id}: {e}")
        update_job_status(db, job_id, "error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to submit job")

@app.get("/status/{job_id}", response_model=StatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Get job status"""
    
    job = get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    response = StatusResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress or 0,
        created_at=job.created_at
    )
    
    if job.status == "completed" and job.stems:
        stems = job.stems.split(",") if job.stems else []
        response.stems = [
            {
                "name": stem.strip(),
                "download_url": f"/download/{job_id}/{stem.strip()}"
            }
            for stem in stems if stem.strip()
        ]
    
    if job.status == "error" and job.error:
        response.error = job.error
    
    # Estimate completion time for pending/processing jobs
    if job.status in ["pending", "processing"]:
        # Rough estimate: 2-5 minutes based on queue position and processing
        estimated_minutes = 3
        response.estimated_completion = datetime.utcnow() + timedelta(minutes=estimated_minutes)
    
    return response

@app.get("/download/{job_id}/{stem}")
def download_stem(job_id: str, stem: str, db: Session = Depends(get_db)):
    """Download separated stem file"""
    
    job = get_job_by_id(db, job_id)
    if not job or job.status != "completed":
        raise HTTPException(status_code=404, detail="Job not found or not completed")
    
    if not job.stems_dir:
        raise HTTPException(status_code=404, detail="Stems directory not found")
    
    # Security: validate stem name to prevent path traversal
    if not stem.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid stem name")
    
    file_path = os.path.join(job.stems_dir, f"{stem}.wav")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Stem file not found")
    
    return FileResponse(
        file_path,
        media_type="audio/wav",
        filename=f"{stem}.wav",
        headers={"Content-Disposition": f"attachment; filename={stem}.wav"}
    )

@app.get("/jobs")
def list_jobs(
    skip: int = 0,
    limit: int = 100,
    status: str = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(security_manager.get_api_key)
):
    """List jobs (admin endpoint)"""
    
    query = db.query(Job)
    
    if status:
        query = query.filter(Job.status == status)
    
    jobs = query.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "jobs": [
            {
                "id": job.id,
                "url": job.url,
                "status": job.status,
                "progress": job.progress,
                "created_at": job.created_at,
                "updated_at": job.updated_at
            }
            for job in jobs
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)