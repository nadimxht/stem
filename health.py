from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
import redis
from config import settings
import psutil
import os
from datetime import datetime

health_router = APIRouter()

@health_router.get("/")
def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Audio Stem Separation API",
        "version": "2.0.0"
    }

@health_router.get("/detailed")
def detailed_health_check(db: Session = Depends(get_db)):
    """Detailed health check with dependencies"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }
    
    # Database check
    try:
        db.execute("SELECT 1")
        health_status["checks"]["database"] = {"status": "healthy"}
    except Exception as e:
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "unhealthy"
    
    # Redis check
    try:
        redis_conn = redis.from_url(settings.redis_url)
        redis_conn.ping()
        queue_info = redis_conn.info()
        health_status["checks"]["redis"] = {
            "status": "healthy",
            "connected_clients": queue_info.get("connected_clients", 0)
        }
    except Exception as e:
        health_status["checks"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "unhealthy"
    
    # System resources
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        health_status["checks"]["system"] = {
            "status": "healthy",
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent
        }
        
        # Mark as unhealthy if resources are critically low
        if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
            health_status["checks"]["system"]["status"] = "warning"
            
    except Exception as e:
        health_status["checks"]["system"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # File system check (jobs directory)
    try:
        jobs_dir = settings.jobs_base_dir
        if not os.path.exists(jobs_dir):
            os.makedirs(jobs_dir)
        
        # Test write access
        test_file = os.path.join(jobs_dir, "health_check.txt")
        with open(test_file, "w") as f:
            f.write("health check")
        os.remove(test_file)
        
        health_status["checks"]["filesystem"] = {"status": "healthy"}
        
    except Exception as e:
        health_status["checks"]["filesystem"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "unhealthy"
    
    # Return appropriate HTTP status
    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status)
    
    return health_status

@health_router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    """Kubernetes readiness probe"""
    try:
        # Quick database check
        db.execute("SELECT 1")
        
        # Quick Redis check
        redis_conn = redis.from_url(settings.redis_url)
        redis_conn.ping()
        
        return {"status": "ready"}
        
    except Exception as e:
        raise HTTPException(
            status_code=503, 
            detail={"status": "not ready", "error": str(e)}
        )

@health_router.get("/live")
def liveness_check():
    """Kubernetes liveness probe"""
    return {"status": "alive"}