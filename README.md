# P8FS - Next Generation Smart Content Management System

P8FS is a distributed content management system designed for secure, scalable storage with advanced indexing capabilities. The system leverages S3-compatible blob storage (SeaweedFS) and TiDB/TiKV for managing a secure "memory vault" where users can upload and manage content with end-to-end encryption.

It can be used with other clients e.g. for Chat Assistants Claude Desktop or Chat GPT via MCP or Obsedian and other note management systems.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        P8FS System                              │
├─────────────────────────────────────────────────────────────────┤
│  Client Layer                                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Mobile    │  │     CLI     │  │     MCP     │             │
│  │    App      │  │   Client    │  │   Server    │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│                        │                                        │
├────────────────────────┼────────────────────────────────────────┤
│  API Layer             │                                        │
│  ┌─────────────────────┼────────────────────────────────┐       │
│  │              p8fs-api                                │       │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │       │
│  │  │  Auth   │ │  Chat   │ │ Health  │ │   MCP   │    │       │
│  │  │ Router  │ │ Router  │ │ Router  │ │ Router  │    │       │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘    │       │
│  └─────────────────────────────────────────────────────┘       │
│                        │                                        │
├────────────────────────┼────────────────────────────────────────┤
│  Service Layer         │                                        │
│  ┌─────────────────────┼────────────────────────────────┐       │
│  │              p8fs                               │       │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │       │
│  │  │ Memory  │ │ Engram  │ │   LLM   │ │ Workers │    │       │
│  │  │ System  │ │Processor│ │ Service │ │ & Queues│    │       │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘    │       │
│  └─────────────────────────────────────────────────────┘       │
│                        │                                        │
├────────────────────────┼────────────────────────────────────────┤
│  Processing Layer      │                                        │
│  ┌─────────────────────┼────────────────────────────────┐       │
│  │              p8fs-node                               │       │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │       │
│  │  │Content  │ │Embedding│ │  Audio  │ │  Video  │    │       │
│  │  │Provider │ │ Service │ │Processor│ │Processor│    │       │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘    │       │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │       │
│  │  │   PDF   │ │Document │ │ Archive │ │   Text  │    │       │
│  │  │Processor│ │Processor│ │Processor│ │Processor│    │       │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘    │       │
│  └─────────────────────────────────────────────────────┘       │
│                        │                                        │
├────────────────────────┼────────────────────────────────────────┤
│  Infrastructure Layer  │                                        │
│  ┌─────────────────────┼────────────────────────────────┐       │
│  │          p8fs-cluster & p8fs-auth                    │       │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │       │
│  │  │ Config  │ │Logging  │ │  Auth   │ │Encryption│   │       │
│  │  │Manager  │ │ System  │ │ System  │ │ Service │    │       │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘    │       │
│  └─────────────────────────────────────────────────────┘       │
│                        │                                        │
├────────────────────────┼────────────────────────────────────────┤
│  Storage & Queue Layer │                                        │
│  ┌─────────────────────┼────────────────────────────────┐       │
│  │  ┌─────────┐ ┌──────┼──┐ ┌─────────┐ ┌─────────┐     │       │
│  │  │PostgreSQL│ │ TiDB │  │ │SeaweedFS│ │  NATS   │     │       │
│  │  │(Dev/Test)│ │(Prod)│  │ │ (Blob)  │ │JetStream│     │       │
│  │  └─────────┘ └──────┼──┘ └─────────┘ └─────────┘     │       │
│  └─────────────────────┼────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

## Module Architecture

### 📁 p8fs-api

FastAPI, MCP and CLI interface to the entire system. Provides RESTful endpoints, streaming chat interfaces, and Model Context Protocol server for IDE integration.

**Key Components:**

- Auth router with OAuth 2.1 implementation
- Chat router with streaming LLM endpoints
- MCP server for development tooling
- Health monitoring and metrics

### 📁 p8fs

The percolate memory system core that handles RAG/IR features, database repositories, and content indexing. Supports both PostgreSQL (dev/test) and TiDB (production) backends.

**Key Components:**

- Memory management with vector/graph indexing
- Engram processor for content chunking
- LLM service abstractions
- Background workers and job queues
- Repository layer with multi-database support

### 📁 p8fs-node

Content processing engine with dual Python/Rust implementation. Handles file format conversion, embedding generation, and content transformation.

**Key Components:**

- Content provider registry (PDF, audio, video, documents)
- Embedding service
- Multi-format processors
- Rust-based high-performance components

### 📁 p8fs-auth

Authentication and encryption module providing mobile-first keypair generation and OAuth 2.1 token issuance with end-to-end encryption capabilities.

**Key Components:**

- Mobile keypair generation
- OAuth 2.1 token service
- End-to-end encryption utilities
- Public key infrastructure

### 📁 p8fs-cluster

Centralized configuration and runtime management for cluster deployments. Provides shared logging, environment management, and system coordination.

**Key Components:**

- Centralized configuration system
- Logging infrastructure
- Environment variable management
- Cluster coordination utilities

## Quick Start

### Prerequisites

