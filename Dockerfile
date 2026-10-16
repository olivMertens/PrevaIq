# =============================================================================
# Backend Dockerfile — Multi-stage with uv for fast, lean builds
# Final image: python:3.12-slim
# =============================================================================

# Stage 1: Build dependencies with uv
FROM ghcr.io/astral-sh/uv:0.8-python3.12-bookworm-slim AS builder

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev deps, no editable installs)
RUN uv sync --frozen --no-dev --no-editable

# Verify agent-framework-core 1.21.x is correctly installed
RUN .venv/bin/python -c "from agent_framework import Agent; from agent_framework.openai import OpenAIChatClient; print('OK:', Agent.__name__)"

# Stage 2: Lean runtime image
# Use GHCR base to avoid Docker Hub unauthenticated pull rate limits in ACR Tasks
FROM ghcr.io/astral-sh/uv:0.8-python3.12-bookworm-slim AS runtime

WORKDIR /app

# Install only minimal runtime deps (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Brand name — baked at build time so each image carries its own brand
ARG BRAND_NAME=PrevaIQ

# Ensure venv is on PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BRAND_NAME=${BRAND_NAME}

# Copy application code (only what's needed at runtime)
COPY api_server.py ./
COPY app/ ./app/
COPY prompts/ ./prompts/
COPY assets/pdf/ ./assets/pdf/
COPY scripts/startup.sh ./scripts/startup.sh

# Make startup script executable
RUN chmod +x scripts/startup.sh

EXPOSE 8000

# Health check — no curl needed (uses Python stdlib)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["/bin/bash", "scripts/startup.sh"]
