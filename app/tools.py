# app/tools.py
import os
import hashlib
import logging
from datetime import datetime, timedelta, UTC
from typing import Dict, Any, Optional
from sqlmodel import Session, select
from pydantic_ai import Agent, RunContext

from app.models import (
    RankResult,
    ResumeDraft,
    Role,
    Profile,
    Application,
    Company,
    UserPreference,
    ApplicationStatus,
    RoleStatus,
)
from app.db import get_session_context, engine
from app.storage import upload_file_to_storage
from app.pdf_utils import render_to_pdf
from app.automation import BrowserAutomation, FormSubmissionError
from app.security import decrypt_password

logger = logging.getLogger(__name__)

# Initialize the LLM agent
ranking_agent = Agent(
    "openai:gpt-4o-mini",
    result_type=RankResult,
    system_prompt="""You are a career advisor evaluating job role matches.
    Analyze the job description and candidate profile to provide an accurate fit score.
    Consider skills, experience level, company culture, and role requirements.""",
)

resume_agent = Agent(
    "openai:gpt-4o-mini",
    result_type=ResumeDraft,
    system_prompt="""You are an expert resume writer and career coach.
    Create compelling, ATS-optimized resumes and cover letters tailored to specific job postings.
    Focus on quantifiable achievements and relevant keywords.""",
)


def generate_unique_hash(company_name: str, title: str) -> str:
    """Creates a stable, unique hash for a job role to prevent duplicates."""
    s = f"{company_name.lower().strip()}-{title.lower().strip()}"
    return hashlib.sha256(s.encode()).hexdigest()


async def rank_role(role_id: int, profile_id: int) -> RankResult:
    """Uses an LLM to rank a role against a profile."""
    with get_session_context() as session:
        role = session.get(Role, role_id)
        profile = session.get(Profile, profile_id)

        if not role or not profile:
            logger.error(f"Role {role_id} or Profile {profile_id} not found")
            return RankResult(score=0.0, rationale="Role or profile not found")

        try:
            # Prepare the context for the LLM
            prompt = f"""
            Job Title: {role.title}
            Company: {role.company.name}
            Job Description: {role.description}
            
            Candidate Profile:
            Headline: {profile.headline}
            Summary: {profile.summary}
            
            Please provide a match score and rationale.
            """

            result = await ranking_agent.run(prompt)

            # Update the role with ranking results
            role.rank_score = result.data.score
            role.rank_rationale = result.data.rationale
            role.status = RoleStatus.RANKED
            session.commit()

            logger.info(f"Ranked role {role_id}: {result.data.score}")
            return result.data

        except Exception as e:
            logger.error(f"LLM ranking failed: {e}")
            return RankResult(score=0.0, rationale=f"LLM call failed: {str(e)}")


