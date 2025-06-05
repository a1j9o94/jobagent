# Personal Job-Application Agent: Complete Engineering Design & Build Document

> **Audience:** A Python full-stack developer comfortable with Docker, Celery, Playwright, and basic DevOps.
> 
> **Goal:** This document provides a complete, actionable blueprint to build, test, and deploy a sophisticated, automated job application agent. Following these instructions will result in a working, containerized application stack that is ready for interaction, local development, and cloud deployment.

## 0. Guiding Principles & Architecture

The architecture is designed to be robust, scalable, and maintainable, balancing modern best practices with pragmatic implementation choices.

| Need | Choice (and Why) |
|---|---|
| Typed & Migratable DB | SQLModel + Alembic → Provides Pydantic-based validation and a full ORM in one class structure. Alembic handles robust, version-controlled schema migrations, critical for development and deployment. |
| API & Agent Tooling | FastAPI → Serves as the core of the api service, exposing both internal "tools" for agent tasks and external webhook endpoints (/ingest, /webhooks) for data ingestion and Human-in-the-Loop (HITL) replies. |
| Scheduling & Async | Celery + Celery-Beat (Redis broker) → Manages the job processing pipeline. Tasks are designed to be short-lived state-change triggers, enabling complex workflows like automated reporting and asynchronous user interaction. |
| Human-in-the-Loop | Twilio WhatsApp (Webhooks) → A webhook handler in the API server receives user replies, updates the application's state in the database, and populates a persistent user knowledge base to make the agent smarter over time. |
| LLM Orchestration | pydantic-ai → Enables structured outputs from LLM calls, ensuring that prompts return predictable Pydantic objects that can be reliably used throughout the system. |
| Browser Automation | Playwright (headless Chromium) → Handles the complex task of web form automation. The core submit_form function is designed as a dispatcher to platform-specific subroutines. |
| File Storage | MinIO Object Store (S3-Compatible) → Securely stores generated artifacts like resumes and cover letters. It is included in the docker-compose stack for a fully self-contained, single-command local deployment. |
| Reproducible Env | uv + multi-stage Docker build → Creates a lean, consistent, and reproducible environment that runs identically on a local machine or a cloud host. |

## 1. System & Data Flow

The system operates as a set of coordinated services that handle job sourcing, ranking, application, and user interaction.

```mermaid
graph TD
    subgraph External Inputs & Triggers
        A[User via curl/script] -->|POST /ingest/profile| S;
        B[Cron / RSS Feed] -->|Source Jobs| C[Celery Beat];
        D[Twilio] -->|POST /webhooks/whatsapp| S;
    end

    subgraph System Boundary
        C -->|Enqueue Task| Q(Redis Broker);
        Q --> W[Celery Worker];
        
        S[FastAPI Server] -->|CRUD| DB[(PostgreSQL)];
        S -->|Enqueue Task| Q;
        S -->|Store/Retrieve Files| O(MinIO Object Store);

        W -->|Call Tool| S;
        W -->|Update State| DB;
        W -->|Send Notification| N(Twilio API);
    end

    style S fill:#f9f,stroke:#333,stroke-width:2px
    style DB fill:#ccf,stroke:#333,stroke-width:2px
```

**Key Workflows:**
- **Smarter Human-in-the-Loop (HITL):** When an application requires user input (e.g., salary), the agent first queries the UserPreference table. If the answer is found, it proceeds automatically. If not, it pings the user via WhatsApp. The user's reply is received by the API, which updates the application and saves the answer to the UserPreference table, making the agent more knowledgeable for the future.
- **Automated Reporting:** Every morning, Celery Beat triggers a task that calls the generate_daily_report tool. This tool queries the database for the previous day's activity (applications sent, interviews scheduled) and sends a concise summary to the user via WhatsApp.

## 2. Core Data Models (app/models.py)

This is the single source of truth for the database schema, defined using SQLModel.

```python
# app/models.py
from enum import Enum
from datetime import datetime, date
from typing import List, Optional, Set, Dict, Any
from sqlmodel import SQLModel, Field, Relationship, Column, String, Text
from pydantic import BaseModel, SecretStr
import sqlalchemy as sa

# --- Enums ---
class RoleCategory(str, Enum):
    SALES = "sales"
    OPERATIONS = "operations"
    ENGINEERING = "engineering"
    PRODUCT = "product"
    FINANCE = "finance"
    OTHER = "other"

class Seniority(str, Enum):
    IC = "individual_contributor"
    MANAGER = "people_manager"
    EXECUTIVE = "executive"

class WorkMode(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"

class RoleStatus(str, Enum):
    SOURCED = "sourced"
    RANKED = "ranked"
    APPLYING = "applying"
    APPLIED = "applied"
    IGNORED = "ignored"

class ApplicationStatus(str, Enum):
    DRAFT = "draft"
    NEEDS_USER_INFO = "needs_user_info"
    READY_TO_SUBMIT = "ready_to_submit"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    ERROR = "error"
    REJECTED = "rejected"
    INTERVIEW = "interview"
    OFFER = "offer"
    CLOSED = "closed"

# --- Pydantic Models (for LLM output) ---
class RankResult(BaseModel):
    score: float = Field(..., description="A score from 0.0 to 1.0 on how well the profile fits the role.")
    rationale: str = Field(..., description="A brief explanation for the score.")

class ResumeDraft(BaseModel):
    resume_md: str
    cover_letter_md: str
    identified_skills: List[str]

# --- SQLModel Tables ---
class Skill(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)

class RoleSkillLink(SQLModel, table=True):
    role_id: Optional[int] = Field(default=None, foreign_key="role.id", primary_key=True)
    skill_id: Optional[int] = Field(default=None, foreign_key="skill.id", primary_key=True)

class Credential(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id")
    site_hostname: str = Field(index=True)
    username: str
    encrypted_password: str = Field(sa_column=Column(Text))

class Company(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    website: Optional[str] = None
    roles: List["Role"] = Relationship(back_populates="company")

class Role(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str = Field(sa_column=Column(Text))
    posting_url: str
    unique_hash: str = Field(unique=True, index=True)
    status: RoleStatus = RoleStatus.SOURCED
    rank_score: Optional[float] = None
    rank_rationale: Optional[str] = Field(default=None, sa_column=Column(Text))
    company_id: int = Field(foreign_key="company.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    company: Company = Relationship(back_populates="roles")
    skills: List[Skill] = Relationship(link_model=RoleSkillLink)
    applications: List["Application"] = Relationship(back_populates="role")

class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    role_id: int = Field(foreign_key="role.id")
    profile_id: int = Field(foreign_key="profile.id")
    celery_task_id: Optional[str] = Field(default=None, index=True)
    status: ApplicationStatus = ApplicationStatus.DRAFT
    resume_s3_url: Optional[str] = None
    cover_letter_s3_url: Optional[str] = None
    custom_answers: Optional[Dict[str, Any]] = Field(
        default_factory=dict, 
        sa_column=Column(sa.JSON)
    )
    submitted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    role: Role = Relationship(back_populates="applications")
    profile: "Profile" = Relationship(back_populates="applications")

class UserPreference(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id")
    key: str = Field(index=True)
    value: str
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    profile: "Profile" = Relationship(back_populates="preferences")

class Profile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    headline: str
    summary: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    credentials: List[Credential] = Relationship()
    preferences: List[UserPreference] = Relationship(back_populates="profile")
    applications: List[Application] = Relationship(back_populates="profile")
```

