# app/api/testing.py
import os
import logging
import random
import string
from datetime import datetime
from fastapi import Request, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import (
    Profile, Company, Role, Application, RoleStatus, ApplicationStatus,
    UserPreference, Skill, RoleSkillLink
)
from app.tools import generate_unique_hash, ranking_agent
from app.tasks import task_generate_documents
from app.tools.notifications import send_sms_message, send_whatsapp_message

from .shared import app

logger = logging.getLogger(__name__)


@app.get("/test/upload", summary="Test file upload to storage", tags=["Testing"])
@app.post("/test/upload", summary="Test file upload to storage", tags=["Testing"])
async def test_storage_upload(session: Session = Depends(get_session)):
    """
    A temporary endpoint to test document generation and upload.
    This creates a dummy profile, company, role, and application,
    then triggers the document generation task.
    """
    try:
        # 1. Create a dummy Company if it doesn't exist
        company_name = "TestCorp"
        company = session.exec(
            select(Company).where(Company.name == company_name)
        ).first()
        if not company:
            company = Company.model_validate(
                {"name": company_name, "website": "http://testcorp.com"}
            )
            session.add(company)
            session.commit()
            session.refresh(company)

        # 2. Create a dummy Profile if it doesn't exist
        profile = session.exec(select(Profile).limit(1)).first()
        if not profile:
            profile = Profile.model_validate(
                {"headline": "Chief Testing Officer", "summary": "I test things."}
            )
            session.add(profile)
            session.commit()
            session.refresh(profile)

        # 3. Create a dummy Role
        random_suffix = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=6)
        )
        test_url = f"http://testcorp.com/jobs/{random_suffix}"
        test_title = f"Principal Test Engineer {random_suffix}"

        role = Role.model_validate(
            {
                "title": test_title,
                "description": "A test role for ensuring uploads work.",
                "posting_url": test_url,
                "unique_hash": generate_unique_hash(test_title, test_url),
                "status": RoleStatus.SOURCED,
                "company_id": company.id,
            }
        )
        session.add(role)
        session.commit()
        session.refresh(role)

        # 4. Create a dummy Application
        application = Application.model_validate(
            {
                "role_id": role.id,
                "profile_id": profile.id,
                "status": ApplicationStatus.DRAFT,
            }
        )
        session.add(application)
        session.commit()
        session.refresh(application)

        # 5. Trigger the document generation task
        task = task_generate_documents.delay(application.id)

        return {
            "status": "success",
            "message": "Document generation task has been queued.",
            "application_id": application.id,
            "task_id": task.id,
        }
    except Exception as e:
        logger.error(f"Test upload endpoint failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to trigger test upload: {e}"
        )


@app.get("/test/openai", summary="Test OpenAI API connectivity", tags=["Testing"])
@app.post("/test/openai", summary="Test OpenAI API connectivity", tags=["Testing"])
async def test_openai_connectivity():
    """
    A temporary endpoint to test direct connectivity and authentication with the OpenAI API.
    Supports both GET and POST methods.
    """
    try:
        # Use the existing ranking_agent to perform a simple, direct query
        prompt = "Give me a one-sentence summary of the three laws of robotics."
        result = await ranking_agent.run(prompt)
        logger.info(f"OpenAI test successful. Response: {result.data.rationale}")
        return {
            "status": "success",
            "message": "OpenAI API call was successful.",
            "response": result.data.rationale,
        }
    except Exception as e:
        logger.error(f"OpenAI connectivity test failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to OpenAI API: {e}",
        )


@app.get("/test/sms", summary="Test sending an SMS message", tags=["Testing"])
@app.post("/test/sms", summary="Test sending an SMS message", tags=["Testing"])
async def test_sms_message(request: Request):
    """
    A temporary endpoint to test sending an SMS message via Twilio.
    This will send a message to the SMS_TO number configured in your environment.
    """
    test_message = f"✅ This is a test message from the Job Agent API, sent at {datetime.now().isoformat()}."

    try:
        to_number = os.getenv("SMS_TO")
        if not to_number:
            raise ValueError("SMS_TO environment variable is not set.")

        success = send_sms_message(test_message, to_number)

        if success:
            logger.info(f"Successfully sent test SMS message to {to_number}")
            return {
                "status": "success",
                "message": f"Test message sent to {to_number}.",
            }
        else:
            raise HTTPException(
                status_code=500, detail="Failed to send message. Check server logs."
            )

    except Exception as e:
        logger.error(f"SMS test endpoint failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send SMS message: {e}")


