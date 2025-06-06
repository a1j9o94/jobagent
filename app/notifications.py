# app/notifications.py
import os
import logging
from twilio.rest import Client
from twilio.request_validator import RequestValidator
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
WA_FROM = os.getenv("WA_FROM")
WA_TO = os.getenv("WA_TO")

# Initialize Twilio client
twilio_client = None
twilio_validator = None

if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN)
else:
    logger.warning("Twilio credentials not configured")


def send_whatsapp_message(message: str, to_number: str = None) -> bool:
    """Send a WhatsApp message via Twilio."""
    if not twilio_client:
        logger.error("Twilio client not initialized")
        return False

    to_number = to_number or WA_TO
    if not to_number or not WA_FROM:
        logger.error("WhatsApp phone numbers not configured")
        return False

    try:
        message_obj = twilio_client.messages.create(
            body=message, from_=WA_FROM, to=to_number
        )
        logger.info(f"WhatsApp message sent: {message_obj.sid}")
        return True
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {e}")
        return False


def health_check() -> bool:
    """Check if notification service is accessible."""
    return twilio_client is not None
