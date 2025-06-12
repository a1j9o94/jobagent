# app/api/profile.py
import logging
from datetime import datetime, UTC
from typing import Dict, Any, Optional, List
from fastapi import Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
from pydantic import BaseModel

from app.db import get_session
from app.models import Profile, UserPreference, Application, Role

from .shared import app, limiter, get_api_key

logger = logging.getLogger(__name__)


# --- Pydantic Models for API ---
class ProfileCreate(BaseModel):
    headline: str
    summary: str


class ProfileUpdate(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None


class PreferenceCreate(BaseModel):
    key: str
    value: str


class PreferenceUpdate(BaseModel):
    value: str


# --- Profile CRUD Routes ---
@app.get(
    "/profile/{profile_id}",
    summary="Get profile details with preferences",
    tags=["Profile"],
)
async def get_profile(
    profile_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    """Get profile details with preferences. Returns JSON by default, HTML if Accept header includes text/html."""
    profile = session.get(Profile, profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    # Get all preferences for this profile
    preferences = session.exec(
        select(UserPreference).where(UserPreference.profile_id == profile_id)
    ).all()
    
    preferences_dict = {pref.key: pref.value for pref in preferences}
    preferences_list = [
        {
            "id": pref.id,
            "key": pref.key,
            "value": pref.value,
            "last_updated": pref.last_updated,
        }
        for pref in preferences
    ]
    
    # Check if client wants HTML response
    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header:
        # Build preferences HTML
        preferences_html = ""
        if preferences_dict:
            preferences_html = "<div class='preferences'><h2>Preferences</h2><ul>"
            for key, value in preferences_dict.items():
                preferences_html += f"<li><strong>{key}:</strong> {value}</li>"
            preferences_html += "</ul></div>"
        
        # Return HTML template response
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Profile - {profile.headline}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                .profile-header {{ background: #f4f4f4; padding: 20px; border-radius: 8px; }}
                .profile-summary {{ margin: 20px 0; }}
                .preferences {{ margin: 20px 0; background: #f9f9f9; padding: 15px; border-radius: 8px; }}
                .preferences ul {{ list-style-type: none; padding: 0; }}
                .preferences li {{ margin: 8px 0; }}
                .meta-info {{ color: #666; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="profile-header">
                <h1>{profile.headline}</h1>
                <div class="meta-info">
                    Profile ID: {profile.id} | 
                    Created: {profile.created_at.strftime('%Y-%m-%d %H:%M:%S')} | 
                    Updated: {profile.updated_at.strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
            <div class="profile-summary">
                <h2>Summary</h2>
                <p>{profile.summary}</p>
            </div>
            {preferences_html}
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    
    # Return JSON response with preferences
    return {
        "id": profile.id,
        "headline": profile.headline,
        "summary": profile.summary,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
        "preferences": preferences_list,
        "preferences_dict": preferences_dict,  # Convenient key-value format
    }


@app.post(
    "/profile",
    summary="Create a new profile",
    dependencies=[Depends(get_api_key)],
    tags=["Profile"],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def create_profile(
    request: Request,
    profile_data: ProfileCreate,
    session: Session = Depends(get_session),
):
    """Create a new profile explicitly."""
    try:
        now = datetime.now(UTC)
        new_profile = Profile(
            headline=profile_data.headline,
            summary=profile_data.summary,
            created_at=now,
            updated_at=now,
        )
        session.add(new_profile)
        session.commit()
        session.refresh(new_profile)

        logger.info(f"Profile {new_profile.id} created successfully")

        return {
            "status": "created",
            "message": "Profile created successfully.",
            "profile_id": new_profile.id,
        }

    except Exception as e:
        logger.error(f"Profile creation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Profile creation failed: {str(e)}",
        )


@app.put(
    "/profile/{profile_id}",
    summary="Update an existing profile",
    dependencies=[Depends(get_api_key)],
    tags=["Profile"],
)
@limiter.limit("10/minute")
async def update_profile(
    profile_id: int,
    request: Request,
    profile_data: ProfileUpdate,
    session: Session = Depends(get_session),
):
    """Update an existing profile."""
    profile = session.get(Profile, profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    try:
        # Update only provided fields
        if profile_data.headline is not None:
            profile.headline = profile_data.headline
        if profile_data.summary is not None:
            profile.summary = profile_data.summary
        
        profile.updated_at = datetime.now(UTC)
        session.add(profile)
        session.commit()

        logger.info(f"Profile {profile_id} updated successfully")

        return {
            "status": "updated",
            "message": "Profile updated successfully.",
            "profile_id": profile_id,
        }

    except Exception as e:
        logger.error(f"Profile update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Profile update failed: {str(e)}",
        )


@app.delete(
    "/profile/{profile_id}",
    summary="Delete a profile",
    dependencies=[Depends(get_api_key)],
    tags=["Profile"],
)
async def delete_profile(profile_id: int, session: Session = Depends(get_session)):
    """Delete a profile and associated preferences and applications.
    
    Note: Roles are not deleted as they can be shared across profiles.
    Only applications (which link profiles to roles) are deleted.
    """
    profile = session.get(Profile, profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    # Get associated data
    applications = session.exec(select(Application).where(Application.profile_id == profile_id)).all()
    preferences = session.exec(select(UserPreference).where(UserPreference.profile_id == profile_id)).all()
    
    # Delete applications (profile-role links)
    for application in applications:
        session.delete(application)
    
    # Delete preferences
    for preference in preferences:
        session.delete(preference)
    
    # Delete the profile itself
    session.delete(profile)
    session.commit()
    
    return {
        "status": "deleted",
        "message": "Profile deleted successfully.",
        "profile_id": profile_id,
    }




# --- UserPreference CRUD Routes ---
@app.get(
    "/profile/{profile_id}/preferences",
    summary="Get all preferences for a profile",
    tags=["User Preferences"],
)
async def get_profile_preferences(
    profile_id: int,
    session: Session = Depends(get_session),
):
    """Get all preferences for a specific profile."""
    # Verify profile exists
    profile = session.get(Profile, profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    preferences = session.exec(
        select(UserPreference).where(UserPreference.profile_id == profile_id)
    ).all()
    
    return {
        "profile_id": profile_id,
        "preferences": [
            {
                "id": pref.id,
                "key": pref.key,
                "value": pref.value,
                "last_updated": pref.last_updated,
            }
            for pref in preferences
        ]
    }


@app.get(
    "/profile/{profile_id}/preferences/{key}",
    summary="Get a specific preference",
    tags=["User Preferences"],
)
async def get_preference(
    profile_id: int,
    key: str,
    session: Session = Depends(get_session),
):
    """Get a specific preference by key."""
    preference = session.exec(
        select(UserPreference).where(
            UserPreference.profile_id == profile_id,
            UserPreference.key == key
        )
    ).first()
    
    if not preference:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preference not found"
        )
    
    return {
        "id": preference.id,
        "profile_id": preference.profile_id,
        "key": preference.key,
        "value": preference.value,
        "last_updated": preference.last_updated,
    }


@app.post(
    "/profile/{profile_id}/preferences",
    summary="Create a new preference",
    dependencies=[Depends(get_api_key)],
    tags=["User Preferences"],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
async def create_preference(
    profile_id: int,
    request: Request,
    preference_data: PreferenceCreate,
    session: Session = Depends(get_session),
):
    """Create a new preference for a profile."""
    # Verify profile exists
    profile = session.get(Profile, profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    # Check if preference already exists
    existing_pref = session.exec(
        select(UserPreference).where(
            UserPreference.profile_id == profile_id,
            UserPreference.key == preference_data.key
        )
    ).first()
    
    if existing_pref:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Preference with this key already exists"
        )
    
    try:
        new_preference = UserPreference(
            profile_id=profile_id,
            key=preference_data.key,
            value=preference_data.value,
            last_updated=datetime.now(UTC),
        )
        session.add(new_preference)
        session.commit()

        logger.info(f"Preference {preference_data.key} created for profile {profile_id}")

        return {
            "status": "created",
            "message": "Preference created successfully.",
            "key": preference_data.key,
            "profile_id": profile_id,
        }

    except Exception as e:
        logger.error(f"Preference creation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preference creation failed: {str(e)}",
        )


@app.put(
    "/profile/{profile_id}/preferences/{key}",
    summary="Update a preference",
    dependencies=[Depends(get_api_key)],
    tags=["User Preferences"],
)
@limiter.limit("20/minute")
async def update_preference(
    profile_id: int,
    key: str,
    request: Request,
    preference_data: PreferenceUpdate,
    session: Session = Depends(get_session),
):
    """Update an existing preference."""
    preference = session.exec(
        select(UserPreference).where(
            UserPreference.profile_id == profile_id,
            UserPreference.key == key
        )
    ).first()
    
    if not preference:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preference not found"
        )
    
    try:
        preference.value = preference_data.value
        preference.last_updated = datetime.now(UTC)
        session.add(preference)
        session.commit()

        logger.info(f"Preference {key} updated for profile {profile_id}")

        return {
            "status": "updated",
            "message": "Preference updated successfully.",
            "key": key,
            "profile_id": profile_id,
        }

    except Exception as e:
        logger.error(f"Preference update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preference update failed: {str(e)}",
        )


@app.delete(
    "/profile/{profile_id}/preferences/{key}",
    summary="Delete a preference",
    dependencies=[Depends(get_api_key)],
    tags=["User Preferences"],
)
async def delete_preference(
    profile_id: int,
    key: str,
    session: Session = Depends(get_session),
):
    """Delete a preference."""
    preference = session.exec(
        select(UserPreference).where(
            UserPreference.profile_id == profile_id,
            UserPreference.key == key
        )
    ).first()
    
    if not preference:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preference not found"
        )
    
    try:
        session.delete(preference)
        session.commit()

        logger.info(f"Preference {key} deleted for profile {profile_id}")

        return {
            "status": "deleted",
            "message": "Preference deleted successfully.",
            "key": key,
            "profile_id": profile_id,
        }

    except Exception as e:
        logger.error(f"Preference deletion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preference deletion failed: {str(e)}",
        ) 