1. **Install uv** (Python package manager)

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # or via pip: pip install uv
   ```

2. **Start Development Services**

   ```bash
   cd p8fs
   docker-compose up postgres -d  # Start PostgreSQL for development
   ```

### uv Workspace Setup

This project uses uv workspaces for seamless monorepo development with automatic editable installs.

1. **Install All Dependencies**

   ```bash
   cd p8fs-modules
   uv sync --extra workers  # Installs all workspace members with editable installs
   ```

2. **Run Development Servers**

   ```bash
   # API server with hot reload
   cd p8fs-api
   uv run uvicorn p8fs_api.main:app --reload

   # CLI tools
   uv run -p p8fs-node p8fs-node process --help
   uv run -p p8fs-auth p8fs-auth generate-keypair
   ```

3. **Run Tests**

   ```bash
   # Run all workspace tests
   uv run pytest

   # Run specific module tests
   uv run -p p8fs pytest tests/
   ```

### Development Benefits

With uv workspaces configured:

- ✅ **Automatic editable installs**: Changes in any module immediately available to dependents
- ✅ **No manual reinstalls**: Modify p8fs-auth models → instantly reflected in p8fs-api
- ✅ **Hot reload support**: uvicorn `--reload` detects changes across all modules
- ✅ **Consistent dependencies**: Single lockfile ensures version compatibility
- ✅ **Fast iteration**: Cross-module development without friction

### Alternative Setup (Legacy)

For environments without uv workspace support:

```bash
# Install direnv for automatic Python path setup
brew install direnv
cd p8fs-modules
direnv allow
```

## Docker

P8FS provides Docker images for containerized deployment with three build variants:

- **Default Image** (3.4GB): Full build with CPU-only PyTorch, all modules, workers, and media processing
- **GPU Image** (~8-9GB): Full build with CUDA support for GPU-accelerated ML workloads
- **Light Image** (1GB): API-only build without media processing dependencies and ML packages

### Building Images

Using Docker Buildx for multi-platform builds:

```bash
# Create and use a new builder
docker buildx create --name p8fs-builder --use

# Build default image (full capabilities with CPU-only PyTorch)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t percolationlabs/p8fs-eco:latest \
  -t percolationlabs/p8fs-eco:default \
  -f Dockerfile.heavy-cpu \
  --push .

# Build GPU image (full capabilities with CUDA support)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t percolationlabs/p8fs-eco:gpu \
  -f Dockerfile \
  --push .

# Build light image (API only)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t percolationlabs/p8fs-eco:light \
  -f Dockerfile.light \
  --push .

# Build for local use only (no push)
#  docker buildx build --platform linux/amd64 -t percolationlabs/p8fs-eco:light-optimized -f Dockerfile.light --load .

docker buildx build \
  --load \
  -t p8fs-eco:local \
  -f Dockerfile.heavy-cpu .
```

### Which Image to Use?

- **`percolationlabs/p8fs-eco:latest` (Default)** - Recommended for most use cases

  - Full functionality with CPU-optimized PyTorch
  - All workers and media processing
  - 3.4GB size
  - Best for development and CPU-based production

- **`percolationlabs/p8fs-eco:gpu`** - For GPU-accelerated workloads

  - NVIDIA CUDA support
  - Maximum ML/AI performance
  - ~8-9GB size
  - Requires GPU infrastructure

- **`percolationlabs/p8fs-eco:light`** - For API-only deployments

  - Minimal footprint (1GB)
  - No ML or media processing
  - Perfect for API gateways and microservices

### Running Docker Images

#### Prerequisites

The API requires JWT signing keys for authentication. Generate them first:

```bash
# Generate JWT keys for development
cd p8fs-api
python scripts/dev/generate_server_jwt_signing_keys.py
```

This will output environment variables that need to be set when running the container.

#### Testing the Docker Container

After starting the container, verify it's working correctly:

```bash
# Check container logs
docker logs p8fs-api

# Test health endpoint
curl http://localhost:8000/health

# View API documentation
open http://localhost:8000/docs

# Stop and remove container
docker stop p8fs-api && docker rm p8fs-api
```

### Running Different Entry Points

The default and GPU images support multiple entry points for different components:

#### 1. API Server (Default)

```bash
# Run with default image (recommended)
docker run -d \
  --name p8fs-api \
  -p 8000:8000 \
  -e P8FS_JWT_PRIVATE_KEY_PEM="YOUR_PRIVATE_KEY_HERE" \
  -e P8FS_JWT_PUBLIC_KEY_PEM="YOUR_PUBLIC_KEY_HERE" \
  percolationlabs/p8fs-eco:latest

# Or use the light image for API-only deployments
docker run -d \
  --name p8fs-api \
  -p 8000:8000 \
  -e P8FS_JWT_PRIVATE_KEY_PEM="YOUR_PRIVATE_KEY_HERE" \
  -e P8FS_JWT_PUBLIC_KEY_PEM="YOUR_PUBLIC_KEY_HERE" \
  percolationlabs/p8fs-eco:light

# Run with custom environment variables
docker run -p 8000:8000 \
  -e P8FS_STORAGE_PROVIDER=postgresql \
  -e P8FS_PG_HOST=host.docker.internal \
  -e P8FS_PG_PORT=5438 \
  percolationlabs/p8fs-eco:latest

