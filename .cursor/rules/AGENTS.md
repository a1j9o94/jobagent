---
description: 
globs: 
alwaysApply: true
---
# Job Application Agent - Cursor Rules

You are an expert in Python, FastAPI, SQLModel, Celery, TypeScript/Node.js, and AI-powered automation systems. You specialize in building scalable job application automation with event-driven architecture, intelligent browser automation, document generation, and SMS integration.

## Key Principles
- Write concise, technical responses with accurate Python and TypeScript examples.
- Use functional, declarative programming; avoid classes where functions suffice.
- Prefer iteration and modularization over code duplication.
- Use descriptive variable names with auxiliary verbs (e.g., is_submitted, has_credentials, should_retry).
- Use lowercase with underscores for directories and files (e.g., app/tools.py, tests/unit/test_automation.py).
- Favor named exports for functions and clear module organization.
- Use the Receive an Object, Return an Object (RORO) pattern for complex functions.
- Follow async-first patterns for I/O operations (database, LLM calls, browser automation, queue operations).

## Architecture Overview
The system uses an event-driven architecture with Redis queues connecting Python FastAPI services with a TypeScript Node.js service for intelligent web automation:

```
SMS/API → Python (FastAPI) → Redis Queue → Node.js (Stagehand) → Redis Queue → Python (Results) → SMS Notifications
```

### Key Components
- **Python FastAPI**: API layer, job ingestion, result processing, database operations
- **TypeScript Node.js**: Intelligent web automation using Stagehand library
- **Redis Queues**: Event-driven communication between services
- **PostgreSQL**: Primary data storage with SQLModel ORM
- **Celery**: Background task processing for Python services

## Python/FastAPI/SQLModel
- Use `def` for pure functions and `async def` for asynchronous operations.
- Use type hints for all function signatures. Prefer SQLModel/Pydantic models over raw dictionaries.
- File structure: models → database → tools → tasks → api routes → tests.
- Use SQLModel for database models to get both SQLAlchemy ORM and Pydantic validation.
- Leverage FastAPI's dependency injection for database sessions and authentication.
- Use contextlib for resource management (database sessions, browser instances, file handles).

## Event-Driven Architecture Patterns

### Queue Management
```python
# app/queue_manager.py
from enum import Enum
from typing import Dict, Any
import redis
import json

class TaskType(Enum):
    JOB_APPLICATION = "job_application"      # Python → Node.js
    UPDATE_JOB_STATUS = "update_job_status"  # Node.js → Python  
    APPROVAL_REQUEST = "approval_request"    # Node.js → Python
    SEND_NOTIFICATION = "send_notification"  # Internal Python

class QueueManager:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_client = redis.from_url(redis_url)
    
    def publish_task(self, task_type: TaskType, data: Dict[str, Any]):
        """Publish a task to the appropriate queue"""
        task = {
            "type": task_type.value,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        queue_name = f"tasks:{task_type.value}"
        self.redis_client.lpush(queue_name, json.dumps(task))
    
    def consume_task(self, task_type: TaskType, timeout: int = 0):
        """Consume a task from a specific queue"""
        queue_name = f"tasks:{task_type.value}"
        result = self.redis_client.brpop(queue_name, timeout=timeout)
        if result:
            return json.loads(result[1])
        return None
```

### Job Processing Flow
```python
# Trigger job application via queue
def trigger_job_application(job_id: int):
    job = Job.query.get(job_id)
    task_data = {
        "job_id": job_id,
        "job_url": job.url,
        "company": job.company,
        "title": job.title,
        "user_data": {
            "name": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "resume_url": user.resume_url,
        }
    }
    
    job.application_status = "applying"
    db.session.commit()
    
    queue_manager.publish_task(TaskType.JOB_APPLICATION, task_data)
```

### Background Task Consumer
```python
# Background consumer for processing results from Node.js
def consume_tasks():
    """Background task consumer for Node.js results"""
    while True:
        for task_type in [TaskType.UPDATE_JOB_STATUS, TaskType.APPROVAL_REQUEST]:
            task = queue_manager.consume_task(task_type, timeout=1)
            if task:
                try:
                    if task_type == TaskType.UPDATE_JOB_STATUS:
                        handle_application_result(task["data"])
                    elif task_type == TaskType.APPROVAL_REQUEST:
                        handle_approval_request(task["data"])
                except Exception as e:
                    logger.error(f"Error processing {task_type.value} task: {e}")
```

## TypeScript/Node.js Service

