#!/bin/bash
set -e

# The migration message is the first argument to the script
MIGRATION_MESSAGE="$1"

if [ -z "$MIGRATION_MESSAGE" ]; then
    echo "❌ Please provide a migration message."
    echo "Usage: uv run poe migrate \"Your migration message\""
    exit 1
fi

echo "🚀 Starting database migration process..."

# 1. Start Docker containers
# We start the 'api' service because it has the code and dependencies.
# 'up -d' is idempotent and will only start services that are not running.
echo "   -> Ensuring required services are running..."
docker compose up -d api

# 2. Apply existing migrations
# Upgrading to 'head' ensures the database is up-to-date before we generate a new migration.
echo "   -> Applying existing migrations (alembic upgrade head)..."
docker compose exec api alembic upgrade head

# 3. Generate new migration file if a message was provided
echo "   -> Generating new migration: '$MIGRATION_MESSAGE'"
# Run as root user to bypass volume permission issues when creating the new file
docker compose exec -u root api alembic revision --autogenerate -m "$MIGRATION_MESSAGE"

echo ""
echo "✅ Success! New migration file created in 'alembic/versions'."
echo "   Please check the new file and commit it to version control." 