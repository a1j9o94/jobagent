# app/tasks/ranking.py
import logging
import asyncio

from .shared import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def task_rank_role(self, role_id: int, profile_id: int):
    """Task to rank a role against a profile."""
    try:
        from app.tools import rank_role  # Local import to avoid circular dependency
        
        # Run the async function from a sync context
        result = asyncio.run(rank_role(role_id, profile_id))
        logger.info(f"Successfully ranked role {role_id}: {result.score}")
        return {
            "status": "success",
            "role_id": role_id,
            "score": result.score,
            "rationale": result.rationale,
        }
    except Exception as e:
        logger.error(f"Failed to rank role {role_id}: {e}")
        if self.request.retries < self.max_retries:
            countdown = 2**self.request.retries
            raise self.retry(countdown=countdown, exc=e)
        return {"status": "error", "message": str(e), "role_id": role_id} 