### Project Structure
```
node-scraper/
├── package.json
├── tsconfig.json
├── src/
│   ├── queue-consumer.ts       # Main queue consumer
│   ├── application-processor.ts # Core application logic
│   ├── stagehand-wrapper.ts    # Stagehand integration
│   ├── types/
│   │   ├── tasks.ts           # Task type definitions
│   │   └── stagehand.ts       # Stagehand type definitions
│   └── utils/
│       ├── redis.ts           # Redis client utilities
│       └── logger.ts          # Structured logging
└── dist/                      # Compiled JavaScript
```

### TypeScript Patterns
```typescript
// src/types/tasks.ts
export interface JobApplicationTask {
    job_id: number;
    job_url: string;
    company: string;
    title: string;
    user_data: {
        name: string;
        email: string;
        phone: string;
        resume_url: string;
        [key: string]: any;
    };
}

export interface UpdateJobStatusTask {
    job_id: number;
    status: 'applied' | 'failed' | 'waiting_approval';
    notes?: string;
}

export enum TaskType {
    JOB_APPLICATION = "job_application",
    UPDATE_JOB_STATUS = "update_job_status", 
    APPROVAL_REQUEST = "approval_request"
}
```

### Stagehand Integration
```typescript
// src/application-processor.ts
import { Stagehand } from '@browserbasehq/stagehand';

export class ApplicationProcessor {
    private stagehand: Stagehand;
    
    async processJobApplication(taskData: JobApplicationTask): Promise<ApplicationResult> {
        const { job_id, job_url, user_data } = taskData;
        
        try {
            const page = await this.stagehand.page();
            await page.goto(job_url);
            
            const result = await this.fillApplication(page, user_data);
            
            if (result.needsApproval) {
                await this.publishTask('approval_request', {
                    job_id,
                    question: result.question,
                    current_state: result.state
                });
            } else {
                await this.publishTask('update_job_status', {
                    job_id,
                    status: result.success ? 'applied' : 'failed',
                    notes: result.notes || result.error
                });
            }
            
            return result;
        } catch (error) {
            await this.publishTask('update_job_status', {
                job_id,
                status: 'failed',
                notes: `Error: ${error.message}`
            });
            throw error;
        }
    }
    
    private async fillApplication(page: any, userData: any): Promise<ApplicationResult> {
        // Use Stagehand's intelligent form filling
        await page.act({ action: `fill name field with ${userData.name}` });
        await page.act({ action: `fill email field with ${userData.email}` });
        
        // Check for questions requiring approval
        const unknownQuestions = await page.extract({
            instruction: "find any questions or fields that seem unusual or require specific answers",
            schema: {
                questions: "array of questions that need human input"
            }
        });
        
        if (unknownQuestions.questions.length > 0) {
            return {
                success: false,
                needsApproval: true,
                question: unknownQuestions.questions[0],
                state: await page.content()
            };
        }
        
        await page.act({ action: 'click apply button' });
        return { success: true };
    }
}
```

## Error Handling and Validation
- Prioritize error handling and edge cases:
  - Handle errors and edge cases at the beginning of functions.
  - Use early returns for error conditions to avoid deeply nested if statements.
  - Place the happy path last in the function for improved readability.
  - Avoid unnecessary else statements; use the if-return pattern instead.
  - Use guard clauses to handle preconditions and invalid states early.
  - Implement proper error logging with structured logging.
  - Use custom exception types for domain-specific errors (FormSubmissionError, DocumentGenerationError).
  - Always handle LLM API failures gracefully with fallback responses.
  - Implement retry logic with exponential backoff for transient failures.
  - Handle queue connection failures and implement reconnection logic.

## Dependencies & Architecture

### Core Stack
- **FastAPI** - API framework with automatic OpenAPI docs
- **SQLModel** - Database models with Pydantic validation
- **Celery + Redis** - Async task processing and scheduling
- **Redis** - Event-driven queue communication between services
- **TypeScript + Node.js** - Intelligent web automation service
- **Stagehand** - AI-powered browser automation library
- **pydantic-ai** - Structured LLM outputs for AI components
- **WeasyPrint** - PDF generation from HTML/Markdown
- **Twilio** - SMS integration for HITL workflows
- **boto3** - S3-compatible object storage (MinIO/Tigris)
- **Alembic** - Database migrations
- **Firecrawl** - Web scraping and content extraction

### Development Tools
- **pytest + pytest-asyncio** - Testing framework with async support
- **httpx** - HTTP client for API testing
- **factory-boy** - Test data generation
- **testcontainers** - Containerized test dependencies
- **jest** - TypeScript/Node.js testing framework
- **ts-node-dev** - TypeScript development with hot reloading

## Human-in-the-Loop Patterns

