# tests/unit/test_tools.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from sqlmodel import select  # Added for SQLModel queries
from app.tools import (
    generate_unique_hash,
    get_user_preference,
    save_user_preference,
    rank_role,  # Added for TestAsyncTools
    draft_and_upload_documents,  # Added for TestAsyncTools
)
from app.models import (
    Profile,
    UserPreference,
    Role,
    Application,
    RankResult,
    ResumeDraft,
    RoleStatus,
    ApplicationStatus,
    Company,
)  # Added missing imports
from app.db import (
    get_session_context,
)  # For direct db interactions if needed outside fixtures


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
        # Create a preference using the fixture data or directly
        from datetime import datetime
        pref = UserPreference(
            profile_id=sample_profile.id, 
            key="salary_expectation", 
            value="120000",
            last_updated=datetime.utcnow()
        )
        session.add(pref)
        session.commit()

        # Test retrieval using the function from app.tools
        # Mock the session context to use our test session
        with patch("app.tools.get_session_context") as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None
            
            value = get_user_preference(
                profile_id=sample_profile.id, key="salary_expectation"
            )
            assert value == "120000"

    def test_get_user_preference_not_exists(self, session, sample_profile):
        """Test retrieving a non-existent user preference."""
        with patch("app.tools.get_session_context") as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None
            
            value = get_user_preference(
                profile_id=sample_profile.id, key="non_existent_key"
            )
            assert value is None

    def test_save_user_preference_new(self, session, sample_profile):
        """Test saving a new user preference."""
        with patch("app.tools.get_session_context") as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None
            
            save_user_preference(
                profile_id=sample_profile.id, key="test_key", value="test_value"
            )

            # Verify it was saved
            pref = session.exec(
                select(UserPreference)
                .where(UserPreference.profile_id == sample_profile.id)
                .where(UserPreference.key == "test_key")
            ).first()
            assert pref is not None
            assert pref.value == "test_value"

    def test_save_user_preference_update(self, session, sample_profile):
        """Test updating an existing user preference."""
        with patch("app.tools.get_session_context") as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None
            
            # Create initial preference
            save_user_preference(sample_profile.id, "test_key", "initial_value")

            # Update it
            save_user_preference(sample_profile.id, "test_key", "updated_value")

            # Verify it was updated
            pref = session.exec(
                select(UserPreference)
                .where(UserPreference.profile_id == sample_profile.id)
                .where(UserPreference.key == "test_key")
            ).first()
            assert pref is not None
            assert pref.value == "updated_value"


class TestAsyncTools:
    @pytest.mark.asyncio
    async def test_rank_role_success(
        self,
        session,
        sample_role: Role,
        sample_profile: Profile,
        sample_company: Company,
    ):
        """Test successful role ranking."""
        # Ensure the sample_role has its company relationship loaded for the tool to access company.name
        # The fixture should handle this, but if not, refresh/load it.
        session.refresh(sample_role)
        if not sample_role.company:  # Ensure company is linked if tool relies on it
            sample_role.company = sample_company
            session.add(sample_role)
            session.commit()
            session.refresh(sample_role)

        with patch("app.tools.ranking_agent") as mock_agent, \
             patch("app.tools.get_session_context") as mock_get_session:
            
            # Mock the session context to return our test session
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None
            
            # Mock the LLM response
            mock_llm_run_result = Mock()  # This is the object returned by agent.run()
            # The actual data is in mock_llm_run_result.data
            mock_rank_result_data = RankResult(
                score=0.85, rationale="Strong technical match"
            )
            mock_llm_run_result.data = mock_rank_result_data
            mock_agent.run = AsyncMock(return_value=mock_llm_run_result)

            # Test the function
            result_data = await rank_role(sample_role.id, sample_profile.id)

            assert result_data.score == 0.85
            assert result_data.rationale == "Strong technical match"

            # Verify database was updated
            session.refresh(sample_role)  # Refresh to get updated values
            assert sample_role.rank_score == 0.85
            assert sample_role.rank_rationale == "Strong technical match"
            assert sample_role.status == RoleStatus.RANKED

    @pytest.mark.asyncio
    async def test_rank_role_llm_failure(
        self,
        session,
        sample_role: Role,
        sample_profile: Profile,
        sample_company: Company,
    ):
        """Test role ranking when LLM call fails."""
        session.refresh(sample_role)
        if not sample_role.company:  # Ensure company is linked
            sample_role.company = sample_company
            session.add(sample_role)
            session.commit()
            session.refresh(sample_role)

        with patch("app.tools.ranking_agent") as mock_agent, \
             patch("app.tools.get_session_context") as mock_get_session:
            
            # Mock the session context to return our test session
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None
            
            mock_agent.run = AsyncMock(side_effect=Exception("LLM service unavailable"))

            result = await rank_role(sample_role.id, sample_profile.id)

            assert result.score == 0.0
            assert "LLM call failed: LLM service unavailable" in result.rationale
            # Check that status is not changed to RANKED
            session.refresh(sample_role)
            assert (
                sample_role.status == RoleStatus.SOURCED
            )  # Assuming default is SOURCED

    @pytest.mark.asyncio
    async def test_draft_and_upload_documents_success(
        self,
        session,
        sample_profile: Profile,
        sample_role: Role,
        sample_company: Company,
    ):
        """Test successful document generation and upload."""
        # Create an application using model_validate to avoid default_factory issues
        application_data = {
            "role_id": sample_role.id,
            "profile_id": sample_profile.id,
            "status": ApplicationStatus.DRAFT,
        }
        application = Application.model_validate(application_data)
        session.add(application)
        session.commit()
        session.refresh(application)

        # Ensure relations are loaded for the tool
        session.refresh(sample_role)
        if not sample_role.company:
            sample_role.company = sample_company
            session.add(sample_role)
            session.commit()
            session.refresh(sample_role)
        application.role = sample_role
        application.profile = sample_profile

        with (
            patch("app.tools.resume_agent") as mock_resume_agent,
            patch("app.tools.upload_file_to_storage") as mock_upload,
            patch(
                "app.tools.render_to_pdf", return_value=b"pdf_bytes"
            ) as mock_render_to_pdf,
            patch("app.tools.get_session_context") as mock_get_session,
        ):
            # Mock the session context to return our test session
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None
            
            # Mock LLM response for resume agent
            mock_llm_resume_result = Mock()
            mock_resume_draft_data = ResumeDraft(
                resume_md="# Resume Content",
                cover_letter_md="# Cover Letter Content",
                identified_skills=["Python", "FastAPI"],
            )
            mock_llm_resume_result.data = mock_resume_draft_data
            mock_resume_agent.run = AsyncMock(return_value=mock_llm_resume_result)

            # Mock file upload
            mock_upload.side_effect = [
                "http://storage/resume.pdf",
                "http://storage/cover_letter.pdf",
            ]

            result = await draft_and_upload_documents(application.id)

            assert result["status"] == "success"
            assert result["resume_url"] == "http://storage/resume.pdf"
            assert result["cover_letter_url"] == "http://storage/cover_letter.pdf"
            assert result["identified_skills"] == ["Python", "FastAPI"]

            # Verify calls
            mock_render_to_pdf.assert_any_call("# Resume Content")
            mock_render_to_pdf.assert_any_call("# Cover Letter Content")
            assert mock_upload.call_count == 2

            # Verify database was updated
            session.refresh(application)
            assert application.resume_s3_url == "http://storage/resume.pdf"
            assert application.cover_letter_s3_url == "http://storage/cover_letter.pdf"
            assert application.status == ApplicationStatus.READY_TO_SUBMIT
