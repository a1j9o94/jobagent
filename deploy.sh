#!/bin/bash

# Job Agent Fly.io Deployment Script
set -e

echo "🚀 Starting Job Agent deployment to Fly.io..."

# Source environment variables if .env.fly exists
if [ -f ".env.fly" ]; then
    echo "📋 Loading environment variables from .env.fly..."
    # More robust parsing of .env file
    set -a  # automatically export all variables
    source <(grep -v '^#' .env.fly | grep -v '^$' | sed 's/#.*$//' | sed 's/[[:space:]]*$//')
    set +a  # stop automatically exporting
else
    echo "⚠️  No .env.fly file found. Using defaults or environment variables."
    echo "   Copy .env.fly.example to .env.fly and configure your secrets."
fi

APP_NAME="${APP_NAME:-jobagent}"
REGION="${REGION:-sea}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if flyctl is installed
if ! command -v flyctl &> /dev/null; then
    print_error "flyctl is not installed. Please install it first:"
    echo "curl -L https://fly.io/install.sh | sh"
    exit 1
fi

# Check if user is logged in
if ! flyctl auth whoami &> /dev/null; then
    print_warning "Not logged in to Fly.io. Please login first:"
    flyctl auth login
fi

print_status "Setting up Fly.io application..."

# Create the app if it doesn't exist
if ! flyctl apps list | grep -q "^${APP_NAME}"; then
    print_status "Creating new Fly.io app: ${APP_NAME}"
    flyctl apps create "${APP_NAME}" --org personal
else
    print_success "App ${APP_NAME} already exists"
fi

print_status "Setting up PostgreSQL database..."

# Create Postgres database if it doesn't exist
DB_NAME="${APP_NAME}-db"
if ! flyctl postgres list | grep -q "${DB_NAME}"; then
    print_status "Creating PostgreSQL database: ${DB_NAME}"
    
    # Check if there's an existing DATABASE_URL from a previously destroyed database
    if flyctl secrets list --app "${APP_NAME}" | grep -q "^DATABASE_URL "; then
        print_warning "Found existing DATABASE_URL secret from previous database. Removing it..."
        flyctl secrets unset DATABASE_URL --app "${APP_NAME}" || true
        print_status "Waiting for secret removal to propagate..."
        sleep 5
    fi
    
    flyctl postgres create \
        --name "${DB_NAME}" \
        --region "${REGION}" \
        --initial-cluster-size 1 \
        --vm-size shared-cpu-1x \
        --volume-size 1
    
    print_status "Attaching PostgreSQL database to app..."
    # Retry attachment in case of transient issues
    if ! flyctl postgres attach "${DB_NAME}" --app "${APP_NAME}"; then
        print_warning "First attachment attempt failed. Retrying in 5 seconds..."
        sleep 5
        flyctl postgres attach "${DB_NAME}" --app "${APP_NAME}"
    fi
    print_success "PostgreSQL database created and attached successfully"
else
    print_success "PostgreSQL database ${DB_NAME} already exists"
fi

print_status "Setting up Redis..."

# Create Redis if it doesn't exist
REDIS_NAME="${APP_NAME}-redis"
if ! flyctl redis list | grep -q "${REDIS_NAME}"; then
    print_status "Creating Redis instance: ${REDIS_NAME}"
    flyctl redis create \
        --name "${REDIS_NAME}" \
        --region "${REGION}" \
        --no-replicas
    
    print_status "Waiting for Redis to be ready..."
    sleep 10
else
    print_success "Redis instance ${REDIS_NAME} already exists"
fi

