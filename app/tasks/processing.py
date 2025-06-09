# app/tasks/processing.py
import logging
from sqlmodel import select

from app.db import get_session_context  
from .shared import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def task_process_new_roles(profile_id: int = 1):  # Added profile_id as arg with default
    """Process newly sourced roles for ranking and application."""
    try:
        from app.models import Role, RoleStatus  # Local import
        from .ranking import task_rank_role  # Local import to avoid circular dependency

        # Using get_session_context for non-FastAPI session management
        with get_session_context() as session:
            # Get unprocessed roles
            # The original query session.query(Role) is SQLAlchemy 1.x style.
            # For SQLModel/SQLAlchemy 2.x style, use session.exec(select(...))
            new_roles_stmt = (
                select(Role).where(Role.status == RoleStatus.SOURCED).limit(10)
            )
            new_roles = session.exec(new_roles_stmt).all()

            processed_count = 0
            for role_obj in new_roles:  # Renamed role to role_obj to avoid conflict
                # Trigger ranking task
                task_rank_role.delay(role_obj.id, profile_id)
                # Update role status to prevent reprocessing
                role_obj.status = RoleStatus.APPLYING
                session.add(role_obj)
                processed_count += 1

            session.commit()  # Commit status changes

            logger.info(
                f"Queued {processed_count} roles for processing for profile {profile_id}"
            )
            return {
                "status": "success",
                "processed": processed_count,
                "profile_id": profile_id,
            }

    except Exception as e:
        logger.error(f"Role processing task failed for profile {profile_id}: {e}")
        return {"status": "error", "message": str(e), "profile_id": profile_id} 