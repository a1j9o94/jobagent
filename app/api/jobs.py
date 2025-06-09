# app/api/jobs.py
from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from app.db import get_session
from app.models import Role

from .shared import app, get_api_key


@app.post(
    "/jobs/rank/{role_id}",
    summary="Rank a specific role",
    dependencies=[Depends(get_api_key)],
    tags=["Job Processing"],
)
async def trigger_role_ranking(
    role_id: int,
    # background_tasks: BackgroundTasks, # BackgroundTasks not used in current implementation
    profile_id: int = 1,  # Default to profile 1 for now
    session: Session = Depends(get_session),
):
    """Trigger ranking for a specific role."""
    # Verify role exists
    role = session.get(Role, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )

    # Enqueue ranking task
    from app.tasks import task_rank_role  # Local import

    task = task_rank_role.delay(role_id, profile_id)

    return {"status": "queued", "task_id": task.id, "role_id": role_id} 