## 3. Database Configuration (app/db.py)

```python
# app/db.py
import os
import logging
from sqlmodel import create_engine, Session, SQLModel
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=300,    # Recycle connections every 5 minutes
    echo=os.getenv("DB_ECHO", "false").lower() == "true"
)

def create_tables():
    """Create all tables. Used in tests and initial setup."""
    SQLModel.metadata.create_all(engine)

def get_session():
    """Dependency for FastAPI to get database sessions."""
    with Session(engine) as session:
        yield session

@contextmanager
def get_session_context():
    """Context manager for database sessions outside of FastAPI."""
    with Session(engine) as session:
        yield session

def health_check() -> bool:
    """Check if database is accessible."""
    try:
        with Session(engine) as session:
            session.exec("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
```

## 4. Encryption Utilities (app/security.py)

```python
# app/security.py
import os
import base64
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    logger.warning("ENCRYPTION_KEY not set, generating temporary key (NOT FOR PRODUCTION)")
    ENCRYPTION_KEY = Fernet.generate_key().decode()

fernet = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)

def encrypt_password(password: str) -> str:
    """Encrypt a password for storage."""
    return fernet.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password: str) -> str:
    """Decrypt a stored password."""
    return fernet.decrypt(encrypted_password.encode()).decode()
```

## 5. Object Storage (app/storage.py)

```python
# app/storage.py
import os
import boto3
import logging
from io import BytesIO
from botocore.exceptions import ClientError

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
S3_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
S3_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

logger = logging.getLogger(__name__)

try:
    s3_client = boto3.client(
        's3',
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name='us-east-1'
    )
    logger.info(f"Successfully initialized S3 client for endpoint: {S3_ENDPOINT_URL}")
except Exception as e:
    logger.error(f"Failed to initialize S3 client: {e}")
    s3_client = None

def ensure_bucket_exists():
    """Create the bucket if it doesn't exist."""
    if not s3_client:
        return False
    
    try:
        s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
        logger.info(f"Bucket {S3_BUCKET_NAME} exists")
        return True
    except ClientError as e:
        error_code = int(e.response['Error']['Code'])
        if error_code == 404:
            try:
                s3_client.create_bucket(Bucket=S3_BUCKET_NAME)
                logger.info(f"Created bucket {S3_BUCKET_NAME}")
                return True
            except ClientError as create_error:
                logger.error(f"Failed to create bucket: {create_error}")
                return False
        else:
            logger.error(f"Error checking bucket: {e}")
            return False

def upload_file_to_storage(
    file_content: bytes, 
    object_name: str, 
    content_type: str = 'application/octet-stream'
) -> str | None:
    """Upload file content to object storage."""
    if not s3_client:
        logger.error("S3 client not available. Cannot upload file.")
        return None
    
    if not ensure_bucket_exists():
        logger.error("Bucket not available. Cannot upload file.")
        return None
    
    try:
        file_stream = BytesIO(file_content)
        s3_client.upload_fileobj(
            File=file_stream,
            Bucket=S3_BUCKET_NAME,
            Key=object_name,
            ExtraArgs={'ContentType': content_type}
        )
        logger.info(f"Successfully uploaded {object_name} to bucket {S3_BUCKET_NAME}.")
        file_url = f"{S3_ENDPOINT_URL}/{S3_BUCKET_NAME}/{object_name}"
        return file_url
    except ClientError as e:
        logger.error(f"Failed to upload {object_name} to S3. Error: {e}")
        return None

def health_check() -> bool:
    """Check if object storage is accessible."""
    if not s3_client:
        return False
    
    try:
        s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
        return True
    except Exception as e:
        logger.error(f"S3 health check failed: {e}")
        return False
```

## 6. PDF Generation (app/pdf_utils.py)

```python
# app/pdf_utils.py
import logging
from io import BytesIO
from weasyprint import HTML, CSS
from markdown import markdown

logger = logging.getLogger(__name__)

def markdown_to_html(md_content: str) -> str:
    """Convert markdown to HTML with basic styling."""
    html_content = markdown(md_content)
    
    # Basic CSS for professional documents
    css_style = """
    <style>
    body {
        font-family: 'Arial', sans-serif;
        line-height: 1.6;
        color: #333;
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
    }
    h1, h2, h3 {
        color: #2c3e50;
        margin-top: 0;
    }
    h1 {
        border-bottom: 2px solid #3498db;
        padding-bottom: 10px;
    }
    ul {
        margin: 10px 0;
        padding-left: 20px;
    }
    </style>
    """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        {css_style}
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """

def render_to_pdf(content: str, is_markdown: bool = True) -> bytes:
    """Convert markdown or HTML content to PDF bytes."""
    try:
        if is_markdown:
            html_content = markdown_to_html(content)
        else:
            html_content = content
        
        pdf_bytes = HTML(string=html_content).write_pdf()
        logger.info("Successfully generated PDF")
        return pdf_bytes
    
    except Exception as e:
        logger.error(f"Failed to generate PDF: {e}")
        raise
```

## 7. Browser Automation (app/automation.py)

