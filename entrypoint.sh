#!/usr/bin/env bash
set -e

echo "🚀 Starting Job Agent service entrypoint..."

# Function to wait for a TCP connection to be available
wait_for_service() {
    local host="$1"
    local port="$2"
    local service_name="$3"
    local max_attempts=${4:-30} # Default to 30 attempts
    local attempt=1
    local sleep_interval=${5:-2} # Default to 2 seconds sleep

    echo "⏳ Waiting for $service_name ($host:$port) to be ready..."
    
    # Using nc (netcat) if available, otherwise fallback or error
    # Ensure nc is available in the Docker image (it's not by default in python:slim usually)
    # If nc is not present, this check will fail. Dockerfile should ensure nc is installed.
    # python:3.12-slim does not have `nc` by default. `curl` is installed though.
    # Alternative: use bash internal /dev/tcp for TCP check if nc is not an option.
    # For now, assume nc is made available or this script is adapted.
    # The Dockerfile installs postgresql-client and curl, but not nc directly.
    # Let's try a bash /dev/tcp approach for wider compatibility if nc isn't there.

    while ! (echo > /dev/tcp/$host/$port) &>/dev/null; do
        if [ $attempt -ge $max_attempts ]; then # Use -ge for "greater than or equal to"
            echo "❌ $service_name ($host:$port) failed to start within timeout ($((max_attempts * sleep_interval)) seconds)."
            exit 1
        fi
        
        echo "   Attempt $attempt/$max_attempts for $service_name..."
        sleep $sleep_interval
        attempt=$((attempt + 1))
    done
    
    echo "✅ $service_name ($host:$port) is ready!"
}

# Determine the main command (first argument to entrypoint.sh)
MAIN_COMMAND="$1"

# Common services to wait for, adjust based on actual command
SHOULD_WAIT_FOR_DB=false
SHOULD_WAIT_FOR_REDIS=false
SHOULD_RUN_MIGRATIONS=false
SHOULD_INIT_MINIO=false

if [ "$MAIN_COMMAND" = "uvicorn" ]; then # API service
    SHOULD_WAIT_FOR_DB=true
    SHOULD_WAIT_FOR_REDIS=true # API might use Redis for caching or other things
    SHOULD_RUN_MIGRATIONS=true
    SHOULD_INIT_MINIO=true
elif [ "$MAIN_COMMAND" = "celery" ]; then # Worker or Beat service
    SHOULD_WAIT_FOR_DB=true  # Celery tasks likely interact with DB
    SHOULD_WAIT_FOR_REDIS=true # Celery requires Redis broker
    # MinIO init and migrations are typically handled by the API service or a dedicated migration job.
fi

# Wait for database if needed
if [ "$SHOULD_WAIT_FOR_DB" = true ]; then
    # DB_HOST and DB_PORT should be available as env vars or fixed (e.g., "db", "5432")
    wait_for_service "${DB_HOST:-db}" "${DB_PORT:-5432}" "PostgreSQL"
fi

# Wait for Redis if needed
if [ "$SHOULD_WAIT_FOR_REDIS" = true ]; then
    # REDIS_HOST and REDIS_PORT should be available as env vars or fixed (e.g., "redis", "6379")
    wait_for_service "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}" "Redis"
fi

# Run database migrations for the API service
if [ "$SHOULD_RUN_MIGRATIONS" = true ]; then
    echo "🔄 Running database migrations..."
    if alembic -c alembic.ini upgrade head; then
        echo "✅ Database migrations completed successfully."
    else
        echo "❌ Database migrations failed. Exiting."
        exit 1
    fi
fi

# Initialize MinIO bucket if this is the API service (or a dedicated init job)
if [ "$SHOULD_INIT_MINIO" = true ]; then
    echo "🪣 Initializing object storage bucket (if not exists)..."
    # S3_ENDPOINT_URL must be configured without http:// for the host part if used directly with nc/dev/tcp.
    # Assuming MinIO is at 'minio:9000' for this check.
    wait_for_service "${MINIO_HOST:-minio}" "${MINIO_PORT:-9000}" "MinIO/S3 Storage"
    
    # The python script call for ensure_bucket_exists:
    # Need to ensure python and boto3 are available here.
    # This assumes the script is run within an environment that has app.storage accessible.
    python -c "
import logging
# Configure basic logging for the init script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('minio_init')

try:
    logger.info('Attempting to import app.storage...')
    from app.storage import ensure_bucket_exists, s3_client, S3_BUCKET_NAME
    logger.info('Successfully imported app.storage.')
    if not s3_client:
        logger.error('S3 client in app.storage is not initialized. Cannot ensure bucket exists.')
        raise ConnectionError('S3 client not initialized')
    if not S3_BUCKET_NAME:
        logger.error('S3_BUCKET_NAME is not configured. Cannot ensure bucket exists.')
        raise ValueError('S3_BUCKET_NAME not configured')

    logger.info('Ensuring bucket \\'%s\\' exists...', S3_BUCKET_NAME)
    if ensure_bucket_exists():
        logger.info('✅ Object storage bucket \\'%s\\' is ready.', S3_BUCKET_NAME)
    else:
        logger.warning('⚠️ Object storage bucket \\'%s\\' initialization may have failed or bucket already checked/exists. Check logs from app.storage.', S3_BUCKET_NAME)
except ImportError as e:
    logger.error('Failed to import app.storage: %s. Ensure PYTHONPATH is correct or app is installed.', e)
    raise
except ConnectionError as e:
    logger.error('MinIO connection error during init: %s', e)
    raise
except ValueError as e:
    logger.error('Configuration error for MinIO init: %s', e)
    raise
except Exception as e:
    logger.error('⚠️ An unexpected error occurred during object storage initialization: %s', e)
    raise
" || echo "MinIO bucket initialization script encountered an error. Check logs."
    # The `|| echo` part ensures the entrypoint doesn't hard fail if the python script returns non-zero,
    # but it will log the python script's error output if any.
    # A more robust solution might involve the python script writing a status file or a more complex check.
fi

echo "🎯 Executing main command: $*"

# Execute the main command passed to the script (e.g., uvicorn, celery)
exec "$@" 