# app/tools/submission.py
import logging
from datetime import datetime
from typing import Dict, Any

from app.models import Application, ApplicationStatus
from app.db import get_session_context
from app.automation import BrowserAutomation, FormSubmissionError
from app.security import decrypt_password

logger = logging.getLogger(__name__)


async def submit_application(application_id: int) -> Dict[str, Any]:
    """Automate the actual form submission using browser automation."""
    with get_session_context() as session:
        application = session.get(Application, application_id)
        if not application:
            return {"status": "error", "message": "Application not found"}

        role = application.role
        profile = application.profile

        # Get user preferences for form data
        preferences = {pref.key: pref.value for pref in profile.preferences}

        # Prepare form data
        form_data = {
            "first_name": preferences.get("first_name", ""),
            "last_name": preferences.get("last_name", ""),
            "email": preferences.get("email", ""),
            "phone": preferences.get("phone", ""),
            "resume_path": None,  # Would need to download from S3 for local file
        }

        # Get credentials for the site
        credentials = {}
        for cred in profile.credentials:
            if cred.site_hostname in role.posting_url:
                credentials = {
                    "username": cred.username,
                    "password": decrypt_password(cred.encrypted_password),
                }
                break

        try:
            application.status = ApplicationStatus.SUBMITTING
            session.commit()

            async with BrowserAutomation() as browser:
                result = await browser.submit_job_application(
                    role.posting_url, form_data, credentials
                )

            if result["status"] == "success":
                application.status = ApplicationStatus.SUBMITTED
                application.submitted_at = datetime.utcnow()
            elif result["status"] == "partial":
                application.status = ApplicationStatus.NEEDS_USER_INFO
            else:
                application.status = ApplicationStatus.ERROR

            session.commit()
            logger.info(f"Application {application_id} submission result: {result}")
            return result

        except Exception as e:
            application.status = ApplicationStatus.ERROR
            session.commit()
            logger.error(f"Application submission failed: {e}")
            return {"status": "error", "message": str(e)} 