### SMS Integration for Approvals
```python
# Enhanced webhook handler for approval workflow
async def handle_sms_reply(request: Request, session: Session = Depends(get_session)):
    from_number = request_form_dict.get("From", "")
    message_body = request_form_dict.get("Body", "").strip()
    
    # URL ingestion
    try:
        url = HttpUrl(message_body)
        new_role, task_id = await process_ingested_role(
            url=str(url), profile_id=1, session=session
        )
        send_sms_message(
            f"✅ Got it! I've added '{new_role.title}' to your queue. Task ID: {task_id}",
            clean_from_number
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValidationError:
        pass  # Not a URL, continue to command processing
    
    # Handle approval responses
    if is_approval_response(message_body):
        await handle_approval_response(from_number, message_body)
    
    # Other command processing...
```

### Approval Request Processing
```python
def handle_approval_request(task_data: Dict[str, Any]):
    """Handle approval requests from Node.js service"""
    job_id = task_data["job_id"]
    question = task_data["question"]
    
    # Update job status
    job = Job.query.get(job_id)
    job.application_status = "waiting_approval"
    job.application_notes = f"Waiting for approval: {question}"
    db.session.commit()
    
    # Send notification
    message = f"🤔 Need approval for {job.title} at {job.company}\n\nQuestion: {question}"
    queue_manager.publish_task(TaskType.SEND_NOTIFICATION, {
        "message": message,
        "type": "sms",
        "job_id": job_id
    })
```

## Code Quality Tools
- Use **ruff** for Python linting and formatting (replaces black, isort, flake8).
- Use **mypy** for Python static type checking.
- Use **ESLint + TypeScript ESLint** for TypeScript code quality.
- Use **Prettier** for TypeScript code formatting.
- Configure ruff with aggressive settings for import sorting and code formatting.
- Use type: ignore comments sparingly and with specific error codes.
- Prefer explicit type annotations over type inference for public APIs.

## FastAPI-Specific Guidelines
- Use functional route handlers with clear dependency injection.
- Use SQLModel models for request/response validation and database operations.
- Implement comprehensive health checks that verify all service dependencies.
- Use `async def` for all route handlers that perform I/O operations.
- Leverage FastAPI's automatic API documentation with proper response models.
- Use dependency injection for database sessions: `session: Session = Depends(get_session)`.
- Implement rate limiting using slowapi for webhook endpoints.
- Use middleware for CORS, logging, and error monitoring.
- Structure responses consistently with status, data, and optional metadata.

## Database & SQLModel Patterns
- Use SQLModel for unified database and API models.
- Implement proper foreign key relationships with `Relationship()`.
- Use context managers for database sessions: `with get_session_context() as session:`.
- Implement database health checks and connection pooling.
- Use Alembic for version-controlled schema migrations.
- Encrypt sensitive data (passwords, API keys) before database storage.
- Use JSONB columns for flexible data storage (PostgreSQL).
- Add queue task tracking fields to models for observability.

## Queue-Based Task Patterns
- Keep tasks focused and idempotent across service boundaries.
- Use task correlation IDs for tracing across Python and Node.js services.
- Implement dead letter queues for failed task handling.
- Use task result tracking for long-running operations.
- Structure tasks to be language-agnostic with clear JSON schemas.
- Implement proper error handling and task failure notifications.
- Use queue monitoring for system health and performance metrics.
- Handle queue connection failures gracefully with reconnection logic.

## Browser Automation Best Practices (Stagehand)
- Use Stagehand's AI-powered automation over traditional CSS selectors.
- Implement intelligent form field detection with natural language instructions.
- Use Stagehand's extraction capabilities for dynamic content analysis.
- Handle complex multi-step applications with state preservation.
- Implement approval workflows for questions requiring human input.
- Take screenshots on automation failures for debugging.
- Use explicit waits for dynamic content loading.
- Implement headless browser mode for production efficiency.
- Handle CAPTCHAs gracefully with fallback to manual intervention.

## AI/LLM Integration Patterns
- Use pydantic-ai for structured outputs from LLM calls.
- Implement proper prompt engineering with system prompts and examples.
- Handle LLM failures gracefully with fallback responses.
- Use result types (Pydantic models) to ensure consistent LLM outputs.
- Implement token usage monitoring and cost tracking.
- Cache LLM responses when appropriate to reduce API calls.
- Use async/await for all LLM API calls to avoid blocking.
- Integrate LLM-powered job detail extraction with Firecrawl scraping.

## SMS/Webhook Security
- Always validate webhook signatures from Twilio.
- Implement rate limiting on webhook endpoints.
- Use structured message parsing for command handling.
- Store user preferences for improved automation over time.
- Implement conversation state management for multi-step interactions.
- Handle webhook retries and duplicate message detection.
- Support URL ingestion and approval workflows via SMS.

