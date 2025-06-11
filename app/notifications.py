"""
Backward compatibility module for notifications.
Re-exports from app.tools.notifications.
"""

from app.tools.notifications import (
    send_sms_message,
    send_whatsapp_message,
    health_check,
    twilio_client,
    twilio_validator,
    SMS_FROM,
    SMS_TO,
    WA_FROM,
    WA_TO,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
)

__all__ = [
    "send_sms_message",
    "send_whatsapp_message", 
    "health_check",
    "twilio_client",
    "twilio_validator",
    "SMS_FROM",
    "SMS_TO",
    "WA_FROM", 
    "WA_TO",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
] 