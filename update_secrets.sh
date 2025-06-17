#!/bin/bash

# Quick script to update specific secrets from .env.fly
set -e

APP_NAME="${APP_NAME:-jobagent}"

# Colors for output
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

# Source environment variables from .env.fly
if [ -f ".env.fly" ]; then
    print_status "Loading environment variables from .env.fly..."
    set -a  # automatically export all variables
    source <(grep -v '^#' .env.fly | grep -v '^$' | sed 's/#.*$//' | sed 's/[[:space:]]*$//')
    set +a  # stop automatically exporting
else
    echo "❌ No .env.fly file found. Please create one first."
    exit 1
fi

print_status "Updating secrets for app: ${APP_NAME}"

# Array to collect secrets to update
SECRETS_TO_UPDATE=()

# Check and add PROFILE_INGEST_API_KEY
if [ -n "${PROFILE_INGEST_API_KEY:-}" ]; then
    SECRETS_TO_UPDATE+=("PROFILE_INGEST_API_KEY=${PROFILE_INGEST_API_KEY}")
    print_status "Will update PROFILE_INGEST_API_KEY"
fi

# Check and add ENCRYPTION_KEY
if [ -n "${ENCRYPTION_KEY:-}" ]; then
    SECRETS_TO_UPDATE+=("ENCRYPTION_KEY=${ENCRYPTION_KEY}")
    print_status "Will update ENCRYPTION_KEY"
fi

# Add other secrets you might want to update
if [ -n "${OPENAI_API_KEY:-}" ]; then
    SECRETS_TO_UPDATE+=("OPENAI_API_KEY=${OPENAI_API_KEY}")
    print_status "Will update OPENAI_API_KEY"
fi

if [ -n "${TWILIO_ACCOUNT_SID:-}" ]; then
    SECRETS_TO_UPDATE+=("TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID}")
    print_status "Will update TWILIO_ACCOUNT_SID"
fi

if [ -n "${TWILIO_AUTH_TOKEN:-}" ]; then
    SECRETS_TO_UPDATE+=("TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN}")
    print_status "Will update TWILIO_AUTH_TOKEN"
fi

if [ -n "${FIRECRAWL_API_KEY:-}" ]; then
    SECRETS_TO_UPDATE+=("FIRECRAWL_API_KEY=${FIRECRAWL_API_KEY}")
    print_status "Will update FIRECRAWL_API_KEY"
fi

if [ -n "${SMS_FROM:-}" ]; then
    SECRETS_TO_UPDATE+=("SMS_FROM=${SMS_FROM}")
    print_status "Will update SMS_FROM"
fi

if [ -n "${SMS_TO:-}" ]; then
    SECRETS_TO_UPDATE+=("SMS_TO=${SMS_TO}")
    print_status "Will update SMS_TO"
fi

if [ -n "${BROWSERBASE_API_KEY:-}" ]; then
    SECRETS_TO_UPDATE+=("BROWSERBASE_API_KEY=${BROWSERBASE_API_KEY}")
    print_status "Will update BROWSERBASE_API_KEY"
fi

if [ -n "${BROWSERBASE_PROJECT_ID:-}" ]; then
    SECRETS_TO_UPDATE+=("BROWSERBASE_PROJECT_ID=${BROWSERBASE_PROJECT_ID}")
    print_status "Will update BROWSERBASE_PROJECT_ID"
fi

# Update secrets in batches
if [ ${#SECRETS_TO_UPDATE[@]} -gt 0 ]; then
    print_status "Updating ${#SECRETS_TO_UPDATE[@]} secrets..."
    
    # Split into chunks of 5 secrets each to avoid command line limits
    for ((i=0; i<${#SECRETS_TO_UPDATE[@]}; i+=5)); do
        chunk=("${SECRETS_TO_UPDATE[@]:i:5}")
        flyctl secrets set --app "${APP_NAME}" "${chunk[@]}"
    done
    
    print_success "✅ All secrets updated successfully!"
    print_warning "🔄 App will restart automatically with new secrets"
else
    print_warning "No secrets found in .env.fly to update"
fi

print_status "Current secrets (keys only):"
flyctl secrets list --app "${APP_NAME}" 