# Run with custom command options
docker run -p 8000:8000 percolationlabs/p8fs-eco:latest \
  python -m uvicorn p8fs_api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### 2. Storage Worker

Note: The light image will start but show warnings about missing p8fs-node. Use the default or GPU image for full media processing.

```bash
# Run storage worker processing from queue
docker run \
  -e P8FS_TENANT_ID=default \
  percolationlabs/p8fs-eco:latest \
  python -m p8fs.workers.storage --queue --tenant-id default

# Process a specific file
docker run \
  -v /path/to/files:/data \
  -e P8FS_TENANT_ID=default \
  percolationlabs/p8fs-eco:latest \
  python -m p8fs.workers.storage --file /data/document.pdf --tenant-id default

# Check available options
docker run --rm percolationlabs/p8fs-eco:latest \
  python -m p8fs.workers.storage --help
```

#### 3. Dreaming Worker

Note: The dreaming worker requires database connectivity and will fail if PostgreSQL is not accessible.

```bash
# Run in batch mode
docker run \
  -e P8FS_TENANT_ID=default \
  percolationlabs/p8fs-eco:latest \
  python -m p8fs.workers.dreaming --mode batch --tenant-id default

# Run in direct mode
docker run \
  -e P8FS_TENANT_ID=default \
  percolationlabs/p8fs-eco:latest \
  python -m p8fs.workers.dreaming --mode direct --tenant-id default

# Check available options
docker run --rm percolationlabs/p8fs-eco:latest \
  python -m p8fs.workers.dreaming --help

# Check completions
docker run percolationlabs/p8fs-eco:latest \
  python -m p8fs.workers.dreaming --mode completion --completion
```

#### 4. P8FS CLI

```bash
# Run agent query
docker run percolationlabs/p8fs-eco:latest \
  p8fs agent "Find all documents about machine learning"

# Process files
docker run \
  -v /path/to/files:/data \
  percolationlabs/p8fs-eco:latest \
  p8fs process /data --recursive

# Run scheduler
docker run percolationlabs/p8fs-eco:latest \
  p8fs scheduler

# Generate SQL from natural language
docker run percolationlabs/p8fs-eco:latest \
  p8fs sql-gen "show me all users created last month"
```

#### 5. P8FS-Node CLI

```bash
# Process a file
docker run \
  -v /path/to/files:/data \
  percolationlabs/p8fs-eco:latest \
  p8fs-node process /data/document.pdf

# List available content providers
docker run percolationlabs/p8fs-eco:latest \
  p8fs-node list-providers

# Test which provider handles a file
docker run \
  -v /path/to/files:/data \
  percolationlabs/p8fs-eco:latest \
  p8fs-node test-file /data/sample.wav
```

### Docker Compose Example

For production deployments with all services:

```yaml
version: "3.8"

services:
  api:
    image: percolationlabs/p8fs-eco:latest
    ports:
      - "8000:8000"
    environment:
      - P8FS_STORAGE_PROVIDER=postgresql
      - P8FS_PG_HOST=postgres
      - P8FS_PG_DATABASE=p8fs
    depends_on:
      - postgres
      - tidb

  storage-worker:
    image: percolationlabs/p8fs-eco:latest
    command: python -m p8fs.workers.storage --queue --tenant-id default
    environment:
      - P8FS_STORAGE_PROVIDER=postgresql
      - P8FS_PG_HOST=postgres
      - P8FS_NATS_URL=nats://nats:4222
    depends_on:
      - postgres
      - nats

  dreaming-worker:
    image: percolationlabs/p8fs-eco:latest
    command: python -m p8fs.workers.dreaming --mode batch --tenant-id default
    environment:
      - P8FS_STORAGE_PROVIDER=postgresql
      - P8FS_PG_HOST=postgres
    depends_on:
      - postgres
```

### Health Check

The API server includes a health check endpoint:

```bash
# Check if the API is healthy
curl http://localhost:8000/health
```

## Design Principles

- **Separation of Concerns**: Each module handles a single responsibility
- **Security First**: End-to-end encryption with client-held keys
- **Minimal Code**: Lean implementations avoiding complexity
- **Testability**: Unit tests with mocks and integration tests with real services
- **Scalability**: Horizontal scaling through KEDA and distributed storage
- **Clean Architecture**: Well-defined interfaces between components

# CI/CD Pipeline

## 🚀 Overview

P8FS implements a **two-stage deployment pipeline** that separates build from release, ensuring only tested and verified images reach production.

### Key Features

- ✅ **CalVer Tagging** - Unique, traceable timestamps for every build
- ✅ **Image Signing** - Cosign with Sigstore/Fulcio (keyless)
- ✅ **SBOM Generation** - Software Bill of Materials for compliance
- ✅ **Vulnerability Scanning** - Trivy at build and release stages
- ✅ **GitOps** - Automated manifest updates via ArgoCD
- ✅ **Multi-Architecture** - Support for amd64 and arm64
- ✅ **Full Traceability** - From commit to production deployment

### Pipeline Philosophy

```
Build frequently → Test thoroughly → Release confidently
```

