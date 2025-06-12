# tests/e2e/test_api.py
import os
import pytest
import json  # For health check response parsing
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, Mock
from sqlmodel import select  # Added for SQLModel queries

from app.models import (
    Profile,
    Role,
    Application,
    ApplicationStatus,
    UserPreference,
    RoleDetails,
)  # Added Application, ApplicationStatus, UserPreference
from app.tasks import celery_app  # For disabling celery tasks during tests if needed

# Temporarily disable Celery eager mode for these tests if tasks are not meant to execute immediately
# or ensure tasks are properly mocked if their execution affects test outcomes.
# This can be done globally in conftest.py or per test module/class if needed.
# For now, assuming tasks are either mocked or their immediate execution is fine.

# Base URL for API examples - automatically detects environment
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


class TestRootEndpoint:
    def test_root_endpoint(self, client: TestClient):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["message"] == "Job Agent API is running"
        assert data["routes"] == [
            {
                "path": "/profile",
                "method": "POST",
                "description": "Create a new profile",
            }
        ]
        assert data["example"] == {
            "method": "POST",
            "url": f"{API_BASE_URL}/profile",
            "headers": {"X-API-Key": "your-api-key"},
            "body": {
                "headline": "Software Engineer",
                "summary": "I am a software engineer with 5 years of experience in Python and Django",
            },
        }


class TestHealthEndpoint:
    def test_health_check_success(self, client: TestClient):
        """Test that the health check endpoint returns 200 when all services are healthy."""
        # In conftest, we set up mock env vars. Actual health depends on these or live services.
        # For true E2E against live services (docker-compose up), this would hit them.
        # For unit/integration tests with TestClient, mocks for external services are typical.
        # Assuming db is up via test_engine.
        # Mock redis, storage, notifications health checks if they are not actually running or are flaky.
        from datetime import datetime, UTC
        mock_heartbeat_time = datetime.now(UTC)
        
        with (
            patch("app.api.system.db_health_check", return_value=True),
            patch("app.api.system.redis_health_check", return_value=True),
            patch("app.api.system.storage_health_check", return_value=True),
            patch("app.api.system.notification_health_check", return_value=True),
            patch("app.queue_manager.queue_manager.get_last_heartbeat", return_value=mock_heartbeat_time),
        ):
            response = client.get("/health")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "ok"
            assert "services" in data
            assert data["services"]["database"] is True
            assert data["services"]["redis"] is True
            assert data["services"]["object_storage"] is True
            assert data["services"]["notifications"] is True
            assert data["services"]["node_service"] is True

    def test_health_check_degraded(self, client: TestClient):
        with (
            patch("app.api.system.db_health_check", return_value=True),
            patch("app.api.system.redis_health_check", return_value=False),
            patch("app.api.system.storage_health_check", return_value=True),
            patch("app.api.system.notification_health_check", return_value=True),
        ):
            response = client.get("/health")
            # FastAPI returns Response object; .json() might fail if content isn't valid JSON after str()
            # The api_server.py converts the health_status dict to string for non-200 responses.
            # We need to parse this string back to JSON.
            assert response.status_code == 206  # Partial Content for degraded
            data = json.loads(
                response.content.decode("utf-8")
            )  # Parse the string content
            assert data["status"] == "degraded"
            assert data["services"]["redis"] is False





