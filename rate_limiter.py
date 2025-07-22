from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
import redis
from config import settings

def get_client_ip(request: Request):
    """Get client IP with proxy support"""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    return request.client.host if request.client else "unknown"

def setup_rate_limiting(app, redis_conn: redis.Redis):
    """Setup rate limiting for the FastAPI app"""
    
    limiter = Limiter(
        key_func=get_client_ip,
        storage_uri=settings.redis_url
    )
    
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Add the limiter to specific endpoints in main.py using:
    # @limiter.limit("5/minute")
    
    return limiter

class ConcurrencyLimiter:
    """Manage concurrent job limits per IP"""
    
    def __init__(self, redis_conn: redis.Redis):
        self.redis = redis_conn
        self.max_concurrent = settings.max_concurrent_jobs
        self.timeout = 600  # 10 minutes
    
    def can_submit_job(self, client_ip: str) -> bool:
        """Check if client can submit a new job"""
        active_key = f"active_jobs:{client_ip}"
        current_count = int(self.redis.get(active_key) or 0)
        return current_count < self.max_concurrent
    
    def increment_active_jobs(self, client_ip: str):
        """Increment active job count for IP"""
        active_key = f"active_jobs:{client_ip}"
        self.redis.incr(active_key)
        self.redis.expire(active_key, self.timeout)
    
    def decrement_active_jobs(self, client_ip: str):
        """Decrement active job count for IP"""
        active_key = f"active_jobs:{client_ip}"
        current = self.redis.get(active_key)
        if current and int(current) > 0:
            self.redis.decr(active_key)