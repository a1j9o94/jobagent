# app/tasks/submission.py
import logging
from datetime import datetime

from .shared import celery_app
from app.queue_manager import queue_manager, TaskType
from app.models import Application, ApplicationStatus
from app.db import get_session_context
from app.security import decrypt_password

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def task_submit_application_queue(self, application_id: int):
    """Task to submit an application using the new queue-based Node.js service."""
    try:
        with get_session_context() as session:
            application = session.get(Application, application_id)
            if not application:
                return {"status": "error", "message": "Application not found"}

            role = application.role
            profile = application.profile

            # Get user preferences for form data
            preferences = {pref.key: pref.value for pref in profile.preferences}

            # Prepare user data
            user_data = {
                "name": f"{preferences.get('first_name', '')} {preferences.get('last_name', '')}".strip(),
                "first_name": preferences.get("first_name", ""),
                "last_name": preferences.get("last_name", ""),
                "email": preferences.get("email", ""),
                "phone": preferences.get("phone", ""),
                "resume_url": application.resume_s3_url,
                "linkedin_url": preferences.get("linkedin_url", ""),
                "github_url": preferences.get("github_url", ""),
                "portfolio_url": preferences.get("portfolio_url", ""),
            }

            # Get credentials for the site
            credentials = None
            for cred in profile.credentials:
                if cred.site_hostname in role.posting_url:
                    credentials = {
                        "username": cred.username,
                        "password": decrypt_password(cred.encrypted_password),
                    }
                    break

            # Update status to submitting
            application.status = ApplicationStatus.SUBMITTING
            session.commit()

            # Publish task to Node.js service via Redis queue
            task_id = queue_manager.publish_job_application_task(
                job_id=role.id,
                application_id=application.id,
                job_url=role.posting_url,
                company=role.company.name,
                title=role.title,
                user_data=user_data,
                credentials=credentials,
                custom_answers=application.custom_answers
            )

            # Store the queue task ID for tracking
            application.queue_task_id = task_id
            session.commit()

            logger.info(f"Published application {application_id} to queue with task ID {task_id}")
            return {
                "status": "queued", 
                "queue_task_id": task_id,
                "application_id": application_id
            }

    except Exception as e:
        logger.error(f"Failed to queue application {application_id}: {e}")
        if self.request.retries < self.max_retries:
            countdown = 60 * (self.request.retries + 1)  # 1 min, 2 min
            raise self.retry(countdown=countdown, exc=e)
        return {"status": "error", "message": str(e), "application_id": application_id}


# Legacy task for backward compatibility (will be deprecated)
@celery_app.task(bind=True, max_retries=2)
async def task_submit_application(self, application_id: int):
    """Legacy async task - deprecated in favor of queue-based approach."""
    logger.warning("Using deprecated task_submit_application. Use task_submit_application_queue instead.")
    
    # For now, redirect to the new queue-based approach
    return task_submit_application_queue.delay(application_id).get()


@celery_app.task(bind=True, max_retries=3)
def task_apply_for_role(self, role_id: int, profile_id: int):
    """
    Task to initiate an application for a role.
    This task will create an Application and set it up for submission.
    """
    logger.info(
        f"Initiating application for role_id: {role_id} and profile_id: {profile_id}"
    )
    
    try:
        from app.models import Application  # Local import to avoid circular dependency
        from app.db import get_session_context
        
        with get_session_context() as session:
            # Create a new Application using model_validate to handle default_factory fields
            application_data = {
                "role_id": role_id,
                "profile_id": profile_id,
                "celery_task_id": self.request.id,  # Track this task
                # status defaults to ApplicationStatus.DRAFT
            }
            application = Application.model_validate(application_data)
            
            session.add(application)
            session.commit()
            session.refresh(application)
            
            logger.info(f"Created application {application.id} for role {role_id} and profile {profile_id}")
            return {
                "status": "success", 
                "application_id": application.id,
                "role_id": role_id, 
                "profile_id": profile_id
            }
            
    except Exception as e:
        logger.error(f"Failed to create application for role {role_id} and profile {profile_id}: {e}")
        if self.request.retries < self.max_retries:
            countdown = 60 * (self.request.retries + 1)  # 1 min, 2 min, 3 min
            raise self.retry(countdown=countdown, exc=e)
        return {"status": "error", "message": str(e), "role_id": role_id, "profile_id": profile_id} 