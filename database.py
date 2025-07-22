from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import Generator
from config import settings
import logging

logger = logging.getLogger(__name__)

# Create engine with connection pooling
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Job(Base):
    __tablename__ = 'jobs'
    
    id = Column(String, primary_key=True, index=True)
    url = Column(Text, nullable=False)
    status = Column(String, default='pending', index=True)  # pending, processing, completed, error
    stems = Column(Text, nullable=True)  # JSON string of stem info
    stems_dir = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    progress = Column(Integer, default=0)  # 0-100
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    client_ip = Column(String, nullable=True)
    processing_time = Column(Integer, nullable=True)  # seconds

def get_db() -> Generator[Session, None, None]:
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def create_tables():
    """Create all tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        raise

def update_job_status(db: Session, job_id: str, status: str, **kwargs) -> bool:
    """Update job status and other fields atomically"""
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.warning(f"Job {job_id} not found for status update")
            return False
            
        job.status = status
        job.updated_at = datetime.utcnow()
        
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
        
        db.commit()
        logger.info(f"Job {job_id} status updated to {status}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating job {job_id}: {e}")
        db.rollback()
        return False

def get_job_by_id(db: Session, job_id: str) -> Job:
    """Get job by ID"""
    return db.query(Job).filter(Job.id == job_id).first()

def get_active_jobs_count(db: Session, client_ip: str) -> int:
    """Get count of active jobs for an IP"""
    return db.query(Job).filter(
        Job.client_ip == client_ip,
        Job.status.in_(['pending', 'processing'])
    ).count()