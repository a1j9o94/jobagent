# app/api/shared.py
import os
import logging
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from twilio.request_validator import RequestValidator

from app.tasks.shared import celery_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_original_webhook_url(request: Request) -> str:
    """
    Reconstruct the original URL that Twilio used, accounting for reverse proxy forwarding.

    Fly.io (and other reverse proxies) terminate HTTPS and forward HTTP requests internally.
    This causes signature validation to fail because Twilio calculates signatures using
    the original HTTPS URL, but FastAPI sees the internal HTTP URL.
    """
    # Check for forwarded protocol headers
    proto = (
        request.headers.get("X-Forwarded-Proto")
        or request.headers.get("X-Forwarded-Protocol")
        or request.headers.get("X-Scheme")
        or "https"  # Default to HTTPS for production webhooks
    )

    # Get the host (should be the external hostname)
    host = (
        request.headers.get("X-Forwarded-Host")
        or request.headers.get("Host")
        or request.url.hostname
    )

    # Construct the original URL
    path_with_query = str(request.url.path)
    if request.url.query:
        path_with_query += f"?{request.url.query}"

    original_url = f"{proto}://{host}{path_with_query}"

    # Debug logging for troubleshooting
    logger.debug(
        f"URL reconstruction: proto={proto}, host={host}, "
        f"path={path_with_query}, original={original_url}, internal={request.url}"
    )

    return original_url


# Initialize FastAPI app
app = FastAPI(
    title="Job Application Agent API",
    description="Automated job application system with AI-powered matching",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include the files router for serving storage files
from app.api.files import router as files_router
app.include_router(files_router)

# API Key authentication
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)
PROFILE_INGEST_API_KEY = os.getenv("PROFILE_INGEST_API_KEY", "default-key")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
if TWILIO_AUTH_TOKEN:
    twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN)
else:
    twilio_validator = None
    logger.warning("TWILIO_AUTH_TOKEN not set, webhook validation will be skipped.")

# Base URL for API examples - automatically detects environment
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Add this near your other environment variable definitions
STORAGE_PROVIDER = os.getenv(
    "STORAGE_PROVIDER", "minio"
)  # Default to minio for local dev


async def get_api_key(api_key: str = Depends(API_KEY_HEADER)):
    if api_key != PROFILE_INGEST_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key"
        )
    return api_key


def redis_health_check() -> bool:
    """Check if Redis/Celery broker is accessible."""
    try:
        # Use Celery's ping to check Redis connectivity
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        return stats is not None
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False 