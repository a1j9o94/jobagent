# Job Agent Deployment Guide

This guide explains how to deploy the Job Agent to Fly.io using the fully automated deployment script.

## Prerequisites

1. **Install Fly.io CLI**:
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Create a Fly.io account** and login:
   ```bash
   flyctl auth login
   ```

3. **Set up your environment variables**:
   ```bash
   cp .env.fly.example .env.fly
   # Edit .env.fly with your actual values
   ```

## Required Environment Variables

You **must** configure these in your `.env.fly` file:

### Required
- `OPENAI_API_KEY`: Your OpenAI API key for LLM functionality
  - Get from: https://platform.openai.com/api-keys

### Optional (for WhatsApp features)
- `TWILIO_ACCOUNT_SID`: Your Twilio account SID for WhatsApp
- `TWILIO_AUTH_TOKEN`: Your Twilio auth token
- `WA_FROM`: Your Twilio WhatsApp number (e.g., `whatsapp:+14155238886`)
- `WA_TO`: Your personal WhatsApp number for notifications
  - Get from: https://console.twilio.com/

### Optional (customization)
- `APP_NAME`: Custom app name (default: `jobagent`)
- `REGION`: Deployment region (default: `sea`)

## Deployment Commands

### Deploy to Fly.io
```bash
# Using poe task
uv run poe deploy

# Or run script directly
./deploy.sh
```

This **fully automated** deployment will:
- ✅ Create Fly.io app if needed
- ✅ Set up managed PostgreSQL database
- ✅ Set up managed Redis instance 
- ✅ Create and configure Tigris object storage
- ✅ Extract and configure all connection URLs automatically
- ✅ Set all environment variables and secrets
- ✅ Update fly.toml with correct configuration
- ✅ Deploy the application with proper VM sizes
- ✅ Run database migrations
- ✅ Validate deployment with health checks

### Check deployment status
```bash
uv run poe deploy-check
```

### View application logs
```bash
uv run poe deploy-logs
```

### SSH into the application
```bash
uv run poe deploy-ssh
```

## What Gets Created Automatically

The deployment script creates and configures:

1. **Fly.io App**: `jobagent` (or your custom name)
2. **PostgreSQL Database**: `jobagent-db` with proper attachment
3. **Redis Instance**: `jobagent-redis` with extracted connection URL
4. **Tigris Storage**: `jobagent-storage` bucket with credentials
5. **Storage Volume**: `jobagent_data` for persistent file storage
6. **Secrets**: All required environment variables and API keys
7. **VM Configuration**: Optimized sizes to prevent OOM issues

## Application Architecture

Your deployed app runs with:

- **API Server** (shared-cpu-2x): FastAPI application on port 8000
- **Worker Process** (shared-cpu-2x): Celery worker for background tasks  
- **Beat Scheduler** (shared-cpu-2x): Celery beat for periodic tasks
- **Database**: Managed PostgreSQL with automatic backups
- **Cache/Queue**: Managed Redis (Upstash)
- **Object Storage**: Tigris S3-compatible storage

## Post-Deployment Validation

The deploy script automatically:
- ✅ Waits for application startup
- ✅ Tests the health endpoint
- ✅ Provides deployment summary
- ✅ Shows useful management commands
- ⚠️ Warns about missing required API keys

## Scaling

Scale your application:
```bash
# Scale to 2 API instances
flyctl scale count 2 --app jobagent

# Scale worker process memory
flyctl scale memory 1024 --process worker --app jobagent

# Scale to different VM sizes
flyctl scale vm shared-cpu-4x --process app --app jobagent
```

## Monitoring

View your application:
- **Application URL**: `https://jobagent.fly.dev`
- **Health Check**: `https://jobagent.fly.dev/health` (returns JSON status)
- **API Documentation**: `https://jobagent.fly.dev/docs`
- **Logs**: `flyctl logs --app jobagent`
- **Metrics**: Available in Fly.io dashboard

## Environment Configuration

### Automatically Generated and Configured
- `PROFILE_INGEST_API_KEY`: Random 32-byte API key
- `ENCRYPTION_KEY`: Random 32-byte encryption key  
- `DATABASE_URL`: PostgreSQL connection (from attachment)
- `REDIS_URL`: Redis connection (extracted automatically)
- `AWS_ACCESS_KEY_ID`: Tigris storage credentials
- `AWS_SECRET_ACCESS_KEY`: Tigris storage credentials
- `AWS_ENDPOINT_URL_S3`: `https://fly.storage.tigris.dev`
- `AWS_REGION`: `auto`
- `BUCKET_NAME`: `jobagent-storage`

### Production Settings (in fly.toml)
- `ENVIRONMENT=production`
- `S3_ENDPOINT_URL=https://fly.storage.tigris.dev`
- `S3_BUCKET_NAME=jobagent-storage` (updated automatically)
- `PORT=8000`

## Troubleshooting

### Check deployment summary
The deploy script provides a complete summary:
```bash
./deploy.sh
# Shows: App name, region, database, Redis, storage, URL
```

### Check app status
```bash
flyctl status --app jobagent
```

### View real-time logs
```bash
flyctl logs --app jobagent --follow
```

### Check health endpoint
```bash
curl https://jobagent.fly.dev/health
# Should return: {"status": "healthy", "database": true, "storage": true}
```

### Access services directly
```bash
# Database
flyctl postgres connect --app jobagent-db

# Redis
flyctl redis connect jobagent-redis

# Storage dashboard
flyctl storage dashboard --app jobagent
```

### Update secrets
```bash
flyctl secrets set OPENAI_API_KEY=new-key --app jobagent
flyctl secrets list --app jobagent
```

### Common Issues

**Health check fails (503)**:
- Check logs: `flyctl logs --app jobagent`
- Verify all secrets are set: `flyctl secrets list --app jobagent`
- Ensure OPENAI_API_KEY is valid

**OOM (Out of Memory) errors**:
- Already handled with shared-cpu-2x VMs
- Scale up if needed: `flyctl scale vm shared-cpu-4x --app jobagent`

**Storage issues**:
- Verify Tigris credentials: `flyctl secrets list --app jobagent | grep AWS`
- Check storage dashboard: `flyctl storage dashboard --app jobagent`

## Cost Estimation

Typical monthly costs with optimized configuration:
- **App instances** (shared-cpu-2x × 3): ~$15-20/month
- **PostgreSQL**: ~$15/month (1GB)
- **Redis**: ~$10/month (256MB, Upstash)
- **Tigris Storage**: ~$0.15/GB/month + requests
- **Bandwidth**: ~$0.02/GB

**Total**: ~$40-45/month for production deployment

## Custom Configuration

### Change app name
```bash
# In .env.fly
APP_NAME=my-custom-jobagent
./deploy.sh
```

### Change region
```bash
# In .env.fly  
REGION=ord  # Chicago, fra (Frankfurt), nrt (Tokyo), etc.
./deploy.sh
```

### Re-run deployment
The script is idempotent - safe to run multiple times:
```bash
./deploy.sh  # Will update existing resources
```

## Security

The deployment includes:
- ✅ Automatic HTTPS termination with Let's Encrypt
- ✅ Encrypted environment variables (Fly.io secrets)
- ✅ Private networking between services (.flycast domains)
- ✅ Secure credential generation and storage
- ✅ Proper VM isolation and resource limits

Your application will be accessible at `https://your-app-name.fly.dev` with automatic SSL certificates and enterprise-grade security. 