# app/tasks/shared.py
import os
import logging
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)

# Initialize Celery
# Ensure REDIS_URL is used here if defined in .env, otherwise default
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