@app.get(
    "/test/whatsapp",
    summary="Test sending a WhatsApp message (DEPRECATED)",
    tags=["Testing"],
)
@app.post(
    "/test/whatsapp",
    summary="Test sending a WhatsApp message (DEPRECATED)",
    tags=["Testing"],
)
async def test_whatsapp_message(request: Request):
    """
    [DEPRECATED] A temporary endpoint to test sending a WhatsApp message via Twilio.
    Use /test/sms instead. This endpoint is kept for backward compatibility.
    """
    test_message = f"✅ This is a test message from the Job Agent API, sent at {datetime.now().isoformat()}."

    try:
        to_number = os.getenv("WA_TO")
        if not to_number:
            raise ValueError("WA_TO environment variable is not set.")

        success = send_whatsapp_message(test_message, to_number)

        if success:
            logger.info(f"Successfully sent test WhatsApp message to {to_number}")
            return {
                "status": "success",
                "message": f"Test message sent to {to_number}.",
            }
        else:
            raise HTTPException(
                status_code=500, detail="Failed to send message. Check server logs."
            )

    except Exception as e:
        logger.error(f"WhatsApp test endpoint failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to send WhatsApp message: {e}"
        )


@app.get("/test/seed-db", summary="Seed database with sample data", tags=["Testing"])
@app.post("/test/seed-db", summary="Seed database with sample data", tags=["Testing"])
async def test_seed_database(session: Session = Depends(get_session)):
    """
    Populate the database with sample data for development/testing.
    This creates profiles, companies, roles, skills, and applications.
    """
    try:
        logger.info("Starting database seeding...")
        
        # Clear existing data (optional - be careful in production!)
        logger.info("Clearing existing data...")
        session.exec(select(Application)).all()
        for app in session.exec(select(Application)).all():
            session.delete(app)
        
        for link in session.exec(select(RoleSkillLink)).all():
            session.delete(link)
            
        for pref in session.exec(select(UserPreference)).all():
            session.delete(pref)
            
        for role in session.exec(select(Role)).all():
            session.delete(role)
            
        for skill in session.exec(select(Skill)).all():
            session.delete(skill)
            
        for company in session.exec(select(Company)).all():
            session.delete(company)
            
        for profile in session.exec(select(Profile)).all():
            session.delete(profile)
            
        session.commit()
        
        # Create Skills
        logger.info("Creating skills...")
        skills_data = [
            "Python", "JavaScript", "TypeScript", "React", "FastAPI", "Django",
            "PostgreSQL", "Redis", "Docker", "AWS", "GCP", "Kubernetes",
            "Machine Learning", "Data Analysis", "REST APIs", "GraphQL",
            "Git", "CI/CD", "Linux", "SQL", "NoSQL", "MongoDB"
        ]
        
        skills = []
        for skill_name in skills_data:
            skill = Skill(name=skill_name)
            skills.append(skill)
            session.add(skill)
        
        session.commit()
        
        # Create Companies
        logger.info("Creating companies...")
        companies_data = [
            {"name": "TechCorp Inc", "website": "https://techcorp.com"},
            {"name": "DataFlow Solutions", "website": "https://dataflow.io"},
            {"name": "CloudNative Systems", "website": "https://cloudnative.dev"},
            {"name": "AI Innovations Lab", "website": "https://ailab.com"},
            {"name": "DevTools Pro", "website": "https://devtools.pro"}
        ]
        
        companies = []
        for company_data in companies_data:
            company = Company.model_validate(company_data)
            companies.append(company)
            session.add(company)
        
        session.commit()
        
        # Create Profiles with Preferences
        logger.info("Creating profiles...")
        profiles_data = [
            {
                "profile": {
                    "headline": "Senior Full-Stack Developer | Python & React Expert",
                    "summary": "Passionate full-stack developer with 8+ years of experience building scalable web applications. Expert in Python, React, and cloud technologies. Love solving complex problems and mentoring junior developers."
                },
                "preferences": {
                    "first_name": "Alex", "last_name": "Johnson", "email": "alex.johnson@email.com",
                    "phone": "+1-555-0101", "location": "San Francisco, CA", 
                    "linkedin": "https://linkedin.com/in/alexjohnson", "github": "https://github.com/alexjohnson",
                    "desired_salary": "$140,000 - $180,000", "work_mode": "remote"
                }
            },
            {
                "profile": {
                    "headline": "Data Scientist & ML Engineer | AI/ML Expert",
                    "summary": "Data scientist with expertise in machine learning, deep learning, and statistical analysis. 5 years of experience turning data into actionable insights. Proficient in Python, TensorFlow, and cloud ML platforms."
                },
                "preferences": {
                    "first_name": "Sarah", "last_name": "Chen", "email": "sarah.chen@email.com",
                    "phone": "+1-555-0102", "location": "Seattle, WA",
                    "linkedin": "https://linkedin.com/in/sarahchen", "github": "https://github.com/sarahchen",
                    "desired_salary": "$130,000 - $170,000", "work_mode": "hybrid"
                }
            },
            {
                "profile": {
                    "headline": "DevOps Engineer | Cloud Infrastructure Specialist",
                    "summary": "DevOps engineer specializing in cloud infrastructure, CI/CD pipelines, and container orchestration. 6 years of experience with AWS, Kubernetes, and infrastructure as code. Passionate about automation and reliability."
                },
                "preferences": {
                    "first_name": "Marcus", "last_name": "Williams", "email": "marcus.williams@email.com",
                    "phone": "+1-555-0103", "location": "Austin, TX",
                    "linkedin": "https://linkedin.com/in/marcuswilliams", "github": "https://github.com/marcuswilliams",
                    "desired_salary": "$120,000 - $160,000", "work_mode": "remote"
                }
            }
        ]
        
        profiles = []
        for profile_data in profiles_data:
            # Create profile
            now = datetime.now()
            profile = Profile(
                headline=profile_data["profile"]["headline"],
                summary=profile_data["profile"]["summary"],
                created_at=now,
                updated_at=now
            )
            session.add(profile)
            session.commit()  # Commit to get ID
            session.refresh(profile)
            profiles.append(profile)
            
            # Create preferences
            for key, value in profile_data["preferences"].items():
                pref_data = {
                    "profile_id": profile.id,
                    "key": key,
                    "value": str(value),
                    "last_updated": now
                }
                preference = UserPreference.model_validate(pref_data)
                session.add(preference)
        
        session.commit()
        
        # Create Roles
        logger.info("Creating job roles...")
        roles_data = [
            {
                "title": "Senior Python Developer",
                "description": "We're looking for a senior Python developer to join our backend team. You'll work on building scalable APIs, optimizing database performance, and mentoring junior developers. Experience with FastAPI, PostgreSQL, and Redis is highly preferred.",
                "posting_url": "https://techcorp.com/jobs/senior-python-dev",
                "company": companies[0],  # TechCorp
                "location": "San Francisco, CA (Remote OK)",
                "requirements": "5+ years Python experience, FastAPI/Django, PostgreSQL, REST APIs, Git",
                "salary_range": "$140,000 - $180,000",
                "skills": ["Python", "FastAPI", "PostgreSQL", "REST APIs", "Git"]
            },
            {
                "title": "Full-Stack Software Engineer",
                "description": "Join our dynamic team to build next-generation data visualization tools. You'll work across the full stack using React, TypeScript, and Python. We're building tools that help companies make sense of their data.",
                "posting_url": "https://dataflow.io/careers/fullstack-engineer",
                "company": companies[1],  # DataFlow
                "location": "Seattle, WA",
                "requirements": "3+ years experience, React, TypeScript, Python, SQL, Experience with data visualization",
                "salary_range": "$110,000 - $150,000",
                "skills": ["React", "TypeScript", "Python", "SQL", "JavaScript"]
            },
            {
                "title": "DevOps Engineer",
                "description": "We need a DevOps engineer to help scale our cloud infrastructure. You'll work with Kubernetes, AWS, and infrastructure as code. Experience with monitoring, logging, and CI/CD pipelines is essential.",
                "posting_url": "https://cloudnative.dev/jobs/devops-engineer",
                "company": companies[2],  # CloudNative
                "location": "Remote",
                "requirements": "3+ years DevOps experience, Kubernetes, AWS, Docker, CI/CD, Infrastructure as Code",
                "salary_range": "$120,000 - $160,000",
                "skills": ["Kubernetes", "AWS", "Docker", "CI/CD", "Linux"]
            },
            {
                "title": "Machine Learning Engineer",
                "description": "Join our AI team to build and deploy machine learning models at scale. You'll work with large datasets, train deep learning models, and deploy them to production. Experience with TensorFlow, PyTorch, and cloud ML platforms required.",
                "posting_url": "https://ailab.com/careers/ml-engineer",
                "company": companies[3],  # AI Innovations
                "location": "San Francisco, CA",
                "requirements": "4+ years ML experience, Python, TensorFlow/PyTorch, Cloud ML platforms, Statistics",
                "salary_range": "$130,000 - $180,000",
                "skills": ["Python", "Machine Learning", "Data Analysis", "AWS", "SQL"]
            },
            {
                "title": "Frontend Developer",
                "description": "We're building the next generation of developer tools and need a talented frontend developer. You'll work with React, TypeScript, and modern CSS frameworks to create beautiful, intuitive user interfaces.",
                "posting_url": "https://devtools.pro/jobs/frontend-dev",
                "company": companies[4],  # DevTools Pro
                "location": "Austin, TX (Hybrid)",
                "requirements": "3+ years frontend experience, React, TypeScript, CSS, Modern frontend tools",
                "salary_range": "$100,000 - $140,000",
                "skills": ["React", "TypeScript", "JavaScript"]
            }
        ]
        
        roles = []
        for role_data in roles_data:
            # Create the role
            unique_hash = generate_unique_hash(role_data["title"], role_data["posting_url"])
            role = Role(
                title=role_data["title"],
                description=role_data["description"],
                posting_url=role_data["posting_url"],
                unique_hash=unique_hash,
                company_id=role_data["company"].id,
                status=RoleStatus.SOURCED,
                location=role_data["location"],
                requirements=role_data["requirements"],
                salary_range=role_data["salary_range"],
                created_at=datetime.now()
            )
            session.add(role)
            session.commit()
            session.refresh(role)
            roles.append(role)
            
            # Link skills to role
            for skill_name in role_data["skills"]:
                skill = session.exec(select(Skill).where(Skill.name == skill_name)).first()
                if skill:
                    role_skill_link = RoleSkillLink(role_id=role.id, skill_id=skill.id)
                    session.add(role_skill_link)
        
        session.commit()
        
        # Create Sample Applications
        logger.info("Creating sample applications...")
        applications_data = [
            {"profile": profiles[0], "role": roles[0], "status": ApplicationStatus.DRAFT},
            {"profile": profiles[0], "role": roles[1], "status": ApplicationStatus.SUBMITTED},
            {"profile": profiles[1], "role": roles[3], "status": ApplicationStatus.READY_TO_SUBMIT},
            {"profile": profiles[2], "role": roles[2], "status": ApplicationStatus.DRAFT}
        ]
        
        applications = []
        for app_data in applications_data:
            application_data = {
                "role_id": app_data["role"].id,
                "profile_id": app_data["profile"].id,
                "status": app_data["status"],
                "created_at": datetime.now()
            }
            application = Application.model_validate(application_data)
            applications.append(application)
            session.add(application)
        
        session.commit()
        
        logger.info("Database seeding completed successfully!")
        
        return {
            "status": "success",
            "message": "Database seeded successfully with sample data.",
            "summary": {
                "skills": len(skills),
                "companies": len(companies),
                "profiles": len(profiles),
                "roles": len(roles),
                "applications": len(applications)
            },
            "endpoints_to_try": {
                "profiles": [f"http://localhost:8000/profile/{i+1}" for i in range(len(profiles))],
                "preferences": [f"http://localhost:8000/profile/{i+1}/preferences" for i in range(len(profiles))],
                "applications": "http://localhost:8000/applications",
                "health": "http://localhost:8000/health"
            }
        }
        
    except Exception as e:
        logger.error(f"Database seeding failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to seed database: {e}"
        ) 