**Build Pipeline**: Creates immutable artifacts (CalVer-tagged images)
**Release Pipeline**: Promotes tested artifacts to production with security attestations

---

# P8FS CI/CD Pipeline Guide

## Overview

Two-stage versioning and release process:

1. **Build Stage** - Bump version, create CalVer images, test, scan with Trivy
2. **Release Stage** - Create clean version tags, sign images, update manifests

---

## 🏗️ Architecture Overview

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     p8fs-ecosystem Repo                         │
│  ┌──────────────────────┐      ┌──────────────────────┐         │
│  │   Build Pipeline     │      │  Release Pipeline    │         │
│  │  (on RC tag push)    │      │  (on clean tag push) │         │
│  │                      │      │                      │         │
│  │ • Generate CalVer    │──────│ • Find CalVer images │         │
│  │ • Build & test       │      │ • Retag (1.x.x-*)    │         │
│  │ • Scan (Trivy)       │      │ • Sign (Cosign)      │         │
│  │ • Push to GHCR       │      │ • SBOM (bom)         │         │
│  │                      │      │                      │         │
│  └──────────────────────┘      └──────────────────────┘         │
│                                         │                       │
└─────────────────────────────────────────┼───────────────────────┘
                                          │
                                          ▼
                        ┌─────────────────────────────────┐
                        │      p8fs-cloud Repo            │
                        │  (Kubernetes Manifests)         │
                        │                                 │
                        │  • api-deployment.yaml          │
                        │  • worker deployments           │
                        │  • Image refs updated           │
                        └─────────────────────────────────┘
                                          │
                                          ▼
                        ┌─────────────────────────────────┐
                        │         ArgoCD                  │
                        │  • Detects manifest changes     │
                        │  • Syncs to Kubernetes          │
                        │  • Deploys updated images       │
                        └─────────────────────────────────┘
```

### Image Variants

| Variant   | Architecture | Use Case                      | Base Image               |
| --------- | ------------ | ----------------------------- | ------------------------ |
| **light** | amd64, arm64 | API Core (p8fs-core)          | Python 3.11 slim         |
| **heavy** | amd64        | Workers (all background jobs) | Python 3.11 with ML libs |

---

## 📋 Complete Development Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Development Workflow                          │
└─────────────────────────────────────────────────────────────────┘

1. BUMP VERSION
   └─ python3 scripts/bump_version.py [--minor|--major]
      └─ Updates VERSION, pyproject.toml files
      └─ Creates commit: "* build v1.2.2 - message"
      └─ Output: "Version for developers: v1.2.2-rc"

2. PUSH COMMIT
   └─ git push origin <branch>
      └─ Commit alone does NOT trigger build

3. CREATE RC TAG (TRIGGERS BUILD)
   └─ git tag v1.2.2-rc
   └─ git push origin v1.2.2-rc
      └─ RC tag triggers Build Pipeline

┌─────────────────────────────────────────────────────────────────┐
│                    BUILD PIPELINE (RC Tag)                       │
│                 Triggered by: v1.2.2-rc tag push               │
└─────────────────────────────────────────────────────────────────┘

   check-build-version
      └─ Detects RC tag
      └─ Extracts version: 1.2.2

   build-test-push (3 variants)
      ├─ light-amd64
      ├─ light-arm64
      └─ heavy-amd64

      For each variant:
         1. Build image
         2. Test (amd64 only)
            ├─ Container runs
            ├─ API health check (light)
            └─ CLI test (heavy)
         3. Trivy scan (amd64 only) ← SECURITY GATE
            └─ Fails if CRITICAL vulns found
         4. Push CalVer image: 2025.01.15.1430-build.123-v1.2.2-abc1234
         5. Store metadata artifacts
            ├─ calver tag
            ├─ build version
            ├─ digest
            └─ image reference

   Output: CalVer tagged images ready in registry

┌─────────────────────────────────────────────────────────────────┐
│                   RELEASE WORKFLOW                               │
│              After build testing completes                      │
└─────────────────────────────────────────────────────────────────┘

4. RELEASE VERSION
   └─ python3 scripts/release_version.py
      └─ Reads version: 1.2.2
      └─ Creates tag: v1.2.2
      └─ Requires manual confirmation: "Continue? [y/N]: y"

5. PUSH RELEASE TAG (TRIGGERS RELEASE PIPELINE)
   └─ git push origin v1.2.2
      └─ Release tag triggers Release Pipeline

┌─────────────────────────────────────────────────────────────────┐
│                 RELEASE PIPELINE (Clean Tag)                     │
│                 Triggered by: v1.2.2 tag push                   │
└─────────────────────────────────────────────────────────────────┘

   find-tags
      └─ Finds CalVer images matching version 1.2.2
      └─ Uses metadata artifacts from build

   retag-images (3 variants)
      ├─ light-amd64
      ├─ light-arm64
      └─ heavy-amd64

      For each variant:
         1. Pull CalVer image
         2. Retag to clean version: 1.2.2-light-amd64
         3. Push clean version
         4. Generate SBOM
         5. Store metadata

   Note: NO Trivy scan here (already done in build)

   update-manifests
      └─ Updates Kubernetes manifests
      └─ Commits to p8fs-cloud repo

   Output: Manifests updated, ready for ArgoCD deployment

┌─────────────────────────────────────────────────────────────────┐
│                      Key Differences                             │
├─────────────────────────────────────────────────────────────────┤
│ BUILD (RC Tag)          │ RELEASE (Clean Tag)                   │
├─────────────────────────┼──────────────────────────────────────┤
│ Triggered by: RC tag    │ Triggered by: clean tag              │
│ Creates: CalVer images  │ Retaggs to: clean version            │
│ Tests: Yes              │ Tests: No (already tested)           │
│ Trivy scan: Yes         │ Trivy scan: No (already scanned)     │
│ Automated: Yes          │ Requires: Manual confirmation        │
│ Fast: < 10 min          │ Fast: < 5 min                        │
└─────────────────────────┴──────────────────────────────────────┘

```

