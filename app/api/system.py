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

    # Get queue statistics
    queue_stats = {}
    try:
        from app.queue_manager import queue_manager
        queue_stats = queue_manager.get_queue_stats()
    except Exception as e:
        queue_stats = {"error": str(e)}

    # Get node service heartbeat status
    node_service_healthy = False
    try:
        from app.queue_manager import queue_manager
        last_heartbeat = queue_manager.get_last_heartbeat('node-scraper')
        if last_heartbeat:
            # Consider service healthy if heartbeat within last minute
            heartbeat_age = datetime.now(UTC) - last_heartbeat
            node_service_healthy = heartbeat_age.total_seconds() < 60
    except Exception:
        pass

    # Get queue health
    queues_healthy = False
    try:
        queues_healthy = queue_manager.health_check()
    except Exception:
        pass

    health_status = {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "services": {
            "database": db_health_check(),
            "redis": redis_health_check(),
            "object_storage": is_storage_healthy,
            "notifications": notification_health_check(),
            "queues": queues_healthy,
            "node_service": node_service_healthy
        },
        "queue_stats": queue_stats,
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


@app.get("/health/queues", summary="Queue Health Check", tags=["System"])
async def queue_health_endpoint():
    """Check the health and statistics of all queue systems."""
    try:
        from app.queue_manager import queue_manager
        
        # Get queue statistics
        queue_stats = queue_manager.get_queue_stats()
        redis_healthy = queue_manager.health_check()
        
        # Calculate total pending tasks
        total_pending = sum(queue_stats.values()) if isinstance(queue_stats, dict) else 0
        
        health_status = {
            "status": "healthy" if redis_healthy else "unhealthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "queue_statistics": queue_stats,
            "details": {
                "redis_healthy": redis_healthy,
                "total_pending_tasks": total_pending,
                "queue_breakdown": queue_stats
            }
        }
        
        return health_status
        
    except Exception as e:
        return {
            "status": "error",
            "timestamp": datetime.now(UTC).isoformat(),
            "error": str(e),
            "details": {
                "redis_healthy": False,
                "total_pending_tasks": 0
            }
        }


@app.get("/health/node-service", summary="Node.js Service Health Check", tags=["System"])
async def node_service_health_endpoint():
    """Check the health of the Node.js automation service via heartbeat messages."""
    try:
        from app.queue_manager import queue_manager
        
        # Check when we last received a heartbeat from Node.js service
        last_heartbeat = queue_manager.get_last_heartbeat("node-scraper")
        
        if last_heartbeat:
            seconds_since = (datetime.now(UTC) - last_heartbeat).total_seconds()
        
            if seconds_since < 60:  # Healthy if heartbeat within last minute
            service_status = "healthy"
            status_code = status.HTTP_200_OK
            details = {
                    "status": "Node.js service is responding",
                    "last_heartbeat": last_heartbeat.isoformat(),
                    "seconds_since_heartbeat": round(seconds_since, 1)
            }
            else:
                service_status = "unhealthy"
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            details = {
                    "status": f"Node.js service not responding - no heartbeat for {round(seconds_since, 1)} seconds",
                    "last_heartbeat": last_heartbeat.isoformat(),
                    "seconds_since_heartbeat": round(seconds_since, 1)
            }
        else:
            service_status = "unhealthy"
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            details = {
                "status": "Node.js service not responding - no heartbeat received",
                "last_heartbeat": None,
                "seconds_since_heartbeat": None
            }
        
        # Also include queue stats for additional context
        queue_stats = queue_manager.get_queue_stats()
        
        health_status = {
            "status": service_status,
            "timestamp": datetime.now(UTC).isoformat(),
            "details": details,
            "queue_stats": queue_stats
        }
        
        return Response(
            content=json.dumps(health_status),
            status_code=status_code,
            media_type="application/json",
        )
        
    except Exception as e:
        return Response(
            content=json.dumps({
                "status": "error",
                "timestamp": datetime.now(UTC).isoformat(),
                "error": str(e),
                "details": {
                    "status": "Cannot determine Node.js service health",
                    "last_heartbeat": None,
                    "seconds_since_heartbeat": None
                }
            }),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
        ) 