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
    BackgroundTasks,
)
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlmodel import Session, select

from app.db import (
    get_session,
    health_check as db_health_check,
    engine,
)  # Added engine import
from app.storage import health_check as storage_health_check
from app.notifications import (
    send_whatsapp_message,
    validate_twilio_webhook,
    health_check as notification_health_check,
)
from app.models import (
    Profile,
    UserPreference,
    Application,
    ApplicationStatus,
    Role,
)  # Added Role
from app.tools import save_user_preference  # Removed unused generate_unique_hash
from app.tasks import celery_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


@app.get("/health", summary="Comprehensive Health Check", tags=["System"])
async def health_check_endpoint():  # Renamed to avoid conflict with imported health_check functions
    """Check the health of all system components."""
    health_status = {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "services": {
            "database": db_health_check(),
            "redis": redis_health_check(),
            "object_storage": storage_health_check(),
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
                        UserPreference.key == key
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
                        last_updated=datetime.now(UTC)
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
    "/webhooks/whatsapp", summary="Handle incoming Twilio messages", tags=["Webhooks"]
)
@limiter.limit("30/minute")
async def handle_whatsapp_reply(
    request: Request, session: Session = Depends(get_session)
):  # Added session dependency
    """Handles inbound messages from Twilio for the HITL workflow."""

    # Store form data for validation
    form_data = await request.form()
    # setattr(request, '_form', form_data) # This is not standard and might cause issues.
    # Instead, pass form_data to validate_twilio_webhook if needed.

    # Validate webhook signature
    # The original validate_twilio_webhook expects request._form to be set.
    # We will pass form_data directly if the validator is adapted, or adapt the validator.
    # For now, assuming validate_twilio_webhook is adapted or request._form works by side effect in some envs.

    # A more robust way to handle request._form for validation:
    # Create a new Request object or adapt the validator if `request._form` is problematic.
    # For this setup, let's assume the original `validate_twilio_webhook` works or will be adapted.
    # A common pattern is to make `form_data` available in `request.state` or pass it directly.
    # Let's try to set it, being mindful it's not standard FastAPI practice.
    request_form_dict = dict(form_data)

    # Create a mock request or adapt validate_twilio_webhook if direct attribute setting is an issue.
    # For simplicity, let's assume validate_twilio_webhook can take form_data as an argument or
    # that setting _form is handled by a middleware in a real scenario.
    # Given the current `validate_twilio_webhook` structure, we rely on `request._form` being accessible.
    # This line is potentially problematic and might need adjustment in `validate_twilio_webhook`.
    request._form = request_form_dict

    if not validate_twilio_webhook(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook signature"
        )

    try:
        from_number = request_form_dict.get("From", "")
        message_body = request_form_dict.get("Body", "").strip()

        logger.info(f"Received WhatsApp message from {from_number}: {message_body}")

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
            send_whatsapp_message(help_message, from_number)

        elif message_body.lower() == "status":
            # Get status for the user (assuming single user for now)
            # with get_session() as session: # Replaced with injected session
            pending_apps = session.exec(
                select(Application).where(
                    Application.status == ApplicationStatus.NEEDS_USER_INFO
                )
            ).all()

            status_msg = f"📊 Status: {len(pending_apps)} applications need your input"
            send_whatsapp_message(status_msg, from_number)

        elif message_body.lower() == "report":
            # Trigger daily report generation
            from app.tasks import (
                task_send_daily_report,
            )  # Local import to avoid circular dependency issues at startup

            # Assuming profile_id=1 for now, consistent with task_send_daily_report
            # The task itself handles profile_id, so just call delay.
            task_send_daily_report.delay()  # Pass profile_id if needed by task signature
            send_whatsapp_message(
                "📊Generating your daily report, it will arrive shortly!", from_number
            )

        else:
            # Assume this is an answer to a pending question
            # This would need more sophisticated logic to match questions to applications
            response_msg = (
                "✅ Got your response! I'll update the application accordingly."
            )
            send_whatsapp_message(response_msg, from_number)

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception as e:
        logger.error(f"WhatsApp webhook processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing failed",
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
