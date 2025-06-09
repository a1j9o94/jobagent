# app/tasks.py
"""
Celery tasks for the Job Agent system.

This module now uses a modular structure where tasks are organized 
in the app.tasks package. This file maintains backward compatibility
by re-exporting all tasks.
"""

# Import all tasks from the new modular structure
from app.tasks import *

# Re-export for backward compatibility
__all__ = [
    "celery_app",
    "debug_task", 
    "task_rank_role",
    "task_generate_documents",
    "task_submit_application", 
    "task_send_daily_report",
    "task_process_new_roles",
]


