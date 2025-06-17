# Job Application Agent

A sophisticated, event-driven job application automation system that streamlines the entire job application process using AI-powered browser automation and intelligent document generation.

## Architecture Overview

The system uses a modern event-driven architecture with Redis queues connecting Python FastAPI services with a TypeScript Node.js service for intelligent web automation:

```
SMS/API → Python (FastAPI) → Redis Queue → Node.js (Stagehand) → Redis Queue → Python (Results) → SMS Notifications
```

### Key Components

- **Python FastAPI Service**: API layer, job ingestion, result processing, database operations, document generation
- **TypeScript Node.js Service**: Intelligent web automation using Stagehand library with Browserbase
- **Redis Queues**: Event-driven communication between services
- **PostgreSQL**: Primary data storage with SQLModel ORM  
- **Celery**: Background task processing for Python services
- **MinIO/S3**: Object storage for generated documents (resumes, cover letters)

## Features

### 🤖 **AI-Powered Automation**
- **Intelligent Browser Automation**: Uses Stagehand with natural language commands for reliable form filling
- **Dynamic Form Analysis**: Automatically detects and adapts to different application form layouts
- **Smart Question Answering**: AI generates contextual responses to company-specific questions
- **Multi-Step Application Support**: Handles complex, multi-page application workflows

### 📄 **Document Generation & Management**
- **AI-Generated Resumes**: Creates tailored, ATS-optimized resumes for each position
- **Custom Cover Letters**: Generates compelling, job-specific cover letters
- **PDF Generation**: Converts documents to professional PDFs with WeasyPrint
- **Cloud Storage**: Secure document storage with direct links for applications
- **SMS Notifications**: Real-time alerts when documents are ready

### 🔄 **Event-Driven Workflow**
- **Queue-Based Processing**: Reliable task distribution between Python and Node.js services
- **Human-in-the-Loop**: SMS integration for approval requests and progress updates
- **Graceful Fallback**: Automatic escalation to manual review when automation isn't possible
- **Status Tracking**: Real-time application status updates and error reporting

### 📱 **SMS Integration**
- **Job URL Ingestion**: Send job posting URLs via SMS to automatically queue applications
- **Progress Notifications**: Real-time updates on application status and document generation
- **Approval Workflows**: Interactive SMS prompts for questions requiring human input
- **Error Alerts**: Immediate notification of any application failures with details

## Project Structure

```
jobagent/
├── alembic/                    # Database migration scripts
│   ├── versions/
│   └── env.py
├── app/                        # Core Python application
│   ├── api/                    # FastAPI route modules
│   │   ├── applications.py     # Application management endpoints
│   │   ├── jobs.py            # Job ingestion and ranking
│   │   ├── webhooks.py        # SMS webhook handlers
│   │   ├── health.py          # System health checks
│   │   └── shared.py          # Common dependencies
│   ├── models.py              # SQLModel database models
│   ├── db.py                  # Database connection and session management
│   ├── queue_manager.py       # Redis queue management for inter-service communication
│   ├── security.py            # Encryption and authentication utilities
│   ├── notifications.py       # SMS/Twilio integration
│   ├── tasks/                 # Celery task definitions
│   │   ├── documents.py       # Document generation tasks
│   │   ├── submission.py      # Application submission workflow
│   │   ├── queue_consumer.py  # Queue task consumers
│   │   ├── ranking.py         # Job ranking tasks
│   │   └── shared.py          # Celery app configuration
│   ├── tools/                 # Business logic modules
│   │   ├── ingestion.py       # Job URL processing with Firecrawl
│   │   ├── documents.py       # AI document generation
│   │   ├── storage.py         # Object storage operations
│   │   ├── notifications.py   # SMS notification utilities
│   │   └── ranking.py         # LLM-powered job ranking
│   └── api_server.py          # FastAPI application entry point
├── node-scraper/              # TypeScript Node.js automation service
│   ├── src/
│   │   ├── queue-consumer.ts      # Main service entry point
│   │   ├── application-processor.ts # Core automation logic
│   │   ├── stagehand-wrapper.ts   # Stagehand integration
│   │   ├── types/
│   │   │   ├── tasks.ts           # Task type definitions
│   │   │   └── stagehand.ts       # Stagehand type definitions
│   │   └── utils/
│   │       ├── redis.ts           # Redis client utilities
│   │       └── logger.ts          # Structured logging
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile
├── tests/                     # Automated tests
│   ├── conftest.py            # Test configuration and fixtures
│   ├── unit/                  # Unit tests
│   └── e2e/                   # End-to-end API tests
├── docker-compose.yml         # Development environment
├── docker-compose.test.yml    # Test environment
├── Dockerfile                 # Multi-stage Docker build
├── pyproject.toml            # Python project configuration with poethepoet tasks
├── .env.example              # Environment variables template
├── .env.fly.example          # Fly.io deployment configuration
└── README.md                 # This file
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- Node.js 20+ (for Node.js service development)

### Environment Setup

1. **Copy and configure environment variables:**
   ```bash
   cp .env.example .env
   ```

2. **Configure required environment variables in `.env`:**
   ```bash
   # Core API Keys (Required)
   OPENAI_API_KEY=your_openai_api_key_here
   BROWSERBASE_API_KEY=your_browserbase_api_key_here
   BROWSERBASE_PROJECT_ID=your_browserbase_project_id_here
   
   # SMS Integration (Optional but recommended)
   TWILIO_ACCOUNT_SID=your_twilio_account_sid
   TWILIO_AUTH_TOKEN=your_twilio_auth_token
   SMS_FROM=+14155238886
   SMS_TO=+1234567890
   
   # Job URL Scraping
   FIRECRAWL_API_KEY=fc-your_firecrawl_api_key
   
   # Security (Auto-generated keys)
   PROFILE_INGEST_API_KEY=your_secure_api_key_here
   ENCRYPTION_KEY=your_32_byte_base64_encryption_key
   ```

### Quick Start

1. **Start all services:**
   ```bash
   uv run poe run-local
   ```
   
   This command will:
   - Build and start all Docker services
   - Run database migrations
   - Configure MinIO object storage
   - Display service URLs

2. **Access your services:**
   - **API Documentation**: http://localhost:8000/docs
   - **Health Check**: http://localhost:8000/health  
   - **MinIO Console**: http://localhost:9001 (admin/minioadmin)

3. **View logs:**
   ```bash
   uv run poe logs-local
   ```

4. **Stop services:**
   ```bash
   uv run poe stop-local
   ```

### Development Commands

```bash
# Run all tests (Python + Node.js)
uv run poe test

