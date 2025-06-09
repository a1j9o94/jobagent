# app/tasks/documents.py
import logging
import asyncio

from .shared import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def task_generate_documents(self, application_id: int):
    """Task to generate and upload application documents."""
    try:
        from app.tools import draft_and_upload_documents  # Local import to avoid circular dependency
        
        # Run the async function from a sync context
        result = asyncio.run(draft_and_upload_documents(application_id))
        logger.info(f"Generated documents for application {application_id}")
        return result
    except Exception as e:
        logger.error(
            f"Failed to generate documents for application {application_id}: {e}"
        )
        if self.request.retries < self.max_retries:
            countdown = 2**self.request.retries
            raise self.retry(countdown=countdown, exc=e)
        return {"status": "error", "message": str(e), "application_id": application_id} 