#!/usr/bin/env bash
# This script runs tasks that should only be executed once per deployment.
# It is called by the 'release_command' in fly.toml.
set -e

echo "🚀 Running release tasks..."

# --- Database Migrations ---
echo "🔄 Running database migrations..."

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

# --- End of Migrations ---

# You can add other release tasks here in the future
# For example:
# echo "🔄 Seeding initial data..."
# python -c "from app.db_seeding import seed_data; seed_data()"

echo "✅ Release tasks completed successfully." 