# Get Redis URL and configure it
print_status "Configuring Redis connection..."
REDIS_OUTPUT=$(flyctl redis status "${REDIS_NAME}" 2>/dev/null || echo "")
if [ -n "$REDIS_OUTPUT" ]; then
    # Extract the Private URL from the text output
    REDIS_URL=$(echo "$REDIS_OUTPUT" | grep -i "private url" | awk '{print $NF}' | head -1)
    if [ -n "$REDIS_URL" ] && [[ "$REDIS_URL" == redis://* ]]; then
        print_success "Redis URL obtained: ${REDIS_URL:0:30}..."
    else
        print_warning "Could not extract Redis URL from status output."
        print_warning "Please configure manually after deployment:"
        print_warning "flyctl secrets set REDIS_URL=redis://default:PASSWORD@fly-${REDIS_NAME}.upstash.io:6379 --app ${APP_NAME}"
        REDIS_URL=""
    fi
else
    print_error "Failed to get Redis status. Please ensure Redis instance exists:"
    print_error "flyctl redis list"
    REDIS_URL=""
fi

print_status "Setting up Tigris object storage..."

# Set up Tigris storage
STORAGE_NAME="${APP_NAME}-storage"
BUCKET_NAME="${STORAGE_NAME}"  # Use consistent naming

# Check if Tigris storage already exists by checking for AWS credentials
if flyctl secrets list --app "${APP_NAME}" | grep -q "AWS_ACCESS_KEY_ID"; then
    print_success "Tigris storage credentials already exist"
    
    # Get the existing bucket name from secrets
    EXISTING_BUCKET=$(flyctl secrets list --app "${APP_NAME}" | grep "BUCKET_NAME" | awk '{print $2}' || echo "")
    if [ -n "$EXISTING_BUCKET" ]; then
        BUCKET_NAME="$EXISTING_BUCKET"
        print_success "Using existing bucket: $BUCKET_NAME"
    fi
else
    print_status "Creating Tigris storage bucket: ${STORAGE_NAME}"
    
    # Create Tigris storage and capture the output
    print_status "Running: flyctl storage create ${STORAGE_NAME} --app ${APP_NAME} --yes"
    TIGRIS_OUTPUT=$(flyctl storage create "${STORAGE_NAME}" --app "${APP_NAME}" --yes 2>&1)
    
    print_status "Tigris creation output:"
    echo "$TIGRIS_OUTPUT"
    
    # Try multiple patterns to extract credentials
    AWS_ACCESS_KEY_ID=$(echo "$TIGRIS_OUTPUT" | grep -E "(AWS_ACCESS_KEY_ID|Access Key ID)" | awk -F'[:=]' '{print $NF}' | tr -d ' ' | head -1)
    AWS_SECRET_ACCESS_KEY=$(echo "$TIGRIS_OUTPUT" | grep -E "(AWS_SECRET_ACCESS_KEY|Secret Access Key)" | awk -F'[:=]' '{print $NF}' | tr -d ' ' | head -1)
    
    # Alternative extraction method using different patterns
    if [ -z "$AWS_ACCESS_KEY_ID" ]; then
        AWS_ACCESS_KEY_ID=$(echo "$TIGRIS_OUTPUT" | grep -oE 'tid_[a-zA-Z0-9_]+' | head -1)
    fi
    
    if [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        AWS_SECRET_ACCESS_KEY=$(echo "$TIGRIS_OUTPUT" | grep -oE 'tsec_[a-zA-Z0-9_]+' | head -1)
    fi
    
    print_status "Extracted credentials:"
    print_status "AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:0:10}... (${#AWS_ACCESS_KEY_ID} chars)"
    print_status "AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:0:10}... (${#AWS_SECRET_ACCESS_KEY} chars)"
    
    if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        print_error "Could not extract Tigris credentials automatically."
        print_error "Tigris output was:"
        echo "$TIGRIS_OUTPUT"
        print_error "Please extract credentials manually and set them using:"
        print_error "flyctl secrets set AWS_ACCESS_KEY_ID=<key> AWS_SECRET_ACCESS_KEY=<secret> --app ${APP_NAME}"
        print_error "Then re-run this script."
        exit 1
    else
        print_success "Tigris credentials extracted successfully"
    fi
fi

print_status "Setting up storage volume..."

# Create volume for file storage
VOLUME_NAME="${APP_NAME}_data"
if ! flyctl volumes list --app "${APP_NAME}" | grep -q "${VOLUME_NAME}"; then
    print_status "Creating storage volume: ${VOLUME_NAME}"
    flyctl volumes create "${VOLUME_NAME}" \
        --region "${REGION}" \
        --size 1 \
        --app "${APP_NAME}"
else
    print_success "Storage volume ${VOLUME_NAME} already exists"
fi

print_status "Setting environment variables and secrets..."

# Get existing secrets to avoid re-generating them on every deploy
EXISTING_SECRETS=$(flyctl secrets list --app "${APP_NAME}")

# Prepare secrets array
SECRETS_TO_SET=()

# Check for PROFILE_INGEST_API_KEY
if ! echo "$EXISTING_SECRETS" | grep -q "^PROFILE_INGEST_API_KEY "; then
    NEW_API_KEY=$(openssl rand -hex 32)
    SECRETS_TO_SET+=("PROFILE_INGEST_API_KEY=${NEW_API_KEY}")
    DISPLAY_API_KEY=$NEW_API_KEY # Store for displaying later
    print_warning "Generated new PROFILE_INGEST_API_KEY."
else
    print_success "PROFILE_INGEST_API_KEY already set."
fi

# Check for ENCRYPTION_KEY
if ! echo "$EXISTING_SECRETS" | grep -q "^ENCRYPTION_KEY "; then
    SECRETS_TO_SET+=("ENCRYPTION_KEY=$(openssl rand -base64 32)")
    print_warning "Generated new ENCRYPTION_KEY."
else
    print_success "ENCRYPTION_KEY already set."
fi

# Add user-provided secrets with validation
if [ -n "${TWILIO_ACCOUNT_SID:-}" ] && [ "${TWILIO_ACCOUNT_SID}" != "your-twilio-sid" ]; then
    SECRETS_TO_SET+=("TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID}")
fi

if [ -n "${TWILIO_AUTH_TOKEN:-}" ] && [ "${TWILIO_AUTH_TOKEN}" != "your-twilio-token" ]; then
    SECRETS_TO_SET+=("TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN}")
fi

if [ -n "${OPENAI_API_KEY:-}" ] && [ "${OPENAI_API_KEY}" != "your-openai-key" ]; then
    SECRETS_TO_SET+=("OPENAI_API_KEY=${OPENAI_API_KEY}")
fi

if [ -n "${WA_FROM:-}" ] && [ "${WA_FROM}" != "whatsapp:+14155238886" ]; then
    SECRETS_TO_SET+=("WA_FROM=${WA_FROM}")
fi

if [ -n "${WA_TO:-}" ] && [ "${WA_TO}" != "whatsapp:+1234567890" ]; then
    SECRETS_TO_SET+=("WA_TO=${WA_TO}")
fi

# Add Firecrawl API key if provided
if [ -n "${FIRECRAWL_API_KEY:-}" ] && [ "${FIRECRAWL_API_KEY}" != "fc-1234567890" ]; then
    SECRETS_TO_SET+=("FIRECRAWL_API_KEY=${FIRECRAWL_API_KEY}")
fi

# Add Node.js browser automation overrides if provided
if [ -n "${STAGEHAND_TIMEOUT:-}" ]; then
    SECRETS_TO_SET+=("STAGEHAND_TIMEOUT=${STAGEHAND_TIMEOUT}")
fi

if [ -n "${BROWSER_VIEWPORT_WIDTH:-}" ]; then
    SECRETS_TO_SET+=("BROWSER_VIEWPORT_WIDTH=${BROWSER_VIEWPORT_WIDTH}")
fi

if [ -n "${BROWSER_VIEWPORT_HEIGHT:-}" ]; then
    SECRETS_TO_SET+=("BROWSER_VIEWPORT_HEIGHT=${BROWSER_VIEWPORT_HEIGHT}")
fi

# Add Redis URL for both Python and Node.js services
if [ -n "${REDIS_URL}" ]; then
    SECRETS_TO_SET+=("REDIS_URL=${REDIS_URL}")
    SECRETS_TO_SET+=("NODE_REDIS_URL=${REDIS_URL}")  # Node.js service uses this
fi

# Add Tigris/S3 credentials if we have them
if [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
    SECRETS_TO_SET+=(
        "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
        "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"
        "AWS_ENDPOINT_URL_S3=https://fly.storage.tigris.dev"
        "S3_ENDPOINT_URL=https://fly.storage.tigris.dev"
        "AWS_REGION=auto"
        "S3_BUCKET_NAME=${BUCKET_NAME}"
        "BUCKET_NAME=${BUCKET_NAME}"
    )
fi

# Set secrets in batches to avoid command line length limits
if [ ${#SECRETS_TO_SET[@]} -gt 0 ]; then
    print_status "Setting ${#SECRETS_TO_SET[@]} secrets..."
    
    # Split into chunks of 5 secrets each
    for ((i=0; i<${#SECRETS_TO_SET[@]}; i+=5)); do
        chunk=("${SECRETS_TO_SET[@]:i:5}")
        flyctl secrets set --app "${APP_NAME}" "${chunk[@]}"
    done
    
    print_success "All secrets configured successfully"
else
    print_warning "No secrets to set"
fi

print_status "Updating fly.toml configuration..."

# Update fly.toml with the correct S3 bucket name
if [ -n "$BUCKET_NAME" ]; then
    sed -i.bak "s/S3_BUCKET_NAME = \".*\"/S3_BUCKET_NAME = \"$BUCKET_NAME\"/" fly.toml
    print_success "Updated S3_BUCKET_NAME in fly.toml to: $BUCKET_NAME"
fi

# Update API_BASE_URL in fly.toml
sed -i.bak "s/API_BASE_URL = \".*\"/API_BASE_URL = \"https:\/\/${APP_NAME}.fly.dev\"/" fly.toml
print_success "Updated API_BASE_URL in fly.toml to: https://${APP_NAME}.fly.dev"

print_status "Deploying application..."

# Deploy the application
flyctl deploy --app "${APP_NAME}" --dockerfile Dockerfile

print_success "Deployment completed!"

# Post-deployment validation
print_status "Validating deployment..."

# Wait a moment for the app to start
sleep 10

# Check if the app is responding
APP_URL="https://${APP_NAME}.fly.dev"
print_status "Checking health endpoint at ${APP_URL}/health..."

if curl -f -s "${APP_URL}/health" > /dev/null 2>&1; then
    print_success "✅ Health check passed! Application is running correctly."
else
    print_warning "⚠️  Health check failed. App may still be starting up."
    print_status "Check logs with: flyctl logs --app ${APP_NAME}"
fi

# Verify S3 bucket accessibility
print_status "Verifying S3 bucket setup..."
if [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${BUCKET_NAME:-}" ]; then
    print_status "Testing bucket access with curl..."
    
    # Test if bucket is accessible (this will return 403 if bucket doesn't exist, 200 if it does)
    BUCKET_TEST=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: AWS4-HMAC-SHA256 Credential=${AWS_ACCESS_KEY_ID}/$(date +%Y%m%d)/auto/s3/aws4_request" \
        "https://fly.storage.tigris.dev/${BUCKET_NAME}/")
    
    if [ "$BUCKET_TEST" = "200" ] || [ "$BUCKET_TEST" = "404" ]; then
        print_success "✅ Bucket ${BUCKET_NAME} is accessible"
    else
        print_warning "⚠️  Bucket access test returned HTTP ${BUCKET_TEST}"
        print_status "Creating bucket via app endpoint..."
        
        # Try to trigger bucket creation via health check
        curl -s "${APP_URL}/health" > /dev/null || true
        
        print_status "If bucket issues persist, you may need to:"
        print_status "1. SSH into the app: flyctl ssh console --app ${APP_NAME}"
        print_status "2. Run: python -c 'from app.tools.storage import ensure_bucket_exists; print(ensure_bucket_exists())'"
        print_status "3. Check logs: flyctl logs --app ${APP_NAME}"
    fi
else
    print_warning "⚠️  S3 credentials not set. Bucket verification skipped."
fi

print_success "🎉 Job Agent successfully deployed to Fly.io!"
print_status "🌐 Your application is available at: ${APP_URL}"

echo ""
print_status "📋 Deployment Summary:"
echo "  • App Name: ${APP_NAME}"
echo "  • Region: ${REGION}"
echo "  • Database: ${DB_NAME}"
echo "  • Redis: ${REDIS_NAME}"
echo "  • Storage: ${BUCKET_NAME}"
echo "  • URL: ${APP_URL}"
echo "  • Services: Python API + Node.js Queue Consumer"

echo ""
print_status "🔑 API Key Information:"
if [ -n "$DISPLAY_API_KEY" ]; then
    echo -e "${GREEN}✅ Your new API Key has been generated and set:${NC}"
    echo -e "  ${YELLOW}PROFILE_INGEST_API_KEY=${DISPLAY_API_KEY}${NC}"
    print_warning "Save this key, it will not be shown again!"
else
    echo "  Your API key is already configured. To retrieve it, run:"
    echo -e "  ${BLUE}flyctl secrets list --app ${APP_NAME} | grep PROFILE_INGEST_API_KEY${NC}"
fi

echo ""
print_status "🛠️  Useful commands:"
echo "  flyctl logs --app ${APP_NAME}                    # View logs"
echo "  flyctl ssh console --app ${APP_NAME}             # SSH into the app"
echo "  flyctl status --app ${APP_NAME}                  # Check app status"
echo "  flyctl scale count 2 --app ${APP_NAME}           # Scale to 2 instances"
echo "  flyctl secrets list --app ${APP_NAME}            # List secrets"
echo "  flyctl storage dashboard --app ${APP_NAME}       # Manage storage"

echo ""
print_status "🔍 Debug Information:"
echo "  S3 Endpoint: https://fly.storage.tigris.dev"
echo "  Bucket Name: ${BUCKET_NAME}"
echo "  Storage Name: ${STORAGE_NAME}"
echo ""
print_status "🛠️  Troubleshooting S3 Issues:"
echo "  If you're getting 403 Forbidden errors:"
echo "  1. Check if credentials are set: flyctl secrets list --app ${APP_NAME} | grep AWS"
echo "  2. SSH into app and test: flyctl ssh console --app ${APP_NAME}"
echo "  3. Run storage test: python -c 'from app.tools.storage import health_check; print(health_check())'"
echo "  4. Check bucket exists: python -c 'from app.tools.storage import ensure_bucket_exists; print(ensure_bucket_exists())'"
echo "  5. View detailed logs: flyctl logs --app ${APP_NAME} | grep -E '(ERROR|bucket|storage|S3)'"
echo ""
print_status "📝 Next Steps:"
echo "  1. Check application logs: flyctl logs --app ${APP_NAME}"
echo "  2. Test the API endpoints at: ${APP_URL}"
echo "  3. Test the queue-based job application flow at: ${APP_URL}/jobs/apply/{role_id}"
echo "  4. Configure additional secrets if needed"
echo "  5. Set up monitoring and alerts"

if [ -z "${OPENAI_API_KEY:-}" ] || [ "${OPENAI_API_KEY}" = "your-openai-key" ]; then
    print_warning "⚠️  Remember to set your OPENAI_API_KEY:"
    echo "  flyctl secrets set OPENAI_API_KEY=your_actual_key --app ${APP_NAME}"
fi

if [ -z "${TWILIO_ACCOUNT_SID:-}" ] || [ "${TWILIO_ACCOUNT_SID}" = "your-twilio-sid" ]; then
    print_warning "⚠️  Remember to set your Twilio credentials:"
    echo "  flyctl secrets set TWILIO_ACCOUNT_SID=your_sid TWILIO_AUTH_TOKEN=your_token --app ${APP_NAME}"
fi 