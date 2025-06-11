# tests/unit/test_models.py
import pytest
from datetime import datetime, UTC
from sqlmodel import select

from app.models import (
    Profile,
    Company,
    Role,
    Application,
    UserPreference,
    ApplicationStatus,
    RoleStatus,
    RoleCategory,
    Seniority,
    WorkMode,
)


class TestApplicationModel:
    """Test the Application model behavior."""

    def test_application_creation_with_defaults(self, session, sample_role, sample_profile):
        """Test creating an Application with default values."""
        application_data = {
            "role_id": sample_role.id,
            "profile_id": sample_profile.id,
        }
        application = Application.model_validate(application_data)
        
        # Verify defaults before saving
        assert application.status == ApplicationStatus.DRAFT
        assert application.custom_answers == {}
        assert application.approval_context == {}  # New field
        assert application.resume_s3_url is None
        assert application.cover_letter_s3_url is None
        assert application.submitted_at is None
        assert application.celery_task_id is None
        assert application.queue_task_id is None  # New field
        assert application.screenshot_url is None  # New field
        assert application.error_message is None  # New field
        assert application.notes is None  # New field
        
        session.add(application)
        session.commit()
        session.refresh(application)
        
        # Verify created_at was set
        assert application.created_at is not None
        assert isinstance(application.created_at, datetime)

    def test_application_relationships(self, session, sample_role, sample_profile):
        """Test Application relationships with Role and Profile."""
        application_data = {
            "role_id": sample_role.id,
            "profile_id": sample_profile.id,
            "celery_task_id": "test_task_123",
        }
        application = Application.model_validate(application_data)
        
        session.add(application)
        session.commit()
        session.refresh(application)
        
        # Test relationships
        assert application.role.id == sample_role.id
        assert application.role.title == sample_role.title
        assert application.profile.id == sample_profile.id
        assert application.profile.headline == sample_profile.headline

    def test_application_status_updates(self, session, sample_application):
        """Test updating Application status."""
        # Start with DRAFT status
        assert sample_application.status == ApplicationStatus.DRAFT
        
        # Update to READY_TO_SUBMIT
        sample_application.status = ApplicationStatus.READY_TO_SUBMIT
        session.commit()
        session.refresh(sample_application)
        
        assert sample_application.status == ApplicationStatus.READY_TO_SUBMIT
        
        # Update to SUBMITTED with timestamp
        sample_application.status = ApplicationStatus.SUBMITTED
        sample_application.submitted_at = datetime.now(UTC)
        session.commit()
        session.refresh(sample_application)
        
        assert sample_application.status == ApplicationStatus.SUBMITTED
        assert sample_application.submitted_at is not None

    def test_application_custom_answers(self, session, sample_application):
        """Test custom_answers JSON field functionality."""
        custom_data = {
            "cover_letter_question": "Why do you want to work here?",
            "years_experience": "5",
            "willing_to_relocate": True,
            "salary_expectation": 150000,
        }
        
        sample_application.custom_answers = custom_data
        session.commit()
        session.refresh(sample_application)
        
        assert sample_application.custom_answers == custom_data
        assert sample_application.custom_answers["willing_to_relocate"] is True
        assert sample_application.custom_answers["salary_expectation"] == 150000

    def test_application_queue_fields(self, session, sample_application):
        """Test the new queue-related fields."""
        # Test queue_task_id
        sample_application.queue_task_id = "job_application_1234_abc123"
        session.commit()
        session.refresh(sample_application)
        assert sample_application.queue_task_id == "job_application_1234_abc123"

        # Test screenshot_url
        sample_application.screenshot_url = "https://example.com/screenshot.png"
        session.commit()
        session.refresh(sample_application)
        assert sample_application.screenshot_url == "https://example.com/screenshot.png"

        # Test error_message
        sample_application.error_message = "Failed to submit application due to network timeout"
        session.commit()
        session.refresh(sample_application)
        assert sample_application.error_message == "Failed to submit application due to network timeout"

        # Test notes
        sample_application.notes = "Application submitted successfully to ATS system"
        session.commit()
        session.refresh(sample_application)
        assert sample_application.notes == "Application submitted successfully to ATS system"

    def test_application_approval_context(self, session, sample_application):
        """Test approval_context JSON field functionality."""
        approval_data = {
            "question": "What is your salary expectation?",
            "current_state": '{"page": "salary_form", "step": 2}',
            "screenshot_url": "https://example.com/approval_screenshot.png",
            "context": {
                "page_title": "Salary Information Form",
                "page_url": "https://company.com/apply/step2",
                "form_fields": ["salary_expectation", "start_date"]
            },
            "requested_at": "2024-01-01T12:00:00Z"
        }
        
        sample_application.approval_context = approval_data
        session.commit()
        session.refresh(sample_application)
        
        assert sample_application.approval_context == approval_data
        assert sample_application.approval_context["question"] == "What is your salary expectation?"
        assert sample_application.approval_context["context"]["page_title"] == "Salary Information Form"
        assert len(sample_application.approval_context["context"]["form_fields"]) == 2


