# alembic/env.py
import os
from logging.config import fileConfig
from sqlmodel import SQLModel
from sqlalchemy import engine_from_config, pool, create_engine  # Added create_engine
from alembic import context
from dotenv import load_dotenv

# Load environment variables from .env file for local alembic runs
# In a Docker environment, these would typically be set in the container environment
load_dotenv()

# Import all models to ensure they're registered with SQLModel.metadata
# This requires your app.models to be importable from the alembic directory.
# If alembic is run from the project root, this path might need adjustment
# or the PYTHONPATH needs to be set up correctly.
# Assuming alembic commands are run from the project root where `app` is a top-level package.
from app.models import *

# This is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the SQLAlchemy URL from environment variable or alembic.ini
# The design doc implies DATABASE_URL from env var is primary.
db_url = os.getenv("DATABASE_URL")
if not db_url:
    # Fallback to alembic.ini if DATABASE_URL env var is not set
    # This is not explicitly in design doc but good practice for alembic.ini usage
    db_url = config.get_main_option("sqlalchemy.url")
if not db_url:
    raise ValueError(
        "DATABASE_URL environment variable or sqlalchemy.url in alembic.ini must be set."
    )

config.set_main_option("sqlalchemy.url", db_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # The original `engine_from_config` assumes config sections specific to SQLAlchemy, like [alembic]
    # If we are primarily using DATABASE_URL, directly creating the engine is simpler.
    connectable = create_engine(config.get_main_option("sqlalchemy.url"))
    # connectable = engine_from_config(
    #     config.get_section(config.config_ini_section, {}),
    #     prefix="sqlalchemy.",
    #     poolclass=pool.NullPool,
    # )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
