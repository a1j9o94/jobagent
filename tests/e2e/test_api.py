# tests/e2e/test_api.py
import pytest
import json # For health check response parsing
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock # Added AsyncMock for Celery task

from app.models import Profile, Role, Application, ApplicationStatus, UserPreference # Added Application, ApplicationStatus, UserPreference
from app.tasks import celery_app # For disabling celery tasks during tests if needed

# Temporarily disable Celery eager mode for these tests if tasks are not meant to execute immediately
# or ensure tasks are properly mocked if their execution affects test outcomes.
# This can be done globally in conftest.py or per test module/class if needed.
# For now, assuming tasks are either mocked or their immediate execution is fine.

class TestHealthEndpoint:
    def test_health_check_success(self, client: TestClient):
        """Test that the health check endpoint returns 200 when all services are healthy."""
        # In conftest, we set up mock env vars. Actual health depends on these or live services.
        # For true E2E against live services (docker-compose up), this would hit them.
        # For unit/integration tests with TestClient, mocks for external services are typical.
        # Assuming db is up via test_engine.
        # Mock redis, storage, notifications health checks if they are not actually running or are flaky.
        with patch('app.api_server.db_health_check', return_value=True), \
             patch('app.api_server.redis_health_check', return_value=True), \
             patch('app.api_server.storage_health_check', return_value=True), \
             patch('app.api_server.notification_health_check', return_value=True):
            
            response = client.get("/health")
            assert response.status_code == 200
            
            data = response.json()
            assert data["status"] == "ok"
            assert "services" in data
            assert data["services"]["database"] is True
            assert data["services"]["redis"] is True
            assert data["services"]["object_storage"] is True
            assert data["services"]["notifications"] is True

    def test_health_check_degraded(self, client: TestClient):
        with patch('app.api_server.db_health_check', return_value=True), \
             patch('app.api_server.redis_health_check', return_value=False), \
             patch('app.api_server.storage_health_check', return_value=True), \
             patch('app.api_server.notification_health_check', return_value=True):
            response = client.get("/health")
            # FastAPI returns Response object; .json() might fail if content isn't valid JSON after str()
            # The api_server.py converts the health_status dict to string for non-200 responses.
            # We need to parse this string back to JSON.
            assert response.status_code == 206 # Partial Content for degraded
            data = json.loads(response.content.decode('utf-8')) # Parse the string content
            assert data["status"] == "degraded"
            assert data["services"]["redis"] is False

