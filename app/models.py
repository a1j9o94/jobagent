# app/models.py
from enum import Enum
from datetime import datetime, UTC
from typing import List, Optional, Dict, Any
from sqlmodel import SQLModel, Field, Relationship, Column, Text
from pydantic import BaseModel
import sqlalchemy as sa


def utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(UTC)


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
    score: float = Field(
        ...,
        description="A score from 0.0 to 1.0 on how well the profile fits the role.",
    )
    rationale: str = Field(..., description="A brief explanation for the score.")


class ResumeDraft(BaseModel):
    resume_md: str
    cover_letter_md: str
    identified_skills: List[str]


class RoleDetails(BaseModel):
    """Details of a job role extracted from a job posting."""
    title: str = Field(..., description="The title of the job role.")
    company_name: str = Field(..., description="The name of the company hiring for the role.")
    description: Optional[str] = Field(None, description="A detailed description of the job role and responsibilities.")
    location: Optional[str] = Field(None, description="The location of the job (e.g., 'San Francisco, CA', 'Remote').")
    requirements: Optional[str] = Field(None, description="The skills, qualifications, and experience required for the role.")
    salary_range: Optional[str] = Field(None, description="The salary range for the role (e.g., '$150,000 - $200,000').")
    skills: List[str] = Field(default_factory=list, description="A list of key skills and technologies required for this role (e.g., ['Python', 'SQL', 'Machine Learning', 'AWS']).")


# --- SQLModel Tables ---
class Skill(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)


class RoleSkillLink(SQLModel, table=True):
    role_id: Optional[int] = Field(
        default=None, foreign_key="role.id", primary_key=True
    )
    skill_id: Optional[int] = Field(
        default=None, foreign_key="skill.id", primary_key=True
    )


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
    created_at: datetime = Field(default_factory=utc_now)
    location: Optional[str] = Field(default=None)
    requirements: Optional[str] = Field(default=None, sa_column=Column(Text))
    salary_range: Optional[str] = Field(default=None)

    company: Company = Relationship(back_populates="roles")
    skills: List[Skill] = Relationship(link_model=RoleSkillLink)
    applications: List["Application"] = Relationship(back_populates="role")


class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    role_id: int = Field(foreign_key="role.id")
    profile_id: int = Field(foreign_key="profile.id")
    celery_task_id: Optional[str] = Field(default=None, index=True)
    queue_task_id: Optional[str] = Field(default=None, index=True)
    status: ApplicationStatus = ApplicationStatus.DRAFT
    resume_s3_url: Optional[str] = None
    cover_letter_s3_url: Optional[str] = None
    custom_answers: Optional[Dict[str, Any]] = Field(
        default_factory=dict, sa_column=Column(sa.JSON)
    )
    approval_context: Optional[Dict[str, Any]] = Field(
        default_factory=dict, sa_column=Column(sa.JSON)
    )
    screenshot_url: Optional[str] = None
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    submitted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)

    role: Role = Relationship(back_populates="applications")
    profile: "Profile" = Relationship(back_populates="applications")


#TODO: Change preferences to "Memory" In practice I'm using it as a key-value store for everything like linkedin url, phone number, etc.
class UserPreference(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id")
    key: str = Field(index=True)
    value: str
    last_updated: datetime = Field(default_factory=utc_now)

    profile: "Profile" = Relationship(back_populates="preferences")


class Profile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    headline: str
    summary: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    credentials: List[Credential] = Relationship()
    preferences: List[UserPreference] = Relationship(back_populates="profile")
    applications: List[Application] = Relationship(back_populates="profile")
