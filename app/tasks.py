# app/tasks.py
import logging
from celery import Celery
from celery.schedules import crontab
from sqlmodel import (
    Session as SQLModelSession,
)  # Renamed to avoid conflict with celery Session

from app.db import engine, get_session_context  # Added get_session_context
from app.tools import (
    rank_role,
    draft_and_upload_documents,
    generate_daily_report,
    submit_application,
)
from app.notifications import send_whatsapp_message
import asyncio

logger = logging.getLogger(__name__)

# Initialize Celery
# Ensure REDIS_URL is used here if defined in .env, otherwise default
import os

BROKER_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "jobagent", broker=BROKER_URL, backend=RESULT_BACKEND, include=["app.tasks"]
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
)

# Asynchronous functions from app.tools need to be called with await
# Celery tasks are typically synchronous wrappers around async functions if needed
# For simplicity, if rank_role, draft_and_upload_documents, submit_application are async
# they would need to be run in an event loop. Example: asyncio.run(rank_role(...))
# However, the design doc shows them being called directly. This implies either:
# 1. The functions in tools.py are blocking/synchronous (not ideal given async def).
# 2. An event loop is managed within the Celery task execution context.
# For now, I will keep them as direct calls as in the design doc, assuming Celery handles the async context or they will be refactored.


@celery_app.task(bind=True, max_retries=3)
async def task_rank_role(self, role_id: int, profile_id: int):
    """Async task to rank a role against a profile."""
    try:
        # Assuming rank_role is an async function as defined in tools.py
        result = await rank_role(role_id, profile_id)
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


@celery_app.task(bind=True, max_retries=3)
def task_generate_documents(self, application_id: int):
    """Task to generate and upload application documents."""
    try:
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


@celery_app.task(bind=True, max_retries=2)
async def task_submit_application(self, application_id: int):
    """Async task to submit an application using browser automation."""
    try:
        result = await submit_application(application_id)
        logger.info(f"Submitted application {application_id}: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to submit application {application_id}: {e}")
        if self.request.retries < self.max_retries:
            countdown = 60 * (self.request.retries + 1)  # 1 min, 2 min
            raise self.retry(countdown=countdown, exc=e)
        return {"status": "error", "message": str(e), "application_id": application_id}


@celery_app.task
def task_send_daily_report(profile_id: int = 1):  # Added profile_id as arg with default
    """Generate and send daily activity report."""
    try:
        # Assuming single user with profile_id=1 for now, as per design doc
        # generate_daily_report is synchronous, so no await needed
        report = generate_daily_report(profile_id)

        # Send via WhatsApp
        success = send_whatsapp_message(report)

        if success:
            logger.info(f"Daily report sent successfully for profile {profile_id}")
            return {"status": "success", "report_sent": True, "profile_id": profile_id}
        else:
            logger.error(f"Failed to send daily report for profile {profile_id}")
            return {
                "status": "error",
                "message": "Failed to send report",
                "profile_id": profile_id,
            }

    except Exception as e:
        logger.error(f"Daily report task failed for profile {profile_id}: {e}")
        return {"status": "error", "message": str(e), "profile_id": profile_id}


@celery_app.task
def task_process_new_roles(profile_id: int = 1):  # Added profile_id as arg with default
    """Process newly sourced roles for ranking and application."""
    try:
        from app.models import Role, RoleStatus  # Local import

        # Using get_session_context for non-FastAPI session management
        with get_session_context() as session:
            # Get unprocessed roles
            # The original query session.query(Role) is SQLAlchemy 1.x style.
            # For SQLModel/SQLAlchemy 2.x style, use session.exec(select(...))
            new_roles_stmt = (
                select(Role).where(Role.status == RoleStatus.SOURCED).limit(10)
            )
            new_roles = session.exec(new_roles_stmt).all()

            processed_count = 0
            for role_obj in new_roles:  # Renamed role to role_obj to avoid conflict
                # Trigger ranking task
                task_rank_role.delay(role_obj.id, profile_id)
                processed_count += 1

            logger.info(
                f"Queued {processed_count} roles for processing for profile {profile_id}"
            )
            return {
                "status": "success",
                "processed": processed_count,
                "profile_id": profile_id,
            }

    except Exception as e:
        logger.error(f"Role processing task failed for profile {profile_id}: {e}")
        return {"status": "error", "message": str(e), "profile_id": profile_id}


# Periodic task scheduling
celery_app.conf.beat_schedule = {
    "send-daily-report": {
        "task": "app.tasks.task_send_daily_report",
        "schedule": crontab(hour=8, minute=0),  # Daily at 8:00 AM UTC
        "args": (1,),  # Assuming profile_id=1 for the scheduled task
    },
    "process-new-roles": {
        "task": "app.tasks.task_process_new_roles",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "args": (1,),  # Assuming profile_id=1 for the scheduled task
    },
}

celery_app.conf.timezone = "UTC"


# Celery signal handlers (example)
@celery_app.task(bind=True)
def debug_task(self):
    logger.info(f"Request: {self.request!r}")
    print(f"Request: {self.request!r}")
