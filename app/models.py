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