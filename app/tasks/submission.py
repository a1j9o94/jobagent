# app/tasks/submission.py
import logging
from datetime import datetime

from celery import chain
from app.tasks.documents import task_generate_documents

from .shared import celery_app
from app.queue_manager import queue_manager, TaskType
from app.models import Application, ApplicationStatus
from app.db import get_session_context
from app.security import decrypt_password

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def task_submit_application_queue(self, documents_result=None, application_id: int = None):
    """Task to submit an application using the new queue-based Node.js service."""
    try:
        # Handle both chained calls (documents_result contains application_id) 
        # and direct calls (application_id passed directly)
        if documents_result and isinstance(documents_result, dict):
            app_id = documents_result.get('application_id') or application_id
            logger.info(f"Chained call: documents generated with result: {documents_result.get('status')}")
        else:
            app_id = application_id or documents_result
            logger.info(f"Direct call with application_id: {app_id}")
        
        if not app_id:
            return {"status": "error", "message": "No application_id provided"}

        with get_session_context() as session:
            application = session.get(Application, app_id)
            if not application:
                return {"status": "error", "message": "Application not found"}

            # Verify documents are ready before proceeding
            if not application.resume_s3_url:
                logger.error(f"Application {app_id} missing resume URL")
                return {"status": "error", "message": "Resume not ready", "application_id": app_id}

            role = application.role
            profile = application.profile

            # Get all user preferences for comprehensive form data
            preferences = {pref.key: pref.value for pref in profile.preferences}

            # Prepare comprehensive user data for enhanced StagehandWrapper
            user_data = {
                # Basic identity
                "name": f"{preferences.get('first_name', '')} {preferences.get('last_name', '')}".strip(),
                "first_name": preferences.get("first_name", ""),
                "last_name": preferences.get("last_name", ""),
                "email": preferences.get("email", ""),
                "phone": preferences.get("phone", ""),
                
                # Generated documents
                "resume_url": application.resume_s3_url,
                "cover_letter_url": application.cover_letter_s3_url,
                
                # Contact and social links
                "linkedin_url": preferences.get("linkedin_url", ""),
                "github_url": preferences.get("github_url", ""),
                "portfolio_url": preferences.get("portfolio_url", ""),
                "website": preferences.get("website", "") or preferences.get("personal_website", ""),
                
                # Location information
                "address": preferences.get("address", ""),
                "city": preferences.get("city", ""),
                "state": preferences.get("state", ""),
                "zip_code": preferences.get("zip_code", "") or preferences.get("postal_code", ""),
                "country": preferences.get("country", ""),
                
                # Professional information for intelligent responses
                "current_role": preferences.get("current_role", "") or preferences.get("current_title", ""),
                "experience_years": self._parse_experience_years(preferences.get("experience_years", "")),
                "education": preferences.get("education", "") or preferences.get("degree", ""),
                "skills": self._parse_skills(preferences.get("skills", "")),
                
                # Work preferences for intelligent answers
                "preferred_work_arrangement": preferences.get("work_arrangement", "") or preferences.get("remote_preference", ""),
                "availability": preferences.get("availability", "") or preferences.get("start_date", ""),
                "salary_expectation": preferences.get("salary_expectation", "") or preferences.get("desired_salary", ""),
                
                # Additional profile context
                "summary": profile.summary if profile.summary else "",
                "headline": profile.headline if profile.headline else "",
                
                # Pass through ALL preferences as additional context
                # This ensures any custom fields are available to the AI
                **{f"pref_{k}": v for k, v in preferences.items() if k not in [
                    'first_name', 'last_name', 'email', 'phone', 'linkedin_url', 
                    'github_url', 'portfolio_url', 'website', 'personal_website',
                    'address', 'city', 'state', 'zip_code', 'postal_code', 'country',
                    'current_role', 'current_title', 'experience_years', 'education',
                    'degree', 'skills', 'work_arrangement', 'remote_preference',
                    'availability', 'start_date', 'salary_expectation', 'desired_salary'
                ]}
            }
            
            # Add AI instructions based on role and profile
            ai_instructions = {
                "tone": "professional",
                "focus_areas": self._extract_focus_areas(role, preferences),
                "avoid_topics": []  # Could be configured per user
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

            # Publish task to Node.js service via Redis queue with enhanced data
            task_id = queue_manager.publish_job_application_task(
                job_id=role.id,
                application_id=application.id,
                job_url=role.posting_url,
                company=role.company.name,
                title=role.title,
                user_data=user_data,
                credentials=credentials,
                custom_answers=application.custom_answers,
                ai_instructions=ai_instructions
            )

            # Store the queue task ID for tracking
            application.queue_task_id = task_id
            session.commit()

            logger.info(f"Published application {app_id} to queue with task ID {task_id}")
            return {
                "status": "queued", 
                "queue_task_id": task_id,
                "application_id": app_id,
                "documents_result": documents_result
            }

    except Exception as e:
        logger.error(f"Failed to queue application: {e}")
        if self.request.retries < self.max_retries:
            countdown = 60 * (self.request.retries + 1)  # 1 min, 2 min
            raise self.retry(countdown=countdown, exc=e)
        return {"status": "error", "message": str(e)}


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

            # Use Celery chain to ensure documents are generated before submission
            workflow = chain(
                task_generate_documents.s(application.id),
                task_submit_application_queue.s(application.id)
            )
            
            # Execute the workflow asynchronously
            workflow_result = workflow.apply_async()
            
            # Get the first task ID (document generation) for tracking
            generate_task_id = workflow_result.id

            return {
                "status": "success", 
                "application_id": application.id,
                "role_id": role_id, 
                "profile_id": profile_id,
                "workflow_id": generate_task_id,
                "message": "Application workflow started: documents will be generated first, then submitted"
            }
            
    except Exception as e:
        logger.error(f"Failed to create application for role {role_id} and profile {profile_id}: {e}")
        if self.request.retries < self.max_retries:
            countdown = 60 * (self.request.retries + 1)  # 1 min, 2 min, 3 min
            raise self.retry(countdown=countdown, exc=e)
        return {"status": "error", "message": str(e), "role_id": role_id, "profile_id": profile_id}


@celery_app.task(bind=True, max_retries=2)
def task_generate_and_submit_application(self, application_id: int):
    """
    Convenience task that chains document generation and submission.
    Use this as an alternative to task_apply_for_role when you already have an Application.
    """
    logger.info(f"Starting document generation and submission workflow for application {application_id}")
    
    try:
        # Use Celery chain to ensure documents are generated before submission
        workflow = chain(
            task_generate_documents.s(application_id),
            task_submit_application_queue.s(application_id)
        )
        
        # Execute the workflow
        workflow_result = workflow.apply_async()
        
        return {
            "status": "workflow_started",
            "application_id": application_id,
            "workflow_id": workflow_result.id,
            "message": "Document generation and submission workflow started"
        }
        
    except Exception as e:
        logger.error(f"Failed to start workflow for application {application_id}: {e}")
        if self.request.retries < self.max_retries:
            countdown = 60 * (self.request.retries + 1)
            raise self.retry(countdown=countdown, exc=e)
        return {"status": "error", "message": str(e), "application_id": application_id}


    def _parse_experience_years(self, experience_str: str) -> int:
        """Parse experience years from various string formats."""
        if not experience_str:
            return 0
        
        import re
        # Try to extract number from strings like "5 years", "3+ years", "5-7 years"
        match = re.search(r'(\d+)', str(experience_str))
        if match:
            return int(match.group(1))
        
        return 0

    def _parse_skills(self, skills_str: str) -> list:
        """Parse skills from various string formats."""
        if not skills_str:
            return []
        
        # Handle different separators: comma, semicolon, pipe, newline
        import re
        skills = re.split(r'[,;\|\n]+', str(skills_str))
        return [skill.strip() for skill in skills if skill.strip()]

    def _extract_focus_areas(self, role, preferences: dict) -> list:
        """Extract focus areas based on role and user preferences."""
        focus_areas = []
        
        # Extract from role title and description
        if hasattr(role, 'title') and role.title:
            title_lower = role.title.lower()
            if any(word in title_lower for word in ['senior', 'lead', 'principal']):
                focus_areas.append('leadership experience')
            if any(word in title_lower for word in ['engineer', 'developer', 'technical']):
                focus_areas.append('technical skills')
            if any(word in title_lower for word in ['manager', 'director']):
                focus_areas.append('management experience')
        
        # Extract from user preferences
        current_role = preferences.get('current_role', '') or preferences.get('current_title', '')
        if current_role:
            if any(word in current_role.lower() for word in ['senior', 'lead', 'principal']):
                focus_areas.append('leadership experience')
            if any(word in current_role.lower() for word in ['manager', 'director']):
                focus_areas.append('management experience')
        
        # Add skills as focus area if available
        skills = self._parse_skills(preferences.get('skills', ''))
        if skills:
            focus_areas.append('technical skills')
        
        # Remove duplicates and return
        return list(set(focus_areas)) if focus_areas else ['professional experience'] 