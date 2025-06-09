# app/tools/ingestion.py
import logging
from sqlmodel import Session, select
from firecrawl import AsyncFirecrawlApp
from pydantic_ai import Agent

from app.models import Role, Profile, RoleDetails
from app.tools.company import get_or_create_company
from app.tools.utils import generate_unique_hash
from app.tasks import task_apply_for_role


logger = logging.getLogger(__name__)


# Create the agent as a module global so it's instantiated only once
# This agent is responsible for extracting structured job details from raw text.
role_extraction_agent = Agent(
    "openai:gpt-4o",  # You can swap this with other models like "anthropic:claude-3.5-sonnet"
    result_type=RoleDetails,
    system_prompt="""
    You are an expert at extracting structured information from job postings.
    Given the markdown content of a job posting, extract the required fields.
    If a field is not present in the text, you can leave it as null.
    """,
)


async def scrape_and_extract_role_details(url: str) -> RoleDetails:
    """
    Scrapes a job posting URL using Firecrawl and extracts role details using a PydanticAI agent.
    """
    app = AsyncFirecrawlApp()  # Assumes FIRECRAWL_API_KEY is in env

    logger.info(f"Scraping URL: {url}")
    scraped_data = await app.scrape_url(url, only_main_content=True)

    if not scraped_data or not scraped_data.get("markdown"):
        raise Exception("Failed to scrape job posting or no markdown content found.")

    markdown_content = scraped_data["markdown"]
    logger.info(f"Successfully scraped {len(markdown_content)} characters from {url}. Extracting details...")
    
    # Run the agent to extract structured data
    result = await role_extraction_agent.run(markdown_content)
    
    # Return the structured RoleDetails object directly
    return result.data


async def process_ingested_role(url: str, profile_id: int, session: Session) -> tuple[Role, str]:
    """
    Takes a URL, scrapes it, creates a role, and queues it for application.

    Returns:
        A tuple containing the newly created Role and the Celery task ID.
    
    Raises:
        ValueError: If the profile is not found or the role already exists.
    """
    profile = session.get(Profile, profile_id)
    if not profile:
        raise ValueError(f"Profile not found with id: {profile_id}")

    logger.info(f"Processing URL for ingestion: {url}")
    role_details = await scrape_and_extract_role_details(url)

    company = get_or_create_company(session, name=role_details.company_name)
    
    unique_hash = generate_unique_hash(
        company_name=company.name, title=role_details.title
    )

    existing_role = session.exec(
        select(Role).where(Role.unique_hash == unique_hash)
    ).first()

    if existing_role:
        raise ValueError(f"Role already exists with id {existing_role.id}")

    # Use model_dump() here to convert the Pydantic model to a dict for Role creation
    role_data = {
        **role_details.model_dump(),
        "company_id": company.id,
        "posting_url": url,
        "unique_hash": unique_hash,
    }
    new_role = Role.model_validate(role_data)

    session.add(new_role)
    session.commit()
    session.refresh(new_role)

    task = task_apply_for_role.delay(role_id=new_role.id, profile_id=profile_id)
    logger.info(f"Created role {new_role.id} and dispatched task {task.id}")

    return new_role, task.id 