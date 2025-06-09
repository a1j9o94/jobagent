# app/tasks/submission.py
import logging

from .shared import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
async def task_submit_application(self, application_id: int):
    """Async task to submit an application using browser automation."""
    try:
        from app.tools import submit_application  # Local import to avoid circular dependency
        
        result = await submit_application(application_id)
        logger.info(f"Submitted application {application_id}: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to submit application {application_id}: {e}")
        if self.request.retries < self.max_retries:
            countdown = 60 * (self.request.retries + 1)  # 1 min, 2 min
            raise self.retry(countdown=countdown, exc=e)
        return {"status": "error", "message": str(e), "application_id": application_id}


@celery_app.task(bind=True, max_retries=3)
async def task_apply_for_role(self, role_id: int, profile_id: int):
    """
    Task to initiate an application for a role.
    This task will create an Application and trigger submission.
    """
    logger.info(
        f"Initiating application for role_id: {role_id} and profile_id: {profile_id}"
    )
    # This is a placeholder. Future implementation will create an Application
    # and potentially chain the task_submit_application task.
    return {"status": "received", "role_id": role_id, "profile_id": profile_id} 