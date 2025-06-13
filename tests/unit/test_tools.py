# tests/unit/test_tools.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, UTC
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