## Testing Strategies
- Use test containers for integration testing with real databases and Redis.
- Mock external API calls (LLM, Twilio, Stagehand) in unit tests.
- Implement fixtures for common test data (profiles, roles, applications).
- Use pytest markers to separate unit tests from integration tests.
- Test error conditions and edge cases thoroughly.
- Use async test patterns for testing async functions.
- Implement database rollback in test teardown.
- Test queue communication between Python and Node.js services.
- Use Jest for TypeScript service testing with Redis mocking.

## Performance Optimization
- Use async/await for all I/O-bound operations (database, HTTP, file operations, queues).
- Implement connection pooling for database, Redis, and external API connections.
- Use lazy loading for large datasets and complex relationships.
- Cache frequently accessed data with appropriate TTL.
- Use bulk operations for database insertions and updates.
- Implement proper indexing on frequently queried columns.
- Monitor queue lengths and processing times across services.
- Use Redis pipelining for batch queue operations.

## Security Considerations
- Encrypt sensitive data using cryptography.fernet before storage.
- Use secure API key authentication with proper key rotation.
- Validate all webhook signatures to prevent tampering.
- Implement proper CORS policies for API access.
- Use environment variables for all secrets and configuration.
- Sanitize all user inputs before processing or storage.
- Implement audit logging for sensitive operations.
- Secure Redis connections with authentication and encryption.
- Validate all queue message schemas to prevent injection attacks.

## File Structure Conventions
```
# Python Service
app/
├── models.py           # SQLModel database models
├── db.py              # Database connection and session management
├── security.py        # Encryption and authentication utilities
├── queue_manager.py   # Redis queue management
├── tools/             # Modular business logic
│   ├── ingestion.py   # Job URL processing with Firecrawl
│   ├── ranking.py     # LLM-powered job ranking
│   ├── documents.py   # PDF generation
│   ├── notifications.py # SMS integration
│   └── storage.py     # Object storage operations
├── tasks/             # Celery task definitions
│   ├── shared.py      # Celery app configuration
│   ├── ranking.py     # Job ranking tasks
│   ├── documents.py   # Document generation tasks
│   └── reporting.py   # Daily report tasks
├── api/               # FastAPI routes
│   ├── shared.py      # Common dependencies
│   ├── jobs.py        # Job ingestion endpoints
│   ├── webhooks.py    # SMS webhook handling
│   └── system.py      # Health checks
└── api_server.py      # FastAPI application

# TypeScript Service
node-scraper/
├── package.json
├── tsconfig.json
├── src/
│   ├── queue-consumer.ts       # Main queue consumer
│   ├── application-processor.ts # Application automation
│   ├── stagehand-wrapper.ts    # Stagehand integration
│   ├── types/
│   │   ├── tasks.ts           # Task interfaces
│   │   └── stagehand.ts       # Stagehand types
│   └── utils/
│       ├── redis.ts           # Redis utilities
│       └── logger.ts          # Logging
└── dist/                      # Compiled output

tests/
├── conftest.py        # Test configuration and fixtures
├── unit/             # Unit tests for individual functions
├── integration/      # Cross-service integration tests
└── e2e/              # End-to-end API tests
```

## Deployment Patterns

### Docker Compose (Development)
```yaml
services:
  api:          # Python FastAPI service
  worker:       # Python Celery worker
  beat:         # Python Celery beat scheduler
  node-scraper: # TypeScript automation service
  db:           # PostgreSQL database
  redis:        # Redis for queues and Celery
  minio:        # S3-compatible object storage
```

### Fly.io (Production)
```toml
[processes]
  app = "uvicorn app.api_server:app --host 0.0.0.0 --port 8000"
  worker = "celery -A app.tasks.celery_app worker --loglevel=info"
  beat = "celery -A app.tasks.celery_app beat --loglevel=info"
  node-scraper = "node dist/queue-consumer.js"
```

## Key Conventions
1. Use dependency injection for all shared resources (database, queues, external APIs).
2. Implement comprehensive error handling with structured logging across services.
3. Use async patterns for all I/O operations to maintain system responsiveness.
4. Structure code for testability with clear separation of concerns.
5. Follow the principle of least privilege for API access and data exposure.
6. Implement proper monitoring and health checks for all system components.
7. Use type hints consistently and leverage mypy/TypeScript for static analysis.
8. Follow language-specific formatting rules (ruff for Python, Prettier for TypeScript).
9. Design queue messages to be language-agnostic and well-documented.
10. Implement graceful degradation when services are unavailable.

Refer to FastAPI, SQLModel, Celery, Stagehand, and TypeScript documentation for implementation details and best practices.