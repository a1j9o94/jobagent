# Multi-stage build for Node.js TypeScript service
FROM node:20-alpine AS builder

WORKDIR /app

# Install system dependencies for Playwright and native modules
RUN apk add --no-cache \
    chromium \
    nss \
    freetype \
    freetype-dev \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    build-base \
    python3 \
    make \
    g++

# Copy package files
COPY package*.json ./
COPY tsconfig.json ./

# Install dependencies (including dev dependencies for builder stage)
RUN npm ci

# Copy source code
COPY src/ ./src/

# Build TypeScript
RUN npm run build

# Development stage - keeps dev dependencies for local development
FROM node:20-alpine AS development

WORKDIR /app

# Install system dependencies for Playwright
RUN apk add --no-cache \
    chromium \
    nss \
    freetype \
    freetype-dev \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    build-base \
    python3 \
    make \
    g++

# Copy package files and install ALL dependencies (including dev)
COPY package*.json ./
COPY tsconfig.json ./
RUN npm ci

# Copy source code
COPY src/ ./src/

# Create non-root user first
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

# Create directories that Stagehand needs and set ownership
RUN mkdir -p /app/downloads /app/tmp && \
    chown -R nodejs:nodejs /app

USER nodejs

# Install Playwright browsers for local development as the nodejs user
RUN npx playwright install chromium

EXPOSE 3000

CMD ["npm", "run", "dev"]

# Production stage
FROM node:20-alpine AS production

WORKDIR /app

# Copy package files and install production dependencies
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

# Copy built application
COPY --from=builder /app/dist ./dist

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

USER nodejs

EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node -e "require('./dist/queue-consumer').JobApplicationService().healthCheck().then(() => process.exit(0)).catch(() => process.exit(1))" || exit 1

CMD ["node", "dist/queue-consumer.js"] 