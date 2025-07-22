from fastapi import FastAPI, HTTPException, Depends, Security, Request
from pydantic import BaseModel
from fastapi.responses import FileResponse
import uuid
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import Base, Job
from datetime import datetime
import redis
from rq import Queue
from worker import process_job
from rq import Retry
from fastapi.security.api_key import APIKeyHeader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from utils.yt_download import download_audio
from utils.demucs import separate_stems

import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg2://username:password@localhost:5432/jobs")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

API_KEY = "DEEM"  # Replace with a secure value or load from env
API_KEY_NAME = "access_token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

app = FastAPI()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

redis_conn = redis.from_url(REDIS_URL)
q = Queue(connection=redis_conn)

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Could not validate credentials")

class SeparateRequest(BaseModel):
    url: str

@app.post("/separate")
@limiter.limit("5/minute")
def separate_audio(req: SeparateRequest, db: Session = Depends(get_db), api_key: str = Depends(get_api_key), request: Request = None):
    # Limit concurrent jobs per IP
    ip = request.client.host if request else "unknown"
    active_jobs_key = f"active_jobs:{ip}"
    active_jobs = int(redis_conn.get(active_jobs_key) or 0)
    MAX_CONCURRENT_JOBS = 2
    if active_jobs >= MAX_CONCURRENT_JOBS:
        raise HTTPException(status_code=429, detail="Too many concurrent jobs for your IP. Please wait.")
    redis_conn.incr(active_jobs_key)
    redis_conn.expire(active_jobs_key, 600)  # expire after 10 minutes

    try:
        cached = redis_conn.hgetall(f"url_cache:{req.url}")
        if cached and cached.get(b'stems'):
            job_id = str(uuid.uuid4())
            job = Job(
                id=job_id,
                url=req.url,
                status="completed",
                stems=cached[b'stems'].decode(),
                stems_dir=cached[b'stems_dir'].decode(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return {"job_id": job_id}

        job_id = str(uuid.uuid4())
        job = Job(id=job_id, url=req.url, status="pending", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.add(job)
        db.commit()
        db.refresh(job)
        # Enqueue the job to RQ with a 10-minute timeout
        q.enqueue(process_job, req.url, job_id, retry=Retry(max=3, interval=[10, 30, 60]), job_timeout=600)
        return {"job_id": job_id}
    finally:
        redis_conn.decr(active_jobs_key)

@app.get("/status/{job_id}")
def get_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    result = {"status": job.status}
    if job.status == "completed":
        stems = job.stems.split(",") if job.stems else []
        result["stems"] = [
            {
                "name": stem,
                "download_url": f"/download/{job_id}/{stem}"
            }
            for stem in stems
        ]
    elif job.status == "error":
        result["error"] = job.error
    return result

@app.get("/download/{job_id}/{stem}")
def download_stem(job_id: str, stem: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.status != "completed":
        raise HTTPException(status_code=404, detail="Job not found or not completed")
    stems_dir = job.stems_dir
    file_path = os.path.join(stems_dir, f"{stem}.wav")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Stem not found")
    return FileResponse(file_path, media_type="audio/wav", filename=f"{stem}.wav")