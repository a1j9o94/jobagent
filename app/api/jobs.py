# app/api/jobs.py
from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select
from pydantic import BaseModel, HttpUrl
import logging
from firecrawl import AsyncFirecrawlApp

from app.db import get_session
from app.models import Role, Profile, Company
from .shared import app, get_api_key
from app.tools import process_ingested_role
from app.tools.company import get_or_create_company
from app.tools.utils import generate_unique_hash


class IngestURLRequest(BaseModel):
    url: HttpUrl
    profile_id: int


async def scrape_and_extract_role_details(url: str) -> dict:
    """
    Scrapes a job posting URL using Firecrawl and extracts role details.
    
    For now, this is a placeholder. Pydantic-AI will be integrated later.
    """
    # TODO: Implement Pydantic-AI agent for extraction from markdown
    app = AsyncFirecrawlApp() # Assumes FIRECRAWL_API_KEY is in env
    
    # Scrape the URL, passing only_main_content directly
    scraped_data = await app.scrape_url(url, only_main_content=True)
    
    if not scraped_data or not scraped_data.get('markdown'):
        raise Exception("Failed to scrape job posting or no markdown content found.")

    # Placeholder for extraction logic
    # In a real scenario, we would feed scraped_data['markdown'] to a Pydantic-AI agent
    return {
        "title": "Software Engineer (Extracted)", # Dummy value
        "company_name": "Firecrawl Inc. (Extracted)", # Dummy value
        "description": scraped_data['markdown'],
        "location": "San Francisco, CA", # Dummy value
        "requirements": "Python, FastAPI", # Dummy value
        "salary_range": "$100,000 - $200,000", # Dummy value
        "url": url,
    }


@app.post(
    "/jobs/ingest/url",
    summary="Ingest a new role from a URL",
    dependencies=[Depends(get_api_key)],
    tags=["Job Processing"],
)
async def ingest_role_from_url(
    request: IngestURLRequest,
    session: Session = Depends(get_session),
):
    """
    Scrapes a job posting URL, creates a new Role, and queues it for application.
    """
    try:
        new_role, task_id = await process_ingested_role(
            url=str(request.url), profile_id=request.profile_id, session=session
        )
        return {"status": "success", "role_id": new_role.id, "task_id": task_id}
    except ValueError as e:
        # Handle duplicate role or missing profile errors from the tool
        if "already exists" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except Exception as e:
        logging.error(f"Error in ingest_role_from_url: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Internal server error during role ingestion."
        )


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