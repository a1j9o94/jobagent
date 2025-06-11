# Testing Guide

This guide covers testing for both the Python FastAPI service and the Node.js/TypeScript automation service in the queue-based architecture.

## Running All Tests

```bash
# Run both Python and Node.js tests
uv run poe test

# Run only Python tests
uv run poe test-python

# Run only Node.js tests
uv run poe test-node
```

## Test Structure

### Python Tests
Located in `tests/` directory:
- **`tests/e2e/test_api.py`** - End-to-end API tests including queue-based job applications
- **`tests/unit/test_tools.py`** - Unit tests for tools and queue consumer tasks
- **`tests/unit/test_models.py`** - Database model tests with new queue fields

### Node.js Tests
Located in `node-scraper/src/` directory:
- **`src/utils/redis.test.ts`** - Redis manager unit tests
- **`src/application-processor.test.ts`** - Application processor unit tests
- **`src/types/tasks.test.ts`** - TypeScript type validation tests
- **`src/test/integration.test.ts`** - Integration tests with Redis

## New Queue-Based Features Tested

### Python API Tests
- **Job Application Endpoint** (`/jobs/apply/{role_id}`)
  - Creates Application records and queues tasks
  - Reuses existing applications when appropriate
  - Proper error handling for invalid role IDs

- **Enhanced Health Checks**
  - Queue statistics monitoring (`/health/queues`)
  - Node.js service health monitoring (`/health/node-service`)
  - Redis queue health checks

- **Application Model Fields**
  - `queue_task_id` - Tracks Node.js task IDs
  - `approval_context` - Stores human-in-the-loop data
  - `screenshot_url` - Automation screenshots
  - `error_message` - Detailed error information
  - `notes` - Application submission notes

### Node.js Service Tests
- **Redis Queue Management**
  - Task publishing and consumption
  - Queue statistics and health checks
  - FIFO task ordering
  - Connection error handling

- **Application Processing**
  - Successful application workflows
  - Approval request handling
  - Error retry logic with exponential backoff
  - Screenshot capture on failures

- **Type Safety**
  - TypeScript interface validation
  - Task payload structure verification
  - Enum value consistency

## Test Environment Setup

### Prerequisites
- Docker and Docker Compose
- Python with UV package manager
- Node.js 20+ and npm

### Environment Variables
Tests use isolated test databases and services:
```bash
# Python tests use these automatically
DATABASE_URL=postgresql+psycopg2://test_user:test_password@test_db:5432/test_jobagent
REDIS_URL=redis://test_redis:6379/0

# Node.js tests use these
NODE_REDIS_URL=redis://test_redis:6379/0
STAGEHAND_HEADLESS=true
LOG_LEVEL=error
```

### Test Data
- **Fixtures**: Created in `tests/conftest.py` for consistent test data
- **Mocks**: Stagehand browser automation is mocked in tests
- **Database**: Each test gets a clean database state
- **Redis**: Isolated Redis instance for queue testing

## Integration Testing

The integration tests verify the complete queue workflow:

1. **Python API** creates Application and publishes to Redis queue
2. **Node.js Service** consumes task and processes job application
3. **Results** are published back to Python via queue
4. **Database** is updated with status and notifications sent

### Running Integration Tests Only

```bash
# Run Redis in background for integration tests
docker run -d --name test-redis -p 6380:6379 redis:alpine

# Run Node.js integration tests
cd node-scraper && npm run test:run -- src/test/integration.test.ts

# Clean up
docker stop test-redis && docker rm test-redis
```

## Test Coverage

### Key Areas Covered
- ✅ Queue task creation and consumption
- ✅ Application status updates via queue
- ✅ Human-in-the-loop approval workflows
- ✅ Error handling and retry logic
- ✅ Health monitoring and queue statistics
- ✅ Database model field validation
- ✅ TypeScript type safety

### Mock Strategy
- **Stagehand**: Mocked to avoid browser dependencies in tests
- **External APIs**: LLM, Twilio, S3 services mocked
- **Redis**: Real Redis instance for integration tests, mocked for unit tests
- **Database**: Real PostgreSQL for integration, isolated per test

## Debugging Tests

### Python Tests
```bash
# Run with verbose output
pytest -v --tb=long tests/

# Run specific test
pytest tests/e2e/test_api.py::TestJobApplicationEndpoint::test_trigger_job_application_success

# Debug mode
pytest --pdb tests/unit/test_tools.py
```

### Node.js Tests
```bash
# Run with UI for debugging
npm run test:ui

# Run specific test file
npm run test:run src/utils/redis.test.ts

# Run with coverage
npm run test:coverage
```

### Common Issues

1. **Redis Connection Errors**
   - Ensure test Redis is running on port 6380
   - Check Docker compose test services are healthy

2. **Database Migration Issues**
   - Verify Alembic migrations are applied in test container
   - Check test database has correct schema

3. **Node.js Dependency Issues**
   - Run `npm ci` in node-scraper directory
   - Ensure TypeScript builds without errors

4. **Queue Test Flakiness**
   - Integration tests may be flaky without proper Redis
   - Unit tests should always pass with mocks

## Performance Testing

Tests include basic performance checks:
- Queue processing speed
- Database query efficiency  
- Memory usage during task processing
- Redis connection pooling

For load testing the queue system:
```bash
# Publish multiple tasks for load testing
cd node-scraper && npm run test:run src/test/load.test.ts
```

## CI/CD Integration

Tests run automatically in Docker containers with:
- Isolated test database and Redis
- All dependencies installed
- Environment variables set
- Parallel execution where possible

The `docker-compose.test.yml` orchestrates all test services and ensures proper dependency order. 