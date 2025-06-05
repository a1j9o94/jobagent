# Job Application Agent

This project is a sophisticated, automated job application agent designed to streamline and manage the job application process.

## Overview

The system leverages a modern Python stack including FastAPI, SQLModel, Celery, and Playwright to handle:
- Job sourcing and ranking against a user profile.
- Automated application form submissions.
- Document generation (resumes, cover letters).
- Human-in-the-Loop (HITL) workflows via WhatsApp for user interaction.
- Persistent user knowledge base to improve automation over time.

For a complete engineering design and build instructions, please refer to the [design_doc.md](design_doc.md).

## Project Structure

```
jobagent/
├── alembic/            # Database migration scripts
│   ├── versions/
│   └── env.py
├── app/                # Core application logic
│   ├── __init__.py
│   ├── models.py         # SQLModel database models
│   ├── db.py             # Database connection and session management
│   ├── security.py       # Encryption and authentication utilities
│   ├── storage.py        # Object storage (S3/MinIO) operations
│   ├── pdf_utils.py      # Document generation utilities
│   ├── automation.py     # Browser automation with Playwright
│   ├── notifications.py  # WhatsApp/Twilio integration
│   ├── api_server.py     # FastAPI application and routes
│   ├── tasks.py          # Celery task definitions
│   └── tools.py          # AI tools and business logic functions
├── tests/              # Automated tests
│   ├── __init__.py
│   ├── conftest.py       # Test configuration and fixtures
│   ├── unit/             # Unit tests
│   └── e2e/              # End-to-end API tests
├── Dockerfile            # Docker image definition
├── docker-compose.yml    # Docker Compose for development environment
├── docker-compose.test.yml # Docker Compose for test environment
├── entrypoint.sh         # Entrypoint script for Docker containers
├── alembic.ini           # Alembic configuration
├── requirements.txt      # Core Python dependencies
├── requirements-dev.txt  # Development and testing dependencies
├── .env.sample           # Sample environment variables template
├── .dockerignore         # Files to ignore for Docker build context
├── .gitignore            # Files to ignore for Git
└── README.md             # This file
```

## Getting Started

1.  **Clone the repository.**
2.  **Copy `.env.sample` to `.env`** and fill in your environment-specific values (API keys, database credentials, etc.). Refer to the comments in `.env.sample` for guidance.
3.  **Build and start services** using Docker Compose:
    ```bash
    docker-compose up --build -d
    ```
4.  **Run database migrations** (the `entrypoint.sh` in the `api` service attempts to do this on startup):
    ```bash
    docker-compose exec api alembic upgrade head
    ```
    If this is the first time, you might need to generate an initial migration if `alembic/versions` is empty:
    ```bash
    docker-compose exec api alembic revision --autogenerate -m "Initial schema"
    docker-compose exec api alembic upgrade head
    ```

Refer to `design_doc.md` for more detailed setup, development, and deployment instructions.

## Running Tests

Use the test-specific Docker Compose file:

```bash
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

This will build the test environment, run `pytest`, and then exit.
