# Multi-stage UV-based Dockerfile for P8FS ecosystem - HEAVY BUILD
# This Dockerfile builds the full image with all ML/media dependencies
# For light builds without ML dependencies, use Dockerfile.light
#
# DEPLOYMENT INSTRUCTIONS:
# 
# Build and push multi-platform Docker image:
#    docker buildx build --platform linux/amd64,linux/arm64 -t percolationlabs/p8fs-eco:latest --push .
# 
# For local development (load into local Docker):
#    docker buildx build --platform linux/amd64 -t percolationlabs/p8fs-eco:latest --load .
# 
# Run services:
#    # API Server
#    docker run -p 8000:8000 percolationlabs/p8fs-eco:latest
#    
#    # Storage Worker (requires heavy image)
#    docker run percolationlabs/p8fs-eco:latest python -m p8fs.workers.storage
#    
#    # Dreaming Worker (requires heavy image)
#    docker run percolationlabs/p8fs-eco:latest python -m p8fs.workers.dreaming
#
#    # CLI tools
#    docker run percolationlabs/p8fs-eco:latest p8fs --help
#    docker run percolationlabs/p8fs-eco:latest p8fs-node --help

ARG PYTHON_VERSION=3.11
ARG UV_VERSION=0.5.11

# Use official UV image
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# Dependencies stage - installs Python dependencies only
FROM python:${PYTHON_VERSION}-slim AS dependencies

# Install system dependencies for heavy builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev mupdf-tools \
    ffmpeg libavcodec-extra \
    libmagic1 \
    tesseract-ocr tesseract-ocr-eng \
    gcc g++ make \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy UV binaries from official image
COPY --from=uv /uv /uvx /bin/

# Set UV environment for optimal builds
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy ONLY dependency files first (this layer will be cached if deps don't change)
COPY pyproject.toml uv.lock ./

# Create stub structure for workspace members (UV needs these to resolve dependencies)
RUN mkdir -p p8fs-cluster/src/p8fs_cluster \
    p8fs-auth/src/p8fs_auth \
    p8fs/src/p8fs \
    p8fs-node/src/p8fs_node \
    p8fs-api/src/p8fs_api

# Copy ONLY the pyproject.toml files from each module (for dependency resolution)
COPY p8fs-cluster/pyproject.toml p8fs-cluster/
COPY p8fs-auth/pyproject.toml p8fs-auth/
COPY p8fs/pyproject.toml p8fs/
COPY p8fs-node/pyproject.toml p8fs-node/
COPY p8fs-api/pyproject.toml p8fs-api/

# Copy README files that are referenced in pyproject.toml
COPY p8fs-cluster/README.md p8fs-cluster/
COPY p8fs-auth/README.md p8fs-auth/
COPY p8fs/README.md p8fs/
COPY p8fs-node/README.md p8fs-node/
COPY p8fs-api/README.md p8fs-api/

# Create minimal __init__.py files to make packages importable
RUN touch p8fs-cluster/src/p8fs_cluster/__init__.py \
    p8fs-auth/src/p8fs_auth/__init__.py \
    p8fs/src/p8fs/__init__.py \
    p8fs-node/src/p8fs_node/__init__.py \
    p8fs-api/src/p8fs_api/__init__.py

# Install dependencies ONLY (this layer is cached when source changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Builder stage - adds source code to dependencies
FROM dependencies AS builder

# Now copy the actual source code (changes here won't invalidate dependency cache)
COPY README.md ./

# Cherry-pick only Python source files to avoid copying build artifacts
# p8fs-cluster
COPY p8fs-cluster/src ./p8fs-cluster/src
COPY p8fs-cluster/pyproject.toml p8fs-cluster/README.md p8fs-cluster/

# p8fs-auth
COPY p8fs-auth/src ./p8fs-auth/src
COPY p8fs-auth/pyproject.toml p8fs-auth/README.md p8fs-auth/

# p8fs
COPY p8fs/src ./p8fs/src
COPY p8fs/pyproject.toml p8fs/README.md p8fs/

# p8fs-node (Python parts only, no Rust)
COPY p8fs-node/src ./p8fs-node/src
COPY p8fs-node/pyproject.toml p8fs-node/README.md p8fs-node/

# p8fs-api
COPY p8fs-api/src ./p8fs-api/src
COPY p8fs-api/pyproject.toml p8fs-api/README.md p8fs-api/

# Install the actual projects WITH ALL EXTRAS (includes workers, torch, etc.)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-extras --no-editable

# Runtime stage - heavy version with all capabilities
FROM python:${PYTHON_VERSION}-slim AS runtime

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev mupdf-tools \
    ffmpeg libavcodec-extra \
    libmagic1 \
    tesseract-ocr tesseract-ocr-eng \
    curl wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r p8fs && useradd -r -g p8fs -m p8fs

# Copy virtual environment from builder with correct ownership
COPY --from=builder --chown=p8fs:p8fs /app/.venv /app/.venv

# Copy application code with correct ownership
COPY --from=builder --chown=p8fs:p8fs /app/README.md /app/
COPY --from=builder --chown=p8fs:p8fs /app/pyproject.toml /app/uv.lock /app/
COPY --from=builder --chown=p8fs:p8fs /app/p8fs-cluster /app/p8fs-cluster
COPY --from=builder --chown=p8fs:p8fs /app/p8fs-auth /app/p8fs-auth
COPY --from=builder --chown=p8fs:p8fs /app/p8fs /app/p8fs
COPY --from=builder --chown=p8fs:p8fs /app/p8fs-node /app/p8fs-node
COPY --from=builder --chown=p8fs:p8fs /app/p8fs-api /app/p8fs-api

# Set Python environment
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/app/.venv

WORKDIR /app
USER p8fs

# Health check for API
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Labels
LABEL org.opencontainers.image.source="https://github.com/percolationlabs/p8fs-modules" \
      org.opencontainers.image.description="P8FS ecosystem Docker image - Heavy build with ML/media dependencies" \
      org.opencontainers.image.licenses="MIT" \
      maintainer="Percolation Labs"

# API Server is the default, but can be overridden
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "p8fs_api.main:app", "--host", "0.0.0.0", "--port", "8000"]