---

## 📦 Stage 1: Build Pipeline

**File:** `.github/workflows/build-and-push.yml`
**Trigger:** Git tag with `-rc` suffix (e.g., `v1.2.2-rc`)

### What Happens

- Triggered by: RC tag push (e.g., `v1.x.x-rc`)
- Creates CalVer tagged images (e.g., `2025.01.15.1430-build.123-v1.2.2-abc1234`)
- Runs tests on amd64 variants
- **Trivy security scan** - Scans all built images for vulnerabilities before pushing
- Pushes images to registry
- Stores build metadata for release pipeline

### Usage

```bash
# After running bump_version.py, create and push RC tag
git tag v1.2.2-rc
git push origin v1.2.2-rc

# Or trigger manually
gh workflow run build-and-push.yml -f build_version=v1.2.2-rc
```

### Process Flow

```
RC Tag: v1.2.2-rc
    ↓
Parse Version (extract 1.2.2)
    ↓
Generate CalVer (2025.01.15.1430-build.123-v1.2.2-abc1234)
    ↓
Build Matrix:
    • light-amd64
    • light-arm64
    • heavy-amd64
    ↓
Test Images (amd64 only)
    ↓
Trivy Scan (CRITICAL only)
    ↓
Push to GHCR
    ↓
Store Metadata
```

### CalVer Tag Format

```
YYYY.MM.DD.HHMM-build.NUMBER-vVERSION-SHA-VARIANT-ARCH
```

**Example:**

```
ghcr.io/percolation-labs/p8fs-ecosystem-test:2025.01.15.1430-build.123-v1.2.2-abc1234-light-amd64
│                                          │     │          │    │        │       │        │     │
│                                          │     │          │    │        │       │        │     └─ Architecture
│                                          │     │          │    │        │       │        └─ Variant
│                                          │     │          │    │        │       └─ Short SHA
│                                          │     │          │    │        └─ Build version
│                                          │     │          │    └─ Build number
│                                          │     └─ Timestamp (UTC)
│                                          └─ CalVer date
```

### Testing Matrix

| Platform  | Tests Executed                                                       |
| --------- | -------------------------------------------------------------------- |
| **amd64** | ✅ Container startup`✅ API health check`✅ CLI tools``✅ Trivy scan |
| **arm64** | ⏭️ Skip tests (build only)                                           |

### Security: Trivy in Build

Trivy scanning happens here because:

- Images are tested before release
- Only good images get CalVer tags
- Vulnerabilities caught before reaching release pipeline
- Fast feedback to developers

---

## 🚀 Stage 2: Release Pipeline

**File:** `.github/workflows/release-retag-update-manifests.yml`
**Trigger:** Git tag without `-rc` suffix (e.g., `v1.2.2`)

### What Happens

- Triggered by: Git tag without `-rc` suffix (e.g., `v1.2.2`)
- Finds CalVer images matching version
- Retaggs to clean version (e.g., `v1.2.2-light-amd64`)
- Signs images with Cosign
- Generates SBOM
- Updates Kubernetes manifests
- **NO Trivy scanning** - Already verified in build stage

### Usage

```bash
# After testing CalVer images, create release tag
git tag v1.2.2
git push origin v1.2.2

# Or use the release script
python3 scripts/release_version.py

# Pipeline automatically:
# 1. Finds CalVer images matching v1.2.2
# 2. Retags to clean versions (1.2.2-light-amd64, etc)
# 3. Signs with Cosign
# 4. Generates and attaches SBOM
# 5. Updates manifests in p8fs-cloud
# 6. ArgoCD deploys to production
```

### Process Flow

```
Tag: v1.2.2
    ↓
Find CalVer Images (*-v1.2.2-*)
    ↓
Pull Images
    ↓
Retag: 1.2.2-light-amd64, 1.2.2-light-arm64, 1.2.2-heavy-amd64
    ↓
Push Clean Tags
    ↓
Sign with Cosign (Keyless OIDC)
    ↓
Generate SBOM (SPDX format)
    ↓
Attach SBOM (Cosign attest)
    ↓
Verify Signatures & SBOM
    ↓
Update Manifests (p8fs-cloud repo)
    ↓
Git Push
    ↓
ArgoCD Syncs
    ↓
✅ Production Deployed
```

