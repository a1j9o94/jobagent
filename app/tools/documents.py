# app/tools/documents.py
import os
import logging
from datetime import datetime
from typing import Dict, Any
from pydantic_ai import Agent

from app.models import ResumeDraft, Application, ApplicationStatus
from app.db import get_session_context
from app.storage import upload_file_to_storage
from app.pdf_utils import render_to_pdf

logger = logging.getLogger(__name__)

resume_agent = Agent(
    "openai:gpt-4o-mini",
    result_type=ResumeDraft,
    system_prompt="""You are an expert resume writer and career coach.
    Create compelling, ATS-optimized resumes and cover letters tailored to specific job postings.
    Focus on quantifiable achievements and relevant keywords.""",
)


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