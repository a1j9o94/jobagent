# app/api/webhooks.py
import logging
from fastapi import Request, Response, Depends, HTTPException, status
from sqlmodel import Session, select
from pydantic import HttpUrl
from pydantic_core import ValidationError

from app.db import get_session
from app.models import Application, ApplicationStatus
from app.tools.notifications import send_sms_message
from app.tools.ingestion import process_ingested_role

from .shared import app, limiter, get_original_webhook_url, twilio_validator

logger = logging.getLogger(__name__)


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
                f"Internal URL: {request.url}, "
                f"Signature: {sig}, Signature256: {sig256}"
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

        # --- URL Ingestion Logic ---
        # First, try to see if the message is a URL
        try:
            url = HttpUrl(message_body)
            # It's a valid URL, so let's process it.
            logger.info(f"Received URL via SMS: {url}")

            # For now, default to profile_id=1.
            # TODO: Implement a way to find profile_id from from_number
            profile_id = 1
            
            new_role, task_id = await process_ingested_role(
                url=str(url), profile_id=profile_id, session=session
            )
            
            send_sms_message(
                f"✅ Got it! I've added '{new_role.title}' to your queue. Task ID: {task_id}",
                clean_from_number
            )
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        except ValidationError:
            # Not a valid URL, proceed to process as a command.
            logger.info("Message is not a URL, processing as command.")
        except ValueError as e:
            # Handle errors from process_ingested_role (e.g., duplicates)
            logger.warning(f"Could not process URL {message_body}: {e}")
            send_sms_message(f"🤔 Hmm, I couldn't process that job. It might already be in your queue.", clean_from_number)
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error processing URL from SMS: {e}", exc_info=True)
            send_sms_message(f"😬 Apologies, I ran into an error trying to process that job.", clean_from_number)
            return Response(status_code=status.HTTP_204_NO_CONTENT)

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