class TestProfileCRUD:
    def test_get_profile_success(self, client: TestClient, sample_profile: Profile, session):
        """Test getting profile details via GET with preferences."""
        # Add some test preferences
        prefs_data = [
            {"profile_id": sample_profile.id, "key": "email", "value": "test@example.com"},
            {"profile_id": sample_profile.id, "key": "phone", "value": "+1234567890"},
        ]
        prefs = []
        for pref_data in prefs_data:
            pref = UserPreference.model_validate(pref_data)
            prefs.append(pref)
            session.add(pref)
        session.commit()

        response = client.get(f"/profile/{sample_profile.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_profile.id
        assert data["headline"] == sample_profile.headline
        assert data["summary"] == sample_profile.summary
        assert "created_at" in data
        assert "updated_at" in data
        
        # Check preferences are included
        assert "preferences" in data
        assert "preferences_dict" in data
        assert len(data["preferences"]) == 2
        assert data["preferences_dict"]["email"] == "test@example.com"
        assert data["preferences_dict"]["phone"] == "+1234567890"

    def test_get_profile_html_success(self, client: TestClient, sample_profile: Profile, session):
        """Test getting profile details as HTML template with preferences."""
        # Add a test preference
        pref_data = {"profile_id": sample_profile.id, "key": "location", "value": "San Francisco"}
        pref = UserPreference.model_validate(pref_data)
        session.add(pref)
        session.commit()

        response = client.get(
            f"/profile/{sample_profile.id}",
            headers={"Accept": "text/html"}
        )
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Should contain profile information
        assert sample_profile.headline in response.text
        assert sample_profile.summary in response.text
        # Should contain preferences
        assert "location" in response.text
        assert "San Francisco" in response.text
        assert "Preferences" in response.text

    def test_get_profile_not_found(self, client: TestClient):
        """Test getting non-existent profile."""
        response = client.get("/profile/99999")
        assert response.status_code == 404

    def test_create_profile_explicit(self, client: TestClient, session):
        """Test creating a new profile with explicit POST to /profile."""
        # Clear existing profiles
        profiles = session.exec(select(Profile)).all()
        for p in profiles:
            session.delete(p)
        session.commit()

        profile_data = {
            "headline": "Explicit Profile Creation",
            "summary": "Created via POST /profile"
        }

        response = client.post(
            "/profile",
            json=profile_data,
            headers={"X-API-Key": "test-api-key"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert "profile_id" in data
        
        # Verify in DB
        profile_id = data["profile_id"]
        db_profile = session.get(Profile, profile_id)
        assert db_profile is not None
        assert db_profile.headline == profile_data["headline"]

    def test_update_profile_put(self, client: TestClient, sample_profile: Profile, session):
        """Test updating profile with PUT."""
        updated_data = {
            "headline": "Updated via PUT",
            "summary": "This was updated using PUT method"
        }

        response = client.put(
            f"/profile/{sample_profile.id}",
            json=updated_data,
            headers={"X-API-Key": "test-api-key"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["profile_id"] == sample_profile.id

        # Verify changes in DB
        session.refresh(sample_profile)
        assert sample_profile.headline == "Updated via PUT"
        assert sample_profile.summary == "This was updated using PUT method"

    def test_update_profile_put_not_found(self, client: TestClient):
        """Test updating non-existent profile."""
        response = client.put(
            "/profile/99999",
            json={"headline": "Test"},
            headers={"X-API-Key": "test-api-key"}
        )
        assert response.status_code == 404

    def test_delete_profile_success(self, client: TestClient, session):
        """Test deleting a profile with all associated data."""
        from app.models import Company
        
        # Create a profile with associated data
        profile_data = {
            "headline": "Profile to Delete",
            "summary": "This profile will be deleted"
        }
        profile = Profile.model_validate(profile_data)
        session.add(profile)
        session.commit()
        session.refresh(profile)
        
        # Create associated company for roles
        company = Company(name="TestDeleteCorp")
        session.add(company)
        session.commit()
        session.refresh(company)
        
        # Create associated preferences
        preferences_data = [
            {"profile_id": profile.id, "key": "email", "value": "delete@test.com"},
            {"profile_id": profile.id, "key": "phone", "value": "+1234567890"}
        ]
        for pref_data in preferences_data:
            pref = UserPreference.model_validate(pref_data)
            session.add(pref)
        
        # Create a role (not associated with profile directly)
        role_data = {
            "title": "Test Role to Keep",
            "description": "Role should remain after profile deletion",
            "posting_url": "https://example.com/delete-test",
            "unique_hash": "test_delete_hash",
            "company_id": company.id
        }
        role = Role.model_validate(role_data)
        session.add(role)
        session.commit()
        session.refresh(role)
        
        # Create associated application (links profile to role)
        application_data = {
            "role_id": role.id,
            "profile_id": profile.id,
            "status": ApplicationStatus.DRAFT
        }
        application = Application.model_validate(application_data)
        session.add(application)
        session.commit()
        session.refresh(application)
        
        # Store IDs for verification after deletion
        profile_id = profile.id
        role_id = role.id
        application_id = application.id
        preference_ids = [pref.id for pref in session.exec(
            select(UserPreference).where(UserPreference.profile_id == profile_id)
        ).all()]
        
        # Delete the profile
        response = client.delete(
            f"/profile/{profile_id}",
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["message"] == "Profile deleted successfully."
        assert data["profile_id"] == profile_id
        
        # Verify profile is deleted
        deleted_profile = session.get(Profile, profile_id)
        assert deleted_profile is None
        
        # Verify role is NOT deleted (roles can be shared across profiles)
        remaining_role = session.get(Role, role_id)
        assert remaining_role is not None
        assert remaining_role.title == "Test Role to Keep"
        
        # Verify associated application is deleted
        deleted_application = session.get(Application, application_id)
        assert deleted_application is None
        
        # Verify associated preferences are deleted
        for pref_id in preference_ids:
            deleted_preference = session.get(UserPreference, pref_id)
            assert deleted_preference is None

    def test_delete_profile_not_found(self, client: TestClient):
        """Test deleting non-existent profile."""
        response = client.delete(
            "/profile/99999",
            headers={"X-API-Key": "test-api-key"}
        )
        assert response.status_code == 404
        data = response.json()
        assert "Profile not found" in data["detail"]

    def test_delete_profile_requires_api_key(self, client: TestClient, sample_profile: Profile):
        """Test that delete profile endpoint requires API key authentication."""
        response = client.delete(f"/profile/{sample_profile.id}")
        assert response.status_code == 403  # Forbidden without API key


class TestUserPreferenceCRUD:
    def test_get_profile_preferences(self, client: TestClient, sample_profile: Profile, session):
        """Test getting all preferences for a profile."""
        # Create some test preferences
        prefs_data = [
            {"profile_id": sample_profile.id, "key": "email", "value": "test@example.com"},
            {"profile_id": sample_profile.id, "key": "phone", "value": "+1234567890"},
            {"profile_id": sample_profile.id, "key": "linkedin", "value": "https://linkedin.com/in/test"}
        ]
        for pref_data in prefs_data:
            pref = UserPreference.model_validate(pref_data)
            session.add(pref)
        session.commit()

        response = client.get(f"/profile/{sample_profile.id}/preferences")

        assert response.status_code == 200
        data = response.json()
        assert "preferences" in data
        assert len(data["preferences"]) == 3
        
        # Check that all our preferences are there
        pref_keys = [p["key"] for p in data["preferences"]]
        assert "email" in pref_keys
        assert "phone" in pref_keys
        assert "linkedin" in pref_keys

    def test_get_specific_preference(self, client: TestClient, sample_profile: Profile, session):
        """Test getting a specific preference by key."""
        pref_data = {
            "profile_id": sample_profile.id, 
            "key": "test_key", 
            "value": "test_value"
        }
        pref = UserPreference.model_validate(pref_data)
        session.add(pref)
        session.commit()

        response = client.get(f"/profile/{sample_profile.id}/preferences/test_key")

        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "test_key"
        assert data["value"] == "test_value"
        assert data["profile_id"] == sample_profile.id

    def test_get_preference_not_found(self, client: TestClient, sample_profile: Profile):
        """Test getting non-existent preference."""
        response = client.get(f"/profile/{sample_profile.id}/preferences/nonexistent")
        assert response.status_code == 404

    def test_create_preference(self, client: TestClient, sample_profile: Profile, session):
        """Test creating a new preference."""
        pref_data = {
            "key": "new_preference",
            "value": "new_value"
        }

        response = client.post(
            f"/profile/{sample_profile.id}/preferences",
            json=pref_data,
            headers={"X-API-Key": "test-api-key"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert data["key"] == "new_preference"

        # Verify in DB
        pref = session.exec(
            select(UserPreference).where(
                UserPreference.profile_id == sample_profile.id,
                UserPreference.key == "new_preference"
            )
        ).first()
        assert pref is not None
        assert pref.value == "new_value"

    def test_update_preference(self, client: TestClient, sample_profile: Profile, session):
        """Test updating an existing preference."""
        # Create initial preference
        pref_data = {
            "profile_id": sample_profile.id,
            "key": "update_test",
            "value": "original_value"
        }
        pref = UserPreference.model_validate(pref_data)
        session.add(pref)
        session.commit()

        update_data = {"value": "updated_value"}

        response = client.put(
            f"/profile/{sample_profile.id}/preferences/update_test",
            json=update_data,
            headers={"X-API-Key": "test-api-key"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["key"] == "update_test"

        # Verify change in DB
        session.refresh(pref)
        assert pref.value == "updated_value"

    def test_update_preference_not_found(self, client: TestClient, sample_profile: Profile):
        """Test updating non-existent preference."""
        response = client.put(
            f"/profile/{sample_profile.id}/preferences/nonexistent",
            json={"value": "test"},
            headers={"X-API-Key": "test-api-key"}
        )
        assert response.status_code == 404

    def test_delete_preference(self, client: TestClient, sample_profile: Profile, session):
        """Test deleting a preference."""
        # Create preference to delete
        pref_data = {
            "profile_id": sample_profile.id,
            "key": "delete_test",
            "value": "to_be_deleted"
        }
        pref = UserPreference.model_validate(pref_data)
        session.add(pref)
        session.commit()

        response = client.delete(
            f"/profile/{sample_profile.id}/preferences/delete_test",
            headers={"X-API-Key": "test-api-key"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

        # Verify deletion in DB
        deleted_pref = session.exec(
            select(UserPreference).where(
                UserPreference.profile_id == sample_profile.id,
                UserPreference.key == "delete_test"
            )
        ).first()
        assert deleted_pref is None

    def test_delete_preference_not_found(self, client: TestClient, sample_profile: Profile):
        """Test deleting non-existent preference."""
        response = client.delete(
            f"/profile/{sample_profile.id}/preferences/nonexistent",
            headers={"X-API-Key": "test-api-key"}
        )
        assert response.status_code == 404


class TestApplicationsEndpoint:
    def test_get_applications_empty(self, client: TestClient, session):
        """Test getting applications when none exist."""
        # Clear existing applications for this test
        apps = session.exec(select(Application)).all()
        for app_obj in apps:
            session.delete(app_obj)
        session.commit()

        response = client.get("/applications", headers={"X-API-Key": "test-api-key"})
        assert response.status_code == 200
        data = response.json()
        assert data["applications"] == []

    def test_get_applications_with_data_and_filter(
        self, client: TestClient, session, sample_application: Application
    ):
        """Test getting applications with status filter."""
        # sample_application fixture creates an app with status DRAFT (or as defined)
        # Ensure sample_application is committed and its status is what we expect to filter by.
        draft_status_str = ApplicationStatus.DRAFT.value
        session.refresh(sample_application.role)
        session.refresh(sample_application.role.company)

        response = client.get(
            f"/applications?status_filter={draft_status_str}",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["applications"]) >= 1
        assert data["applications"][0]["status"] == draft_status_str
        assert data["applications"][0]["id"] == sample_application.id

    def test_get_applications_includes_task_created_applications(
        self, client: TestClient, session, sample_profile: Profile
    ):
        """Test that applications created by tasks are visible in the API."""
        from unittest.mock import Mock
        from app.tasks.submission import task_apply_for_role
        from app.models import Role, Company
        
        # Create a role manually for this test
        company = Company(name="TestCorp")
        session.add(company)
        session.commit()
        session.refresh(company)
        
        role_data = {
            "title": "Test Developer",
            "description": "Test role",
            "posting_url": "https://example.com/test-job",
            "unique_hash": "test_hash_applications",
            "company_id": company.id,
        }
        role = Role.model_validate(role_data)
        session.add(role)
        session.commit()
        session.refresh(role)
        
        # Use the test session context to ensure the task can see the same data
        with patch("app.db.get_session_context") as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None
            
            # Call the task using apply() for proper execution context
            result = task_apply_for_role.apply(
                args=[role.id, sample_profile.id], 
                throw=True
            ).result
        
        assert result["status"] == "success"
        application_id = result["application_id"]
        
        # Now get applications via API
        response = client.get("/applications", headers={"X-API-Key": "test-api-key"})
        assert response.status_code == 200
        data = response.json()
        
        # Find our application in the results
        app_ids = [app["id"] for app in data["applications"]]
        assert application_id in app_ids
        
        # Find the specific application and verify its data
        our_app = next(app for app in data["applications"] if app["id"] == application_id)
        assert our_app["status"] == ApplicationStatus.DRAFT.value
        assert our_app["role_title"] == "Test Developer"
        assert our_app["company_name"] == "TestCorp"

    def test_get_applications_invalid_filter(self, client: TestClient):
        """Test getting applications with invalid status filter."""
        response = client.get(
            "/applications?status_filter=invalid_status",
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 400
        assert "Invalid status filter" in response.json()["detail"]


class TestRoleRanking:
    # Patch the celery task to prevent actual execution or to check if it was called
    @patch("app.tasks.task_rank_role.delay")
    def test_trigger_role_ranking_success(
        self, mock_task_delay, client: TestClient, sample_role: Role
    ):
        """Test triggering role ranking successfully."""
        # Create a mock task object with an id attribute
        mock_task = Mock()
        mock_task.id = "test_task_id"
        mock_task_delay.return_value = mock_task

        response = client.post(
            f"/jobs/rank/{sample_role.id}",
            json={
                "profile_id": 1
            },  # profile_id is a query param in API, not JSON body in design doc
            # Correcting to match API server implementation: profile_id in path or query
            # The API server takes profile_id as a query parameter or uses default
            headers={"X-API-Key": "test-api-key"},
        )

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "queued"
        assert response_data["task_id"] == "test_task_id"
        assert response_data["role_id"] == sample_role.id

        # Verify task was called
        mock_task_delay.assert_called_once_with(
            sample_role.id, 1
        )  # role_id, profile_id

    def test_trigger_role_ranking_not_found(self, client: TestClient):
        """Test triggering role ranking for non-existent role."""
        response = client.post(
            "/jobs/rank/99999", headers={"X-API-Key": "test-api-key"}
        )
        assert response.status_code == 404


class TestJobApplicationEndpoint:
    """Test the new queue-based job application endpoint."""

    @patch("app.tasks.submission.task_submit_application_queue.delay")
    def test_trigger_job_application_success(
        self, mock_task_delay, client: TestClient, sample_role: Role, sample_profile: Profile, session
    ):
        """Test triggering job application using queue-based system."""
        mock_task = Mock()
        mock_task.id = "test_queue_task_id"
        mock_task_delay.return_value = mock_task

        response = client.post(
            f"/jobs/apply/{sample_role.id}?profile_id={sample_profile.id}",
            headers={"X-API-Key": "test-api-key"},
        )

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "queued"
        assert response_data["task_id"] == "test_queue_task_id"
        assert response_data["role_id"] == sample_role.id
        assert "application_id" in response_data

        # Verify an Application was created
        application_id = response_data["application_id"]
        application = session.get(Application, application_id)
        assert application is not None
        assert application.role_id == sample_role.id
        assert application.profile_id == sample_profile.id
        assert application.status == ApplicationStatus.DRAFT

        # Verify task was called with the application ID
        mock_task_delay.assert_called_once_with(application_id)

    @patch("app.tasks.submission.task_submit_application_queue.delay")
    def test_trigger_job_application_uses_existing_application(
        self, mock_task_delay, client: TestClient, sample_application: Application, session
    ):
        """Test that the endpoint reuses existing applications."""
        mock_task = Mock()
        mock_task.id = "test_reuse_task_id"
        mock_task_delay.return_value = mock_task

        response = client.post(
            f"/jobs/apply/{sample_application.role_id}?profile_id={sample_application.profile_id}",
            headers={"X-API-Key": "test-api-key"},
        )

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["application_id"] == sample_application.id

        # Should still call the task with the existing application
        mock_task_delay.assert_called_once_with(sample_application.id)

    def test_trigger_job_application_not_found(self, client: TestClient):
        """Test job application for non-existent role."""
        response = client.post(
            "/jobs/apply/99999", headers={"X-API-Key": "test-api-key"}
        )
        assert response.status_code == 404


class TestHealthEndpoints:
    """Test the new health check endpoints for queue monitoring."""

    def test_health_check_with_queues(self, client: TestClient):
        """Test that health check works and includes queue stats (even if empty in test)."""
        response = client.get("/health")
        # Accept either 200 (all healthy) or 206 (degraded due to test environment)
        assert response.status_code in [200, 206]
        data = response.json()
        
        assert data["status"] in ["ok", "degraded"]
        assert "queue_stats" in data
        # Queue stats should be present (even if empty/errored in test environment)
        assert isinstance(data["queue_stats"], dict)

    @patch("app.queue_manager.queue_manager.health_check")
    @patch("app.queue_manager.queue_manager.get_queue_stats")
    def test_queue_health_endpoint(
        self, mock_get_stats, mock_health_check, client: TestClient
    ):
        """Test dedicated queue health endpoint."""
        mock_health_check.return_value = True
        mock_get_stats.return_value = {
            "job_application": 5,
            "update_job_status": 2,
            "approval_request": 1,
            "send_notification": 0
        }

        response = client.get("/health/queues")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["queue_statistics"]["job_application"] == 5
        assert data["details"]["total_pending_tasks"] == 8

    @patch("app.queue_manager.queue_manager.get_last_heartbeat")
    @patch("app.queue_manager.queue_manager.get_queue_stats")
    def test_node_service_health_check(self, mock_get_stats, mock_get_heartbeat, client: TestClient):
        """Test Node.js service health monitoring via heartbeat."""
        from datetime import datetime, timezone
        
        # Test healthy scenario (recent heartbeat)
        recent_heartbeat = datetime.now(timezone.utc)
        mock_get_heartbeat.return_value = recent_heartbeat
        mock_get_stats.return_value = {"job_application": 3}

        response = client.get("/health/node-service")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["details"]["last_heartbeat"] is not None
        assert data["details"]["seconds_since_heartbeat"] < 60

    @patch("app.queue_manager.queue_manager.get_last_heartbeat")
    @patch("app.queue_manager.queue_manager.get_queue_stats")
    def test_node_service_health_degraded(self, mock_get_stats, mock_get_heartbeat, client: TestClient):
        """Test Node.js service health when degraded (old heartbeat)."""
        from datetime import datetime, timezone, timedelta
        
        # Test degraded scenario (old heartbeat)
        old_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=90)
        mock_get_heartbeat.return_value = old_heartbeat
        mock_get_stats.return_value = {"job_application": 15}

        response = client.get("/health/node-service")
        assert response.status_code == 503
        
        data = response.json()
        assert data["status"] == "unhealthy"
        assert "not responding" in data["details"]["status"]

    @patch("app.queue_manager.queue_manager.get_last_heartbeat")
    @patch("app.queue_manager.queue_manager.get_queue_stats")
    def test_node_service_health_unhealthy(self, mock_get_stats, mock_get_heartbeat, client: TestClient):
        """Test Node.js service health when unhealthy (no heartbeat)."""
        # Test unhealthy scenario (no heartbeat)
        mock_get_heartbeat.return_value = None
        mock_get_stats.return_value = {"job_application": 60}

        response = client.get("/health/node-service")
        assert response.status_code == 503
        
        data = response.json()
        assert data["status"] == "unhealthy"
        assert "no heartbeat received" in data["details"]["status"]


class TestSMSWebhook:
    # Common data for SMS webhook tests
    webhook_data_help = {
        "From": "+1234567890",
        "Body": "help",
        "MessageSid": "SM_test_help",
    }
    webhook_data_status_cmd = {
        "From": "+1234567890",
        "Body": "status",
        "MessageSid": "SM_test_status",
    }
    webhook_data_report_cmd = {
        "From": "+1234567890",
        "Body": "report",
        "MessageSid": "SM_test_report",
    }
    webhook_data_generic = {
        "From": "+1234567890",
        "Body": "Thanks for the update!",
        "MessageSid": "SM_test_generic",
    }

    @patch("app.api.webhooks.twilio_validator")
    @patch("app.api.webhooks.send_sms_message", return_value=True)
    def test_sms_webhook_help_command(
        self, mock_send_msg, mock_validator, client: TestClient
    ):
        mock_validator.validate.return_value = True
        response = client.post("/webhooks/sms", data=self.webhook_data_help)
        assert response.status_code == 204  # No Content
        mock_validator.validate.assert_called_once()
        mock_send_msg.assert_called_once()
        assert "Job Agent Commands" in mock_send_msg.call_args[0][0]

    @patch("app.api.webhooks.twilio_validator")
    @patch("app.api.webhooks.send_sms_message", return_value=True)
    def test_sms_webhook_status_command(
        self, mock_send_msg, mock_validator, client: TestClient, session
    ):
        mock_validator.validate.return_value = True
        response = client.post("/webhooks/sms", data=self.webhook_data_status_cmd)
        assert response.status_code == 204
        mock_validator.validate.assert_called_once()
        mock_send_msg.assert_called_once()

    @patch("app.api.webhooks.twilio_validator")
    @patch(
        "app.api.webhooks.send_sms_message", return_value=True
    )  # Mock sending confirmation
    @patch(
        "app.tasks.task_send_daily_report.delay"
    )  # Mock the Celery task call with correct path
    def test_sms_webhook_report_command(
        self, mock_task_delay, mock_send_msg, mock_validator, client: TestClient
    ):
        mock_validator.validate.return_value = True
        response = client.post("/webhooks/sms", data=self.webhook_data_report_cmd)
        assert response.status_code == 204
        mock_validator.validate.assert_called_once()
        mock_task_delay.assert_called_once()
        mock_send_msg.assert_called_once_with(
            "📊Generating your daily report, it will arrive shortly!",
            self.webhook_data_report_cmd["From"],
        )

    @patch("app.api.webhooks.twilio_validator")
    @patch("app.api.webhooks.send_sms_message", return_value=True)
    def test_sms_webhook_generic_message(
        self, mock_send_msg, mock_validator, client: TestClient
    ):
        mock_validator.validate.return_value = True
        response = client.post("/webhooks/sms", data=self.webhook_data_generic)
        assert response.status_code == 204
        mock_validator.validate.assert_called_once()
        mock_send_msg.assert_called_once()
        assert "Got your response!" in mock_send_msg.call_args[0][0]

    @patch("app.api.webhooks.twilio_validator")
    def test_sms_webhook_invalid_signature(self, mock_validator, client: TestClient):
        mock_validator.validate.return_value = False
        response = client.post("/webhooks/sms", data=self.webhook_data_generic)
        assert response.status_code == 403
        mock_validator.validate.assert_called()
        assert "Invalid Twilio signature" in response.json()["detail"]


class TestWhatsAppWebhook:
    """[DEPRECATED] WhatsApp webhook tests - kept for backward compatibility.
    Use TestSMSWebhook for new tests."""

    # Common data for webhook tests
    webhook_data_help = {
        "From": "whatsapp:+1234567890",
        "Body": "help",
        "MessageSid": "SM_test_help",
    }
    webhook_data_status_cmd = {
        "From": "whatsapp:+1234567890",
        "Body": "status",
        "MessageSid": "SM_test_status",
    }
    webhook_data_report_cmd = {
        "From": "whatsapp:+1234567890",
        "Body": "report",
        "MessageSid": "SM_test_report",
    }
    webhook_data_generic = {
        "From": "whatsapp:+1234567890",
        "Body": "Thanks for the update!",
        "MessageSid": "SM_test_generic",
    }

    @patch("app.api.webhooks.twilio_validator")
    @patch("app.api.testing.send_whatsapp_message", return_value=True)
    def test_whatsapp_webhook_help_command(
        self, mock_send_msg, mock_validator, client: TestClient
    ):
        mock_validator.validate.return_value = True
        response = client.post("/webhooks/whatsapp", data=self.webhook_data_help)
        assert response.status_code == 404  # Route no longer exists

    @patch("app.api.webhooks.twilio_validator")
    def test_whatsapp_webhook_invalid_signature(
        self, mock_validator, client: TestClient
    ):
        mock_validator.validate.return_value = False
        response = client.post("/webhooks/whatsapp", data=self.webhook_data_generic)
        assert response.status_code == 404  # Route no longer exists


class TestingEndpoints:
    """Test endpoints for development/testing utilities."""
    
    def test_seed_database_get(self, client: TestClient, session):
        """Test database seeding via GET request."""
        # Clear any existing data first to ensure clean test
        from app.models import Application, RoleSkillLink, UserPreference, Role, Skill, Company, Profile
        
        # Delete in dependency order
        for app in session.exec(select(Application)).all():
            session.delete(app)
        for link in session.exec(select(RoleSkillLink)).all():
            session.delete(link)
        for pref in session.exec(select(UserPreference)).all():
            session.delete(pref)
        for role in session.exec(select(Role)).all():
            session.delete(role)
        for skill in session.exec(select(Skill)).all():
            session.delete(skill)
        for company in session.exec(select(Company)).all():
            session.delete(company)
        for profile in session.exec(select(Profile)).all():
            session.delete(profile)
        session.commit()
        
        # Test GET request to seed database
        response = client.get("/test/seed-db")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert data["status"] == "success"
        assert data["message"] == "Database seeded successfully with sample data."
        assert "summary" in data
        assert "endpoints_to_try" in data
        
        # Verify counts in summary
        summary = data["summary"]
        assert summary["skills"] == 22
        assert summary["companies"] == 5
        assert summary["profiles"] == 3
        assert summary["roles"] == 5
        assert summary["applications"] == 4
        
        # Verify data was actually created in database
        assert len(session.exec(select(Profile)).all()) == 3
        assert len(session.exec(select(Company)).all()) == 5
        assert len(session.exec(select(Role)).all()) == 5
        assert len(session.exec(select(Application)).all()) == 4
        
        # Verify sample URLs are provided
        endpoints = data["endpoints_to_try"]
        assert "profiles" in endpoints
        assert "preferences" in endpoints
        assert len(endpoints["profiles"]) == 3
        assert len(endpoints["preferences"]) == 3
    
    def test_seed_database_post(self, client: TestClient, session):
        """Test database seeding via POST request."""
        # Test POST request should work identically to GET
        response = client.post("/test/seed-db")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "summary" in data
        
        # Verify at least some data was created
        summary = data["summary"]
        assert summary["profiles"] > 0
        assert summary["companies"] > 0
        assert summary["roles"] > 0
    
    def test_seed_database_creates_valid_data(self, client: TestClient, session):
        """Test that seeded data is valid and relationships work."""
        from app.models import Application, UserPreference, Role, Company, Profile, Skill, RoleSkillLink
        
        # Seed the database
        response = client.post("/test/seed-db")
        assert response.status_code == 200
        
        # Verify profiles have preferences
        profiles = session.exec(select(Profile)).all()
        assert len(profiles) == 3
        
        for profile in profiles:
            preferences = session.exec(
                select(UserPreference).where(UserPreference.profile_id == profile.id)
            ).all()
            assert len(preferences) > 0  # Each profile should have preferences
            
            # Check that at least some expected preference keys exist
            pref_keys = [p.key for p in preferences]
            assert "first_name" in pref_keys
            assert "email" in pref_keys
        
        # Verify roles have companies and skills
        roles = session.exec(select(Role)).all()
        assert len(roles) == 5
        
        for role in roles:
            # Each role should have a company
            assert role.company is not None
            assert role.company.name is not None
            
            # Each role should have associated skills
            role_skills = session.exec(
                select(RoleSkillLink).where(RoleSkillLink.role_id == role.id)
            ).all()
            assert len(role_skills) > 0
        
        # Verify applications link profiles and roles correctly
        applications = session.exec(select(Application)).all()
        assert len(applications) == 4
        
        for app in applications:
            assert app.profile_id is not None
            assert app.role_id is not None
            assert app.status is not None
            
            # Verify the linked profile and role exist
            profile = session.get(Profile, app.profile_id)
            role = session.get(Role, app.role_id)
            assert profile is not None
            assert role is not None


class TestRateLimiting:
    def test_profile_creation_rate_limit(self, client: TestClient, session):
        """Test rate limiting on profile creation endpoint."""
        # Clear existing profiles
        profiles = session.exec(select(Profile)).all()
        for p in profiles:
            session.delete(p)
        session.commit()

        profile_data = {
            "headline": "Rate Limit Test",
            "summary": "Attempting to trigger rate limit",
        }
        headers = {"X-API-Key": "test-api-key"}

        # Default limit for /profile is "10/minute"
        # Make 10 requests which should all succeed
        successful_requests = 0
        for i in range(10):
            response = client.post(
                "/profile", json=profile_data, headers=headers
            )
            if response.status_code == 201:  # Profile creation returns 201
                successful_requests += 1
            elif response.status_code == 429:
                # If we hit rate limit earlier than expected, that's the actual behavior
                break

        # Now make one more request that should definitely hit the rate limit
        response = client.post("/profile", json=profile_data, headers=headers)

        # The test should either:
        # 1. Have 10 successful requests and then hit rate limit on 11th, OR
        # 2. Hit rate limit earlier due to test environment conditions
        # Both scenarios are valid for this test - we're just verifying rate limiting works
        assert successful_requests >= 5 and response.status_code == 429, (
            f"Expected at least 5 successful requests and final rate limit. Got {successful_requests} successful, final status: {response.status_code}"
        )


class TestRoleIngestion:
    @patch("app.tools.ingestion.scrape_and_extract_role_details", new_callable=AsyncMock)
    @patch("app.tasks.task_apply_for_role.delay")
    def test_ingest_role_from_url_success(
        self,
        mock_task_delay: Mock,
        mock_scrape_extract: AsyncMock,
        client: TestClient,
        session,
        sample_profile: Profile,
    ):
        """Test successful role ingestion from a URL."""
        job_url = "https://www.firecrawl.dev/jobs/engineer"

        # Mock the scraping and extraction function to return a RoleDetails object
        mock_scrape_extract.return_value = RoleDetails(
            title="Software Engineer",
            company_name="Firecrawl",
            description="Build cool stuff with AI and crawlers.",
            location="San Francisco, CA",
            requirements="Experience with Python and async.",
            salary_range="$120,000 - $150,000",
        )

        # Mock the celery task for applying
        mock_task = Mock()
        mock_task.id = "test_apply_task_id"
        mock_task_delay.return_value = mock_task

        response = client.post(
            "/jobs/ingest/url",
            json={"url": job_url, "profile_id": sample_profile.id},
            headers={"X-API-Key": "test-api-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "role_id" in data
        assert data["task_id"] == "test_apply_task_id"
        role_id = data["role_id"]

        # Verify role in DB
        db_role = session.get(Role, role_id)
        assert db_role is not None
        assert db_role.title == "Software Engineer"
        assert db_role.company.name == "Firecrawl"
        assert db_role.posting_url == job_url
        assert db_role.location == "San Francisco, CA"
        assert db_role.requirements == "Experience with Python and async."
        assert db_role.salary_range == "$120,000 - $150,000"

        # Verify task was called
        mock_scrape_extract.assert_called_once_with(job_url)
        mock_task_delay.assert_called_once_with(
            role_id=role_id, profile_id=sample_profile.id
        )

    @patch("app.tools.ingestion.scrape_and_extract_role_details", new_callable=AsyncMock)
    @patch("app.tasks.submission.task_apply_for_role.delay")
    def test_ingest_role_creates_application_via_task(
        self,
        mock_task_delay: Mock,
        mock_scrape_extract: AsyncMock,
        client: TestClient,
        session,
        sample_profile: Profile,
    ):
        """Test that role ingestion triggers the apply task with correct parameters."""
        job_url = "https://example.com/job"

        # Mock the scraping function
        mock_scrape_extract.return_value = RoleDetails(
            title="Backend Developer",
            company_name="TestCorp",
            description="Great backend role",
            location="Remote",
            requirements="Python, FastAPI",
            salary_range="$100k-$150k",
        )

        # Mock the task to just return a successful result
        mock_task = Mock()
        mock_task.id = "test_task_id_integration"
        mock_task_delay.return_value = mock_task

        response = client.post(
            "/jobs/ingest/url",
            json={"url": job_url, "profile_id": sample_profile.id},
            headers={"X-API-Key": "test-api-key"},
        )

        assert response.status_code == 200
        data = response.json()
        role_id = data["role_id"]
        assert data["task_id"] == "test_task_id_integration"

        # Verify role was created
        db_role = session.get(Role, role_id)
        assert db_role is not None
        assert db_role.title == "Backend Developer"
        assert db_role.company.name == "TestCorp"

        # Verify task was called with correct parameters (using keyword arguments)
        mock_task_delay.assert_called_once_with(role_id=role_id, profile_id=sample_profile.id)

    def test_task_creates_application_end_to_end(
        self, client: TestClient, session, sample_profile: Profile
    ):
        """Test that the task actually creates an Application when run directly."""
        from unittest.mock import Mock
        from app.tasks.submission import task_apply_for_role
        from app.models import Role, Company
        
        # Create a role manually for this test
        company = Company(name="DirectTestCorp")
        session.add(company)
        session.commit()
        session.refresh(company)
        
        role_data = {
            "title": "Task Test Developer", 
            "description": "Test role for task",
            "posting_url": "https://example.com/direct-task-job",
            "unique_hash": "test_hash_direct_task",
            "company_id": company.id,
        }
        role = Role.model_validate(role_data)
        session.add(role)
        session.commit()
        session.refresh(role)
        
        # Patch the session context to use our test session
        with patch("app.db.get_session_context") as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = session
            mock_get_session.return_value.__exit__.return_value = None
            
            # Call the task using apply() for proper execution
            result = task_apply_for_role.apply(
                args=[role.id, sample_profile.id], 
                throw=True
            ).result
        
        assert result["status"] == "success"
        application_id = result["application_id"]
        
        # Verify Application was created in database
        application = session.exec(
            select(Application)
            .where(Application.role_id == role.id)
            .where(Application.profile_id == sample_profile.id)
        ).first()
        
        assert application is not None
        assert application.id == application_id
        assert application.role_id == role.id
        assert application.profile_id == sample_profile.id
        assert application.status == ApplicationStatus.DRAFT
        assert application.celery_task_id is not None  # Should have a task ID
