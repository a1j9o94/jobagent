#!/usr/bin/env bash
set -e

echo "🚀 Starting Job Agent service entrypoint..."

# Function to parse DATABASE_URL and extract host and port
parse_database_url() {
    if [ -z "$DATABASE_URL" ]; then
        echo "DB_HOST=db"
        echo "DB_PORT=5432"
        return
    fi
    
    # Remove the protocol part (postgresql:// or postgres://)
    local url_without_protocol="${DATABASE_URL#*://}"
    
    # Extract the part after @ (host:port/database)
    local host_port_db="${url_without_protocol#*@}"
    
    # Extract host:port (before the /)
    local host_port="${host_port_db%%/*}"
    
    # Extract host and port
    local host="${host_port%:*}"
    local port="${host_port#*:}"
    
    # If port is the same as host, then no port was specified, use default
    if [ "$port" = "$host" ]; then
        port="5432"
    fi
    
    echo "DB_HOST=$host"
    echo "DB_PORT=$port"
}

# Function to parse REDIS_URL and extract host and port
parse_redis_url() {
    if [ -z "$REDIS_URL" ]; then
        echo "REDIS_HOST=redis"
        echo "REDIS_PORT=6379"
        return
    fi
    
    # Remove the protocol part (redis://)
    local url_without_protocol="${REDIS_URL#*://}"
    
    # Extract the part after @ if it exists, otherwise use the whole thing
    if [[ "$url_without_protocol" == *"@"* ]]; then
        local host_port_db="${url_without_protocol#*@}"
    else
        local host_port_db="$url_without_protocol"
    fi
    
    # Extract host:port (before the /)
    local host_port="${host_port_db%%/*}"
    
    # Extract host and port
    local host="${host_port%:*}"
    local port="${host_port#*:}"
    
    # If port is the same as host, then no port was specified, use default
    if [ "$port" = "$host" ]; then
        port="6379"
    fi
    
    echo "REDIS_HOST=$host"
    echo "REDIS_PORT=$port"
}

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
    SHOULD_INIT_MINIO=false  # Use external S3 service (Tigris), no need to wait for local MinIO
elif [ "$MAIN_COMMAND" = "celery" ]; then # Worker or Beat service
    SHOULD_WAIT_FOR_DB=true  # Celery tasks likely interact with DB
    SHOULD_WAIT_FOR_REDIS=true # Celery requires Redis broker
    # MinIO init and migrations are typically handled by the API service or a dedicated migration job.
fi

# Parse database connection details from DATABASE_URL
if [ "$SHOULD_WAIT_FOR_DB" = true ]; then
    echo "🔍 Parsing database connection details..."
    eval $(parse_database_url)
    echo "   Database host: $DB_HOST:$DB_PORT"
    wait_for_service "$DB_HOST" "$DB_PORT" "PostgreSQL"
fi

# Parse Redis connection details from REDIS_URL
if [ "$SHOULD_WAIT_FOR_REDIS" = true ]; then
    echo "🔍 Parsing Redis connection details..."
    eval $(parse_redis_url)
    echo "   Redis host: $REDIS_HOST:$REDIS_PORT"
    wait_for_service "$REDIS_HOST" "$REDIS_PORT" "Redis"
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
    # For external S3 services like Tigris, we don't need to wait for a local service
    # Just try to ensure the bucket exists using the Python API
    python -c "
import logging
# Configure basic logging for the init script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('s3_init')

try:
    logger.info('Attempting to import app.storage...')
    from app.storage import ensure_bucket_exists, s3_client, S3_BUCKET_NAME
    logger.info('Successfully imported app.storage.')
    if not s3_client:
        logger.warning('S3 client in app.storage is not initialized. This is normal for external S3 services.')
    if not S3_BUCKET_NAME:
        logger.error('S3_BUCKET_NAME is not configured. Cannot ensure bucket exists.')
        raise ValueError('S3_BUCKET_NAME not configured')

    logger.info('Ensuring bucket \\'%s\\' exists...', S3_BUCKET_NAME)
    if ensure_bucket_exists():
        logger.info('✅ Object storage bucket \\'%s\\' is ready.', S3_BUCKET_NAME)
    else:
        logger.info('✅ Object storage bucket \\'%s\\' check completed (may already exist).', S3_BUCKET_NAME)
except ImportError as e:
    logger.error('Failed to import app.storage: %s. Ensure PYTHONPATH is correct or app is installed.', e)
    exit(1)
except ConnectionError as e:
    logger.warning('S3 connection issue during init (this is normal for external services): %s', e)
    logger.info('✅ Continuing startup - S3 connectivity will be handled at runtime.')
except ValueError as e:
    logger.error('Configuration error for S3 init: %s', e)
    exit(1)
except Exception as e:
    logger.warning('S3 storage initialization encountered an issue: %s. Continuing startup.', e)
    logger.info('✅ S3 connectivity will be handled at runtime.')
"
    echo "✅ S3 storage initialization completed."
fi

echo "🎯 Executing main command: $*"

# Execute the main command passed to the script (e.g., uvicorn, celery)
exec "$@" 