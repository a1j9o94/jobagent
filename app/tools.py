# app/tools.py
"""
Business logic tools for the Job Agent system.

This module now uses a modular structure where tools are organized 
in the app.tools package. This file maintains backward compatibility
by re-exporting all tools.
"""

# Import all tools from the new modular structure
from app.tools import *

# Re-export for backward compatibility
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
]