```python
# app/automation.py
import logging
import asyncio
from playwright.async_api import async_playwright, Browser, Page
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class FormSubmissionError(Exception):
    """Raised when form submission fails."""
    pass

class BrowserAutomation:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None
    
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def submit_job_application(
        self, 
        posting_url: str, 
        form_data: Dict[str, Any],
        credentials: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Submit a job application form.
        
        Returns a dictionary with submission status and details.
        """
        if not self.browser:
            raise FormSubmissionError("Browser not initialized")
        
        page = await self.browser.new_page()
        
        try:
            logger.info(f"Navigating to job posting: {posting_url}")
            await page.goto(posting_url, wait_until='networkidle')
            
            # Platform-specific submission logic
            if 'greenhouse.io' in posting_url:
                return await self._submit_greenhouse_form(page, form_data)
            elif 'workday.com' in posting_url:
                return await self._submit_workday_form(page, form_data, credentials)
            elif 'lever.co' in posting_url:
                return await self._submit_lever_form(page, form_data)
            else:
                return await self._submit_generic_form(page, form_data)
                
        except Exception as e:
            logger.error(f"Form submission failed: {e}")
            # Take screenshot for debugging
            await page.screenshot(path=f"error_{posting_url.split('/')[-1]}.png")
            return {
                "status": "error",
                "message": str(e),
                "screenshot_taken": True
            }
        finally:
            await page.close()
    
    async def _submit_greenhouse_form(self, page: Page, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Greenhouse.io application forms."""
        try:
            # Wait for and click apply button
            await page.wait_for_selector('a[data-mapped="true"]', timeout=10000)
            await page.click('a[data-mapped="true"]')
            
            # Fill basic information
            await page.fill('input[name="first_name"]', form_data.get('first_name', ''))
            await page.fill('input[name="last_name"]', form_data.get('last_name', ''))
            await page.fill('input[name="email"]', form_data.get('email', ''))
            await page.fill('input[name="phone"]', form_data.get('phone', ''))
            
            # Upload resume if provided
            if 'resume_path' in form_data:
                await page.set_input_files('input[type="file"]', form_data['resume_path'])
            
            # Submit form
            await page.click('input[type="submit"]')
            
            # Wait for success confirmation
            await page.wait_for_selector('.confirmation', timeout=15000)
            
            return {
                "status": "success",
                "platform": "greenhouse",
                "message": "Application submitted successfully"
            }
            
        except Exception as e:
            raise FormSubmissionError(f"Greenhouse submission failed: {e}")
    
    async def _submit_workday_form(self, page: Page, form_data: Dict[str, Any], credentials: Dict[str, str]) -> Dict[str, Any]:
        """Handle Workday application forms (requires login)."""
        # This is a more complex implementation due to Workday's authentication
        # Implementation would include login flow, form navigation, etc.
        logger.warning("Workday automation not fully implemented")
        return {
            "status": "pending",
            "platform": "workday",
            "message": "Workday automation requires manual intervention"
        }
    
    async def _submit_lever_form(self, page: Page, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Lever.co application forms."""
        try:
            # Lever typically has simpler forms
            await page.fill('input[name="name"]', f"{form_data.get('first_name', '')} {form_data.get('last_name', '')}")
            await page.fill('input[name="email"]', form_data.get('email', ''))
            await page.fill('input[name="phone"]', form_data.get('phone', ''))
            
            if 'resume_path' in form_data:
                await page.set_input_files('input[name="resume"]', form_data['resume_path'])
            
            await page.click('button[type="submit"]')
            await page.wait_for_url('**/confirmation', timeout=15000)
            
            return {
                "status": "success",
                "platform": "lever",
                "message": "Application submitted successfully"
            }
            
        except Exception as e:
            raise FormSubmissionError(f"Lever submission failed: {e}")
    
    async def _submit_generic_form(self, page: Page, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle generic job application forms."""
        # Basic form field detection and filling
        logger.info("Attempting generic form submission")
        
        # Common form field patterns
        field_patterns = {
            'first_name': ['input[name*="first"]', 'input[id*="first"]', 'input[placeholder*="First"]'],
            'last_name': ['input[name*="last"]', 'input[id*="last"]', 'input[placeholder*="Last"]'],
            'email': ['input[type="email"]', 'input[name*="email"]', 'input[id*="email"]'],
            'phone': ['input[type="tel"]', 'input[name*="phone"]', 'input[id*="phone"]']
        }
        
        filled_fields = 0
        for field_name, selectors in field_patterns.items():
            if field_name in form_data:
                for selector in selectors:
                    try:
                        if await page.locator(selector).count() > 0:
                            await page.fill(selector, str(form_data[field_name]))
                            filled_fields += 1
                            break
                    except Exception:
                        continue
        
        return {
            "status": "partial",
            "platform": "generic",
            "message": f"Filled {filled_fields} form fields, manual review required"
        }
```

## 8. Agent Tools & LLM Integration (app/tools.py)

```python
# app/tools.py
import os
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlmodel import Session, select
from pydantic_ai import Agent, RunContext

from app.models import (
    RankResult, ResumeDraft, Role, Profile, Application, 
    Company, UserPreference, ApplicationStatus, RoleStatus
)
from app.db import get_session_context, engine
from app.storage import upload_file_to_storage
from app.pdf_utils import render_to_pdf
from app.automation import BrowserAutomation, FormSubmissionError
from app.security import decrypt_password

logger = logging.getLogger(__name__)

# Initialize the LLM agent
ranking_agent = Agent(
    'openai:gpt-4o-mini',
    result_type=RankResult,
    system_prompt="""You are a career advisor evaluating job role matches.
    Analyze the job description and candidate profile to provide an accurate fit score.
    Consider skills, experience level, company culture, and role requirements."""
)

resume_agent = Agent(
    'openai:gpt-4o-mini',
    result_type=ResumeDraft,
    system_prompt="""You are an expert resume writer and career coach.
    Create compelling, ATS-optimized resumes and cover letters tailored to specific job postings.
    Focus on quantifiable achievements and relevant keywords."""
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
        
        try:
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
            resume_filename = f"resume_{application_id}_{datetime.now().isoformat()}.pdf"
            cover_letter_filename = f"cover_letter_{application_id}_{datetime.now().isoformat()}.pdf"
            
            resume_url = upload_file_to_storage(resume_pdf, resume_filename, 'application/pdf')
            cover_letter_url = upload_file_to_storage(cover_letter_pdf, cover_letter_filename, 'application/pdf')
            
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
                    "identified_skills": draft.identified_skills
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
            "resume_path": None  # Would need to download from S3 for local file
        }
        
        # Get credentials for the site
        credentials = {}
        for cred in profile.credentials:
            if cred.site_hostname in role.posting_url:
                credentials = {
                    "username": cred.username,
                    "password": decrypt_password(cred.encrypted_password)
                }
                break
        
        try:
            application.status = ApplicationStatus.SUBMITTING
            session.commit()
            
            async with BrowserAutomation() as browser:
                result = await browser.submit_job_application(
                    role.posting_url, 
                    form_data, 
                    credentials
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
        end_of_day = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        
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
            pref.last_updated = datetime.utcnow()
        else:
            pref = UserPreference(
                profile_id=profile_id,
                key=key,
                value=value
            )
            session.add(pref)
        
        session.commit()
        logger.info(f"Saved preference {key} for profile {profile_id}")
```

## 9. Webhook & Notification Utilities (app/notifications.py)

```python
# app/notifications.py
import os
import logging
from twilio.rest import Client
from twilio.request_validator import RequestValidator
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
WA_FROM = os.getenv("WA_FROM")
WA_TO = os.getenv("WA_TO")

# Initialize Twilio client
twilio_client = None
twilio_validator = None

if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN)
else:
    logger.warning("Twilio credentials not configured")

def send_whatsapp_message(message: str, to_number: str = None) -> bool:
    """Send a WhatsApp message via Twilio."""
    if not twilio_client:
        logger.error("Twilio client not initialized")
        return False
    
    to_number = to_number or WA_TO
    if not to_number or not WA_FROM:
        logger.error("WhatsApp phone numbers not configured")
        return False
    
    try:
        message_obj = twilio_client.messages.create(
            body=message,
            from_=WA_FROM,
            to=to_number
        )
        logger.info(f"WhatsApp message sent: {message_obj.sid}")
        return True
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {e}")
        return False

def validate_twilio_webhook(request: Request) -> bool:
    """Validate that a webhook request came from Twilio."""
    if not twilio_validator:
        logger.warning("Twilio validator not initialized, skipping validation")
        return True
    
    try:
        # Get the full URL including query parameters
        url = str(request.url)
        
        # Get the signature from headers
        signature = request.headers.get('X-Twilio-Signature', '')
        
        # Get the POST parameters
        form_data = {}
        if hasattr(request, '_form'):
            form_data = dict(request._form)
        
        # Validate the request
        is_valid = twilio_validator.validate(url, form_data, signature)
        
        if not is_valid:
            logger.warning(f"Invalid Twilio webhook signature for URL: {url}")
        
        return is_valid
        
    except Exception as e:
        logger.error(f"Error validating Twilio webhook: {e}")
        return False

def health_check() -> bool:
    """Check if notification service is accessible."""
    return twilio_client is not None
```

