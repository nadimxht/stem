from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+psycopg2://username:password@localhost:5432/jobs"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Security
    api_key: Optional[str] = None
    api_key_name: str = "access_token"
    secret_key: str = "your-secret-key-change-this"
    
    # Rate Limiting
    rate_limit_per_minute: int = 5
    max_concurrent_jobs: int = 2
    
    # Job Configuration
    job_timeout: int = 600  # 10 minutes
    max_retries: int = 3
    retry_intervals: list = [10, 30, 60]
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "app.log"
    
    # File Storage
    jobs_base_dir: str = "jobs"
    max_file_size_mb: int = 100
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Validate required settings
        if not self.api_key:
            raise ValueError("API_KEY environment variable is required")

settings = Settings()