# Run only Python tests
uv run poe test-python

# Run only Node.js tests  
uv run poe test-node

# Database migrations
uv run poe migrate
uv run poe alembic-revision "description"

# Deployment
uv run poe deploy
uv run poe deploy-logs
```

## Usage Workflow

### 1. SMS Job Ingestion
Send a job posting URL via SMS to your configured number:
```
https://company.com/careers/software-engineer-123
```

The system will:
- Extract job details using Firecrawl
- Rank the position against your profile
- Generate tailored resume and cover letter
- Send document links via SMS
- Queue the application for automated submission

### 2. Automated Application Process
The Node.js service will:
- Navigate to the job posting
- Fill out application forms intelligently
- Handle multi-step applications
- Upload generated documents
- Submit the application

### 3. Human-in-the-Loop Approval
When the system encounters questions it can't answer:
- Pauses the application process
- Sends SMS with the question and screenshot
- Waits for your response via SMS
- Continues with your provided answer

### 4. Status Notifications
Receive SMS updates for:
- ✅ Document generation complete
- 🔄 Application submission started
- ✅ Application submitted successfully
- ❌ Application failed (with error details)
- 🤔 Approval needed for specific questions

## API Endpoints

### Core Endpoints
- `POST /api/v1/jobs/ingest` - Add new job posting
- `GET /api/v1/applications` - List applications
- `GET /api/v1/applications/{id}` - Get application details
- `POST /webhooks/sms` - Twilio SMS webhook

### System Endpoints  
- `GET /health` - System health check
- `GET /queue/stats` - Queue statistics
- `GET /system/status` - Service status overview

## Deployment

### Local Development
```bash
uv run poe run-local
```

### Production (Fly.io)
1. **Configure deployment variables:**
   ```bash
   cp .env.fly.example .env.fly
   # Edit .env.fly with your values
   ```

2. **Deploy:**
   ```bash
   uv run poe deploy
   ```

The deploy script automatically provisions:
- PostgreSQL database
- Redis instance  
- Tigris object storage
- Environment variable configuration

## Testing

### Run All Tests
```bash
uv run poe test
```

### Test Structure
- **Unit Tests**: Individual component testing
- **Integration Tests**: Cross-service communication
- **E2E Tests**: Full workflow testing
- **Node.js Tests**: TypeScript service testing with Vitest

## Key Technologies

### Python Stack
- **FastAPI**: Modern, async web framework with automatic OpenAPI docs
- **SQLModel**: Type-safe database models with Pydantic validation
- **Celery + Redis**: Distributed task processing and scheduling
- **pydantic-ai**: Structured LLM outputs for AI components
- **WeasyPrint**: PDF generation from HTML/Markdown
- **Twilio**: SMS integration for HITL workflows
- **Firecrawl**: Web scraping and content extraction

### Node.js Stack
- **TypeScript**: Type-safe JavaScript development
- **Stagehand**: AI-powered browser automation library
- **Browserbase**: Cloud browser infrastructure
- **Redis**: Queue communication with Python services
- **Vitest**: Fast testing framework

### Infrastructure
- **Docker**: Containerized development and deployment
- **PostgreSQL**: Primary database with JSON support
- **Redis**: Message queues and caching
- **MinIO/S3**: Object storage for documents
- **Fly.io**: Production deployment platform

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `uv run poe test`
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
