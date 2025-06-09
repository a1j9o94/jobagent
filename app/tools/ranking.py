# app/tools/ranking.py
import logging
from pydantic_ai import Agent

from app.models import RankResult, Role, Profile, RoleStatus
from app.db import get_session_context

logger = logging.getLogger(__name__)

# Initialize the LLM agent
ranking_agent = Agent(
    "openai:gpt-4o-mini",
    result_type=RankResult,
    system_prompt="""You are a career advisor evaluating job role matches.
    Analyze the job description and candidate profile to provide an accurate fit score.
    Consider skills, experience level, company culture, and role requirements.""",
)


async def rank_role(role_id: int, profile_id: int) -> RankResult:
    """Uses an LLM to rank a role against a profile."""
    with get_session_context() as session:
        role = session.get(Role, role_id)
        profile = session.get(Profile, profile_id)

        if not role or not profile:
            logger.error(f"Role {role_id} or Profile {profile_id} not found")
            return RankResult(score=0.0, rationale="Role or profile not found")

        try:
            # Prepare the context for the LLM
            prompt = f"""
            Job Title: {role.title}
            Company: {role.company.name}
            Job Description: {role.description}
            
            Candidate Profile:
            Headline: {profile.headline}
            Summary: {profile.summary}
            
            Please provide a match score and rationale.
            """

            result = await ranking_agent.run(prompt)

            # Update the role with ranking results
            role.rank_score = result.data.score
            role.rank_rationale = result.data.rationale
            role.status = RoleStatus.RANKED
            session.commit()

            logger.info(f"Ranked role {role_id}: {result.data.score}")
            return result.data

        except Exception as e:
            logger.error(f"LLM ranking failed: {e}")
            return RankResult(score=0.0, rationale=f"LLM call failed: {str(e)}") 