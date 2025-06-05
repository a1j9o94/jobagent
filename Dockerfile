# Multi-stage build for optimized production image
FROM python:3.12-slim-bookworm AS base

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    libglib2.0-0 \
    libgdk-pixbuf-2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency management
RUN pip install uv

WORKDIR /code

# Builder stage
FROM base AS builder

# Install build dependencies (only in builder stage)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files needed for installation
COPY pyproject.toml entrypoint.sh alembic.ini ./
COPY app/ ./app/
COPY alembic/ ./alembic/

# Using --system to install to system Python, common for Docker images
# Using --no-cache as good practice for builders, though uv handles caching differently than pip
# Install both main and dev dependencies for testing capabilities
RUN uv pip install --system --no-cache-dir ".[dev]"

# Install Playwright browsers and their system dependencies
# This command installs browsers to a default location that should be accessible by the final image
# if the cache directory is copied correctly.
RUN playwright install chromium --with-deps

# Final stage
FROM base AS final

# Copy installed Python packages from builder stage (fixed path)
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy Playwright browser cache from builder stage
# The path /root/.cache/ms-playwright/ is the default for Playwright
COPY --from=builder /root/.cache/ms-playwright/ /root/.cache/ms-playwright/

# Copy application code from builder stage
COPY --from=builder /code /code

# Create non-root user for security (before setting USER)
RUN useradd --create-home --shell /bin/bash jobagent

# Make entrypoint executable and fix ownership
RUN chmod +x entrypoint.sh && chown -R jobagent:jobagent /code /root/.cache/ms-playwright/

USER jobagent

ENTRYPOINT ["./entrypoint.sh"]
# Default command if entrypoint.sh doesn't override or is not used for uvicorn directly
CMD ["uvicorn", "app.api_server:app", "--host", "0.0.0.0", "--port", "8000"]