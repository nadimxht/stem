# Audio Stem Separation API v2.0

A robust FastAPI-based service for separating audio stems from YouTube videos using Demucs.

## 🚀 Features

- **Secure Authentication**: API key-based authentication with rate limiting
- **Background Processing**: Redis Queue (RQ) for handling long-running jobs
- **Caching**: Redis-based URL caching to avoid reprocessing
- **Health Monitoring**: Comprehensive health checks and metrics
- **Database Management**: PostgreSQL with SQLAlchemy ORM
- **Error Handling**: Robust error handling and logging
- **Docker Support**: Complete containerization with docker-compose
- **Testing**: Comprehensive test suite with pytest
- **Monitoring**: Prometheus metrics integration

## 📋 Requirements

- Python 3.9+
- PostgreSQL 15+
- Redis 7+
- FFmpeg
- CUDA (optional, for GPU acceleration)

## 🔧 Installation

### Using Docker (Recommended)

1. Clone the repository:
```bash
git clone <your-repo-url>
cd stem-separation-api
```

2. Copy environment file:
```bash
cp .env.example .env
```

3. Edit `.env` with your configuration:
```bash
# Generate a secure API key
openssl rand -hex 32

# Update .env with your values
API_KEY=your-generated-api-key
POSTGRES_PASSWORD=your-secure-password
```

4. Start all services:
```bash
docker-compose up -d
```

5. Verify services are running:
```bash
docker-compose ps
curl http://localhost:8000/health/
```

### Manual Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Install system dependencies:
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y ffmpeg postgresql redis-server

# macOS
brew install ffmpeg postgresql redis
```

3. Setup database:
```bash
createdb stemsdb
```

4. Set environment variables:
```bash
export DATABASE_URL="postgresql+psycopg2://user:pass@localhost:5432/stemsdb"
export REDIS_URL="redis://localhost:6379/0"
export API_KEY="your-secure-api-key"
```

5. Start services:
```bash
# Terminal 1: API server
uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2: Worker
python worker.py

# Terminal 3: Redis (if not running as service)
redis-server

# Terminal 4: PostgreSQL (if not running as service)
postgres -D /usr/local/var/postgres
```

## 🔑 API Usage

### Authentication
All requests require an API key in the header:
```bash
Authorization: Bearer your-api-key
# OR
access_token: your-api-key
```

### Submit Job
```bash
curl -X POST "http://localhost:8000/separate" \
  -H "access_token: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

Response:
```json
{
  "job_id": "uuid-string",
  "status": "pending",
  "message": "Job submitted successfully"
}
```

### Check Status
```bash
curl "http://localhost:8000/status/your-job-id"
```

Response:
```json
{
  "job_id": "uuid-string",
  "status": "completed",
  "progress": 100,
  "stems": [
    {
      "name": "vocals",
      "download_url": "/download/job-id/vocals"
    },
    {
      "name": "drums", 
      "download_url": "/download/job-id/drums"
    }
  ]
}
```

### Download Stems
```bash
curl -O "http://localhost:8000/download/your-job-id/vocals"
```

### Health Check
```bash
curl "http://localhost:8000/health/detailed"
```

## 🔒 Security Features

- **API Key Authentication**: Secure access control
- **Rate Limiting**: 5 requests/minute per IP
- **Concurrent Job Limiting**: Max 2 jobs per IP
- **Input Validation**: YouTube URL validation
- **SQL Injection Protection**: Parameterized queries
- **Path Traversal Protection**: Secure file serving
- **CORS Configuration**: Configurable cross-origin requests

## 📊 Monitoring

### Health Endpoints
- `GET /health/` - Basic health check
- `GET /health/detailed` - Detailed system health
- `GET /health/ready` - Kubernetes readiness probe
- `GET /health/live` - Kubernetes liveness probe

### Metrics
- `GET /metrics` - Prometheus metrics endpoint

### Logs
- Application logs: `app.log`
- Worker logs: `worker.log`
- Request metrics and performance data

## 🧪 Testing

Run the test suite:
```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_main.py -v
```

## 🚢 Deployment

### Docker Production
```bash
# Build and deploy
docker-compose -f docker-compose.prod.yml up -d

# Scale workers
docker-compose up --scale worker=4 -d

# View logs
docker-compose logs -f backend worker
```

### Environment Variables
Key configuration options:

```bash
# Required
API_KEY=your-secure-api-key
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db
REDIS_URL=redis://host:6379/0

# Optional
LOG_LEVEL=INFO
MAX_CONCURRENT_JOBS=2
RATE_LIMIT_PER_MINUTE=5
JOB_TIMEOUT=600
JOBS_BASE_DIR=jobs
MAX_FILE_SIZE_MB=100
```

## 🔧 Configuration

### Performance Tuning
- Adjust `MAX_CONCURRENT_JOBS` based on system resources
- Scale worker processes: `docker-compose up --scale worker=N`
- Configure Redis memory limits in `redis.conf`
- Tune PostgreSQL settings for your workload

### GPU Support
For GPU acceleration (NVIDIA):
```bash
# Install CUDA support
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118

# Update docker-compose.yml to expose GPU
services:
  worker:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## 📝 API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 🐛 Troubleshooting

### Common Issues

1. **Worker not processing jobs**:
   - Check Redis connection: `redis-cli ping`
   - Verify worker logs: `docker-compose logs worker`

2. **Database connection errors**:
   - Verify PostgreSQL is running
   - Check connection string format
   - Ensure database exists

3. **Out of disk space**:
   - Check jobs directory size
   - Configure automatic cleanup
   - Monitor disk usage

4. **Performance issues**:
   - Scale worker processes
   - Enable GPU acceleration
   - Increase system resources

### Logs
```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend
docker-compose logs -f worker
```

## 📜 License

MIT License - see LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality  
4. Ensure all tests pass
5. Submit a pull request

## 🆘 Support

For issues and questions:
- Create an issue on GitHub
- Check the troubleshooting section
- Review the logs for error details