### Output

**Clean Version Tags:**

```
ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.2-light-amd64  ✅ Signed ✅ SBOM
ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.2-light-arm64  ✅ Signed ✅ SBOM
ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.2-heavy-amd64  ✅ Signed ✅ SBOM
```

### Deployment Mapping

| Application      | Variant | Architecture | Manifest Files                                                                                                                                                                                                                                        |
| ---------------- | ------- | ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **p8fs-core**    | light   | amd64        | api-deployment.yaml                                                                                                                                                                                                                                   |
| **p8fs-workers** | heavy   | amd64        | dreaming-worker.yaml`seaweedfs-event-poller.yaml`seaweedfs-grpc-subscriber.yaml`seaweedfs-metadata-subscriber.yaml`storage-worker-large.yaml`storage-worker-medium.yaml`storage-worker-small.yaml`tiered-storage-router.yaml`user-insight-worker.yaml |

### Why No Trivy in Release

Trivy already ran during build on the same image. Scanning it again in release wastes 6+ minutes and cluster resources without adding security value.

---

## 🛠️ Using the Scripts

### Script 1: bump_version.py

**Purpose**: Bump version and prepare for build pipeline

**Usage**:

```bash
# Bump patch version (1.2.2 → 1.2.3)
python3 scripts/bump_version.py

# Bump minor version (1.2.2 → 1.3.0)
python3 scripts/bump_version.py --minor

# Bump major version (1.2.2 → 2.0.0)
python3 scripts/bump_version.py --major

# Preview changes without committing
python3 scripts/bump_version.py --dry-run

# Custom message
python3 scripts/bump_version.py -m "Add new feature"
```

**What It Does**:

1. Reads current version from VERSION file
2. Calculates new version based on bump type
3. Updates VERSION file
4. Updates all pyproject.toml files across modules
5. Creates git commit: `* build v1.x.x - [message]`
6. Outputs RC version for developers: `v1.x.x-rc`

**Output Example**:

```
Bumping patch version: 1.2.1 → 1.2.2
Updated VERSION: 1.2.2
Updated p8fs-api/pyproject.toml: 1.2.2
Updated p8fs/pyproject.toml: 1.2.2
Updated p8fs-auth/pyproject.toml: 1.2.2
Updated p8fs-cluster/pyproject.toml: 1.2.2
Updated p8fs-node/pyproject.toml: 1.2.2

Version for developers to use: v1.2.2-rc

Created commit: * build v1.2.2 - Bumping build
Staged 6 file(s)

Next steps:
  1. Push commit to your branch: git push origin <branch>
  2. Create and push RC tag to trigger build:
     git tag v1.2.2-rc
     git push origin v1.2.2-rc
```

**What To Do After Running**:

1. Push the commit to your branch: `git push origin <your-branch>`
2. Create the RC tag to trigger the build pipeline:
   ```bash
   git tag v1.2.2-rc
   git push origin v1.2.2-rc
   ```
3. The RC tag triggers the build pipeline (watch GitHub Actions)
4. Wait for build to complete - monitor:
   - CalVer images being created (e.g., 2025.01.15.1430-build.123-v1.2.2-abc1234)
   - Trivy scan results on amd64 variants
   - Test results (API health check for light, CLI for heavy)
5. If Trivy finds CRITICAL vulnerabilities: Fix the issue, delete the tag, and retry
6. If tests fail: Fix the issue, delete the tag, and retry
7. If all passes: CalVer images are ready. Proceed to release_version.py

**Handling Build Failures**:

If Trivy scan fails:

```bash
git tag -d v1.2.2-rc          # Delete local tag
git push origin :v1.2.2-rc    # Delete remote tag
# Fix vulnerability or update Dockerfile
git tag v1.2.2-rc             # Retag
git push origin v1.2.2-rc     # Retry build
```

---

### Script 2: release_version.py

**Purpose**: Create clean release tag and trigger release pipeline

**Usage**:

```bash
# Create and push release tag
python3 scripts/release_version.py

# Preview only
python3 scripts/release_version.py --dry-run

# Create tag but don't push (manual push later)
python3 scripts/release_version.py --no-push
```

**What It Does**:

1. Reads version from VERSION file
2. Creates git tag: `v1.2.2`
3. **Requires manual confirmation** - "Continue? [y/N]:"
4. Pushes tag to trigger release pipeline

**Output Example**:

```
Current version: 1.2.2
Release tag: v1.2.2
Current branch: main

This will:
  1. Create tag: v1.2.2
  2. Push tag to origin
  3. Trigger release pipeline

Continue? [y/N]: y

Created tag: v1.2.2
Pushed tag to origin: v1.2.2

Release pipeline triggered!

What happens next:
  1. Release pipeline finds CalVer images matching v1.2.2
  2. Images retagged as 1.2.2-light-amd64, 1.2.2-heavy-amd64, etc.
  3. Images signed with Cosign
  4. SBOM generated and attached
  5. Kubernetes manifests updated in p8fs-cloud repo
  6. ArgoCD deploys to production
```

**Key Difference from bump_version.py**:

- bump_version.py: Automated push (development focus)
- release_version.py: **Manual confirmation required** (production focus)

