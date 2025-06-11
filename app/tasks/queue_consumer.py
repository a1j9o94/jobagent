# app/tasks/queue_consumer.py
import logging
from datetime import datetime
from typing import Dict, Any

from .shared import celery_app
from app.queue_manager import queue_manager, TaskType, QueueTask
from app.models import Application, ApplicationStatus
from app.db import get_session_context
from app.notifications import send_sms_message

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def task_consume_status_updates(self):
    """Task to consume status updates from the Node.js service."""
    try:
        # Consume tasks from the update_job_status queue
        task = queue_manager.consume_task(TaskType.UPDATE_JOB_STATUS, timeout=5)
        
        if task:
            logger.info(f"Processing status update task {task.id}")
            process_status_update(task)
            return {"status": "processed", "task_id": task.id}
        else:
            return {"status": "no_tasks"}

    except Exception as e:
        logger.error(f"Error consuming status updates: {e}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def task_consume_approval_requests(self):
    """Task to consume approval requests from the Node.js service."""
    try:
        # Consume tasks from the approval_request queue
        task = queue_manager.consume_task(TaskType.APPROVAL_REQUEST, timeout=5)
        
        if task:
            logger.info(f"Processing approval request task {task.id}")
            process_approval_request(task)
            return {"status": "processed", "task_id": task.id}
        else:
            return {"status": "no_tasks"}

    except Exception as e:
        logger.error(f"Error consuming approval requests: {e}")
        return {"status": "error", "message": str(e)}


def process_status_update(task: QueueTask):
    """Process a status update from the Node.js service."""
    try:
        payload = task.payload
        application_id = payload.get("application_id")
        status = payload.get("status")
        notes = payload.get("notes")
        error_message = payload.get("error_message")
        screenshot_url = payload.get("screenshot_url")
        submitted_at = payload.get("submitted_at")

        with get_session_context() as session:
            application = session.get(Application, application_id)
            if not application:
                logger.error(f"Application {application_id} not found")
                return

            # Update application status
            if status == "applied":
                application.status = ApplicationStatus.SUBMITTED
                if submitted_at:
                    application.submitted_at = datetime.fromisoformat(submitted_at)
                
                # Send success notification
                send_success_notification(application)
                
            elif status == "failed":
                application.status = ApplicationStatus.ERROR
                application.error_message = error_message
                
                # Send failure notification
                send_failure_notification(application, error_message)
                
            elif status == "waiting_approval":
                application.status = ApplicationStatus.NEEDS_USER_INFO
                
            elif status == "needs_user_info":
                application.status = ApplicationStatus.NEEDS_USER_INFO

            # Update additional fields
            if notes:
                application.notes = notes
            if screenshot_url:
                application.screenshot_url = screenshot_url

            session.commit()
            logger.info(f"Updated application {application_id} status to {status}")

    except Exception as e:
        logger.error(f"Error processing status update: {e}")


def process_approval_request(task: QueueTask):
    """Process an approval request from the Node.js service."""
    try:
        payload = task.payload
        application_id = payload.get("application_id")
        question = payload.get("question")
        current_state = payload.get("current_state")
        screenshot_url = payload.get("screenshot_url")
        context = payload.get("context", {})

        with get_session_context() as session:
            application = session.get(Application, application_id)
            if not application:
                logger.error(f"Application {application_id} not found")
                return

            # Store approval context
            application.approval_context = {
                "question": question,
                "current_state": current_state,
                "screenshot_url": screenshot_url,
                "context": context,
                "requested_at": datetime.utcnow().isoformat()
            }
            application.status = ApplicationStatus.NEEDS_USER_INFO
            
            if screenshot_url:
                application.screenshot_url = screenshot_url

            session.commit()

            # Send approval request notification
            send_approval_notification(application, question, screenshot_url)
            
            logger.info(f"Processed approval request for application {application_id}")

    except Exception as e:
        logger.error(f"Error processing approval request: {e}")


def send_success_notification(application: Application):
    """Send notification for successful application submission."""
    try:
        message = (
            f"✅ Application submitted successfully!\n\n"
            f"Job: {application.role.title}\n"
            f"Company: {application.role.company.name}\n"
            f"Status: Submitted"
        )
        
        # Get user's phone number from profile preferences
        phone_number = None
        for pref in application.profile.preferences:
            if pref.key == "phone":
                phone_number = pref.value
                break

        if phone_number:
            send_sms_message(message, phone_number)
            logger.info(f"Sent success notification for application {application.id}")

    except Exception as e:
        logger.error(f"Error sending success notification: {e}")


def send_failure_notification(application: Application, error_message: str):
    """Send notification for failed application submission."""
    try:
        message = (
            f"❌ Application failed to submit\n\n"
            f"Job: {application.role.title}\n"
            f"Company: {application.role.company.name}\n"
            f"Error: {error_message}\n\n"
            f"Please check the job posting manually."
        )
        
        # Get user's phone number from profile preferences
        phone_number = None
        for pref in application.profile.preferences:
            if pref.key == "phone":
                phone_number = pref.value
                break

        if phone_number:
            send_sms_message(message, phone_number)
            logger.info(f"Sent failure notification for application {application.id}")

    except Exception as e:
        logger.error(f"Error sending failure notification: {e}")


def send_approval_notification(application: Application, question: str, screenshot_url: str = None):
    """Send notification requesting user approval."""
    try:
        message = (
            f"🤔 Job application needs your input\n\n"
            f"Job: {application.role.title}\n"
            f"Company: {application.role.company.name}\n\n"
            f"Question: {question}\n\n"
            f"Please reply with your answer to continue the application."
        )
        
        if screenshot_url:
            message += f"\n\nScreenshot: {screenshot_url}"
        
        # Get user's phone number from profile preferences
        phone_number = None
        for pref in application.profile.preferences:
            if pref.key == "phone":
                phone_number = pref.value
                break

        if phone_number:
            send_sms_message(message, phone_number)
            logger.info(f"Sent approval notification for application {application.id}")

    except Exception as e:
        logger.error(f"Error sending approval notification: {e}")


# Periodic tasks to consume from queues
@celery_app.task(bind=True)
def task_queue_consumer_runner(self):
    """Periodic task to run queue consumers."""
    try:
        # Process status updates
        status_result = task_consume_status_updates.delay()
        
        # Process approval requests  
        approval_result = task_consume_approval_requests.delay()
        
        return {
            "status_updates": status_result.get(timeout=30),
            "approval_requests": approval_result.get(timeout=30)
        }
    except Exception as e:
        logger.error(f"Error in queue consumer runner: {e}")
        return {"status": "error", "message": str(e)} 