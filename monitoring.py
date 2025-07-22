from fastapi import Request, Response
import time
import logging
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response as FastAPIResponse

logger = logging.getLogger(__name__)

# Prometheus metrics
request_count = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

job_count = Counter(
    'jobs_total',
    'Total jobs processed',
    ['status']
)

job_duration = Histogram(
    'job_processing_duration_seconds',
    'Job processing duration',
    ['status']
)

class MonitoringMiddleware:
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        start_time = time.time()
        
        # Process the request
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Record metrics
                duration = time.time() - start_time
                status_code = message["status"]
                
                request_count.labels(
                    method=request.method,
                    endpoint=request.url.path,
                    status=status_code
                ).inc()
                
                request_duration.labels(
                    method=request.method,
                    endpoint=request.url.path
                ).observe(duration)
                
                logger.info(
                    f"{request.method} {request.url.path} "
                    f"- {status_code} - {duration:.3f}s"
                )
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)

def setup_monitoring(app):
    """Setup monitoring middleware and endpoints"""
    
    # Add monitoring middleware
    app.add_middleware(MonitoringMiddleware)
    
    @app.get("/metrics")
    def get_metrics():
        """Prometheus metrics endpoint"""
        return FastAPIResponse(
            generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )
    
    return {
        "job_count": job_count,
        "job_duration": job_duration
    }