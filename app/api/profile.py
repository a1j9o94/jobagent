# app/api/profile.py
import logging
from datetime import datetime, UTC
from typing import Dict, Any, Optional
from fastapi import Request, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db import get_session
from app.models import Profile, UserPreference

from .shared import app, limiter, get_api_key

logger = logging.getLogger(__name__)


@app.post(
    "/ingest/profile",
    summary="Ingest a user's full profile",
    dependencies=[Depends(get_api_key)],
    tags=["Data Ingestion"],
)
@limiter.limit("5/minute")
async def ingest_profile_data(
    request: Request,
    profile_data: Dict[str, Any],
    session: Session = Depends(get_session),
):
    """A protected endpoint to upload or update the user's professional profile."""
    try:
        # Check if profile exists (assuming single user for now)
        existing_profile = session.exec(select(Profile)).first()

        profile_id: Optional[int] = None  # ensure profile_id is defined

        if existing_profile:
            # Update existing profile
            existing_profile.headline = profile_data.get(
                "headline", existing_profile.headline
            )
            existing_profile.summary = profile_data.get(
                "summary", existing_profile.summary
            )
            existing_profile.updated_at = datetime.now(UTC)
            session.add(existing_profile)  # ensure changes are staged
            session.commit()  # Commit the profile update first
            profile_id = existing_profile.id
        else:
            # Create new profile
            now = datetime.now(UTC)
            new_profile = Profile(
                headline=profile_data.get("headline", ""),
                summary=profile_data.get("summary", ""),
                created_at=now,
                updated_at=now,
            )
            session.add(new_profile)
            session.commit()  # Commit to get ID
            session.refresh(new_profile)
            profile_id = new_profile.id

        # Save any preferences included in the profile data
        # Save preferences directly in the same session to avoid transaction isolation issues
        preferences = profile_data.get("preferences", {})
        if profile_id is not None:  # Check if profile_id was set
            for key, value in preferences.items():
                # Check if preference already exists
                existing_pref = session.exec(
                    select(UserPreference).where(
                        UserPreference.profile_id == profile_id,
                        UserPreference.key == key,
                    )
                ).first()

                if existing_pref:
                    existing_pref.value = str(value)
                    existing_pref.last_updated = datetime.now(UTC)
                else:
                    new_pref = UserPreference(
                        profile_id=profile_id,
                        key=key,
                        value=str(value),
                        last_updated=datetime.now(UTC),
                    )
                    session.add(new_pref)

            # Commit all changes together
            session.commit()

        # No additional commit needed since everything is handled above
        logger.info(f"Profile {profile_id} ingested successfully")

        return {
            "status": "success",
            "message": "Profile ingested successfully.",
            "profile_id": profile_id,
        }

    except Exception as e:
        logger.error(f"Profile ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Profile ingestion failed: {str(e)}",
        ) 