async def draft_and_upload_documents(application_id: int) -> Dict[str, Any]:
    """Generates resume/CL, uploads them, and saves URLs to the Application model."""
    with get_session_context() as session:
        application = session.get(Application, application_id)
        if not application:
            logger.error(f"Application {application_id} not found")
            return {"status": "error", "message": "Application not found"}

        role = application.role
        profile = application.profile
        
        # Check if we should use a mock for testing
        use_mock = os.getenv("USE_MOCK_LLM", "false").lower() == "true"

        try:
            if use_mock:
                # Use hardcoded mock data instead of calling the LLM
                draft = ResumeDraft(
                    resume_md="# Mock Resume\n\nThis is a test.",
                    cover_letter_md="# Mock Cover Letter\n\nThis is a test.",
                    identified_skills=["testing", "mocking"],
                )
                logger.info("Using mock LLM data for document generation.")
            else:
                # Generate documents using LLM
                prompt = f"""
                Create a resume and cover letter for this application:
                
                Job: {role.title} at {role.company.name}
                Description: {role.description}
                
                Candidate: {profile.headline}
                Summary: {profile.summary}
                
                Make the resume ATS-friendly and the cover letter compelling but concise.
                """
    
                result = await resume_agent.run(prompt)
                draft = result.data

            # Convert to PDF and upload
            resume_pdf = render_to_pdf(draft.resume_md)
            cover_letter_pdf = render_to_pdf(draft.cover_letter_md)

            # Upload to object storage
            resume_filename = (
                f"resume_{application_id}_{datetime.now().isoformat()}.pdf"
            )
            cover_letter_filename = (
                f"cover_letter_{application_id}_{datetime.now().isoformat()}.pdf"
            )

            resume_url = upload_file_to_storage(
                resume_pdf, resume_filename, "application/pdf"
            )
            cover_letter_url = upload_file_to_storage(
                cover_letter_pdf, cover_letter_filename, "application/pdf"
            )

            if resume_url and cover_letter_url:
                # Update application with document URLs
                application.resume_s3_url = resume_url
                application.cover_letter_s3_url = cover_letter_url
                application.status = ApplicationStatus.READY_TO_SUBMIT
                session.commit()

                logger.info(f"Documents generated for application {application_id}")
                return {
                    "status": "success",
                    "resume_url": resume_url,
                    "cover_letter_url": cover_letter_url,
                    "identified_skills": draft.identified_skills,
                }
            else:
                return {"status": "error", "message": "Failed to upload documents"}

        except Exception as e:
            logger.error(f"Document generation failed: {e}")
            application.status = ApplicationStatus.ERROR
            session.commit()
            return {"status": "error", "message": str(e)}


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


def generate_daily_report(profile_id: int) -> str:
    """Queries the DB for activity and returns a formatted string."""
    with get_session_context() as session:
        # Get yesterday's date range
        yesterday = datetime.now() - timedelta(days=1)
        start_of_day = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = yesterday.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        # Query for applications submitted yesterday
        submitted_apps = session.exec(
            select(Application)
            .where(Application.profile_id == profile_id)
            .where(Application.submitted_at >= start_of_day)
            .where(Application.submitted_at <= end_of_day)
        ).all()

        # Query for new roles sourced yesterday
        new_roles = session.exec(
            select(Role)
            .where(Role.created_at >= start_of_day)
            .where(Role.created_at <= end_of_day)
        ).all()

        # Query for applications needing user input
        pending_apps = session.exec(
            select(Application)
            .where(Application.profile_id == profile_id)
            .where(Application.status == ApplicationStatus.NEEDS_USER_INFO)
        ).all()

        # Generate report
        report_lines = [
            "📈 Daily Job Application Report",
            f"📅 {yesterday.strftime('%Y-%m-%d')}",
            "",
            f"✅ Applications Submitted: {len(submitted_apps)}",
            f"🔍 New Roles Found: {len(new_roles)}",
            f"⏳ Pending Your Input: {len(pending_apps)}",
        ]

        if submitted_apps:
            report_lines.append("\n📋 Submitted Applications:")
            for app in submitted_apps:
                report_lines.append(f"  • {app.role.title} at {app.role.company.name}")

        if pending_apps:
            report_lines.append("\n❓ Applications Needing Your Input:")
            for app in pending_apps:
                report_lines.append(f"  • {app.role.title} at {app.role.company.name}")

        return "\n".join(report_lines)


def get_user_preference(profile_id: int, key: str) -> Optional[str]:
    """Get a user preference value, or None if not found."""
    with get_session_context() as session:
        pref = session.exec(
            select(UserPreference)
            .where(UserPreference.profile_id == profile_id)
            .where(UserPreference.key == key)
        ).first()
        return pref.value if pref else None


def save_user_preference(profile_id: int, key: str, value: str) -> None:
    """Save or update a user preference."""
    with get_session_context() as session:
        # Try to find existing preference
        pref = session.exec(
            select(UserPreference)
            .where(UserPreference.profile_id == profile_id)
            .where(UserPreference.key == key)
        ).first()

        if pref:
            pref.value = value
            pref.last_updated = datetime.now(UTC)
        else:
            pref = UserPreference(
                profile_id=profile_id, 
                key=key, 
                value=value,
                last_updated=datetime.now(UTC)
            )
            session.add(pref)

        session.commit()
        logger.info(f"Saved preference {key} for profile {profile_id}")
