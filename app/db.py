# app/db.py
import os
import logging
from sqlmodel import create_engine, Session, SQLModel
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=300,  # Recycle connections every 5 minutes
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
)


def create_tables():
    """Create all tables. Used in tests and initial setup."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Dependency for FastAPI to get database sessions."""
    with Session(engine) as session:
        yield session


@contextmanager
def get_session_context():
    """Context manager for database sessions outside of FastAPI."""
    with Session(engine) as session:
        yield session


def health_check() -> bool:
    """Check if database is accessible."""
    try:
        with Session(engine) as session:
            session.exec("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
