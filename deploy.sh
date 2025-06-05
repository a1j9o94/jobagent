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
    flyctl postgres create \
        --name "${DB_NAME}" \
        --region "${REGION}" \
        --initial-cluster-size 1 \
        --vm-size shared-cpu-1x \
        --volume-size 1
    
    print_status "Attaching PostgreSQL database to app..."
    flyctl postgres attach "${DB_NAME}" --app "${APP_NAME}"
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
else
    print_status "Creating Tigris storage bucket: ${STORAGE_NAME}"
    
    # Create Tigris storage and capture the output
    TIGRIS_OUTPUT=$(flyctl storage create "${STORAGE_NAME}" --app "${APP_NAME}" --yes 2>&1 || true)
    
    # Extract credentials from output
    AWS_ACCESS_KEY_ID=$(echo "$TIGRIS_OUTPUT" | grep "AWS_ACCESS_KEY_ID:" | awk '{print $2}' || echo "")
    AWS_SECRET_ACCESS_KEY=$(echo "$TIGRIS_OUTPUT" | grep "AWS_SECRET_ACCESS_KEY:" | awk '{print $2}' || echo "")
    
    if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        print_warning "Could not extract Tigris credentials automatically."
        print_warning "Please set them manually using the output from the storage creation."
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

# Prepare secrets array
SECRETS_TO_SET=()

# Add basic secrets
SECRETS_TO_SET+=(
    "PROFILE_INGEST_API_KEY=$(openssl rand -hex 32)"
    "ENCRYPTION_KEY=$(openssl rand -base64 32)"
)

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

# Add Redis URL
if [ -n "${REDIS_URL}" ]; then
    SECRETS_TO_SET+=("REDIS_URL=${REDIS_URL}")
fi

# Add Tigris/S3 credentials if we have them
if [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
    SECRETS_TO_SET+=(
        "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
        "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"
        "AWS_ENDPOINT_URL_S3=https://fly.storage.tigris.dev"
        "AWS_REGION=auto"
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

# Update fly.toml with correct bucket name if needed
if [ -n "${BUCKET_NAME}" ]; then
    # Update S3_BUCKET_NAME in fly.toml to match actual bucket
    if grep -q "S3_BUCKET_NAME.*=" fly.toml; then
        sed -i.bak "s/S3_BUCKET_NAME = .*/S3_BUCKET_NAME = \"${BUCKET_NAME}\"/" fly.toml
        print_success "Updated S3_BUCKET_NAME in fly.toml to: ${BUCKET_NAME}"
    fi
fi

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

echo ""
print_status "🛠️  Useful commands:"
echo "  flyctl logs --app ${APP_NAME}                    # View logs"
echo "  flyctl ssh console --app ${APP_NAME}             # SSH into the app"
echo "  flyctl status --app ${APP_NAME}                  # Check app status"
echo "  flyctl scale count 2 --app ${APP_NAME}           # Scale to 2 instances"
echo "  flyctl secrets list --app ${APP_NAME}            # List secrets"
echo "  flyctl storage dashboard --app ${APP_NAME}       # Manage storage"

echo ""
print_status "📝 Next Steps:"
echo "  1. Check application logs: flyctl logs --app ${APP_NAME}"
echo "  2. Test the API endpoints at: ${APP_URL}"
echo "  3. Configure additional secrets if needed"
echo "  4. Set up monitoring and alerts"

if [ -z "${OPENAI_API_KEY:-}" ] || [ "${OPENAI_API_KEY}" = "your-openai-key" ]; then
    print_warning "⚠️  Remember to set your OPENAI_API_KEY:"
    echo "  flyctl secrets set OPENAI_API_KEY=your_actual_key --app ${APP_NAME}"
fi

if [ -z "${TWILIO_ACCOUNT_SID:-}" ] || [ "${TWILIO_ACCOUNT_SID}" = "your-twilio-sid" ]; then
    print_warning "⚠️  Remember to set your Twilio credentials:"
    echo "  flyctl secrets set TWILIO_ACCOUNT_SID=your_sid TWILIO_AUTH_TOKEN=your_token --app ${APP_NAME}"
fi 