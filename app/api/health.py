# app/api/health.py
from fastapi import Depends
from sqlmodel import Session
import logging

from app.db import get_session
from app.queue_manager import queue_manager
from .shared import app, redis_health_check

logger = logging.getLogger(__name__)


@app.get("/health", summary="Health check endpoint", tags=["Health"])
async def health_check(session: Session = Depends(get_session)):
    """
    Comprehensive health check including database, Redis, and queue statistics.
    """
    health_status = {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z",  # Will be updated below
        "services": {},
        "queue_stats": {},
        "details": {}
    }

    try:
        from datetime import datetime
        health_status["timestamp"] = datetime.utcnow().isoformat()

        # Check database connectivity
        try:
            # Simple query to test database
            result = session.exec("SELECT 1").first()
            health_status["services"]["database"] = "healthy" if result else "unhealthy"
        except Exception as e:
            health_status["services"]["database"] = "unhealthy"
            health_status["details"]["database_error"] = str(e)
            health_status["status"] = "unhealthy"

        # Check Redis connectivity
        try:
            redis_healthy = redis_health_check()
            health_status["services"]["redis"] = "healthy" if redis_healthy else "unhealthy"
            
            if not redis_healthy:
                health_status["status"] = "unhealthy"
        except Exception as e:
            health_status["services"]["redis"] = "unhealthy"
            health_status["details"]["redis_error"] = str(e)
            health_status["status"] = "unhealthy"

        # Check queue manager and get statistics
        try:
            queue_healthy = queue_manager.health_check()
            health_status["services"]["queue_manager"] = "healthy" if queue_healthy else "unhealthy"
            
            if queue_healthy:
                # Get queue statistics
                health_status["queue_stats"] = queue_manager.get_queue_stats()
            else:
                health_status["status"] = "unhealthy"
        except Exception as e:
            health_status["services"]["queue_manager"] = "unhealthy"
            health_status["details"]["queue_error"] = str(e)
            health_status["status"] = "unhealthy"

        # Overall status
        if health_status["status"] == "healthy":
            return health_status
        else:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=health_status
            )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


@app.get("/health/queues", summary="Queue health and statistics", tags=["Health"])
async def queue_health():
    """
    Detailed queue health check and statistics.
    """
    try:
        from datetime import datetime
        
        # Check if queue manager is healthy
        queue_healthy = queue_manager.health_check()
        
        if not queue_healthy:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "unhealthy", "message": "Queue manager unavailable"}
            )

        # Get detailed queue statistics
        queue_stats = queue_manager.get_queue_stats()
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "queue_statistics": queue_stats,
            "details": {
                "total_pending_tasks": sum(queue_stats.values()),
                "queue_breakdown": queue_stats
            }
        }

    except Exception as e:
        logger.error(f"Queue health check failed: {e}")
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "error": str(e)}
        )


@app.get("/health/node-service", summary="Node.js service health check", tags=["Health"])
async def node_service_health():
    """
    Check the health of the Node.js Stagehand service by examining queue activity.
    """
    try:
        from datetime import datetime, timedelta
        
        # Check if there are any stuck tasks (basic heuristic)
        queue_stats = queue_manager.get_queue_stats()
        
        # A simple health check: if there are too many pending job applications
        # it might indicate the Node.js service is not processing them
        job_application_queue_length = queue_stats.get("job_application", 0)
        
        status = "healthy"
        details = {
            "job_application_queue_length": job_application_queue_length,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Heuristic: if there are more than 10 pending applications, 
        # it might indicate processing issues
        if job_application_queue_length > 10:
            status = "degraded"
            details["warning"] = "High number of pending job applications"
        
        # Heuristic: if there are more than 50 pending applications,
        # likely the Node.js service is down
        if job_application_queue_length > 50:
            status = "unhealthy"
            details["error"] = "Node.js service appears to be down or overloaded"

        response = {
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "node_service": status,
            "details": details
        }

        if status == "unhealthy":
            from fastapi import HTTPException, status as http_status
            raise HTTPException(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=response
            )

        return response

    except Exception as e:
        logger.error(f"Node service health check failed: {e}")
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "error": str(e)}
        ) 