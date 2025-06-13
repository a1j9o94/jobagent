# app/tools/documents.py
import os
import logging
from datetime import datetime
from typing import Dict, Any
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from app.models import ResumeDraft, Application, ApplicationStatus
from app.db import get_session_context
from app.tools.storage import upload_file_to_storage
from app.tools.pdf_utils import render_to_pdf
from app.tools.notifications import send_sms_message

logger = logging.getLogger(__name__)

resume_agent = Agent(
    "openai:gpt-4o-mini",
    result_type=ResumeDraft,
    model_settings=ModelSettings(
        parallel_tool_calls=False,
        tool_choice="auto",
        max_retries=3,
        timeout=30.0
    ),
    system_prompt="""You are an expert resume writer and career coach.
    Create compelling, ATS-optimized resumes and cover letters tailored to specific job postings.
    Focus on quantifiable achievements and relevant keywords.""",
)


def send_documents_ready_notification(application: Application, resume_url: str, cover_letter_url: str):
    """Send notification that documents are ready with links."""
    try:
        message = (
            f"📄 Your application documents are ready!\n\n"
            f"Job: {application.role.title}\n"
            f"Company: {application.role.company.name}\n\n"
            f"Resume: {resume_url}\n"
            f"Cover Letter: {cover_letter_url}\n\n"
            f"Documents saved and ready for submission!"
        )
        
        # Send to default SMS_TO number from environment variables
        # This matches the pattern used in webhooks.py for notifications
        send_sms_message(message)
        logger.info(f"Sent documents ready notification for application {application.id}")

    except Exception as e:
        logger.error(f"Error sending documents ready notification: {e}")


async def draft_and_upload_documents(application_id: int) -> Dict[str, Any]:
    """Generates resume/CL, uploads them, and saves URLs to the Application model."""
    with get_session_context() as session:
        application = session.get(Application, application_id)
        if not application:
            logger.error(f"Application {application_id} not found")
            return {"status": "error", "message": "Application not found"}

        role = application.role
        profile = application.profile

        try:

            # Generate documents using LLM
            prompt = f"""
            Create a resume and cover letter for this application:
            
            Job: {role.title} at {role.company.name}
            Description: {role.description}
            Location: {role.location or 'Not specified'}
            Requirements: {role.requirements or 'Not specified'}
            Salary Range: {role.salary_range or 'Not specified'}
            Job URL: {role.posting_url}
            {f'Role Ranking Score: {role.rank_score}/1.0' if role.rank_score else ''}
            {f'Why this role fits: {role.rank_rationale}' if role.rank_rationale else ''}
            {f'Required Skills: {", ".join([skill.name for skill in role.skills])}' if role.skills else ''}
            
            Candidate: {profile.headline}
            Summary: {profile.summary}
            Applicant preferences: {profile.preferences}
            
            Make the resume ATS-friendly and the cover letter compelling but concise.
            Focus on the specific requirements and skills mentioned above.
            """

            # Try with retry logic for pydantic AI agent
            max_retries = 3
            draft = None
            
            for attempt in range(max_retries):
                try:
                    result = await resume_agent.run(prompt)
                    draft = result.data
                    break
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for document generation: {e}")
                    if attempt == max_retries - 1:
                        logger.error(f"All {max_retries} attempts failed for document generation")
                        # Create a simple fallback draft
                        draft = ResumeDraft(
                            resume_md=f"# Resume for {profile.headline}\n\nApplying for: {role.title} at {role.company.name}\n\n## Summary\n{profile.summary}",
                            cover_letter_md=f"# Cover Letter\n\nDear Hiring Manager,\n\nI am applying for the {role.title} position at {role.company.name}.\n\n{profile.summary}\n\nSincerely,\n{profile.headline}",
                            identified_skills=[]
                        )
                    else:
                        # Wait before retry
                        import asyncio
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff

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
                resume_pdf, resume_filename
            )
            cover_letter_url = upload_file_to_storage(
                cover_letter_pdf, cover_letter_filename
            )

            if resume_url and cover_letter_url:
                # Update application with document URLs
                application.resume_s3_url = resume_url
                application.cover_letter_s3_url = cover_letter_url
                application.status = ApplicationStatus.READY_TO_SUBMIT
                session.commit()

                # Send notification with document links
                send_documents_ready_notification(application, resume_url, cover_letter_url)

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