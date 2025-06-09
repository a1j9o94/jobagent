# app/tools/__init__.py
"""
Tools module - organized business logic functions for the Job Agent system.

This module provides a clean separation of business logic while maintaining
backward compatibility with existing imports.
"""

# Import all tools from their respective modules
from .utils import generate_unique_hash
from .ranking import ranking_agent, rank_role
from .documents import resume_agent, draft_and_upload_documents
from .submission import submit_application
from .reporting import generate_daily_report
from .preferences import get_user_preference, save_user_preference
from .pdf_utils import markdown_to_html, render_to_pdf
from .notifications import send_sms_message, send_whatsapp_message
from .storage import upload_file_to_storage, ensure_bucket_exists, health_check as storage_health_check

# Re-export all tools for backward compatibility
__all__ = [
    "generate_unique_hash",
    "ranking_agent",
    "rank_role",
    "resume_agent", 
    "draft_and_upload_documents",
    "submit_application",
    "generate_daily_report",
    "get_user_preference",
    "save_user_preference",
    "markdown_to_html",
    "render_to_pdf",
    "send_sms_message",
    "send_whatsapp_message",
    "upload_file_to_storage",
    "ensure_bucket_exists", 
    "storage_health_check",
] 