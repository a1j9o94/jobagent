# app/api_server.py
import os
import logging
from datetime import datetime, UTC
from typing import Dict, Any, Optional, List
from fastapi import (
    FastAPI,
    Request,
    Response,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlmodel import Session, select
import random
import string

from app.db import (
    get_session,
    health_check as db_health_check,
)  # Added engine import
from app.storage import health_check as storage_health_check
from app.notifications import (
    send_sms_message,
    send_whatsapp_message,  # Keep for backward compatibility in test endpoint
    health_check as notification_health_check,
)
from app.models import (
    Profile,
    Application,
    ApplicationStatus,
    Role,
    Company,
    RoleStatus,
)  # Added Role, Company, and RoleStatus
from app.tools import (
    generate_unique_hash,
    ranking_agent,
)  # Removed unused generate_unique_hash
from app.tasks import celery_app, task_generate_documents
from twilio.request_validator import RequestValidator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_original_webhook_url(request: Request) -> str:
    """
    Reconstruct the original URL that Twilio used, accounting for reverse proxy forwarding.

    Fly.io (and other reverse proxies) terminate HTTPS and forward HTTP requests internally.
    This causes signature validation to fail because Twilio calculates signatures using
    the original HTTPS URL, but FastAPI sees the internal HTTP URL.
    """
    # Check for forwarded protocol headers
    proto = (
        request.headers.get("X-Forwarded-Proto")
        or request.headers.get("X-Forwarded-Protocol")
        or request.headers.get("X-Scheme")
        or "https"  # Default to HTTPS for production webhooks
    )

    # Get the host (should be the external hostname)
    host = (
        request.headers.get("X-Forwarded-Host")
        or request.headers.get("Host")
        or request.url.hostname
    )

    # Construct the original URL
    path_with_query = str(request.url.path)
    if request.url.query:
        path_with_query += f"?{request.url.query}"

    original_url = f"{proto}://{host}{path_with_query}"

    # Debug logging for troubleshooting
    logger.debug(
        f"URL reconstruction: proto={proto}, host={host}, "
        f"path={path_with_query}, original={original_url}, internal={request.url}"
    )

    return original_url


# Initialize FastAPI app
app = FastAPI(
    title="Job Application Agent API",
    description="Automated job application system with AI-powered matching",
    version="1.0.0",
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
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
if TWILIO_AUTH_TOKEN:
    twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN)
else:
    twilio_validator = None
    logger.warning("TWILIO_AUTH_TOKEN not set, webhook validation will be skipped.")

# Base URL for API examples - automatically detects environment
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Add this near your other environment variable definitions
STORAGE_PROVIDER = os.getenv(
    "STORAGE_PROVIDER", "minio"
)  # Default to minio for local dev


async def get_api_key(api_key: str = Depends(API_KEY_HEADER)):
    if api_key != PROFILE_INGEST_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key"
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


# Root route, that just shows if the app is running, the list of routes, and an example of how to use the ingest endpoint
@app.get("/", summary="Root route", tags=["System"])
async def root():
    return {
        "status": "ok",
        "message": "Job Agent API is running",
        "routes": [
            {
                "path": "/ingest/profile",
                "method": "POST",
                "description": "Ingest a user's full profile",
            }
        ],
        "example": {
            "method": "POST",
            "url": f"{API_BASE_URL}/ingest/profile",
            "headers": {"X-API-Key": "your-api-key"},
            "body": {
                "headline": "Software Engineer",
                "summary": "I am a software engineer with 5 years of experience in Python and Django",
            },
        },
    }


@app.get("/health", summary="Comprehensive Health Check", tags=["System"])
async def health_check_endpoint():  # Renamed to avoid conflict with imported health_check functions
    """Check the health of all system components."""

    # Dynamically check storage based on the environment
    is_storage_healthy = True  # Assume healthy for managed services like Tigris
    if STORAGE_PROVIDER == "minio":
        is_storage_healthy = storage_health_check()

    health_status = {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "services": {
            "database": db_health_check(),
            "redis": redis_health_check(),
            "object_storage": is_storage_healthy,
            "notifications": notification_health_check(),
        },
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
        import json

        return Response(
            content=json.dumps(health_status),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
        )
    elif health_status["status"] == "degraded":
        # Return JSON response properly for degraded status
        import json

        response = Response(
            content=json.dumps(health_status),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type="application/json",
        )
        return response

    return health_status


@app.post(
    "/ingest/profile",
    summary="Ingest a user's full profile",
    dependencies=[Depends(get_api_key)],
    tags=["Data Ingestion"],
)
@limiter.limit("5/minute")
async def ingest_profile_data(
    request: Request,
    profile_data: Dict[str, Any],
    session: Session = Depends(get_session),
):
    """A protected endpoint to upload or update the user's professional profile."""
    try:
        # Check if profile exists (assuming single user for now)
        existing_profile = session.exec(select(Profile)).first()

        profile_id: Optional[int] = None  # ensure profile_id is defined

        if existing_profile:
            # Update existing profile
            existing_profile.headline = profile_data.get(
                "headline", existing_profile.headline
            )
            existing_profile.summary = profile_data.get(
                "summary", existing_profile.summary
            )
            existing_profile.updated_at = datetime.now(UTC)
            session.add(existing_profile)  # ensure changes are staged
            session.commit()  # Commit the profile update first
            profile_id = existing_profile.id
        else:
            # Create new profile
            now = datetime.now(UTC)
            new_profile = Profile(
                headline=profile_data.get("headline", ""),
                summary=profile_data.get("summary", ""),
                created_at=now,
                updated_at=now,
            )
            session.add(new_profile)
            session.commit()  # Commit to get ID
            session.refresh(new_profile)
            profile_id = new_profile.id

        # Save any preferences included in the profile data
        # Save preferences directly in the same session to avoid transaction isolation issues
        preferences = profile_data.get("preferences", {})
        if profile_id is not None:  # Check if profile_id was set
            for key, value in preferences.items():
                # Create UserPreference directly instead of using save_user_preference
                # which creates its own session context
                from app.models import UserPreference

                # Check if preference already exists
                existing_pref = session.exec(
                    select(UserPreference).where(
                        UserPreference.profile_id == profile_id,
                        UserPreference.key == key,
                    )
                ).first()

                if existing_pref:
                    existing_pref.value = str(value)
                    existing_pref.last_updated = datetime.now(UTC)
                else:
                    new_pref = UserPreference(
                        profile_id=profile_id,
                        key=key,
                        value=str(value),
                        last_updated=datetime.now(UTC),
                    )
                    session.add(new_pref)

            # Commit all changes together
            session.commit()

        # No additional commit needed since everything is handled above
        logger.info(f"Profile {profile_id} ingested successfully")

        return {
            "status": "success",
            "message": "Profile ingested successfully.",
            "profile_id": profile_id,
        }

    except Exception as e:
        logger.error(f"Profile ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Profile ingestion failed: {str(e)}",
        )


@app.post(
    "/webhooks/sms", summary="Handle incoming Twilio SMS messages", tags=["Webhooks"]
)
@limiter.limit("30/minute")
async def handle_sms_reply(request: Request, session: Session = Depends(get_session)):
    """Handles inbound SMS messages from Twilio for the HITL workflow."""
    if not twilio_validator:
        logger.error("Twilio validator not initialized. Cannot process webhook.")
        # Return a 204 to prevent Twilio from retrying, but log the error.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Reconstruct the original HTTPS URL that Twilio used for signature calculation
    url = get_original_webhook_url(request)
    sig = request.headers.get("X-Twilio-Signature", "")
    sig256 = request.headers.get("X-Twilio-Signature-256", "")

    valid = False
    try:
        # Decide how to grab the body based on content type
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            body = await request.body()  # raw bytes
            valid = twilio_validator.validate(
                url, body, sig
            ) or twilio_validator.validate(url, body, sig256)
        else:
            form = await request.form()
            form_dict = dict(form)
            valid = twilio_validator.validate(
                url, form_dict, sig
            ) or twilio_validator.validate(url, form_dict, sig256)

        if not valid:
            logger.error(
                f"Invalid Twilio signature. "
                f"Original URL: {url}, "
                f"Internal URL: {request.url}",
                f"Signature: {sig}, Signature256: {sig256}",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid Twilio signature. This could mean the request was tampered with or is not from Twilio. Please ensure you are using valid Twilio credentials and the request is properly signed.",
            )

        # Get form data for business logic, re-using if already read
        if "form_dict" in locals():
            request_form_dict = form_dict
        elif "body" in locals():
            import json

            request_form_dict = json.loads(body)
        else:
            # This case should not be reached if validation logic is correct
            # but as a fallback, we can try to read the form.
            form = await request.form()
            request_form_dict = dict(form)

        from_number = request_form_dict.get("From", "")
        message_body = request_form_dict.get("Body", "").strip()
        message_sid = request_form_dict.get("MessageSid", "N/A")

        # Sanitize phone number (remove any channel prefixes like 'whatsapp:')
        clean_from_number = (
            from_number.replace("whatsapp:", "").replace("sms:", "").strip()
        )

        logger.info(f"SMS webhook OK. SID: {message_sid}, From: {clean_from_number}")

        # Basic message processing
        if message_body.lower() in ["help", "h"]:
            help_message = """
                🤖 Job Agent Commands:
                • 'status' - Check application status
                • 'report' - Get daily report
                • 'stop' - Pause applications
                • 'start' - Resume applications
                • Or answer any pending questions
            """
            send_sms_message(help_message, clean_from_number)

        elif message_body.lower() == "status":
            # Get status for the user (assuming single user for now)
            pending_apps = session.exec(
                select(Application).where(
                    Application.status == ApplicationStatus.NEEDS_USER_INFO
                )
            ).all()

            status_msg = f"📊 Status: {len(pending_apps)} applications need your input"
            send_sms_message(status_msg, clean_from_number)

        elif message_body.lower() == "report":
            # Trigger daily report generation
            from app.tasks import (
                task_send_daily_report,
            )  # Local import to avoid circular dependency issues at startup

            task_send_daily_report.delay()
            send_sms_message(
                "📊Generating your daily report, it will arrive shortly!",
                clean_from_number,
            )

        else:
            # Assume this is an answer to a pending question
            response_msg = (
                "✅ Got your response! I'll update the application accordingly."
            )
            send_sms_message(response_msg, clean_from_number)

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException as http_exc:
        logger.warning(
            f"Invalid Twilio signature for original URL: {url} (internal: {request.url}). "
            f"Details: {http_exc.detail}"
        )
        raise http_exc  # Re-raise the exception to let FastAPI handle it

    except Exception as e:
        logger.error(f"SMS webhook processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}",
        )


@app.post(
    "/jobs/rank/{role_id}",
    summary="Rank a specific role",
    dependencies=[Depends(get_api_key)],
    tags=["Job Processing"],
)
async def trigger_role_ranking(
    role_id: int,
    # background_tasks: BackgroundTasks, # BackgroundTasks not used in current implementation
    profile_id: int = 1,  # Default to profile 1 for now
    session: Session = Depends(get_session),
):
    """Trigger ranking for a specific role."""
    # Verify role exists
    role = session.get(Role, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )

    # Enqueue ranking task
    from app.tasks import task_rank_role  # Local import

    task = task_rank_role.delay(role_id, profile_id)

    return {"status": "queued", "task_id": task.id, "role_id": role_id}


@app.get(
    "/applications",
    summary="Get application status",
    dependencies=[Depends(get_api_key)],
    tags=["Applications"],
)
async def get_applications(
    status_filter: Optional[str] = None, session: Session = Depends(get_session)
) -> Dict[str, List[Dict[str, Any]]]:  # Added return type hint
    """Get list of applications with optional status filtering."""
    query = select(Application).join(
        Role
    )  # Added join to access Role attributes easily

    if status_filter:
        try:
            status_enum = ApplicationStatus(status_filter)
            query = query.where(Application.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter: {status_filter}. Valid statuses are: {[s.value for s in ApplicationStatus]}",
            )

    applications_db = session.exec(query).all()

    # Construct response with role details
    apps_response = []
    for app_db in applications_db:
        app_data = {
            "id": app_db.id,
            "role_title": app_db.role.title
            if app_db.role
            else "N/A",  # Handle if role is somehow None
            "company_name": app_db.role.company.name
            if app_db.role and app_db.role.company
            else "N/A",
            "status": app_db.status.value,  # Return string value of enum
            "created_at": app_db.created_at.isoformat() if app_db.created_at else None,
            "submitted_at": app_db.submitted_at.isoformat()
            if app_db.submitted_at
            else None,
        }
        apps_response.append(app_data)

    return {"applications": apps_response}


@app.get("/test/upload", summary="Test file upload to storage", tags=["Testing"])
@app.post("/test/upload", summary="Test file upload to storage", tags=["Testing"])
async def test_storage_upload(session: Session = Depends(get_session)):
    """
    A temporary endpoint to test document generation and upload.
    This creates a dummy profile, company, role, and application,
    then triggers the document generation task.
    """
    try:
        # 1. Create a dummy Company if it doesn't exist
        company_name = "TestCorp"
        company = session.exec(
            select(Company).where(Company.name == company_name)
        ).first()
        if not company:
            company = Company.model_validate(
                {"name": company_name, "website": "http://testcorp.com"}
            )
            session.add(company)
            session.commit()
            session.refresh(company)

        # 2. Create a dummy Profile if it doesn't exist
        profile = session.exec(select(Profile).limit(1)).first()
        if not profile:
            profile = Profile.model_validate(
                {"headline": "Chief Testing Officer", "summary": "I test things."}
            )
            session.add(profile)
            session.commit()
            session.refresh(profile)

        # 3. Create a dummy Role
        random_suffix = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=6)
        )
        test_url = f"http://testcorp.com/jobs/{random_suffix}"
        test_title = f"Principal Test Engineer {random_suffix}"

        role = Role.model_validate(
            {
                "title": test_title,
                "description": "A test role for ensuring uploads work.",
                "posting_url": test_url,
                "unique_hash": generate_unique_hash(test_title, test_url),
                "status": RoleStatus.SOURCED,
                "company_id": company.id,
            }
        )
        session.add(role)
        session.commit()
        session.refresh(role)

        # 4. Create a dummy Application
        application = Application.model_validate(
            {
                "role_id": role.id,
                "profile_id": profile.id,
                "status": ApplicationStatus.DRAFT,
            }
        )
        session.add(application)
        session.commit()
        session.refresh(application)

        # 5. Trigger the document generation task
        task = task_generate_documents.delay(application.id)

        return {
            "status": "success",
            "message": "Document generation task has been queued.",
            "application_id": application.id,
            "task_id": task.id,
        }
    except Exception as e:
        logger.error(f"Test upload endpoint failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to trigger test upload: {e}"
        )


