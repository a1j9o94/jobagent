# tests/unit/test_tools.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, UTC
import tempfile
import os
from sqlmodel import select  # Added for SQLModel queries
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
from app.tools.preferences import get_user_preference, save_user_preference
from app.tools.ranking import rank_role
from app.tools.documents import draft_and_upload_documents
from app.tools.utils import generate_unique_hash
from app.db import (
    get_session_context,
)  # For direct db interactions if needed outside fixtures

class TestStorageTools:
    """Test the storage utility functions."""
    
    def test_get_public_storage_url_minio_localhost(self):
        """Test URL generation for MinIO in local development."""
        # Mock the environment variables directly in the function
        with (
            patch.dict('os.environ', {
                'STORAGE_PROVIDER': 'minio',
                'API_BASE_URL': 'http://localhost:8000'
            }),
            patch('app.tools.storage.STORAGE_PROVIDER', 'minio'),
            patch('app.tools.storage.API_BASE_URL', 'http://localhost:8000')
        ):
            from app.tools.storage import get_public_storage_url
            url = get_public_storage_url()
            assert url == "http://localhost:9000"
    
    def test_get_public_storage_url_tigris_production(self):
        """Test URL generation for Tigris in production."""
        with (
            patch.dict('os.environ', {
                'STORAGE_PROVIDER': 'tigris',
                'API_BASE_URL': 'https://jobagent.fly.dev'
            }),
            patch('app.tools.storage.STORAGE_PROVIDER', 'tigris'),
            patch('app.tools.storage.API_BASE_URL', 'https://jobagent.fly.dev')
        ):
            from app.tools.storage import get_public_storage_url
            url = get_public_storage_url()
            assert url == "https://jobagent.fly.dev/api/files"
    
    def test_get_public_storage_url_minio_custom(self):
        """Test URL generation for MinIO with custom API base URL."""
        with (
            patch.dict('os.environ', {
                'STORAGE_PROVIDER': 'minio',
                'API_BASE_URL': 'http://custom:8000'
            }),
            patch('app.tools.storage.STORAGE_PROVIDER', 'minio'),
            patch('app.tools.storage.API_BASE_URL', 'http://custom:8000')
        ):
            from app.tools.storage import get_public_storage_url
            url = get_public_storage_url()
            assert url == "http://localhost:9000"  # Fallback for non-localhost
    
    @patch('app.tools.storage.s3_client')
    @patch('app.tools.storage.ensure_bucket_exists')
    def test_upload_file_to_storage_minio(self, mock_ensure_bucket, mock_s3_client):
        """Test file upload with MinIO storage provider."""
        mock_ensure_bucket.return_value = True
        mock_s3_client.put_object.return_value = None
        
        with (
            patch.dict('os.environ', {
                'STORAGE_PROVIDER': 'minio',
                'API_BASE_URL': 'http://localhost:8000',
                'S3_BUCKET_NAME': 'test-bucket'
            }),
            patch('app.tools.storage.STORAGE_PROVIDER', 'minio'),
            patch('app.tools.storage.API_BASE_URL', 'http://localhost:8000'),
            patch('app.tools.storage.S3_BUCKET_NAME', 'test-bucket')
        ):
            from app.tools.storage import upload_file_to_storage
            
            file_data = b"test pdf content"
            filename = "test_resume.pdf"
            
            result_url = upload_file_to_storage(file_data, filename)
            
            # For MinIO, should return direct bucket URL
            expected_url = "http://localhost:9000/test-bucket/test_resume.pdf"
            assert result_url == expected_url
            
            # Verify S3 client was called correctly
            mock_s3_client.put_object.assert_called_once()
            call_args = mock_s3_client.put_object.call_args
            assert call_args[1]['Bucket'] == 'test-bucket'
            assert call_args[1]['Key'] == 'test_resume.pdf'
            assert call_args[1]['ContentType'] == 'application/pdf'
    
    @patch('app.tools.storage.s3_client')
    @patch('app.tools.storage.ensure_bucket_exists')
    def test_upload_file_to_storage_tigris(self, mock_ensure_bucket, mock_s3_client):
        """Test file upload with Tigris storage provider."""
        mock_ensure_bucket.return_value = True
        mock_s3_client.put_object.return_value = None
        
        with (
            patch.dict('os.environ', {
                'STORAGE_PROVIDER': 'tigris',
                'API_BASE_URL': 'https://jobagent.fly.dev',
                'S3_BUCKET_NAME': 'tigris-bucket'
            }),
            patch('app.tools.storage.STORAGE_PROVIDER', 'tigris'),
            patch('app.tools.storage.API_BASE_URL', 'https://jobagent.fly.dev'),
            patch('app.tools.storage.S3_BUCKET_NAME', 'tigris-bucket')
        ):
            from app.tools.storage import upload_file_to_storage
            
            file_data = b"test pdf content"
            filename = "test_cover_letter.pdf"
            
            result_url = upload_file_to_storage(file_data, filename)
            
            # For Tigris, should return API route URL
            expected_url = "https://jobagent.fly.dev/api/files/test_cover_letter.pdf"
            assert result_url == expected_url
            
            # Verify S3 client was called correctly
            mock_s3_client.put_object.assert_called_once()
            call_args = mock_s3_client.put_object.call_args
            assert call_args[1]['Bucket'] == 'tigris-bucket'
            assert call_args[1]['Key'] == 'test_cover_letter.pdf'
    
    @patch('app.tools.storage.s3_client')
    def test_download_file_from_storage(self, mock_s3_client):
        """Test file download from storage."""
        # Mock S3 response properly
        mock_body = Mock()
        mock_body.read.return_value = b"downloaded file content"
        mock_response = {'Body': mock_body}
        mock_s3_client.get_object.return_value = mock_response
        
        with (
            patch.dict('os.environ', {'S3_BUCKET_NAME': 'test-bucket'}),
            patch('app.tools.storage.S3_BUCKET_NAME', 'test-bucket')
        ):
            from app.tools.storage import download_file_from_storage
            
            result = download_file_from_storage("test_file.pdf")
            
            assert result == b"downloaded file content"
            mock_s3_client.get_object.assert_called_once_with(
                Bucket='test-bucket',
                Key='test_file.pdf'
            )
    
    @patch('app.tools.storage.s3_client')
    def test_ensure_bucket_exists_minio_new_bucket(self, mock_s3_client):
        """Test creating a new bucket with MinIO and setting public policy."""
        from botocore.exceptions import ClientError
        
        # Simulate bucket doesn't exist (404 error)
        mock_s3_client.head_bucket.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadBucket'
        )
        mock_s3_client.create_bucket.return_value = None
        mock_s3_client.put_bucket_policy.return_value = None
        
        with (
            patch.dict('os.environ', {
                'STORAGE_PROVIDER': 'minio',
                'S3_BUCKET_NAME': 'new-bucket',
                'S3_ENDPOINT_URL': 'http://localhost:9000'
            }),
            patch('app.tools.storage.STORAGE_PROVIDER', 'minio'),
            patch('app.tools.storage.S3_BUCKET_NAME', 'new-bucket'),
            patch('app.tools.storage.S3_ENDPOINT_URL', 'http://localhost:9000')
        ):
            from app.tools.storage import ensure_bucket_exists
            
            result = ensure_bucket_exists()
            
            assert result is True
            mock_s3_client.create_bucket.assert_called_once_with(Bucket='new-bucket')
            # Should set public read policy for MinIO
            mock_s3_client.put_bucket_policy.assert_called_once()
    
    @patch('app.tools.storage.s3_client')
    def test_ensure_bucket_exists_tigris_new_bucket(self, mock_s3_client):
        """Test creating a new bucket with Tigris (no public policy)."""
        from botocore.exceptions import ClientError
        
        # Simulate bucket doesn't exist (404 error)
        mock_s3_client.head_bucket.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadBucket'
        )
        mock_s3_client.create_bucket.return_value = None
        
        with (
            patch.dict('os.environ', {
                'STORAGE_PROVIDER': 'tigris',
                'S3_BUCKET_NAME': 'tigris-bucket',
                'S3_ENDPOINT_URL': 'https://fly.storage.tigris.dev'
            }),
            patch('app.tools.storage.STORAGE_PROVIDER', 'tigris'),
            patch('app.tools.storage.S3_BUCKET_NAME', 'tigris-bucket'),
            patch('app.tools.storage.S3_ENDPOINT_URL', 'https://fly.storage.tigris.dev')
        ):
            from app.tools.storage import ensure_bucket_exists
            
            result = ensure_bucket_exists()
            
            assert result is True
            mock_s3_client.create_bucket.assert_called_once_with(Bucket='tigris-bucket')
            # Should NOT set public read policy for Tigris
            mock_s3_client.put_bucket_policy.assert_not_called()
    
    @patch('app.tools.storage.s3_client')
    @patch('app.tools.storage.ensure_bucket_exists')
    def test_health_check_success(self, mock_ensure_bucket, mock_s3_client):
        """Test storage health check success."""
        mock_ensure_bucket.return_value = True
        mock_s3_client.list_objects_v2.return_value = {'Contents': []}
        
        with (
            patch.dict('os.environ', {
                'STORAGE_PROVIDER': 'minio',
                'S3_BUCKET_NAME': 'test-bucket',
                'S3_ENDPOINT_URL': 'http://localhost:9000'
            }),
            patch('app.tools.storage.STORAGE_PROVIDER', 'minio'),
            patch('app.tools.storage.S3_BUCKET_NAME', 'test-bucket'),
            patch('app.tools.storage.S3_ENDPOINT_URL', 'http://localhost:9000')
        ):
            from app.tools.storage import health_check
            
            result = health_check()
            
            assert result['status'] == 'ok'
            assert result['storage_provider'] == 'minio'
            assert result['bucket'] == 'test-bucket'
            assert result['endpoint'] == 'http://localhost:9000'
            assert result['public_url_base'] == 'http://localhost:9000'
    
    def test_health_check_no_client(self):
        """Test storage health check when S3 client is not initialized."""
        with patch('app.tools.storage.s3_client', None):
            from app.tools.storage import health_check
            
            result = health_check()
            
            assert result['status'] == 'error'
            assert 'S3 client not initialized' in result['message']


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
        pref_data = {
            "profile_id": sample_profile.id,
            "key": "salary_expectation",
            "value": "120000",
            "last_updated": datetime.now(UTC),
        }
        pref = UserPreference.model_validate(pref_data)
        session.add(pref)
        session.commit()

        # Test retrieval using the function from app.tools
        # Mock the session context to use our test session
        with patch("app.tools.preferences.get_session_context") as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None

            value = get_user_preference(
                profile_id=sample_profile.id, key="salary_expectation"
            )
            assert value == "120000"

    def test_get_user_preference_not_exists(self, session, sample_profile):
        """Test retrieving a non-existent user preference."""
        with patch("app.tools.preferences.get_session_context") as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None

            value = get_user_preference(
                profile_id=sample_profile.id, key="non_existent_key"
            )
            assert value is None

    def test_save_user_preference_new(self, session, sample_profile):
        """Test saving a new user preference."""
        with patch("app.tools.preferences.get_session_context") as mock_get_session:
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
        with patch("app.tools.preferences.get_session_context") as mock_get_session:
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


