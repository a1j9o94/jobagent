"""
API module - organized endpoints for the Job Agent API.

This module provides a clean separation of endpoints while maintaining
backward compatibility with existing imports.
"""

from .shared import (
    app,
    limiter,
    get_api_key,
    redis_health_check,
    get_original_webhook_url,
)

# Import all endpoint modules to register routes
from . import system
from . import profile  
from . import applications
from . import jobs
from . import webhooks
from . import testing

# Re-export the FastAPI app for main.py and tests
__all__ = [
    "app", 
    "limiter", 
    "get_api_key", 
    "redis_health_check",
    "get_original_webhook_url",
] 