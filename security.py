from fastapi import HTTPException, Security, Request
from fastapi.security.api_key import APIKeyHeader
from config import settings
import secrets
import hashlib
import time
from typing import Optional

api_key_header = APIKeyHeader(name=settings.api_key_name, auto_error=False)

class SecurityManager:
    def __init__(self):
        self.api_key_hash = hashlib.sha256(settings.api_key.encode()).hexdigest()
    
    def get_api_key(self, api_key: Optional[str] = Security(api_key_header)) -> str:
        """Validate API key"""
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="API key required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Use constant-time comparison to prevent timing attacks
        provided_hash = hashlib.sha256(api_key.encode()).hexdigest()
        if not secrets.compare_digest(provided_hash, self.api_key_hash):
            raise HTTPException(
                status_code=403,
                detail="Invalid API key"
            )
        
        return api_key
    
    def get_client_ip(self, request: Request) -> str:
        """Get client IP address with proxy support"""
        # Check for forwarded headers (common in proxy setups)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"
    
    def validate_youtube_url(self, url: str) -> bool:
        """Basic YouTube URL validation"""
        youtube_domains = [
            "youtube.com",
            "youtu.be",
            "www.youtube.com",
            "m.youtube.com"
        ]
        
        return any(domain in url.lower() for domain in youtube_domains)

# Global security manager instance
security_manager = SecurityManager()