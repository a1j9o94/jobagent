# tests/conftest.py
# import pytest
import os
import asyncio
from typing import Generator, AsyncGenerator
import pytest
from unittest.mock import patch
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlmodel import Session, create_engine, SQLModel
from fastapi.testclient import TestClient

from app.api_server import app
from app.db import get_session
from app.models import (
    Profile,
    Company,
    Role,
    Application,
    UserPreference,
    ApplicationStatus,
    RoleStatus,
)

# Test environment setup - use the existing containers from docker-compose
os.environ.update(
    {
        "PROFILE_INGEST_API_KEY": "test-api-key",
        "ENCRYPTION_KEY": "test_encryption_key_32_characters_long",
        "OPENAI_API_KEY": "test-openai-key",
        "S3_ENDPOINT_URL": "http://localhost:9000",
        "AWS_ACCESS_KEY_ID": "testminioadmin",
        "AWS_SECRET_ACCESS_KEY": "testminioadmin",
        "S3_BUCKET_NAME": "test-job-agent-documents",
        "TWILIO_ACCOUNT_SID": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "TWILIO_AUTH_TOKEN": "test_twilio_auth_token_here",
        "SMS_FROM": "+14155238886",
        "SMS_TO": "+12345678900",
        "WA_FROM": "whatsapp:+14155238886",  # Keep for backward compatibility
        "WA_TO": "whatsapp:+12345678900",
        # Use the containers that are already running in docker-compose
        "DATABASE_URL": "postgresql+psycopg2://test_user:test_password@test_db:5432/test_jobagent",
        "REDIS_URL": "redis://test_redis:6379/0",
    }
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_engine():
    """Create a test database engine using the docker-compose database."""
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url, echo=False)

    # Create all tables
    SQLModel.metadata.create_all(engine)

    yield engine

    # Note: We don't drop tables here since other tests might be running
    # The database container will be recreated between test runs
    engine.dispose()


@pytest.fixture(scope="function")
def session(test_engine) -> Generator[Session, None, None]:
    """Create a test database session. Rolls back changes after each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    db_session = Session(bind=connection)

    yield db_session

    db_session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(session: Session) -> Generator[TestClient, None, None]:
    """Create a test client with database dependency override."""

    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# Mock fixtures for external services
@pytest.fixture(autouse=True)
def mock_external_services():
    """Mock external services to prevent real API calls during tests."""
    with (
        patch("app.tools.ranking_agent") as mock_ranking_agent,
        patch("app.tools.resume_agent") as mock_resume_agent,
        patch("app.tools.upload_file_to_storage") as mock_upload,
        patch("app.tools.send_sms_message") as mock_sms,
        patch("app.tools.send_whatsapp_message") as mock_whatsapp,
    ):
        # Set up default mock returns
        mock_sms.return_value = True
        mock_whatsapp.return_value = True
        mock_upload.return_value = "http://mock-storage/file.pdf"

        yield {
            "ranking_agent": mock_ranking_agent,
            "resume_agent": mock_resume_agent,
            "upload_file_to_storage": mock_upload,
            "send_sms_message": mock_sms,
            "send_whatsapp_message": mock_whatsapp,
        }


@pytest.fixture
def sample_profile_data() -> dict:
    return {
        "headline": "Senior Software Engineer | Python & Cloud",
        "summary": "Experienced engineer specializing in building scalable backend systems.",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }


@pytest.fixture
def sample_profile(session: Session, sample_profile_data: dict) -> Profile:
    """Create a sample profile for testing."""
    profile = Profile(**sample_profile_data)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@pytest.fixture
def sample_company_data() -> dict:
    return {"name": "TechCorp Inc.", "website": "https://techcorp.com"}


@pytest.fixture
def sample_company(session: Session, sample_company_data: dict) -> Company:
    """Create a sample company for testing."""
    company = Company(**sample_company_data)
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


@pytest.fixture
def sample_role_data(sample_company: Company) -> dict:
    return {
        "title": "Senior Python Developer",
        "description": "We are looking for an experienced Python developer...",
        "posting_url": "https://techcorp.com/jobs/senior-python-dev",
        "unique_hash": "test_hash_123",
        "company_id": sample_company.id,
        "created_at": datetime.now(UTC),
    }


@pytest.fixture
def sample_role(
    session: Session, sample_role_data: dict, sample_company: Company
) -> Role:
    """Create a sample role for testing."""
    if "company_id" not in sample_role_data and sample_company:
        sample_role_data["company_id"] = sample_company.id
    role = Role(**sample_role_data)
    session.add(role)
    session.commit()
    session.refresh(role)
    return role


@pytest.fixture
def sample_application_data(sample_role: Role, sample_profile: Profile) -> dict:
    return {
        "role_id": sample_role.id,
        "profile_id": sample_profile.id,
        "status": ApplicationStatus.DRAFT,
    }


@pytest.fixture
def sample_application(session: Session, sample_application_data: dict) -> Application:
    application = Application.model_validate(sample_application_data)
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


@pytest.fixture
def sample_user_preference_data(sample_profile: Profile) -> dict:
    return {
        "profile_id": sample_profile.id,
        "key": "salary_expectation",
        "value": "150000",
        "last_updated": datetime.now(UTC),
    }


@pytest.fixture
def sample_user_preference(
    session: Session, sample_user_preference_data: dict
) -> UserPreference:
    preference = UserPreference(**sample_user_preference_data)
    session.add(preference)
    session.commit()
    session.refresh(preference)
    return preference


# If you need an async session fixture for async db operations in tests:
@pytest.fixture(scope="session")
async def async_test_engine():
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def async_session(async_test_engine) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(async_test_engine) as session:
        yield session