**Why Manual Release Confirmation**:

Requires explicit confirmation so releases aren't triggered by mistake - builds are fast and easy, releases are intentional and deliberate.

---

## 🔐 Security & Compliance

### Image Signing (Cosign)

**Keyless signing with Sigstore/Fulcio:**

```bash
# Verify image signature
cosign verify \
  --certificate-identity-regexp="https://github.com/Percolation-Labs/p8fs-ecosystem" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.0-light-amd64
```

**What gets signed:**

- Image digest (SHA256)
- Build metadata
- Workflow provenance

**Security Level:** SLSA Level 2+

### SBOM (Software Bill of Materials)

**SPDX format with full dependency tree:**

```bash
# Verify and inspect SBOM
cosign verify-attestation \
  --type=spdxjson \
  --certificate-identity-regexp="https://github.com/Percolation-Labs/p8fs-ecosystem" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.0-light-amd64 \
  | jq -r '.payload' | base64 -d | jq '.predicate'
```

**SBOM includes:**

- All Python packages (from requirements.txt)
- System libraries
- OS packages
- License information
- Package versions

### Vulnerability Scanning

**Trivy scans - Build Stage Only**

1. Scans locally built images
   - Severity: CRITICAL only
   - Blocks build on CRITICAL vulnerabilities
   - Prevents bad images from reaching registry

```bash
# View scan results from GitHub Actions
gh run list --workflow=build-and-push.yml
gh run view <run-id> --log
```

### Security Summary

**Build Pipeline**:

- Creates and tests images
- Runs Trivy to catch vulnerabilities early
- Only good images tagged with CalVer

**Release Pipeline**:

- Verifies image integrity via Cosign signature
- Retaggs to clean version
- Updates manifests
- No redundant scanning

**Result**: Fast deployments with security guarantees, intentional release process.

---

## 🔍 Traceability

Every production deployment can be traced back to its source:

```bash
# 1. Find image in production
kubectl get deployment p8fs-api -o jsonpath='{.spec.template.spec.containers[0].image}'
# Output: ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.0-light-amd64

# 2. Verify signature and extract metadata
cosign verify ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.0-light-amd64

# 3. View SBOM
cosign verify-attestation --type=spdxjson \
  ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.0-light-amd64

# 4. Find original CalVer build
# Tag format reveals: 2025.01.15.1430-build.123-v1.2.0-abc1234-light-amd64
# - Built: Jan 15, 2025 at 14:30 UTC
# - Build number: 123
# - Git commit: abc1234
# - Version: v1.2.0

# 5. Inspect commit in GitHub
git show abc1234
```

---

## 📚 Complete Workflow Example

### Development Workflow

```bash
# 1. Feature Development
git checkout -b feature/new-feature
# ... make changes ...

# 2. Bump version and create build commit
python3 scripts/bump_version.py              # Patch: 0.1.4 -> 0.1.5
python3 scripts/bump_version.py --minor      # Minor: 0.1.4 -> 0.2.0
python3 scripts/bump_version.py --major      # Major: 0.1.4 -> 1.0.0

# 3. Push commit (does NOT trigger build)
git push origin feature/new-feature

# 4. Create and push RC tag (TRIGGERS BUILD)
git tag v1.2.0-rc
git push origin v1.2.0-rc

# 5. Wait for build to complete
# Check: GitHub Actions → "Build and Push Docker Images"
# Verify: CalVer images in GHCR, Trivy scan results

# 6. Test CalVer images in staging environment
# Verify functionality and performance

# 7. Create release (requires manual yes)
python3 scripts/release_version.py
# Answer "y" when prompted

# 8. Release pipeline runs automatically
# Manifests update, ArgoCD deploys
```

### Version Numbering

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.x.x): Breaking changes
- **MINOR** (x.1.x): New features (backward compatible)
- **PATCH** (x.x.1): Bug fixes (backward compatible)

### Best Practices

- Never skip vulnerability scans
- Review Trivy reports before releases
- Keep dependencies updated
- Monitor SBOM for license compliance
- Test CalVer images thoroughly before releasing
- Use meaningful commit messages with version bumps

---

## 🔧 Troubleshooting

### Build Pipeline Issues

**Problem:** Build triggered but no images created

```bash
# Check if RC tag exists
git tag -l "v*-rc"

# Verify workflow triggered
gh workflow list
gh run list --workflow=build-and-push.yml

# Check recent workflow runs
gh run list --workflow=build-and-push.yml --limit 5
```

**Problem:** Tests failing for amd64 builds

```bash
# Check test logs
gh run view <run-id> --log-failed

# Test locally with same image
docker run --rm ghcr.io/percolation-labs/p8fs-ecosystem-test:<calver-tag> \
  python -m pytest
```

**Problem:** Trivy scan failures

```bash
# View Trivy scan results
gh run view <run-id> --log | grep -A 20 "Trivy"

# Delete failed tag and retry
git tag -d v1.2.2-rc
git push origin :v1.2.2-rc

# Fix vulnerabilities, then retag
git tag v1.2.2-rc
git push origin v1.2.2-rc
```

### Release Pipeline Issues