## 10. API Server (app/api_server.py)

```python
# app/api_server.py
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, Response, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlmodel import Session, select

from app.db import get_session, health_check as db_health_check
from app.storage import health_check as storage_health_check
from app.notifications import (
    send_whatsapp_message, 
    validate_twilio_webhook, 
    health_check as notification_health_check
)
from app.models import Profile, UserPreference, Application, ApplicationStatus
from app.tools import save_user_preference
from app.tasks import celery_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Job Application Agent API",
    description="Automated job application system with AI-powered matching",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# API Key authentication
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)
PROFILE_INGEST_API_KEY = os.getenv("PROFILE_INGEST_API_KEY", "default-key")

async def get_api_key(api_key: str = Depends(API_KEY_HEADER)):
    if api_key != PROFILE_INGEST_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Invalid API Key"
        )
    return api_key

def redis_health_check() -> bool:
    """Check if Redis/Celery broker is accessible."""
    try:
        # Use Celery's ping to check Redis connectivity
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        return stats is not None
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False

@app.get("/health", summary="Comprehensive Health Check", tags=["System"])
def health_check():
    """Check the health of all system components."""
    health_status = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": db_health_check(),
            "redis": redis_health_check(),
            "object_storage": storage_health_check(),
            "notifications": notification_health_check()
        }
    }
    
    # Determine overall status
    all_services_healthy = all(health_status["services"].values())
    
    if not all_services_healthy:
        health_status["status"] = "degraded"
        
        # If database is down, this is critical
        if not health_status["services"]["database"]:
            health_status["status"] = "critical"
    
    # Return appropriate HTTP status code
    if health_status["status"] == "critical":
        return Response(
            content=str(health_status),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json"
        )
    elif health_status["status"] == "degraded":
        return Response(
            content=str(health_status),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type="application/json"
        )
    
    return health_status

@app.post("/ingest/profile", 
          summary="Ingest a user's full profile",
          dependencies=[Depends(get_api_key)],
          tags=["Data Ingestion"])
@limiter.limit("5/minute")
async def ingest_profile_data(
    request: Request,
    profile_data: Dict[str, Any],
    session: Session = Depends(get_session)
):
    """A protected endpoint to upload or update the user's professional profile."""
    try:
        # Check if profile exists (assuming single user for now)
        existing_profile = session.exec(select(Profile)).first()
        
        if existing_profile:
            # Update existing profile
            existing_profile.headline = profile_data.get("headline", existing_profile.headline)
            existing_profile.summary = profile_data.get("summary", existing_profile.summary)
            existing_profile.updated_at = datetime.utcnow()
            profile_id = existing_profile.id
        else:
            # Create new profile
            new_profile = Profile(
                headline=profile_data.get("headline", ""),
                summary=profile_data.get("summary", "")
            )
            session.add(new_profile)
            session.commit()
            session.refresh(new_profile)
            profile_id = new_profile.id
        
        # Save any preferences included in the profile data
        preferences = profile_data.get("preferences", {})
        for key, value in preferences.items():
            save_user_preference(profile_id, key, str(value))
        
        session.commit()
        logger.info(f"Profile {profile_id} ingested successfully")
        
        return {
            "status": "success", 
            "message": "Profile ingested successfully.", 
            "profile_id": profile_id
        }
        
    except Exception as e:
        logger.error(f"Profile ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Profile ingestion failed: {str(e)}"
        )

@app.post("/webhooks/whatsapp", 
          summary="Handle incoming Twilio messages", 
          tags=["Webhooks"])
@limiter.limit("30/minute")
async def handle_whatsapp_reply(request: Request):
    """Handles inbound messages from Twilio for the HITL workflow."""
    
    # Store form data for validation
    form_data = await request.form()
    request._form = form_data
    
    # Validate webhook signature
    if not validate_twilio_webhook(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature"
        )
    
    try:
        from_number = form_data.get('From', '')
        message_body = form_data.get('Body', '').strip()
        
        logger.info(f"Received WhatsApp message from {from_number}: {message_body}")
        
        # Basic message processing
        if message_body.lower() in ['help', 'h']:
            help_message = """
🤖 Job Agent Commands:
• 'status' - Check application status
• 'report' - Get daily report
• 'stop' - Pause applications
• 'start' - Resume applications
• Or answer any pending questions
            """
            send_whatsapp_message(help_message, from_number)
            
        elif message_body.lower() == 'status':
            # Get status for the user (assuming single user for now)
            with get_session() as session:
                pending_apps = session.exec(
                    select(Application)
                    .where(Application.status == ApplicationStatus.NEEDS_USER_INFO)
                ).all()
                
                status_msg = f"📊 Status: {len(pending_apps)} applications need your input"
                send_whatsapp_message(status_msg, from_number)
                
        elif message_body.lower() == 'report':
            # Trigger daily report generation
            from app.tasks import task_send_daily_report
            task_send_daily_report.delay()
            
        else:
            # Assume this is an answer to a pending question
            # This would need more sophisticated logic to match questions to applications
            response_msg = "✅ Got your response! I'll update the application accordingly."
            send_whatsapp_message(response_msg, from_number)
        
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    except Exception as e:
        logger.error(f"WhatsApp webhook processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing failed"
        )

@app.post("/jobs/rank/{role_id}",
          summary="Rank a specific role",
          dependencies=[Depends(get_api_key)],
          tags=["Job Processing"])
async def trigger_role_ranking(
    role_id: int,
    background_tasks: BackgroundTasks,
    profile_id: int = 1,  # Default to profile 1 for now
    session: Session = Depends(get_session)
):
    """Trigger ranking for a specific role."""
    # Verify role exists
    role = session.get(Role, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Enqueue ranking task
    from app.tasks import task_rank_role
    task = task_rank_role.delay(role_id, profile_id)
    
    return {
        "status": "queued",
        "task_id": task.id,
        "role_id": role_id
    }

@app.get("/applications", 
         summary="Get application status",
         dependencies=[Depends(get_api_key)],
         tags=["Applications"])
async def get_applications(
    status_filter: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """Get list of applications with optional status filtering."""
    query = select(Application)
    
    if status_filter:
        try:
            status_enum = ApplicationStatus(status_filter)
            query = query.where(Application.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter: {status_filter}"
            )
    
    applications = session.exec(query).all()
    
    return {
        "applications": [
            {
                "id": app.id,
                "role_title": app.role.title,
                "company_name": app.role.company.name,
                "status": app.status,
                "created_at": app.created_at,
                "submitted_at": app.submitted_at
            }
            for app in applications
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## 11. Async Tasks (app/tasks.py)

```python
# app/tasks.py
import logging
from celery import Celery
from celery.schedules import crontab
from sqlmodel import Session

