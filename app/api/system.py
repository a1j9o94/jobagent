# app/api/system.py
import json
from datetime import datetime, UTC
from fastapi import Response, status

from app.db import health_check as db_health_check
from app.tools.storage import health_check as storage_health_check
from app.tools.notifications import health_check as notification_health_check

from .shared import app, redis_health_check, STORAGE_PROVIDER, API_BASE_URL


# Root route, that just shows if the app is running, the list of routes, and an example of how to use the ingest endpoint
@app.get("/", summary="Root route", tags=["System"])
async def root():
    return {
        "status": "ok",
        "message": "Job Agent API is running",
        "routes": [
            {
                "path": "/ingest/profile",
                "method": "POST",
                "description": "Ingest a user's full profile",
            }
        ],
        "example": {
            "method": "POST",
            "url": f"{API_BASE_URL}/ingest/profile",
            "headers": {"X-API-Key": "your-api-key"},
            "body": {
                "headline": "Software Engineer",
                "summary": "I am a software engineer with 5 years of experience in Python and Django",
            },
        },
    }


@app.get("/health", summary="Comprehensive Health Check", tags=["System"])
async def health_check_endpoint():  # Renamed to avoid conflict with imported health_check functions
    """Check the health of all system components."""

    # Dynamically check storage based on the environment
    is_storage_healthy = True  # Assume healthy for managed services like Tigris
    if STORAGE_PROVIDER == "minio":
        is_storage_healthy = storage_health_check()

    health_status = {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "services": {
            "database": db_health_check(),
            "redis": redis_health_check(),
            "object_storage": is_storage_healthy,
            "notifications": notification_health_check(),
        },
    }

    # Determine overall status
    all_services_healthy = all(health_status["services"].values())

    if not all_services_healthy:
        health_status["status"] = "degraded"

        # If database is down, this is critical
        if not health_status["services"]["database"]:
            health_status["status"] = "critical"

    # Return appropriate HTTP status code
    if health_status["status"] == "critical":
        return Response(
            content=json.dumps(health_status),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
        )
    elif health_status["status"] == "degraded":
        # Return JSON response properly for degraded status
        response = Response(
            content=json.dumps(health_status),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type="application/json",
        )
        return response

    return health_status 