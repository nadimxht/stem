import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os
import json

from main import app
from database import Base, get_db
from config import settings

# Test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def api_headers():
    return {"access_token": settings.api_key}

def test_health_check(client):
    """Test basic health check"""
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_detailed_health_check(client):
    """Test detailed health check"""
    response = client.get("/health/detailed")
    assert response.status_code == 200
    data = response.json()
    assert "checks" in data
    assert "database" in data["checks"]

def test_separate_audio_without_auth(client):
    """Test separation endpoint without authentication"""
    response = client.post(
        "/separate",
        json={"url": "https://www.youtube.com/watch?v=test"}
    )
    assert response.status_code == 401

def test_separate_audio_invalid_url(client, api_headers):
    """Test separation endpoint with invalid URL"""
    response = client.post(
        "/separate",
        json={"url": "https://invalid-site.com/video"},
        headers=api_headers
    )
    assert response.status_code == 400
    assert "Invalid YouTube URL" in response.json()["detail"]

def test_separate_audio_valid_url(client, api_headers):
    """Test separation endpoint with valid URL"""
    response = client.post(
        "/separate",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        headers=api_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] in ["pending", "completed"]

def test_job_status_not_found(client):
    """Test job status for non-existent job"""
    response = client.get("/status/non-existent-job")
    assert response.status_code == 404

def test_job_status_found(client, api_headers):
    """Test job status for existing job"""
    # First create a job
    response = client.post(
        "/separate",
        json={"url": "https://www.youtube.com/watch?v=test"},
        headers=api_headers
    )
    job_id = response.json()["job_id"]
    
    # Then check its status
    response = client.get(f"/status/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert "status" in data
    assert "progress" in data

def test_download_stem_not_found(client):
    """Test download for non-existent job"""
    response = client.get("/download/non-existent-job/vocals")
    assert response.status_code == 404

def test_list_jobs_without_auth(client):
    """Test jobs list without authentication"""
    response = client.get("/jobs")
    assert response.status_code in [401, 403]

def test_list_jobs_with_auth(client, api_headers):
    """Test jobs list with authentication"""
    response = client.get("/jobs", headers=api_headers)
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert isinstance(data["jobs"], list)

def test_rate_limiting(client, api_headers):
    """Test rate limiting (this would need to be adjusted based on your limits)"""
    # Make multiple requests quickly
    responses = []
    for _ in range(10):
        response = client.post(
            "/separate",
            json={"url": "https://www.youtube.com/watch?v=test"},
            headers=api_headers
        )
        responses.append(response.status_code)
    
    # Should get rate limited at some point
    assert 429 in responses

class TestSecurity:
    """Security-focused tests"""
    
    def test_sql_injection_protection(self, client, api_headers):
        """Test protection against SQL injection"""
        malicious_url = "https://youtube.com/watch?v='; DROP TABLE jobs; --"
        response = client.post(
            "/separate",
            json={"url": malicious_url},
            headers=api_headers
        )
        # Should handle gracefully, not crash
        assert response.status_code in [200, 400]
    
    def test_path_traversal_protection(self, client):
        """Test protection against path traversal in downloads"""
        response = client.get("/download/../../etc/passwd/vocals")
        assert response.status_code == 404
    
    def test_invalid_stem_name(self, client, api_headers):
        """Test download with invalid stem name"""
        # First create a job
        response = client.post(
            "/separate",
            json={"url": "https://www.youtube.com/watch?v=test"},
            headers=api_headers
        )
        job_id = response.json()["job_id"]
        
        # Try to download with invalid stem name
        response = client.get(f"/download/{job_id}/../../../etc/passwd")
        assert response.status_code == 400

if __name__ == "__main__":
    pytest.main([__file__])