# app/tasks/__init__.py
"""
Tasks module - organized Celery tasks for the Job Agent system.

This module provides a clean separation of task types while maintaining
backward compatibility with existing imports.
"""

from .shared import celery_app, debug_task

# Import all task modules to register tasks
from .ranking import task_rank_role
from .documents import task_generate_documents
from .submission import task_submit_application, task_apply_for_role
from .reporting import task_send_daily_report
from .processing import task_process_new_roles

# Re-export all tasks for backward compatibility
__all__ = [
    "celery_app",
    "debug_task",
    "task_rank_role",
    "task_generate_documents", 
    "task_submit_application",
    "task_apply_for_role",
    "task_send_daily_report",
    "task_process_new_roles",
] 