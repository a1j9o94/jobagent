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
    "openai:gpt-4o",
    result_type=ResumeDraft,
    model_settings=ModelSettings(
        parallel_tool_calls=False,
        tool_choice="auto",
        max_retries=3,
        timeout=180
    ),
    system_prompt="""You are an expert resume writer and career coach.
    Create compelling, ATS-optimized resumes and cover letters tailored to specific job postings.
    Focus on quantifiable achievements and relevant keywords. IMPORTANT: Resumes must be concise and formatted to fit on a single page.""",
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
            ## Task
            Create a tailored resume and cover letter for this specific job application:

            **Job Details:**
            - Role: {role.title} at {role.company.name}
            - Description: {role.description}
            - Location: {role.location or 'Not specified'}
            - Requirements: {role.requirements or 'Not specified'}
            - Salary Range: {role.salary_range or 'Not specified'}
            - Job URL: {role.posting_url}
            {f'Role Ranking Score: {role.rank_score}/1.0' if role.rank_score else ''}
            {f'Why this role fits: {role.rank_rationale}' if role.rank_rationale else ''}
            {f'Required Skills: {", ".join([skill.name for skill in role.skills])}' if role.skills else ''}

            **Candidate Profile:**
            - Name: {profile.headline}
            - Summary: {profile.summary}
            - Preferences: {profile.preferences}

            ## Resume Requirements

            ### Content Strategy
            1. **Skills Alignment**: Carefully match the candidate's experience to the job requirements. Prioritize experiences that directly relate to the required skills and responsibilities.

            2. **Quantified Impact**: Extract specific metrics, dollar amounts, percentages, and scale indicators from the candidate's full bio. Examples:
            - Revenue/pipeline numbers ($6B transformation, $300M pipeline, $100M ARR)
            - Percentage improvements (15% YoY growth, 80% to 100% NRR improvement)
            - Scale indicators (Fortune 500 clients, $150B company, 10+ M&A transactions)
            - Team/project sizes (80+ sellers, 7-person team, 464 learners)

            3. **Technical Depth**: When relevant to the role, include specific technologies, frameworks, and tools from the candidate's background. Don't just list them—show how they were applied.

            4. **Achievement Focus**: Transform responsibilities into achievements. Instead of "Managed sales pipeline," write "Managed $300M sales pipeline, contributing to ~$100M ARR through weekly performance tracking and optimization."

            ### Formatting Guidelines
            - **ATS-Friendly**: Use standard section headers, bullet points, and simple formatting
            - **Single Page**: Prioritize the most relevant and impressive experiences
            - **Information Hierarchy**: Lead with the most relevant experiences for this specific role
            - **Metrics Prominence**: Lead bullet points with quantified results when possible

            ### Content Selection Priority
            1. **Direct Role Matches**: Experiences that directly align with the job description
            2. **Transferable Skills**: Adjacent experiences that demonstrate relevant capabilities
            3. **Leadership/Impact**: Instances showing progression, leadership, or significant business impact
            4. **Technical Skills**: Relevant certifications, tools, and technical competencies

            ## Cover Letter Requirements

            ### Content Strategy
            1. **Compelling Opening**: Connect the candidate's background directly to the company's needs
            2. **Specific Value Proposition**: Highlight 2-3 key achievements that directly relate to the role requirements
            3. **Company Research**: Reference specific aspects of the company, role, or industry that resonate with the candidate's experience
            4. **Quantified Impact**: Include 1-2 specific metrics that demonstrate capability

            ### Formatting Guidelines
            - **Professional Header**: Include full contact information
            - **Proper Addressing**: Use "Dear Hiring Manager" or "Dear [Company Name] Team"
            - **Concise Length**: 3-4 paragraphs, ~300-400 words
            - **Strong Close**: Express enthusiasm and next steps
            - **No Placeholders**: Complete, ready-to-submit document

            ## Key Instructions
            - **Mine the Full Bio**: The candidate summary contains extensive detail—use it to find specific examples, metrics, and achievements
            - **Tailor Everything**: Every bullet point should feel specifically crafted for this role
            - **Show Don't Tell**: Instead of "strong leadership skills," describe "Led 7-person intern team that built recruiting platform adopted company-wide"
            - **Prioritize Relevance**: If space is limited, include the most job-relevant information first
            - **Maintain Authenticity**: All content should be truthful and directly supported by the candidate's actual experience

            ## Output Format
            Provide both documents in clean markdown format that will be converted to PDF for submission. Use proper markdown formatting including:
            - Headers (#, ##, ###) for document structure
            - **Bold** for emphasis on names, companies, and key achievements
            - *Italics* for dates, locations, and role titles
            - Bullet points (-) for experience details
            - Proper spacing and line breaks for professional PDF rendering

            The documents should be formatted for optimal PDF conversion while maintaining professional appearance and readability.

            ## Resume Example Format

            ```markdown
            # Adrian Obleton
            10727 Domain Dr, Austin, TX 78758 | obletonadrian@gmail.com | (706) 664-1258

            ## Experience

            ### Consultant → Senior Consultant, Bain & Company | Atlanta, GA & Austin, TX
            *2017-2025*

            * Led enterprise transformation initiatives for Fortune 500 clients across industrials, healthcare, and technology sectors.
            * Orchestrated GTM transformation for a $6B global IT services business - including sales process redesign, pricing overhaul, and renewal strategy - driving ~15% YoY growth across recurring contracts.
            * Designed and implemented enterprise-wide tracking systems with BU and finance leaders to manage transformation KPIs, reversing a 10% revenue decline to 1% growth for a major OEM.
            * Stood up a strategic PMO for a $150B medical products company to drive a multiyear cost and margin improvement program across procurement, ops, and commercial functions.

            ### Associate Consultant, Bain & Company | Atlanta, GA
            *2017-2019*

            * Served clients across private equity, education, and technology industries.
            * Developed growth strategy and detailed financial plan to expand a 5,000-student charter school system to 10,000.
            * Conducted commercial due diligence for 6 M&A transactions worth $70B+, building industry forecast models, running surveys, and interviewing industry experts.
            ```

            ## Cover Letter Example Format

            ```markdown
            Adrian Obleton
            Austin, TX
            obletonadrian@gmail.com
            +1 706-664-1258

            Hiring Manager
            Google

            Dear Hiring Manager,

            I am writing to express my strong interest in the Senior Business Operations and Planning Lead position within Google's Trust and Safety organization. With an MBA from Harvard and over eight years of strategic planning and operations experience, including pivotal roles at Bain & Company and Turbonomic, I am excited by the opportunity to contribute to Google's mission of building trust in technology.

            At Bain & Company, I successfully led transformation projects for global firms, achieving significant KPI-driven results. My experience managing executive stakeholders and implementing strategic initiatives that align with organizational goals has been proven in fast-paced environments. As the Strategy & Sales Operations Manager at Turbonomic, I played a key role in managing a $300M pipeline, leading to improved sales velocity and client retention by utilizing data-driven insights.

            In my entrepreneurial ventures, I honed my ability to navigate dynamic and challenging environments, demonstrating my capacity to drive operational excellence and innovation. I am particularly drawn to this role at Google due to its alignment with my skills in management consulting, business strategy, and trust and safety frameworks.

            I am eager to bring my experience and skills to Google's Trust and Safety team to help further its mission of delivering safe and trusted user experiences worldwide.

            Thank you for considering my application.

            Sincerely,
            Adrian Obleton
            ```
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