from app.db import engine
from app.tools import rank_role, draft_and_upload_documents, generate_daily_report, submit_application
from app.notifications import send_whatsapp_message

logger = logging.getLogger(__name__)

# Initialize Celery
BROKER_URL = "redis://redis:6379/0"
RESULT_BACKEND = "redis://redis:6379/0"

celery_app = Celery(
    "jobagent", 
    broker=BROKER_URL, 
    backend=RESULT_BACKEND,
    include=['app.tasks']
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
)

@celery_app.task(bind=True, max_retries=3)
def task_rank_role(self, role_id: int, profile_id: int):
    """Async task to rank a role against a profile."""
    try:
        result = rank_role(role_id, profile_id)
        logger.info(f"Successfully ranked role {role_id}: {result.score}")
        return {
            "status": "success",
            "role_id": role_id,
            "score": result.score,
            "rationale": result.rationale
        }
    except Exception as e:
        logger.error(f"Failed to rank role {role_id}: {e}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries
            raise self.retry(countdown=countdown, exc=e)
        
        return {"status": "error", "message": str(e)}

@celery_app.task(bind=True, max_retries=3)
def task_generate_documents(self, application_id: int):
    """Async task to generate and upload application documents."""
    try:
        result = draft_and_upload_documents(application_id)
        logger.info(f"Generated documents for application {application_id}")
        return result
    except Exception as e:
        logger.error(f"Failed to generate documents for application {application_id}: {e}")
        
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries
            raise self.retry(countdown=countdown, exc=e)
        
        return {"status": "error", "message": str(e)}

@celery_app.task(bind=True, max_retries=2)
def task_submit_application(self, application_id: int):
    """Async task to submit an application using browser automation."""
    try:
        result = submit_application(application_id)
        logger.info(f"Submitted application {application_id}: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to submit application {application_id}: {e}")
        
        if self.request.retries < self.max_retries:
            countdown = 60 * (self.request.retries + 1)  # 1 min, 2 min
            raise self.retry(countdown=countdown, exc=e)
        
        return {"status": "error", "message": str(e)}

@celery_app.task
def task_send_daily_report():
    """Generate and send daily activity report."""
    try:
        # Assuming single user with profile_id=1 for now
        profile_id = 1
        report = generate_daily_report(profile_id)
        
        # Send via WhatsApp
        success = send_whatsapp_message(report)
        
        if success:
            logger.info("Daily report sent successfully")
            return {"status": "success", "report_sent": True}
        else:
            logger.error("Failed to send daily report")
            return {"status": "error", "message": "Failed to send report"}
            
    except Exception as e:
        logger.error(f"Daily report task failed: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task
def task_process_new_roles():
    """Process newly sourced roles for ranking and application."""
    try:
        from app.models import Role, RoleStatus
        
        with Session(engine) as session:
            # Get unprocessed roles
            new_roles = session.query(Role).filter(
                Role.status == RoleStatus.SOURCED
            ).limit(10).all()  # Process in batches
            
            processed_count = 0
            for role in new_roles:
                # Trigger ranking task
                task_rank_role.delay(role.id, 1)  # Assuming profile_id=1
                processed_count += 1
            
            logger.info(f"Queued {processed_count} roles for processing")
            return {"status": "success", "processed": processed_count}
            
    except Exception as e:
        logger.error(f"Role processing task failed: {e}")
        return {"status": "error", "message": str(e)}

# Periodic task scheduling
celery_app.conf.beat_schedule = {
    'send-daily-report': {
        'task': 'app.tasks.task_send_daily_report',
        'schedule': crontab(hour=8, minute=0),  # Daily at 8:00 AM UTC
    },
    'process-new-roles': {
        'task': 'app.tasks.task_process_new_roles',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
}

celery_app.conf.timezone = 'UTC'

# Celery signal handlers
@celery_app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
```

## 12. Database Migrations (alembic/env.py)

```python
# alembic/env.py
import os
from logging.config import fileConfig
from sqlmodel import SQLModel
from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import all models to ensure they're registered
from app.models import *

# This is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the SQLAlchemy URL from environment variable
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

target_metadata = SQLModel.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

## 13. Project Structure & Key Files

### 13.5 Enhanced docker-compose.yml
```yaml
version: "3.9"

services:
  api:
    build: 
      context: .
      target: final
    env_file: .env
    ports: 
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_started
    volumes:
      - ./app:/code/app:ro  # For development hot reload
    command: ["uvicorn", "app.api_server:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  worker:
    build: 
      context: .
      target: final
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_started
    command: ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
    volumes:
      - ./app:/code/app:ro

  beat:
    build: 
      context: .
      target: final
    env_file: .env
    depends_on:
      redis:
        condition: service_healthy
      db:
        condition: service_healthy
    command: ["celery", "-A", "app.tasks.celery_app", "beat", "--loglevel=info"]
    volumes:
      - ./app:/code/app:ro

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports: 
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  minio:
    image: minio/minio:latest
    ports: 
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

volumes:
  postgres_data:
  redis_data:
  minio_data:

networks:
  default:
    name: jobagent_network
```

### 13.6 Test Docker Compose (docker-compose.test.yml)
```yaml
version: "3.9"

services:
  test_db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_password
      POSTGRES_DB: test_jobagent
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test_user -d test_jobagent"]
      interval: 5s
      timeout: 5s
      retries: 5

  test_redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"

  tests:
    build: 
      context: .
      target: final
    environment:
      DATABASE_URL: postgresql+psycopg2://test_user:test_password@test_db:5432/test_jobagent
      REDIS_URL: redis://test_redis:6379/0
      PROFILE_INGEST_API_KEY: test-api-key
    depends_on:
      test_db:
        condition: service_healthy
      test_redis:
        condition: service_started
    command: ["pytest", "-v", "--tb=short"]
    volumes:
      - ./tests:/code/tests
      - ./app:/code/app
```

### 13.7 Enhanced .env.sample
```bash
# PostgreSQL Database
POSTGRES_USER=jobagent_user
POSTGRES_PASSWORD=secure_postgres_password_123
POSTGRES_DB=jobagent

# Database URL for applications (adjust host for local/container context)
# For local development (when running alembic from host):
DATABASE_URL=postgresql+psycopg2://jobagent_user:secure_postgres_password_123@localhost:5432/jobagent
# For container context, this would be: postgresql+psycopg2://jobagent_user:secure_postgres_password_123@db:5432/jobagent

# Redis Configuration
REDIS_URL=redis://redis:6379/0

# MinIO/S3 Object Store
S3_ENDPOINT_URL=http://minio:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET_NAME=job-agent-documents
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# Security & Encryption
PROFILE_INGEST_API_KEY=your_very_secure_random_api_key_here_32_chars
ENCRYPTION_KEY=your_32_character_encryption_key_123

# LLM Configuration
OPENAI_API_KEY=sk-your_openai_api_key_here

# Twilio WhatsApp Configuration
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
WA_FROM=whatsapp:+14155238886
WA_TO=whatsapp:+1XXXXXXXXXX

# Development Settings
DB_ECHO=false
LOG_LEVEL=INFO
```

### 13.8 Enhanced entrypoint.sh
```bash
#!/usr/bin/env bash
set -e

echo "🚀 Starting Job Agent service..."

# Function to wait for a service
wait_for_service() {
    local host="$1"
    local port="$2"
    local service_name="$3"
    local max_attempts=30
    local attempt=1

    echo "⏳ Waiting for $service_name to be ready..."
    
    while ! nc -z "$host" "$port" 2>/dev/null; do
        if [ $attempt -eq $max_attempts ]; then
            echo "❌ $service_name failed to start within timeout"
            exit 1
        fi
        
        echo "   Attempt $attempt/$max_attempts..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "✅ $service_name is ready!"
}

# Wait for database
wait_for_service "db" "5432" "PostgreSQL"

# Wait for Redis
wait_for_service "redis" "6379" "Redis"

# Run database migrations
echo "🔄 Running database migrations..."
if alembic -c alembic.ini upgrade head; then
    echo "✅ Database migrations completed successfully"
else
    echo "❌ Database migrations failed"
    exit 1
fi

# Initialize MinIO bucket if this is the API service
if [[ "$1" == "uvicorn" ]]; then
    echo "🪣 Initializing object storage..."
    python -c "
from app.storage import ensure_bucket_exists
import time
import sys

# Wait a bit for MinIO to start
time.sleep(5)

try:
    if ensure_bucket_exists():
        print('✅ Object storage initialized')
    else:
        print('⚠️  Object storage initialization failed')
        sys.exit(1)
except Exception as e:
    print(f'⚠️  Object storage error: {e}')
    sys.exit(1)
"
fi

echo "🎯 Starting application with command: $*"

# Execute the main command
exec "$@"
```

### 13.9 Test Configuration (tests/conftest.py)
```python
# tests/conftest.py
import pytest
import os
import asyncio
from typing import Generator
from sqlmodel import Session, create_engine, SQLModel
from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from app.api_server import app
from app.db import get_session
from app.models import Profile, Company, Role

# Test environment setup
os.environ.update({
    "PROFILE_INGEST_API_KEY": "test-api-key",
    "ENCRYPTION_KEY": "test_encryption_key_32_characters",
    "OPENAI_API_KEY": "test-openai-key",
})

@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL container for testing."""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres

@pytest.fixture(scope="session")
def redis_container():
    """Start a Redis container for testing."""
    with RedisContainer("redis:7-alpine") as redis:
        yield redis

@pytest.fixture(scope="session")
def test_engine(postgres_container):
    """Create a test database engine."""
    database_url = postgres_container.get_connection_url()
    engine = create_engine(database_url)
    
    # Create all tables
    SQLModel.metadata.create_all(engine)
    
    yield engine
    
    # Cleanup
    SQLModel.metadata.drop_all(engine)

@pytest.fixture
def session(test_engine) -> Generator[Session, None, None]:
    """Create a test database session."""
    with Session(test_engine) as session:
        yield session

@pytest.fixture
def client(session: Session) -> Generator[TestClient, None, None]:
    """Create a test client with database dependency override."""
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()

@pytest.fixture
def sample_profile(session: Session) -> Profile:
    """Create a sample profile for testing."""
    profile = Profile(
        headline="Senior Software Engineer | Python & Cloud",
        summary="Experienced engineer specializing in building scalable backend systems."
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile

@pytest.fixture
def sample_company(session: Session) -> Company:
    """Create a sample company for testing."""
    company = Company(
        name="TechCorp Inc.",
        website="https://techcorp.com"
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return company

@pytest.fixture
def sample_role(session: Session, sample_company: Company) -> Role:
    """Create a sample role for testing."""
    role = Role(
        title="Senior Python Developer",
        description="We are looking for an experienced Python developer...",
        posting_url="https://techcorp.com/jobs/senior-python-dev",
        unique_hash="test_hash_123",
        company_id=sample_company.id
    )
    session.add(role)
    session.commit()
    session.refresh(role)
    return role

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

## 14. Comprehensive Testing Suite

### 14.1 Unit Tests (tests/unit/test_tools.py)
```python
# tests/unit/test_tools.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.tools import generate_unique_hash, get_user_preference, save_user_preference
from app.models import Profile, UserPreference

class TestTools:
    def test_generate_unique_hash_is_stable(self):
        """Tests that the hashing function is deterministic."""
        h1 = generate_unique_hash("Google", "Software Engineer")
        h2 = generate_unique_hash("Google", "Software Engineer")
        assert h1 == h2

    def test_generate_unique_hash_is_case_insensitive(self):
        """Tests that casing and whitespace do not affect the hash."""
        h1 = generate_unique_hash("Google", "Software Engineer")
        h2 = generate_unique_hash("  google  ", "  software engineer  ")
        assert h1 == h2

    def test_generate_unique_hash_different_inputs(self):
        """Tests that different inputs produce different hashes."""
        h1 = generate_unique_hash("Google", "Software Engineer")
        h2 = generate_unique_hash("Microsoft", "Software Engineer")
        assert h1 != h2

    def test_get_user_preference_exists(self, session, sample_profile):
        """Test retrieving an existing user preference."""
        # Create a preference
        pref = UserPreference(
            profile_id=sample_profile.id,
            key="salary_expectation",
            value="120000"
        )
        session.add(pref)
        session.commit()

        # Test retrieval
        value = get_user_preference(sample_profile.id, "salary_expectation")
        assert value == "120000"

    def test_get_user_preference_not_exists(self, sample_profile):
        """Test retrieving a non-existent user preference."""
        value = get_user_preference(sample_profile.id, "nonexistent_key")
        assert value is None

    def test_save_user_preference_new(self, session, sample_profile):
        """Test saving a new user preference."""
        save_user_preference(sample_profile.id, "test_key", "test_value")
        
        # Verify it was saved
        value = get_user_preference(sample_profile.id, "test_key")
        assert value == "test_value"

    def test_save_user_preference_update(self, session, sample_profile):
        """Test updating an existing user preference."""
        # Create initial preference
        save_user_preference(sample_profile.id, "test_key", "initial_value")
        
        # Update it
        save_user_preference(sample_profile.id, "test_key", "updated_value")
        
        # Verify update
        value = get_user_preference(sample_profile.id, "test_key")
        assert value == "updated_value"

class TestAsyncTools:
    @pytest.mark.asyncio
    async def test_rank_role_success(self, session, sample_role, sample_profile):
        """Test successful role ranking."""
        with patch('app.tools.ranking_agent') as mock_agent:
            # Mock the LLM response
            mock_result = Mock()
            mock_result.data.score = 0.85
            mock_result.data.rationale = "Strong technical match"
            mock_agent.run = AsyncMock(return_value=mock_result)

            # Test the function
            result = await rank_role(sample_role.id, sample_profile.id)

            assert result.score == 0.85
            assert result.rationale == "Strong technical match"

            # Verify database was updated
            session.refresh(sample_role)
            assert sample_role.rank_score == 0.85
            assert sample_role.rank_rationale == "Strong technical match"

    @pytest.mark.asyncio
    async def test_rank_role_llm_failure(self, session, sample_role, sample_profile):
        """Test role ranking when LLM call fails."""
        with patch('app.tools.ranking_agent') as mock_agent:
            mock_agent.run = AsyncMock(side_effect=Exception("LLM service unavailable"))

            result = await rank_role(sample_role.id, sample_profile.id)

            assert result.score == 0.0
            assert "LLM call failed" in result.rationale

    @pytest.mark.asyncio
    async def test_draft_and_upload_documents_success(self, session, sample_profile, sample_role):
        """Test successful document generation and upload."""
        from app.models import Application

        # Create an application
        application = Application(
            role_id=sample_role.id,
            profile_id=sample_profile.id
        )
        session.add(application)
        session.commit()
        session.refresh(application)

        with patch('app.tools.resume_agent') as mock_agent, \
             patch('app.tools.upload_file_to_storage') as mock_upload:
            
            # Mock LLM response
            mock_result = Mock()
            mock_result.data.resume_md = "# Resume Content"
            mock_result.data.cover_letter_md = "# Cover Letter Content"
            mock_result.data.identified_skills = ["Python", "FastAPI"]
            mock_agent.run = AsyncMock(return_value=mock_result)

            # Mock file upload
            mock_upload.side_effect = [
                "http://storage/resume.pdf",
                "http://storage/cover_letter.pdf"
            ]

            result = await draft_and_upload_documents(application.id)

            assert result["status"] == "success"
            assert "resume_url" in result
            assert "cover_letter_url" in result
            assert result["identified_skills"] == ["Python", "FastAPI"]
```

### 14.2 API Integration Tests (tests/e2e/test_api.py)
```python
# tests/e2e/test_api.py
import pytest
from fastapi.testclient import TestClient
from app.models import Profile

class TestHealthEndpoint:
    def test_health_check_success(self, client: TestClient):
        """Test that the health check endpoint returns 200 when all services are healthy."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] in ["ok", "degraded", "critical"]
        assert "services" in data
        assert "database" in data["services"]

class TestProfileIngestion:
    def test_ingest_profile_success(self, client: TestClient):
        """Test successful profile ingestion."""
        profile_data = {
            "headline": "Senior Software Engineer | Python & Cloud",
            "summary": "Experienced engineer specializing in building scalable backend systems.",
            "preferences": {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com"
            }
        }
        
        response = client.post(
            "/ingest/profile",
            json=profile_data,
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "profile_id" in data

    def test_ingest_profile_invalid_api_key(self, client: TestClient):
        """Test profile ingestion with invalid API key."""
        response = client.post(
            "/ingest/profile",
            json={"headline": "Test"},
            headers={"X-API-Key": "invalid-key"}
        )
        
        assert response.status_code == 403
        assert "Invalid API Key" in response.json()["detail"]

    def test_ingest_profile_missing_api_key(self, client: TestClient):
        """Test profile ingestion without API key."""
        response = client.post(
            "/ingest/profile",
            json={"headline": "Test"}
        )
        
        assert response.status_code == 403

    def test_ingest_profile_update_existing(self, client: TestClient, sample_profile: Profile):
        """Test updating an existing profile."""
        updated_data = {
            "headline": "Updated Headline",
            "summary": "Updated summary"
        }
        
        response = client.post(
            "/ingest/profile",
            json=updated_data,
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

class TestApplicationsEndpoint:
    def test_get_applications_empty(self, client: TestClient):
        """Test getting applications when none exist."""
        response = client.get(
            "/applications",
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["applications"] == []

    def test_get_applications_with_filter(self, client: TestClient):
        """Test getting applications with status filter."""
        response = client.get(
            "/applications?status_filter=draft",
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 200
        
    def test_get_applications_invalid_filter(self, client: TestClient):
        """Test getting applications with invalid status filter."""
        response = client.get(
            "/applications?status_filter=invalid_status",
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 400

class TestRoleRanking:
    def test_trigger_role_ranking_success(self, client: TestClient, sample_role):
        """Test triggering role ranking."""
        response = client.post(
            f"/jobs/rank/{sample_role.id}",
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "task_id" in data
        assert data["role_id"] == sample_role.id

    def test_trigger_role_ranking_not_found(self, client: TestClient):
        """Test triggering role ranking for non-existent role."""
        response = client.post(
            "/jobs/rank/99999",
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 404

class TestWhatsAppWebhook:
    def test_whatsapp_webhook_help_command(self, client: TestClient):
        """Test WhatsApp webhook with help command."""
        webhook_data = {
            "From": "whatsapp:+1234567890",
            "Body": "help"
        }
        
        with patch('app.api_server.validate_twilio_webhook', return_value=True), \
             patch('app.api_server.send_whatsapp_message', return_value=True) as mock_send:
            
            response = client.post(
                "/webhooks/whatsapp",
                data=webhook_data
            )
            
            assert response.status_code == 204
            mock_send.assert_called_once()

    def test_whatsapp_webhook_status_command(self, client: TestClient):
        """Test WhatsApp webhook with status command."""
        webhook_data = {
            "From": "whatsapp:+1234567890",
            "Body": "status"
        }
        
        with patch('app.api_server.validate_twilio_webhook', return_value=True), \
             patch('app.api_server.send_whatsapp_message', return_value=True) as mock_send:
            
            response = client.post(
                "/webhooks/whatsapp",
                data=webhook_data
            )
            
            assert response.status_code == 204
            mock_send.assert_called_once()

    def test_whatsapp_webhook_invalid_signature(self, client: TestClient):
        """Test WhatsApp webhook with invalid signature."""
        webhook_data = {
            "From": "whatsapp:+1234567890",
            "Body": "test message"
        }
        
        with patch('app.api_server.validate_twilio_webhook', return_value=False):
            response = client.post(
                "/webhooks/whatsapp",
                data=webhook_data
            )
            
            assert response.status_code == 403

class TestRateLimiting:
    def test_profile_ingestion_rate_limit(self, client: TestClient):
        """Test rate limiting on profile ingestion endpoint."""
        profile_data = {"headline": "Test", "summary": "Test"}
        headers = {"X-API-Key": "test-api-key"}
        
        # Make multiple requests to trigger rate limit
        for i in range(6):  # Limit is 5/minute
            response = client.post(
                "/ingest/profile",
                json=profile_data,
                headers=headers
            )
            
            if i < 5:
                assert response.status_code == 200
            else:
                assert response.status_code == 429  # Too Many Requests
```

## 15. Local Development Workflow

### 15.1 Initial Setup
```bash
# 1. Clone and setup project
git clone <your-repo>
cd jobagent

# 2. Create and configure environment
cp .env.sample .env
# Edit .env file with your actual API keys and configurations

# 3. Install local development tools
pip install -r requirements-dev.txt

# 4. Build and start all services
docker-compose up --build -d

# 5. Wait for services to be ready
docker-compose logs -f api

# 6. Create initial database migration
docker-compose exec api alembic revision --autogenerate -m "Initial schema"

# 7. Access MinIO console and create bucket
# Navigate to http://localhost:9001
# Login with minioadmin/minioadmin
# Create bucket named 'job-agent-documents'
```

### 15.2 Development Commands
```bash
# View all service logs
docker-compose logs -f

# Run tests
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit

# Run specific test categories
docker-compose exec api pytest tests/unit/ -v
docker-compose exec api pytest tests/e2e/ -v -m e2e

# Check service health
curl http://localhost:8000/health

# Test API endpoints
curl -X POST http://localhost:8000/ingest/profile \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -d '{
    "headline": "Senior Software Engineer | Python & Cloud",
    "summary": "Experienced engineer specializing in building scalable backend systems.",
    "preferences": {
      "first_name": "John",
      "last_name": "Doe",
      "email": "john.doe@example.com",
      "phone": "+1234567890"
    }
  }'

# Monitor Celery tasks
docker-compose exec worker celery -A app.tasks.celery_app inspect active
docker-compose exec worker celery -A app.tasks.celery_app inspect stats

# Access database
docker-compose exec db psql -U jobagent_user -d jobagent

# View MinIO files
# Navigate to http://localhost:9001 for web interface
```

### 15.3 Database Management
```bash
# Create new migration
docker-compose exec api alembic revision --autogenerate -m "Add new table"

# Apply migrations
docker-compose exec api alembic upgrade head

# Rollback migration
docker-compose exec api alembic downgrade -1

# View migration history
docker-compose exec api alembic history
```

## 16. Production Deployment Guide

### 16.1 Fly.io Deployment (Simplified Single-App Approach)
```bash
# 1. Install Fly CLI and login
fly auth login

# 2. Launch app (don't deploy yet)
fly launch --no-deploy

# 3. Provision services
fly postgres create --name jobagent-db
fly redis create --name jobagent-redis

# 4. Create volume for file storage (if not using external S3)
fly volumes create jobagent_data --size 10

# 5. Attach services
fly postgres attach --postgres-app jobagent-db
fly redis attach jobagent-redis

# 6. Set environment secrets
fly secrets set PROFILE_INGEST_API_KEY=your_secure_api_key_here
fly secrets set ENCRYPTION_KEY=your_32_character_encryption_key
fly secrets set OPENAI_API_KEY=sk-your_openai_key_here
fly secrets set TWILIO_ACCOUNT_SID=ACxxxx
fly secrets set TWILIO_AUTH_TOKEN=your_twilio_token
fly secrets set WA_FROM=whatsapp:+14155238886
fly secrets set WA_TO=whatsapp:+1your_number

# 7. Deploy
fly deploy
```

### 16.2 Production fly.toml
```toml
app = "jobagent"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[env]
  LOG_LEVEL = "INFO"
  S3_BUCKET_NAME = "jobagent-documents"

[[mounts]]
  source = "jobagent_data"
  destination = "/data"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 1

[http_service.checks.health]
  type = "http"
  path = "/health"
  interval = "10s"
  timeout = "5s"
  grace_period = "30s"

[processes]
  api = "./entrypoint.sh uvicorn app.api_server:app --host 0.0.0.0 --port 8000"
  worker = "./entrypoint.sh celery -A app.tasks.celery_app worker --loglevel=info --concurrency=1"
  beat = "./entrypoint.sh celery -A app.tasks.celery_app beat --loglevel=info"

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 1024
  processes = ["api"]

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 512
  processes = ["worker", "beat"]
```

### 16.3 Production Environment Variables
```bash
# Set production environment variables
fly secrets set DATABASE_URL="postgresql://user:pass@host:5432/db"
fly secrets set REDIS_URL="redis://host:6379/0"
fly secrets set S3_ENDPOINT_URL="https://s3.amazonaws.com"
fly secrets set AWS_ACCESS_KEY_ID="your_aws_key"
fly secrets set AWS_SECRET_ACCESS_KEY="your_aws_secret"
```

### 16.4 Scaling Commands
```bash
# Scale API instances
fly scale count api=2

# Scale worker instances
fly scale count worker=2

# Scale beat (should only be 1)
fly scale count beat=1

# Check app status
fly status
fly logs
```

## 17. Monitoring & Maintenance

### 17.1 Health Monitoring
- The `/health` endpoint provides comprehensive service status
- Set up external monitoring to hit this endpoint regularly
- Configure alerts for when health checks fail

### 17.2 Log Monitoring
```bash
# View application logs
fly logs --app jobagent

#.1 Complete Project Tree
```
jobagent/
├── alembic/
│   ├── versions/
│   └── env.py
├── app/
│   ├── __init__.py
│   ├── models.py
│   ├── db.py
│   ├── security.py
│   ├── storage.py
│   ├── pdf_utils.py
│   ├── automation.py
│   ├── notifications.py
│   ├── api_server.py
│   ├── tasks.py
│   └── tools.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_tools.py
│   │   ├── test_models.py
│   │   └── test_security.py
│   └── e2e/
│       ├── __init__.py
│       └── test_api.py
├── Dockerfile
├── docker-compose.yml
├── docker-compose.test.yml
├── entrypoint.sh
├── alembic.ini
├── requirements.txt
├── requirements-dev.txt
├── .env.sample
├── .dockerignore
├── .gitignore
└── README.md
```

### 13.2 requirements.txt
```
# Core Framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic[email]==2.4.2

# Database
sqlmodel==0.0.14
alembic==1.12.1
psycopg2-binary==2.9.9

# Task Queue
celery[redis]==5.3.4
redis==5.0.1

# AI/LLM
pydantic-ai==0.0.12
openai==1.3.6

# Browser Automation
playwright==1.40.0

# Document Generation
weasyprint==60.2
markdown==3.5.1

# Object Storage
boto3==1.34.0

# Communications
twilio==8.10.0

# Security
cryptography==41.0.8

# API Enhancements
slowapi==0.1.9

# Environment
python-dotenv==1.0.0

# Logging
structlog==23.2.0
```

### 13.3 requirements-dev.txt
```
# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-mock==3.12.0
httpx==0.25.2
factory-boy==3.3.0

# Code Quality
black==23.11.0
isort==5.12.0
flake8==6.1.0
ruff==0.11.8

# Development Tools
ipython==8.17.2
```

### 13.4 Enhanced Dockerfile
```dockerfile
# Multi-stage build for optimized production image
FROM python:3.12-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency management
RUN pip install uv

WORKDIR /code

# Builder stage
FROM base AS builder

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps

# Copy application code
COPY . .

# Final stage
FROM base AS final

# Copy installed packages and application from builder
COPY --from=builder /usr/local/ /usr/local/
COPY --from=builder /root/.cache/ms-playwright/ /root/.cache/ms-playwright/
COPY --from=builder /code /code

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash jobagent
RUN chown -R jobagent:jobagent /code
USER jobagent

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.api_server:app", "--host", "0.0.0.0", "--port", "8000"]
```