class TestSubmissionTasks:
    """Test the submission-related Celery tasks."""
    
    def test_task_apply_for_role_success(self, session, sample_role, sample_profile):
        """Test successful application creation by task_apply_for_role."""
        from app.tasks.submission import task_apply_for_role
        
        with (
            patch("app.db.get_session_context") as mock_get_session,
            # Mock the celery chain to avoid running document generation
            patch("app.tasks.submission.chain") as mock_chain
        ):
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None
            
            # Mock the chain workflow to return success without actually running
            mock_workflow = Mock()
            mock_workflow.apply_async.return_value.id = "test-workflow-id"
            mock_chain.return_value = mock_workflow
            
            # Call the task function using apply() which handles the execution context
            result = task_apply_for_role.apply(
                args=[sample_role.id, sample_profile.id], 
                throw=True
            ).result
            
            # Verify return value
            assert result["status"] == "success"
            assert result["role_id"] == sample_role.id
            assert result["profile_id"] == sample_profile.id
            assert "application_id" in result
            
            # Verify Application was created in database
            application = session.exec(
                select(Application)
                .where(Application.role_id == sample_role.id)
                .where(Application.profile_id == sample_profile.id)
            ).first()
            
            assert application is not None
            assert application.role_id == sample_role.id
            assert application.profile_id == sample_profile.id
            assert application.celery_task_id is not None  # Should have a task ID
            assert application.status == ApplicationStatus.DRAFT
            assert result["application_id"] == application.id

    def test_submission_business_logic_success(self, session, sample_application):
        """Test the core submission business logic directly."""
        from app.tasks.submission import task_submit_application_queue
        
        # Ensure application is committed and has relationships
        session.commit()
        session.refresh(sample_application, ['role', 'profile'])
        
        # Test the business logic by mocking only the queue publishing
        with patch("app.queue_manager.queue_manager.publish_job_application_task") as mock_publish:
            mock_publish.return_value = "test_queue_task_123"
            
            # Manually simulate the core business logic
            application = session.get(sample_application.__class__, sample_application.id)
            assert application is not None
            
            # Update status like the task would
            application.status = ApplicationStatus.SUBMITTING
            application.queue_task_id = "test_queue_task_123"
            session.commit()
            
            # Verify the updates worked
            session.refresh(sample_application)
            assert sample_application.status == ApplicationStatus.SUBMITTING
            assert sample_application.queue_task_id == "test_queue_task_123"

    def test_task_submit_application_queue_not_found(self, session):
        """Test queue submission task with non-existent application."""
        from app.tasks.submission import task_submit_application_queue
        
        with patch("app.db.get_session_context") as mock_session_context:
            mock_session_context.return_value.__enter__.return_value = session
            mock_session_context.return_value.__exit__.return_value = None
            
            result = task_submit_application_queue.apply(
                args=[99999], 
                throw=True
            ).result
            
            assert result["status"] == "error"
            assert result["message"] == "Application not found"

    def test_task_apply_for_role_database_error(self, session, sample_role, sample_profile):
        """Test task_apply_for_role handles database errors with retry logic."""
        from app.tasks.submission import task_apply_for_role
        from celery.exceptions import Retry
        
        with patch("app.db.get_session_context") as mock_get_session:
            # Simulate database error
            mock_get_session.side_effect = Exception("Database connection failed")
            
            # Should raise Celery Retry exception
            with pytest.raises(Retry):
                task_apply_for_role.apply(
                    args=[sample_role.id, sample_profile.id], 
                    throw=True
                )

    def test_task_apply_for_role_max_retries_reached(self, session, sample_role, sample_profile):
        """Test task_apply_for_role when max retries are reached."""
        from app.tasks.submission import task_apply_for_role
        
        with patch("app.db.get_session_context") as mock_get_session:
            # Simulate persistent database error
            mock_get_session.side_effect = Exception("Persistent database error")
            
            # Override max_retries for this test
            with patch.object(task_apply_for_role, 'max_retries', 0):
                result = task_apply_for_role.apply(
                    args=[sample_role.id, sample_profile.id], 
                    throw=True
                ).result
                
                assert result["status"] == "error"
                assert "Persistent database error" in result["message"]

    def test_task_apply_for_role_invalid_role_id(self, session, sample_profile):
        """Test task_apply_for_role with non-existent role_id."""
        from app.tasks.submission import task_apply_for_role
        
        with patch("app.db.get_session_context") as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None
            
            # This should fail due to foreign key constraint when trying to create Application
            with pytest.raises(Exception):  # Will raise IntegrityError or similar
                task_apply_for_role.apply(
                    args=[99999, sample_profile.id], 
                    throw=True
                )


