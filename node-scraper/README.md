# Job Agent Node.js Scraper Service

This is a TypeScript-based Node.js service that handles intelligent job application automation using [Stagehand](https://docs.stagehand.dev/). It consumes job application tasks from Redis queues and processes them using AI-powered web automation.

## Architecture

```
Python FastAPI ──→ Redis Queue ──→ Node.js Service (Stagehand) ──→ Results ──→ Python FastAPI
```

### Key Components

- **Queue Consumer**: Main entry point that listens for job application tasks
- **Application Processor**: Orchestrates the job application workflow
- **Stagehand Wrapper**: Handles intelligent web automation using Stagehand
- **Redis Manager**: Manages queue communication with the Python service

## Features

- **Intelligent Form Filling**: Uses Stagehand's AI capabilities to understand and fill job application forms
- **Multi-step Applications**: Handles complex application workflows with multiple pages
- **Human-in-the-Loop**: Detects when human input is needed and requests approval
- **Error Recovery**: Implements retry logic with exponential backoff
- **Screenshot Capture**: Takes screenshots for debugging and approval workflows
- **Type Safety**: Full TypeScript implementation with comprehensive type definitions

## Queue Communication

### Task Types

1. **`job_application`** (Python → Node.js): Job application requests
2. **`update_job_status`** (Node.js → Python): Status updates
3. **`approval_request`** (Node.js → Python): Human approval needed

### Task Flow

```typescript
interface JobApplicationTask {
    job_id: number;
    job_url: string;
    company: string;
    title: string;
    user_data: {
        name: string;
        email: string;
        phone: string;
        resume_url?: string;
        // ... other fields
    };
    credentials?: {
        username: string;
        password: string;
    };
}
```

## Development Setup

### Prerequisites

- Node.js 20+
- npm or yarn
- Redis (running via Docker Compose)

### Installation

```bash
# Install dependencies
npm install

# Copy environment config
cp .env.example .env

# Build TypeScript
npm run build

# Run in development mode (with hot reload)
npm run dev

# Run in production mode
npm start
```

### Environment Variables

```bash
# Redis Configuration
NODE_REDIS_URL=redis://redis:6379/0

# Stagehand Configuration
STAGEHAND_HEADLESS=true
STAGEHAND_TIMEOUT=30000

# Browser Configuration
BROWSER_VIEWPORT_WIDTH=1280
BROWSER_VIEWPORT_HEIGHT=720

# Logging
LOG_LEVEL=info
```

## Docker Usage

### Development

```bash
# Run with Docker Compose (from project root)
docker-compose up node-scraper

# Build and run standalone
docker build -t jobagent-node-scraper .
docker run -e NODE_REDIS_URL=redis://host.docker.internal:6379 jobagent-node-scraper
```

### Production

The service is automatically built and deployed as part of the main application stack.

## Application Processing Flow

1. **Task Reception**: Listens for `job_application` tasks from Redis
2. **Navigation**: Uses Stagehand to navigate to the job URL
3. **Form Analysis**: Analyzes the application form using AI
4. **Authentication**: Handles login if credentials are provided
5. **Form Filling**: Intelligently fills form fields with user data
6. **Submission**: Submits the application and captures confirmation
7. **Result Publishing**: Sends status updates back to Python service

### Automation Capabilities

- **Smart Form Detection**: Identifies form fields automatically
- **Multi-page Handling**: Navigates through multi-step applications
- **File Upload Detection**: Identifies when resume upload is needed
- **Error Detection**: Recognizes failed submissions and retries
- **Success Verification**: Confirms successful application submission

## Error Handling

### Retry Logic

- **Exponential Backoff**: Delays increase with each retry (1s, 2s, 4s, ...)
- **Maximum Retries**: Configurable (default: 3 attempts)
- **Error Categories**: Different handling for network vs. automation errors

### Human Intervention

When the automation encounters scenarios requiring human input:

1. **Approval Request**: Publishes task with question details
2. **State Preservation**: Saves current page state for continuation
3. **Screenshot Capture**: Takes screenshot for user context
4. **SMS Notification**: Python service sends SMS to user

## Monitoring and Health Checks

### Health Check Endpoint

The service exposes health check functionality:

```typescript
const health = await service.healthCheck();
// Returns: { status: 'healthy'|'unhealthy', details: {...} }
```

### Logging

Structured logging with Winston:

```typescript
logger.info('Processing job application', {
    taskId: 'task_123',
    jobId: 456,
    company: 'Example Corp'
});
```

### Metrics

- Queue lengths and processing times
- Success/failure rates
- Retry statistics
- Memory and performance metrics

## Integration with Python Service

### Task Publishing (Python)

```python
from app.queue_manager import QueueManager

queue = QueueManager()
await queue.publish_task(TaskType.JOB_APPLICATION, {
    "job_id": 123,
    "job_url": "https://company.com/jobs/456",
    "user_data": user_data
})
```

### Result Consumption (Python)

```python
# Listen for status updates
result = await queue.consume_task(TaskType.UPDATE_JOB_STATUS)
# Process application status update
```

## Testing

### Unit Tests

```bash
npm test
```

### Integration Tests

```bash
# Run with test Redis instance
npm run test:integration
```

### Manual Testing

```bash
# Test with sample job application
npm run test:manual
```

## Performance Considerations

- **Browser Reuse**: Stagehand browsers are reused when possible
- **Memory Management**: Automatic cleanup of browser instances
- **Concurrent Processing**: Multiple applications can be processed simultaneously
- **Resource Limits**: Configurable memory and timeout limits

## Deployment

The service is deployed as part of the main application stack:

- **Docker Compose**: Local development
- **Fly.io**: Production deployment
- **Health Checks**: Automatic service monitoring
- **Graceful Shutdown**: Proper cleanup on termination

## Troubleshooting

### Common Issues

1. **Redis Connection**: Check `NODE_REDIS_URL` configuration
2. **Browser Issues**: Ensure Chrome/Chromium is available
3. **Memory Leaks**: Monitor browser instance cleanup
4. **Network Timeouts**: Adjust `STAGEHAND_TIMEOUT` setting

### Debugging

1. **Enable Debug Logging**: Set `LOG_LEVEL=debug`
2. **Screenshot Analysis**: Check captured screenshots
3. **Queue Inspection**: Monitor Redis queue contents
4. **Health Checks**: Use health check endpoint for diagnostics

## Contributing

1. Follow TypeScript best practices
2. Add comprehensive type definitions
3. Include unit tests for new features
4. Update documentation for API changes
5. Test integration with Python service

## Links

- [Stagehand Documentation](https://docs.stagehand.dev/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)
- [Redis Node.js Client](https://redis.js.org/)
- [Winston Logging](https://github.com/winstonjs/winston) 