class TestProfileIngestion:
    def test_ingest_profile_success_new(self, client: TestClient, session): # Added session to clear data
        """Test successful profile ingestion for a new profile."""
        # Ensure no profile exists initially for this specific test
        profiles = session.query(Profile).all()
        for p in profiles: session.delete(p)
        session.commit()

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
            headers={"X-API-Key": "test-api-key"} # From conftest.py os.environ
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "profile_id" in data
        profile_id = data["profile_id"]

        # Verify in DB
        db_profile = session.get(Profile, profile_id)
        assert db_profile is not None
        assert db_profile.headline == profile_data["headline"]
        pref = session.query(UserPreference).filter_by(profile_id=profile_id, key="email").first()
        assert pref is not None
        assert pref.value == "john.doe@example.com"


    def test_ingest_profile_update_existing(self, client: TestClient, sample_profile: Profile, session):
        """Test updating an existing profile."""
        updated_data = {
            "headline": "Updated Headline",
            "summary": "Updated summary",
            "preferences": {"email": "updated.john.doe@example.com"}
        }
        
        response = client.post(
            "/ingest/profile", # This endpoint assumes a single profile system and updates or creates
            json=updated_data,
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["profile_id"] == sample_profile.id # Should update the existing one

        session.refresh(sample_profile) # Refresh from DB
        assert sample_profile.headline == "Updated Headline"
        updated_pref = session.query(UserPreference).filter_by(profile_id=sample_profile.id, key="email").first()
        assert updated_pref is not None
        assert updated_pref.value == "updated.john.doe@example.com"

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
        assert response.status_code == 403 # Due to APIKeyHeader auto_error=True

class TestApplicationsEndpoint:
    def test_get_applications_empty(self, client: TestClient, session):
        """Test getting applications when none exist."""
        # Clear existing applications for this test
        apps = session.query(Application).all()
        for app_obj in apps: session.delete(app_obj)
        session.commit()

        response = client.get(
            "/applications",
            headers={"X-API-Key": "test-api-key"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["applications"] == []

    def test_get_applications_with_data_and_filter(self, client: TestClient, session, sample_application: Application):
        """Test getting applications with status filter."""
        # sample_application fixture creates an app with status DRAFT (or as defined)
        # Ensure sample_application is committed and its status is what we expect to filter by.
        draft_status_str = ApplicationStatus.DRAFT.value
        session.refresh(sample_application.role)
        session.refresh(sample_application.role.company)
        
        response = client.get(
            f"/applications?status_filter={draft_status_str}",
            headers={"X-API-Key": "test-api-key"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["applications"]) >= 1
        assert data["applications"][0]["status"] == draft_status_str
        assert data["applications"][0]["id"] == sample_application.id
        
    def test_get_applications_invalid_filter(self, client: TestClient):
        """Test getting applications with invalid status filter."""
        response = client.get(
            "/applications?status_filter=invalid_status",
            headers={"X-API-Key": "test-api-key"}
        )
        assert response.status_code == 400
        assert "Invalid status filter" in response.json()["detail"]

class TestRoleRanking:
    # Patch the celery task to prevent actual execution or to check if it was called
    @patch('app.api_server.task_rank_role.delay', new_callable=AsyncMock) 
    def test_trigger_role_ranking_success(self, mock_task_delay, client: TestClient, sample_role: Role):
        """Test triggering role ranking successfully."""
        mock_task_delay.return_value = Mock(id="test_task_id") # Mock the task object returned by .delay()
        
        response = client.post(
            f"/jobs/rank/{sample_role.id}",
            json={"profile_id": 1}, # profile_id is a query param in API, not JSON body in design doc
                                   # Correcting to match API server implementation: profile_id in path or query
                                   # The API server takes profile_id as a query parameter (defaulting to 1)
                                   # So, no JSON body is needed here based on current API server.
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["task_id"] == "test_task_id"
        assert data["role_id"] == sample_role.id
        mock_task_delay.assert_called_once_with(sample_role.id, 1) # profile_id defaults to 1

    def test_trigger_role_ranking_not_found(self, client: TestClient):
        """Test triggering role ranking for non-existent role."""
        response = client.post(
            "/jobs/rank/99999",
            headers={"X-API-Key": "test-api-key"}
        )
        assert response.status_code == 404

class TestWhatsAppWebhook:
    # Common data for webhook tests
    webhook_data_help = {"From": "whatsapp:+1234567890", "Body": "help"}
    webhook_data_status_cmd = {"From": "whatsapp:+1234567890", "Body": "status"}
    webhook_data_report_cmd = {"From": "whatsapp:+1234567890", "Body": "report"}
    webhook_data_generic = {"From": "whatsapp:+1234567890", "Body": "Thanks for the update!"}

    @patch('app.api_server.validate_twilio_webhook', return_value=True)
    @patch('app.api_server.send_whatsapp_message', return_value=True)
    def test_whatsapp_webhook_help_command(self, mock_send_msg, mock_validate, client: TestClient):
        response = client.post("/webhooks/whatsapp", data=self.webhook_data_help)
        assert response.status_code == 204 # No Content
        mock_validate.assert_called_once()
        mock_send_msg.assert_called_once()
        assert "Job Agent Commands" in mock_send_msg.call_args[0][0]

    @patch('app.api_server.validate_twilio_webhook', return_value=True)
    @patch('app.api_server.send_whatsapp_message', return_value=True)
    def test_whatsapp_webhook_status_command(self, mock_send_msg, mock_validate, client: TestClient, session):
        # Setup: create an application that needs user info
        # Need a profile and role first from fixtures or created here.
        # For simplicity, assume sample_application fixture can be used and its status modified.
        # Or, more robustly, create the specific state needed.
        # Since the endpoint queries for NEEDS_USER_INFO, let's ensure one exists.
        # (Actual creation of such an app might involve more steps not tested here but in unit tests for tools)
        
        response = client.post("/webhooks/whatsapp", data=self.webhook_data_status_cmd)
        assert response.status_code == 204
        mock_validate.assert_called_once()
        mock_send_msg.assert_called_once()
        # The message content depends on DB state; here we check it was called.
        # Example: assert "applications need your input" in mock_send_msg.call_args[0][0]

    @patch('app.api_server.validate_twilio_webhook', return_value=True)
    @patch('app.api_server.send_whatsapp_message', return_value=True) # Mock sending confirmation
    @patch('app.api_server.task_send_daily_report.delay') # Mock the Celery task call
    def test_whatsapp_webhook_report_command(self, mock_task_delay, mock_send_msg, mock_validate, client: TestClient):
        response = client.post("/webhooks/whatsapp", data=self.webhook_data_report_cmd)
        assert response.status_code == 204
        mock_validate.assert_called_once()
        mock_task_delay.assert_called_once()
        mock_send_msg.assert_called_once_with("📊Generating your daily report, it will arrive shortly!", self.webhook_data_report_cmd["From"])


    @patch('app.api_server.validate_twilio_webhook', return_value=True)
    @patch('app.api_server.send_whatsapp_message', return_value=True)
    def test_whatsapp_webhook_generic_message(self, mock_send_msg, mock_validate, client: TestClient):
        response = client.post("/webhooks/whatsapp", data=self.webhook_data_generic)
        assert response.status_code == 204
        mock_validate.assert_called_once()
        mock_send_msg.assert_called_once()
        assert "Got your response!" in mock_send_msg.call_args[0][0]

    @patch('app.api_server.validate_twilio_webhook', return_value=False) # Simulate invalid signature
    def test_whatsapp_webhook_invalid_signature(self, mock_validate, client: TestClient):
        response = client.post("/webhooks/whatsapp", data=self.webhook_data_generic)
        assert response.status_code == 403
        mock_validate.assert_called_once()
        assert "Invalid webhook signature" in response.json()["detail"]

class TestRateLimiting:
    def test_profile_ingestion_rate_limit(self, client: TestClient, session):
        """Test rate limiting on profile ingestion endpoint."""
        # Clear existing profile to ensure create path is hit consistently for this test count
        profiles = session.query(Profile).all()
        for p in profiles: session.delete(p)
        session.commit()

        profile_data = {"headline": "Rate Limit Test", "summary": "Attempting to trigger rate limit"}
        headers = {"X-API-Key": "test-api-key"}
        
        # Default limit in api_server.py for /ingest/profile is "5/minute"
        for i in range(6):
            response = client.post("/ingest/profile", json=profile_data, headers=headers)
            if i < 5:
                assert response.status_code == 200, f"Request {i+1} failed unexpectedly: {response.text}"
            else:
                assert response.status_code == 429, f"Request {i+1} did not trigger rate limit as expected" 