# app/api_server.py
"""
FastAPI application for the Job Agent system.

This module now uses a modular structure where endpoints are organized 
in the app.api package. This file maintains backward compatibility
by re-exporting the main app instance.
"""

# Import the FastAPI app from the new modular structure
from app.api import app

# Re-export for backward compatibility and main.py
__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
