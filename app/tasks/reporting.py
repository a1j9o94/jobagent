# app/tasks/reporting.py
import logging

from app.notifications import send_sms_message
from .shared import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def task_send_daily_report(profile_id: int = 1):  # Added profile_id as arg with default
    """Generate and send daily activity report."""
    try:
        from app.tools import generate_daily_report  # Local import to avoid circular dependency
        
        # Assuming single user with profile_id=1 for now, as per design doc
        # generate_daily_report is synchronous, so no await needed
        report = generate_daily_report(profile_id)

        # Send via SMS
        success = send_sms_message(report)

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