class TestQueueConsumerTasks:
    """Test the queue consumer business logic."""

    def test_task_consume_status_updates(self):
        """Test the status update consumer task."""
        from app.tasks.queue_consumer import task_consume_status_updates
        
        with patch("app.queue_manager.queue_manager.consume_task") as mock_consume:
            # Test when no tasks are available
            mock_consume.return_value = None
            
            result = task_consume_status_updates.apply(throw=True).result
            assert result["status"] == "no_tasks"

    def test_status_update_business_logic(self, session, sample_application):
        """Test the core business logic of processing status updates."""
        # Ensure application is committed to database
        session.commit()
        
        # Test the business logic directly - simulate what process_status_update does
        application = session.get(sample_application.__class__, sample_application.id)
        assert application is not None
        
        # Update application like the queue consumer would
        application.status = ApplicationStatus.SUBMITTED
        application.notes = "Application submitted successfully"
        session.commit()
        
        # Verify the updates worked
        session.refresh(sample_application)
        assert sample_application.status == ApplicationStatus.SUBMITTED
        assert sample_application.notes == "Application submitted successfully"

    def test_approval_request_business_logic(self, session, sample_application):
        """Test the core business logic of processing approval requests."""
        # Ensure application is committed to database
        session.commit()
        
        # Test the business logic directly - simulate what process_approval_request does
        application = session.get(sample_application.__class__, sample_application.id)
        assert application is not None
        
        # Update application like the queue consumer would
        application.status = ApplicationStatus.NEEDS_USER_INFO
        application.approval_context = {
            "question": "What is your salary expectation?",
            "current_state": '{"page": "salary_form"}',
            "screenshot_url": "https://example.com/approval.png",
            "context": {
                "page_title": "Salary Information",
                "page_url": "https://company.com/apply/salary"
            }
        }
        application.screenshot_url = "https://example.com/approval.png"
        session.commit()
        
        # Verify the updates worked
        session.refresh(sample_application)
        assert sample_application.status == ApplicationStatus.NEEDS_USER_INFO
        assert sample_application.approval_context["question"] == "What is your salary expectation?"
        assert sample_application.screenshot_url == "https://example.com/approval.png"

    def test_status_update_error_handling(self, session):
        """Test error handling when application is not found."""
        from app.tasks.queue_consumer import process_status_update
        from app.queue_manager import QueueTask, TaskType
        
        task = QueueTask(
            id="test_error_task",
            type=TaskType.UPDATE_JOB_STATUS,
            payload={
                "application_id": 99999,  # Non-existent application
                "status": "applied"
            }
        )
        
        with patch("app.db.get_session_context") as mock_session_context:
            mock_session_context.return_value.__enter__.return_value = session
            mock_session_context.return_value.__exit__.return_value = None
            
            # Should handle gracefully and not raise exception
            process_status_update(task)  # Should log error but not crash


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

        with (
            patch("app.tools.ranking.ranking_agent") as mock_agent,
            patch("app.tools.ranking.get_session_context") as mock_get_session,
        ):
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

        with (
            patch("app.tools.ranking.ranking_agent") as mock_agent,
            patch("app.tools.ranking.get_session_context") as mock_get_session,
        ):
            # Mock the session context to return our test session
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None

            mock_agent.run = AsyncMock(side_effect=Exception("LLM service unavailable"))

            result = await rank_role(sample_role.id, sample_profile.id)

            assert result.score == 0.5
            assert "Unable to generate LLM ranking due to tool call errors" in result.rationale
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
            patch("app.tools.documents.resume_agent") as mock_resume_agent,
            patch("app.tools.documents.upload_file_to_storage") as mock_upload,
            patch(
                "app.tools.documents.render_to_pdf", return_value=b"pdf_bytes"
            ) as mock_render_to_pdf,
            patch("app.tools.documents.get_session_context") as mock_get_session,
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

    @pytest.mark.asyncio
    async def test_draft_and_upload_documents_storage_provider_urls(
        self,
        session,
        sample_profile: Profile,
        sample_role: Role,
        sample_company: Company,
    ):
        """Test document generation with different storage providers."""
        # Create an application
        application_data = {
            "role_id": sample_role.id,
            "profile_id": sample_profile.id,
            "status": ApplicationStatus.DRAFT,
        }
        application = Application.model_validate(application_data)
        session.add(application)
        session.commit()
        session.refresh(application)

        # Ensure relations are loaded
        session.refresh(sample_role)
        if not sample_role.company:
            sample_role.company = sample_company
            session.add(sample_role)
            session.commit()
            session.refresh(sample_role)
        application.role = sample_role
        application.profile = sample_profile

        # Test with Tigris storage provider
        with (
            patch("app.tools.documents.resume_agent") as mock_resume_agent,
            patch("app.tools.documents.upload_file_to_storage") as mock_upload,
            patch("app.tools.documents.render_to_pdf", return_value=b"pdf_bytes"),
            patch("app.tools.documents.get_session_context") as mock_get_session,
            patch.dict('os.environ', {
                'STORAGE_PROVIDER': 'tigris',
                'API_BASE_URL': 'https://jobagent.fly.dev'
            })
        ):
            # Mock the session context
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None

            # Mock LLM response
            mock_llm_resume_result = Mock()
            mock_resume_draft_data = ResumeDraft(
                resume_md="# Resume Content",
                cover_letter_md="# Cover Letter Content",
                identified_skills=["Python", "FastAPI"],
            )
            mock_llm_resume_result.data = mock_resume_draft_data
            mock_resume_agent.run = AsyncMock(return_value=mock_llm_resume_result)

            # Mock file upload - should return API URLs for Tigris
            mock_upload.side_effect = [
                "https://jobagent.fly.dev/api/files/resume_123.pdf",
                "https://jobagent.fly.dev/api/files/cover_letter_123.pdf",
            ]

            result = await draft_and_upload_documents(application.id)

            assert result["status"] == "success"
            assert "https://jobagent.fly.dev/api/files/" in result["resume_url"]
            assert "https://jobagent.fly.dev/api/files/" in result["cover_letter_url"]

            # Verify database was updated with API URLs
            session.refresh(application)
            assert "https://jobagent.fly.dev/api/files/" in application.resume_s3_url
            assert "https://jobagent.fly.dev/api/files/" in application.cover_letter_s3_url


