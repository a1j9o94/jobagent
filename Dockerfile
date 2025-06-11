# Multi-stage build for optimized production image
FROM python:3.12-slim-bookworm AS base

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    # WeasyPrint dependencies
    libglib2.0-0 \
    libgdk-pixbuf-2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libfontconfig1 \
    libfreetype6 \
    libffi-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    libssl-dev \
    zlib1g-dev \
    # Node.js for the scraper service
    nodejs \
    npm \
    # Browser dependencies for Stagehand
    chromium \
    chromium-sandbox \
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
COPY pyproject.toml entrypoint.sh alembic.ini release-tasks.sh ./
COPY app/ ./app/
COPY alembic/ ./alembic/

# Copy Node.js service files
COPY node-scraper/ ./node-scraper/

# Using --system to install to system Python, common for Docker images
# Using --no-cache as good practice for builders, though uv handles caching differently than pip
# Install both main and dev dependencies for testing capabilities
RUN uv pip install --system --no-cache-dir ".[dev]"

# Skip Playwright browser installation - we'll use system chromium
# RUN playwright install chromium --with-deps

# Build Node.js service
WORKDIR /code/node-scraper
RUN npm ci  # Install all dependencies including dev (TypeScript) for building
RUN npm run build
RUN npm prune --omit=dev  # Remove dev dependencies after building

# Return to main working directory
WORKDIR /code

# Final stage
FROM base AS final

# Copy installed Python packages from builder stage (fixed path)
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application code from builder stage
COPY --from=builder /code /code

# Create non-root user for security (before setting USER)
RUN useradd --create-home --shell /bin/bash jobagent

# Skip copying Playwright cache since we're using system chromium
# COPY --from=builder /root/.cache/ms-playwright/ /home/jobagent/.cache/ms-playwright/

# Make entrypoint executable and fix ownership
RUN chown -R jobagent:jobagent /code && chmod +x /code/entrypoint.sh /code/release-tasks.sh

USER jobagent

ENTRYPOINT ["./entrypoint.sh"]
# Default command if entrypoint.sh doesn't override or is not used for uvicorn directly
CMD ["uvicorn", "app.api_server:app", "--host", "0.0.0.0", "--port", "8000"]