# app/tools/preferences.py
import logging
from datetime import datetime, UTC
from typing import Optional
from sqlmodel import select

from app.models import UserPreference
from app.db import get_session_context

logger = logging.getLogger(__name__)


def get_user_preference(profile_id: int, key: str) -> Optional[str]:
    """Get a user preference value, or None if not found."""
    with get_session_context() as session:
        pref = session.exec(
            select(UserPreference)
            .where(UserPreference.profile_id == profile_id)
            .where(UserPreference.key == key)
        ).first()
        return pref.value if pref else None


def save_user_preference(profile_id: int, key: str, value: str) -> None:
    """Save or update a user preference."""
    with get_session_context() as session:
        # Try to find existing preference
        pref = session.exec(
            select(UserPreference)
            .where(UserPreference.profile_id == profile_id)
            .where(UserPreference.key == key)
        ).first()

        if pref:
            pref.value = value
            pref.last_updated = datetime.now(UTC)
        else:
            pref = UserPreference(
                profile_id=profile_id,
                key=key,
                value=value,
                last_updated=datetime.now(UTC),
            )
            session.add(pref)

        session.commit()
        logger.info(f"Saved preference {key} for profile {profile_id}") 