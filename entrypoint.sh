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

# In production, Fly.io handles service readiness and migrations via release commands.
# The app should start immediately without waiting.
if [ "$ENVIRONMENT" != "production" ]; then
    if [ "$MAIN_COMMAND" = "uvicorn" ]; then # API service
        SHOULD_WAIT_FOR_DB=true
        SHOULD_WAIT_FOR_REDIS=true # API might use Redis for caching or other things
        SHOULD_RUN_MIGRATIONS=true
        if [[ "${S3_ENDPOINT_URL:-}" == *"minio"* ]] || [[ "${S3_ENDPOINT_URL:-}" == *"localhost"* ]] || [[ "${S3_ENDPOINT_URL:-}" == *"127.0.0.1"* ]]; then
            SHOULD_INIT_MINIO=true
        fi
    elif [ "$MAIN_COMMAND" = "celery" ]; then # Worker or Beat service
        SHOULD_WAIT_FOR_DB=true
        SHOULD_WAIT_FOR_REDIS=true
    elif [ "$MAIN_COMMAND" = "alembic" ]; then # Alembic CLI command
        SHOULD_WAIT_FOR_DB=true
    elif [[ "$MAIN_COMMAND" == *"node"* ]] || [[ "$1" == *"node"* ]] || [[ "$*" == *"node"* ]]; then # Node.js service
        SHOULD_WAIT_FOR_REDIS=true
    fi
else
    echo "✅ Production environment detected. Skipping startup waits and migration checks."
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
    # For Fly.io deployments, migrations are handled by the release_command in fly.toml.
    # For local Docker development, we run them here.
    if [ "$ENVIRONMENT" != "production" ]; then
        echo "🔄 Running database migrations for local development..."
        
        # Check if we have any migration files
        MIGRATION_COUNT=$(find alembic/versions -name "*.py" -not -name "__*" | wc -l)
        
        if [ "$MIGRATION_COUNT" -eq 0 ]; then
            echo "📋 No migration files found. Generating initial database schema..."
            
            # Generate initial migration from SQLModel models
            if alembic revision --autogenerate -m "Initial database schema"; then
                echo "✅ Initial migration generated successfully."
                
                # Fix common SQLModel import issue in generated migration
                LATEST_MIGRATION=$(find alembic/versions -name "*.py" -not -name "__*" | sort | tail -1)
                if [ -n "$LATEST_MIGRATION" ]; then
                    echo "🔧 Fixing SQLModel imports in generated migration..."
                    sed -i 's/from alembic import op/from alembic import op\nimport sqlmodel.sql.sqltypes/' "$LATEST_MIGRATION"
                    echo "✅ Migration imports fixed."
                fi
            else
                echo "❌ Failed to generate initial migration. Exiting."
                exit 1
            fi
        else
            echo "📋 Found $MIGRATION_COUNT existing migration file(s)."
        fi
        
        # Run migrations to update database to latest schema
        if alembic -c alembic.ini upgrade head; then
            echo "✅ Database migrations completed successfully."
        else
            echo "❌ Database migrations failed. Exiting."
            exit 1
        fi
    else
        echo "✅ Skipping migrations in entrypoint for production (handled by flyctl release_command)."
    fi
fi

# Initialize MinIO bucket if this is the API service (or a dedicated init job)
if [ "$SHOULD_INIT_MINIO" = true ]; then
    echo "🪣 Initializing object storage bucket (if not exists)..."
    
    # Check if this is local MinIO vs external S3
    if [[ "${S3_ENDPOINT_URL:-}" == *"minio"* ]] || [[ "${S3_ENDPOINT_URL:-}" == *"localhost"* ]] || [[ "${S3_ENDPOINT_URL:-}" == *"127.0.0.1"* ]]; then
        # Local MinIO setup
        echo "🔧 Detected local MinIO, creating bucket using mc command..."
        
        # Wait for MinIO to be ready
        MINIO_HOST=$(echo "${S3_ENDPOINT_URL}" | sed 's|http://||' | sed 's|https://||' | cut -d':' -f1)
        MINIO_PORT=$(echo "${S3_ENDPOINT_URL}" | sed 's|http://||' | sed 's|https://||' | cut -d':' -f2)
        
        # Default to minio:9000 if parsing fails
        MINIO_HOST="${MINIO_HOST:-minio}"
        MINIO_PORT="${MINIO_PORT:-9000}"
        
        wait_for_service "$MINIO_HOST" "$MINIO_PORT" "MinIO"
        
        # Create bucket using mc command (MinIO client)
        # Note: This assumes mc is available in the container, which it might not be
        # For local development, it's better to create the bucket externally
        echo "✅ MinIO is ready. Bucket creation should be handled by docker-compose setup."
        echo "💡 If bucket doesn't exist, run: docker compose exec minio mc mb /data/${S3_BUCKET_NAME} --ignore-existing"
    else
        # External S3 services like Tigris - use Python API
        python -c "
import logging
# Configure basic logging for the init script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('s3_init')

try:
    logger.info('Attempting to import app.tools...')
    from app.tools import ensure_bucket_exists, s3_client, S3_BUCKET_NAME
    logger.info('Successfully imported app.tools.')
    if not s3_client:
        logger.warning('S3 client in app.tools is not initialized. This is normal for external S3 services.')
    if not S3_BUCKET_NAME:
        logger.error('S3_BUCKET_NAME is not configured. Cannot ensure bucket exists.')
        raise ValueError('S3_BUCKET_NAME not configured')

    logger.info('Ensuring bucket \\'%s\\' exists...', S3_BUCKET_NAME)
    if ensure_bucket_exists():
        logger.info('✅ Object storage bucket \\'%s\\' is ready.', S3_BUCKET_NAME)
    else:
        logger.info('✅ Object storage bucket \\'%s\\' check completed (may already exist).', S3_BUCKET_NAME)
except ImportError as e:
    logger.error('Failed to import app.tools: %s. Ensure PYTHONPATH is correct or app is installed.', e)
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
    fi
    echo "✅ S3 storage initialization completed."
fi

echo "🎯 Executing main command: $*"

# Execute the main command passed to the script (e.g., uvicorn, celery)
exec "$@" 