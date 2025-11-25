# Multi-stage build for p8fs-node Rust API
FROM rust:1.87-slim AS builder

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    ca-certificates \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy workspace and package manifests
COPY Cargo.toml Cargo.lock ./
COPY p8fs-node/Cargo.toml ./p8fs-node/

# Create dummy source files to cache dependencies
RUN mkdir -p p8fs-node/src && \
    echo "fn main() {println!(\"Building dependencies...\");}" > p8fs-node/src/main.rs && \
    echo "pub fn dummy() {}" > p8fs-node/src/lib.rs

# Build dependencies (this will be cached)
RUN cargo build --release --bin p8fs-node && \
    rm -rf p8fs-node/src

# Copy actual source code
COPY p8fs-node/src ./p8fs-node/src

# Build the final binary
RUN cargo build --release --bin p8fs-node

# Runtime stage - minimal image
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl3 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser \
    && useradd -r -g appuser -s /bin/false -d /app appuser

# Copy binary from builder stage
COPY --from=builder /app/target/release/p8fs-node /usr/local/bin/p8fs-node

# Create app directory and set ownership
WORKDIR /app
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Environment variables with defaults
ENV EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ENV EMBEDDING_DIMENSIONS=384
ENV RUST_LOG=info
ENV HOST=0.0.0.0
ENV PORT=3000

# Expose the port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:3000/ || exit 1

# Run the application
CMD ["p8fs-node"]