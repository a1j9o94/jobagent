# app/api/testing.py
import os
import logging
import random
import string
from datetime import datetime
from fastapi import Request, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import Profile, Company, Role, Application, RoleStatus, ApplicationStatus
from app.tools import generate_unique_hash, ranking_agent
from app.tasks import task_generate_documents
from app.tools.notifications import send_sms_message, send_whatsapp_message

from .shared import app

logger = logging.getLogger(__name__)


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
    test_message = f"✅ This is a test message from the Job Agent API, sent at {datetime.now().isoformat()}."

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
    test_message = f"✅ This is a test message from the Job Agent API, sent at {datetime.now().isoformat()}."

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