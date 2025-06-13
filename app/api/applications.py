# app/api/applications.py
from typing import Optional, List, Dict, Any
from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from app.db import get_session
from app.models import Application, ApplicationStatus, Role

from .shared import app 


@app.get(
    "/applications",
    summary="Get application status",
    tags=["Applications"],
)
async def get_applications(
    status_filter: Optional[str] = None, session: Session = Depends(get_session)
) -> Dict[str, List[Dict[str, Any]]]:  # Added return type hint
    """Get list of applications with optional status filtering."""
    query = select(Application).join(
        Role
    )  # Added join to access Role attributes easily

    if status_filter:
        try:
            status_enum = ApplicationStatus(status_filter)
            query = query.where(Application.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter: {status_filter}. Valid statuses are: {[s.value for s in ApplicationStatus]}",
            )

    applications_db = session.exec(query).all()

    # Construct response with role details
    apps_response = []
    for app_db in applications_db:
        app_data = {
            "id": app_db.id,
            "role_title": app_db.role.title
            if app_db.role
            else "N/A",  # Handle if role is somehow None
            "company_name": app_db.role.company.name
            if app_db.role and app_db.role.company
            else "N/A",
            "status": app_db.status.value,  # Return string value of enum
            "created_at": app_db.created_at.isoformat() if app_db.created_at else None,
            "submitted_at": app_db.submitted_at.isoformat()
            if app_db.submitted_at
            else None,
        }
        apps_response.append(app_data)

    return {"applications": apps_response} 