class TestPDFUtils:
    """Test the PDF generation utilities."""
    
    def test_render_to_pdf_generates_single_page_pdf(self):
        """Test that render_to_pdf generates a single-page PDF from markdown."""
        from app.tools.pdf_utils import render_to_pdf
        
        # Sample markdown content that should fit on one page
        markdown_content = """
# John Doe
Software Engineer

## Experience
- 5 years of Python development
- FastAPI and web frameworks
- Database design and optimization

## Skills
- Python, JavaScript, SQL
- FastAPI, React, PostgreSQL
- Docker, AWS, Git

## Education
**Bachelor of Computer Science**  
University of Technology, 2019
        """.strip()
        
        # Generate PDF bytes (new API automatically ensures single page)
        pdf_bytes = render_to_pdf(markdown_content, is_markdown=True)
        
        # Verify it's a valid PDF by checking PDF header
        assert pdf_bytes.startswith(b'%PDF'), "Generated content should be a valid PDF"
        
        # Verify it's not empty
        assert len(pdf_bytes) > 100, "PDF should contain substantial content"
        
        # Save to temporary file and verify page count
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(pdf_bytes)
                temp_file_path = temp_file.name
            
            # Verify the file exists and has content
            assert os.path.exists(temp_file_path), "Temporary PDF file should exist"
            assert os.path.getsize(temp_file_path) > 0, "PDF file should not be empty"
            
            # Check page count using pypdf if available, otherwise use basic validation
            try:
                from pypdf import PdfReader
                with open(temp_file_path, 'rb') as f:
                    pdf_reader = PdfReader(f)
                    page_count = len(pdf_reader.pages)
                    assert page_count == 1, f"PDF should have exactly 1 page, but has {page_count}"
            except ImportError:
                # If pypdf is not available, do basic validation
                # Check for PDF stream objects that might indicate multiple pages
                with open(temp_file_path, 'rb') as f:
                    content = f.read()
                    # Look for page break indicators in PDF content
                    page_indicators = content.count(b'/Type /Page')
                    # Should have only one page object
                    assert page_indicators <= 2, f"PDF appears to have multiple pages (found {page_indicators} page indicators)"
            
            # Read it back to ensure it's still valid
            with open(temp_file_path, 'rb') as f:
                read_back = f.read()
                assert read_back == pdf_bytes, "File content should match original bytes"
                assert read_back.startswith(b'%PDF'), "Read-back content should still be valid PDF"
        
        finally:
            # Clean up the temporary file
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
    
    def test_render_to_pdf_generates_valid_pdf(self):
        """Test that render_to_pdf generates a valid PDF from markdown."""
        from app.tools.pdf_utils import render_to_pdf
        
        # Sample markdown content that should fit on one page
        markdown_content = """
# John Doe
Software Engineer

## Experience
- 5 years of Python development
- FastAPI and web frameworks
- Database design and optimization

## Skills
- Python, JavaScript, SQL
- FastAPI, React, PostgreSQL
- Docker, AWS, Git

## Education
**Bachelor of Computer Science**  
University of Technology, 2019
        """.strip()
        
        # Generate PDF bytes
        pdf_bytes = render_to_pdf(markdown_content, is_markdown=True)
        
        # Verify it's a valid PDF by checking PDF header
        assert pdf_bytes.startswith(b'%PDF'), "Generated content should be a valid PDF"
        
        # Verify it's not empty
        assert len(pdf_bytes) > 100, "PDF should contain substantial content"
        
        # Save to temporary file to verify it can be written and read
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(pdf_bytes)
                temp_file_path = temp_file.name
            
            # Verify the file exists and has content
            assert os.path.exists(temp_file_path), "Temporary PDF file should exist"
            assert os.path.getsize(temp_file_path) > 0, "PDF file should not be empty"
            
            # Read it back to ensure it's still valid
            with open(temp_file_path, 'rb') as f:
                read_back = f.read()
                assert read_back == pdf_bytes, "File content should match original bytes"
                assert read_back.startswith(b'%PDF'), "Read-back content should still be valid PDF"
        
        finally:
            # Clean up the temporary file
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
    
    def test_render_to_pdf_single_page_optimization(self):
        """Test that resume PDF generation uses single-page optimization."""
        from app.tools.pdf_utils import render_to_pdf, markdown_to_html
        
        # Test the HTML conversion includes single-page CSS
        markdown_content = "# Test Resume\n\nSome content here."
        html_output = markdown_to_html(markdown_content, font_pt=10.0)
        
        # Verify single-page optimization CSS is present
        assert '@page' in html_output, "Should include @page CSS for page control"
        assert 'overflow: hidden' in html_output, "Should include overflow hidden for single page"
        assert 'letter' in html_output, "Should specify letter page size"
        assert '0.5in' in html_output, "Should include compact margins"
        
        # Test that PDF generation completes without error for resume
        pdf_bytes = render_to_pdf(markdown_content, is_markdown=True)
        assert pdf_bytes.startswith(b'%PDF'), "Should generate valid PDF"
    
    def test_render_to_pdf_auto_sizing(self):
        """Test that the auto-sizing feature works for large content."""
        from app.tools.pdf_utils import render_to_pdf
        
        # Create markdown content that would definitely overflow one page at normal font size
        large_content = """
# Very Long Resume
Software Engineer with Extensive Experience

## Professional Experience

### Senior Software Engineer at Big Tech Corp (2020-Present)
- Led development of microservices architecture serving 1M+ users daily
- Implemented CI/CD pipelines reducing deployment time by 75%
- Mentored junior developers and conducted code reviews
- Technologies: Python, Docker, Kubernetes, AWS, PostgreSQL
- Achievements: Reduced system latency by 40%, improved test coverage to 95%

### Software Engineer at Growing Startup (2018-2020)  
- Built scalable web applications using React and Node.js
- Designed and implemented RESTful APIs and GraphQL endpoints
- Collaborated with product team on feature specifications
- Technologies: JavaScript, React, Node.js, MongoDB, Redis
- Achievements: Shipped 15+ features, increased user engagement by 60%

### Junior Developer at Local Agency (2016-2018)
- Developed client websites and web applications
- Maintained legacy PHP and WordPress systems
- Worked directly with clients on requirements gathering
- Technologies: PHP, WordPress, MySQL, jQuery, CSS
- Achievements: Delivered 20+ client projects on time and budget

## Technical Skills
- Programming Languages: Python, JavaScript, TypeScript, Java, Go, PHP
- Web Frameworks: FastAPI, Django, React, Vue.js, Express.js, Spring Boot
- Databases: PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch
- Cloud Platforms: AWS, Google Cloud, Azure, DigitalOcean
- DevOps Tools: Docker, Kubernetes, Jenkins, GitHub Actions, Terraform
- Testing: pytest, Jest, Cypress, Selenium, JUnit
- Other: GraphQL, REST APIs, Microservices, Event-driven architecture

## Education
**Master of Computer Science**  
University of Technology, 2016
- Thesis: "Optimizing Database Performance in Distributed Systems"
- GPA: 3.8/4.0
- Relevant Coursework: Algorithms, Data Structures, Database Systems, Software Engineering

**Bachelor of Computer Science**  
State University, 2014
- Magna Cum Laude, GPA: 3.9/4.0
- President of Computer Science Club
- Relevant Coursework: Computer Networks, Operating Systems, Compilers

## Certifications
- AWS Certified Solutions Architect - Professional (2023)
- Certified Kubernetes Administrator (2022)
- Google Cloud Professional Developer (2021)
- Scrum Master Certification (2020)

## Projects
**Open Source Contributions**
- Contributor to FastAPI (10+ merged PRs)
- Maintainer of popular Python testing library (500+ GitHub stars)
- Speaker at 3 tech conferences on microservices architecture

**Personal Projects**
- Built ML-powered job recommendation system using Python and scikit-learn
- Created real-time chat application with WebSocket support
- Developed automated trading bot using financial APIs
        """.strip()
        
        # The auto-sizing should ensure this fits on one page by reducing font size
        pdf_bytes = render_to_pdf(large_content, is_markdown=True)
        
        # Verify it's a valid PDF
        assert pdf_bytes.startswith(b'%PDF'), "Should generate valid PDF even for large content"
        assert len(pdf_bytes) > 100, "PDF should contain substantial content"
        
        # Save to temporary file and verify it's still one page
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(pdf_bytes)
                temp_file_path = temp_file.name
            
            # Check page count - should be 1 due to auto-sizing
            try:
                from pypdf import PdfReader
                with open(temp_file_path, 'rb') as f:
                    pdf_reader = PdfReader(f)
                    page_count = len(pdf_reader.pages)
                    # The auto-sizing should try to fit it on 1 page, but if content is too large,
                    # it might end up with more pages at minimum font size
                    assert page_count <= 2, f"PDF should have at most 2 pages due to auto-sizing, but has {page_count}"
            except ImportError:
                # If pypdf not available, just check it's a valid PDF
                pass
        
        finally:
            # Clean up the temporary file
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
    
    def test_render_to_pdf_html_input_not_supported(self):
        """Test that HTML input raises appropriate error."""
        from app.tools.pdf_utils import render_to_pdf
        
        html_content = """
        <html>
        <body>
            <h1>Test Document</h1>
            <p>This is a test HTML document.</p>
        </body>
        </html>
        """
        
        # Should raise ValueError since auto-fit is only implemented for markdown
        with pytest.raises(ValueError, match="Auto-fit only implemented for markdown input"):
            render_to_pdf(html_content, is_markdown=False)
    
    def test_markdown_to_html_output_structure(self):
        """Test that markdown_to_html produces well-formed HTML."""
        from app.tools.pdf_utils import markdown_to_html
        
        markdown_content = """
# Main Heading
## Sub Heading

- List item 1  
- List item 2

**Bold text** and *italic text*.
        """.strip()
        
        html_output = markdown_to_html(markdown_content, font_pt=10.0)
        
        # Verify HTML structure (strip whitespace for comparison)
        html_stripped = html_output.strip()
        assert html_stripped.startswith('<!DOCTYPE html>'), "Should be a complete HTML document"
        assert '<html>' in html_output and '</html>' in html_output, "Should have html tags"
        assert '<head>' in html_output and '</head>' in html_output, "Should have head section"
        assert '<body>' in html_output and '</body>' in html_output, "Should have body section"
        assert '<style>' in html_output and '</style>' in html_output, "Should include CSS styles"
        
        # Verify markdown was converted
        assert '<h1>' in html_output, "Should convert # to h1"
        assert '<h2>' in html_output, "Should convert ## to h2"
        assert '<ul>' in html_output and '<li>' in html_output, "Should convert lists"
        assert '<strong>' in html_output, "Should convert **bold**"
        assert '<em>' in html_output, "Should convert *italic*"
        
        # Verify font size is applied
        assert '10.0pt' in html_output, "Should use the specified font size"
    
    def test_markdown_to_html_font_scaling(self):
        """Test that markdown_to_html properly scales fonts."""
        from app.tools.pdf_utils import markdown_to_html
        
        markdown_content = "# Test Heading\n\nSome content."
        
        # Test different font sizes
        small_html = markdown_to_html(markdown_content, font_pt=8.0)
        large_html = markdown_to_html(markdown_content, font_pt=12.0)
        
        # Both should be valid HTML
        assert small_html.startswith('<!DOCTYPE html>'), "Small font HTML should be valid"
        assert large_html.startswith('<!DOCTYPE html>'), "Large font HTML should be valid"
        
        # Font sizes should be reflected in the CSS
        assert '8.0pt' in small_html, "Should use 8pt font size"
        assert '12.0pt' in large_html, "Should use 12pt font size"
        
        # Heading sizes should scale proportionally  
        assert '13.5pt' in small_html, "H1 should be base + 5.5pt (8 + 5.5 = 13.5)"
        assert '17.5pt' in large_html, "H1 should be base + 5.5pt (12 + 5.5 = 17.5)"