**Problem:** No CalVer images found for version

```bash
# Ensure build pipeline completed first
gh run list --workflow=build-and-push.yml | grep v1.2.0

# Check GHCR for images
gh api /orgs/percolation-labs/packages/container/p8fs-ecosystem-test/versions \
  | jq -r '.[] | .metadata.container.tags[]' | grep v1.2.0

# Verify metadata artifacts exist
gh run view <build-run-id> --log | grep "metadata"
```

**Problem:** Cosign verification fails

```bash
# Verify signing identity
cosign verify \
  --certificate-identity-regexp="https://github.com/Percolation-Labs/p8fs-ecosystem" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.0-light-amd64

# Check SBOM attestation
cosign verify-attestation --type=spdxjson \
  ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.0-light-amd64
```

**Problem:** Manifests not updated in p8fs-cloud

```bash
# Check release workflow logs
gh run view <run-id> --log | grep "Updating manifests"

# Verify p8fs-cloud repository access
gh repo view Percolation-Labs/p8fs-cloud

# Check for merge conflicts
cd p8fs-cloud
git pull origin main
git log --oneline | grep "Update image tags"
```

### Common Issues

**Problem:** RC tag push doesn't trigger build

```bash
# Verify tag format (must have -rc suffix)
git tag -l | grep v1.2.2

# Check workflow file trigger conditions
cat .github/workflows/build-and-push.yml | grep -A 5 "on:"

# Manually trigger if needed
gh workflow run build-and-push.yml -f build_version=v1.2.2-rc
```

**Problem:** Clean tag push doesn't trigger release

```bash
# Verify tag format (must NOT have -rc suffix)
git tag -l | grep v1.2.2

# Ensure CalVer images exist first
gh api /orgs/percolation-labs/packages/container/p8fs-ecosystem-test/versions \
  | jq -r '.[] | .metadata.container.tags[]' | grep v1.2.2

# Check release workflow logs
gh run list --workflow=release-retag-update-manifests.yml
```

---

## 🎯 Quick Reference

### Common Commands

```bash
# Version Management
python3 scripts/bump_version.py              # Bump patch
python3 scripts/bump_version.py --minor      # Bump minor
python3 scripts/bump_version.py --major      # Bump major
python3 scripts/release_version.py           # Create release tag

# Trigger Build (via RC tag)
git tag v1.2.0-rc
git push origin v1.2.0-rc

# Trigger Release (via clean tag)
git tag v1.2.0
git push origin v1.2.0

# Or use release script
python3 scripts/release_version.py

# View Workflows
gh run list --workflow=build-and-push.yml --limit 5
gh run list --workflow=release-retag-update-manifests.yml --limit 5

# Check Images
gh api /orgs/percolation-labs/packages/container/p8fs-ecosystem-test/versions \
  | jq -r '.[] | .metadata.container.tags[]' | head -20

# Verify Deployment
kubectl get deployment p8fs-api -o yaml | grep image:

# Verify Security
cosign verify ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.0-light-amd64
cosign verify-attestation --type=spdxjson \
  ghcr.io/percolation-labs/p8fs-ecosystem-test:1.2.0-light-amd64
```

### Pipeline Triggers

| Action                      | Triggers           | Result                         |
| --------------------------- | ------------------ | ------------------------------ |
| `git push origin v1.2.0-rc` | Build Pipeline     | CalVer images created & tested |
| `git push origin v1.2.0`    | Release Pipeline   | Clean tags, signed & deployed  |
| Commit only (no tag)        | Nothing            | No pipeline execution          |
| Manual workflow dispatch    | Specified pipeline | Pipeline runs with parameters  |

### Environment Variables

| Variable              | Description            | Required            |
| --------------------- | ---------------------- | ------------------- |
| `GITHUB_TOKEN`        | GitHub API access      | Yes (auto-provided) |
| `COSIGN_EXPERIMENTAL` | Enable keyless signing | Yes (set to `1`)    |
| `REGISTRY`            | Container registry     | Yes (ghcr.io)       |
| `IMAGE_NAME`          | Image name             | Yes                 |

---

## 📖 Additional Resources

- [CalVer Specification](https://calver.org/)
- [Cosign Documentation](https://docs.sigstore.dev/cosign/overview/)
- [Trivy Scanning Guide](https://aquasecurity.github.io/trivy/)
- [SPDX SBOM Format](https://spdx.dev/)
- [ArgoCD GitOps](https://argo-cd.readthedocs.io/)
- [Semantic Versioning](https://semver.org/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [SLSA Framework](https://slsa.dev/)

### Getting Started with AI Agents

🚀 **New to P8FS? Start here!** Check out our comprehensive getting-started guide:

```bash
cd p8fs-modules
uv run jupyter notebook getting_started.ipynb
```

The notebook demonstrates:

- Creating AI agents with function calling (weather agent example)
- Using MemoryProxy in **normal**, **streaming**, and **batch** modes
- Detailed CallingContext configurations
- Advanced function registration patterns
- Complete working examples with mock implementations

Perfect for understanding how to build AI-powered applications with P8FS!

## Documentation

For detailed development guidance, see each module's CLAUDE.md file.