class TestRoleModel:
    """Test the Role model behavior."""

    def test_role_creation_with_company(self, session, sample_company):
        """Test creating a Role with a Company relationship."""
        role_data = {
            "title": "Senior Python Developer",
            "description": "Build awesome Python applications",
            "posting_url": "https://example.com/job/123",
            "unique_hash": "test_unique_hash_123",
            "company_id": sample_company.id,
            "location": "San Francisco, CA",
            "requirements": "5+ years Python experience",
            "salary_range": "$150,000 - $200,000",
        }
        role = Role.model_validate(role_data)
        
        session.add(role)
        session.commit()
        session.refresh(role)
        
        # Test defaults
        assert role.status == RoleStatus.SOURCED
        assert role.rank_score is None
        assert role.rank_rationale is None
        assert role.created_at is not None
        
        # Test relationship
        assert role.company.id == sample_company.id
        assert role.company.name == sample_company.name

    def test_role_ranking_updates(self, session, sample_role):
        """Test updating Role with ranking information."""
        assert sample_role.status == RoleStatus.SOURCED
        assert sample_role.rank_score is None
        
        # Update with ranking
        sample_role.rank_score = 0.85
        sample_role.rank_rationale = "Strong technical match"
        sample_role.status = RoleStatus.RANKED
        
        session.commit()
        session.refresh(sample_role)
        
        assert sample_role.rank_score == 0.85
        assert sample_role.rank_rationale == "Strong technical match"
        assert sample_role.status == RoleStatus.RANKED


class TestProfileModel:
    """Test the Profile model behavior."""

    def test_profile_with_preferences(self, session, sample_profile):
        """Test Profile with UserPreference relationships."""
        # Add some preferences
        preferences_data = [
            {
                "profile_id": sample_profile.id,
                "key": "first_name",
                "value": "John",
            },
            {
                "profile_id": sample_profile.id,
                "key": "email",
                "value": "john@example.com",
            },
            {
                "profile_id": sample_profile.id,
                "key": "salary_expectation",
                "value": "150000",
            },
        ]
        preferences = [UserPreference.model_validate(pref_data) for pref_data in preferences_data]
        
        for pref in preferences:
            session.add(pref)
        session.commit()
        
        # Refresh to load relationships
        session.refresh(sample_profile)
        
        # Test relationships
        profile_preferences = sample_profile.preferences
        assert len(profile_preferences) == 3
        
        # Check specific preferences
        pref_dict = {pref.key: pref.value for pref in profile_preferences}
        assert pref_dict["first_name"] == "John"
        assert pref_dict["email"] == "john@example.com"
        assert pref_dict["salary_expectation"] == "150000"

    def test_profile_with_applications(self, session, sample_profile, sample_role):
        """Test Profile with Application relationships."""
        # Create applications
        app1_data = {"role_id": sample_role.id, "profile_id": sample_profile.id}
        app1 = Application.model_validate(app1_data)
        
        app2_data = {
            "role_id": sample_role.id,
            "profile_id": sample_profile.id,
            "status": ApplicationStatus.SUBMITTED,
        }
        app2 = Application.model_validate(app2_data)
        
        session.add_all([app1, app2])
        session.commit()
        session.refresh(sample_profile)
        
        # Test relationships
        assert len(sample_profile.applications) == 2
        statuses = [app.status for app in sample_profile.applications]
        assert ApplicationStatus.DRAFT in statuses
        assert ApplicationStatus.SUBMITTED in statuses


class TestEnums:
    """Test enum values and behavior."""

    def test_application_status_enum(self):
        """Test ApplicationStatus enum values."""
        assert ApplicationStatus.DRAFT == "draft"
        assert ApplicationStatus.NEEDS_USER_INFO == "needs_user_info"
        assert ApplicationStatus.READY_TO_SUBMIT == "ready_to_submit"
        assert ApplicationStatus.SUBMITTING == "submitting"
        assert ApplicationStatus.SUBMITTED == "submitted"
        assert ApplicationStatus.ERROR == "error"

    def test_role_status_enum(self):
        """Test RoleStatus enum values."""
        assert RoleStatus.SOURCED == "sourced"
        assert RoleStatus.RANKED == "ranked"
        assert RoleStatus.APPLYING == "applying"
        assert RoleStatus.APPLIED == "applied"
        assert RoleStatus.IGNORED == "ignored"

    def test_role_category_enum(self):
        """Test RoleCategory enum values."""
        assert RoleCategory.SALES == "sales"
        assert RoleCategory.OPERATIONS == "operations"
        assert RoleCategory.ENGINEERING == "engineering"
        assert RoleCategory.PRODUCT == "product"
        assert RoleCategory.FINANCE == "finance"
        assert RoleCategory.OTHER == "other"


class TestModelValidation:
    """Test model validation and constraints."""

    def test_role_unique_hash_constraint(self, session, sample_company):
        """Test that Role unique_hash constraint works."""
        role1_data = {
            "title": "Developer",
            "description": "First role",
            "posting_url": "https://example.com/job1",
            "unique_hash": "duplicate_hash",
            "company_id": sample_company.id,
        }
        role1 = Role.model_validate(role1_data)
        
        role2_data = {
            "title": "Developer",
            "description": "Second role",
            "posting_url": "https://example.com/job2",
            "unique_hash": "duplicate_hash",  # Same hash
            "company_id": sample_company.id,
        }
        role2 = Role.model_validate(role2_data)
        
        session.add(role1)
        session.commit()
        
        # Adding second role with same hash should fail
        session.add(role2)
        with pytest.raises(Exception):  # IntegrityError or similar
            session.commit()

    def test_application_foreign_key_constraints(self, session):
        """Test that Application requires valid role_id and profile_id."""
        # Try to create application with non-existent role_id
        app_data = {"role_id": 99999, "profile_id": 1}
        app = Application.model_validate(app_data)
        session.add(app)
        
        with pytest.raises(Exception):  # Foreign key constraint error
            session.commit()