@app.get("/test/openai", summary="Test OpenAI API connectivity", tags=["Testing"])
@app.post("/test/openai", summary="Test OpenAI API connectivity", tags=["Testing"])
async def test_openai_connectivity():
    """
    A temporary endpoint to test direct connectivity and authentication with the OpenAI API.
    Supports both GET and POST methods.
    """
    try:
        # Use the existing ranking_agent to perform a simple, direct query
        prompt = "Give me a one-sentence summary of the three laws of robotics."
        result = await ranking_agent.run(prompt)
        logger.info(f"OpenAI test successful. Response: {result.data.rationale}")
        return {
            "status": "success",
            "message": "OpenAI API call was successful.",
            "response": result.data.rationale,
        }
    except Exception as e:
        logger.error(f"OpenAI connectivity test failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to OpenAI API: {e}",
        )


@app.get("/test/sms", summary="Test sending an SMS message", tags=["Testing"])
@app.post("/test/sms", summary="Test sending an SMS message", tags=["Testing"])
async def test_sms_message(request: Request):
    """
    A temporary endpoint to test sending an SMS message via Twilio.
    This will send a message to the SMS_TO number configured in your environment.
    """
    test_message = f"✅ This is a test message from the Job Agent API, sent at {datetime.now(UTC).isoformat()}."

    try:
        to_number = os.getenv("SMS_TO")
        if not to_number:
            raise ValueError("SMS_TO environment variable is not set.")

        success = send_sms_message(test_message, to_number)

        if success:
            logger.info(f"Successfully sent test SMS message to {to_number}")
            return {
                "status": "success",
                "message": f"Test message sent to {to_number}.",
            }
        else:
            raise HTTPException(
                status_code=500, detail="Failed to send message. Check server logs."
            )

    except Exception as e:
        logger.error(f"SMS test endpoint failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send SMS message: {e}")


@app.get(
    "/test/whatsapp",
    summary="Test sending a WhatsApp message (DEPRECATED)",
    tags=["Testing"],
)
@app.post(
    "/test/whatsapp",
    summary="Test sending a WhatsApp message (DEPRECATED)",
    tags=["Testing"],
)
async def test_whatsapp_message(request: Request):
    """
    [DEPRECATED] A temporary endpoint to test sending a WhatsApp message via Twilio.
    Use /test/sms instead. This endpoint is kept for backward compatibility.
    """
    test_message = f"✅ This is a test message from the Job Agent API, sent at {datetime.now(UTC).isoformat()}."

    try:
        to_number = os.getenv("WA_TO")
        if not to_number:
            raise ValueError("WA_TO environment variable is not set.")

        success = send_whatsapp_message(test_message, to_number)

        if success:
            logger.info(f"Successfully sent test WhatsApp message to {to_number}")
            return {
                "status": "success",
                "message": f"Test message sent to {to_number}.",
            }
        else:
            raise HTTPException(
                status_code=500, detail="Failed to send message. Check server logs."
            )

    except Exception as e:
        logger.error(f"WhatsApp test endpoint failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to send WhatsApp message: {e}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
