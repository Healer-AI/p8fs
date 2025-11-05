# P8FS - Next Generation Smart Content Management System

## Quick Start Guide

For detailed step-by-step instructions on using P8FS, see `/Users/sirsh/code/p8fs-modules/how-to.md`. This provides a complete walkthrough of:

- Starting Docker services and setting up the environment
- Processing files and generating embeddings
- Performing semantic search queries
- Using AI agents (DreamModel, MomentBuilder) for content analysis
- Creating custom agent models for specific analysis tasks

**Quick reference for common tasks:**

```bash
# 1. Start PostgreSQL (from p8fs directory)
cd p8fs
docker compose up postgres -d

# 2. Set API keys
export OPENAI_API_KEY=sk-your-key-here
export ANTHROPIC_API_KEY=sk-ant-your-key-here  # Optional

# 3. Process a file (generates embeddings automatically)
uv run python -m p8fs.cli process tests/sample_data/content/diary_sample.md

# 4. Search semantically
uv run python -m p8fs.cli query \
  --table resources \
  --hint semantic \
  --limit 3 \
  "What did I do today?"

# 5. Analyze with AI agent (DreamModel extracts goals, dreams, fears)
uv run python -m p8fs.cli eval \
  --agent-model agentlets.dreaming.DreamModel \
  --file tests/sample_data/content/diary_sample.md \
  --model claude-sonnet-4-5 \
  --format yaml
```

**Database verification:**

```bash
# Connect to PostgreSQL (without -it flag for non-TTY environments)
docker exec percolate psql -U postgres -d app

# Check resources
SELECT name, category, length(content) as content_length
FROM resources WHERE tenant_id = 'tenant-test' LIMIT 5;

# Check embeddings
SELECT r.name, e.field_name, e.embedding_provider, e.vector_dimension
FROM resources r
JOIN embeddings.resources_embeddings e ON r.id = e.entity_id
WHERE r.tenant_id = 'tenant-test' LIMIT 5;
```

## System Overview

P8FS is a distributed content management system designed for secure, scalable storage with advanced indexing capabilities. The system leverages S3-compatible blob storage (SeaweedFS) and TiDB/TiKV for managing a secure "memory vault" where users can upload and manage content with end-to-end encryption.


NB! If you need to create test scripts creating the either in `/tmp` or `./claude/scratch`. Never creating loose files. Sometimes adding files as tests can be useful but only if the conform to test writing standards

### Core Components

- **Storage Layer**: S3-compatible SeaweedFS for blob storage
- **Database Layer**: TiDB/TiKV for content indexing (graph, vector, SQL, key-value)
- **Message Queue**: NATS JetStreams for job processing
- **Scaling**: KEDA for on-demand worker scaling
- **Authentication**: Mobile-first keypair generation with OAuth 2.1 token issuance
- **Content Processing**: Modular content providers for various formats (PDF, WAV, video, DOCX, Markdown)

## Design Principles

1. **Separation of Concerns**: Each module handles a single responsibility
2. **Security First**: End-to-end encryption for user data with client-held keys
3. **Minimal Code**: Lean implementations avoiding unnecessary complexity
4. **Testability**: Comprehensive unit tests with mocks and integration tests with real services
5. **Scalability**: Horizontal scaling through KEDA and distributed storage
6. **Clean Architecture**: Well-defined interfaces between components
7. **Centralized Configuration**: Single source of truth for all configuration

## How We Work

### Code Quality Standards

- Write minimal, efficient code with clear intent
- Avoid workarounds; implement proper solutions
- Prioritize maintainability over quick fixes
- Keep implementations lean and purposeful

### Testing Requirements

- Unit tests with appropriate mocking for isolated testing
- Integration tests against real services
- Test coverage for critical paths
- Performance benchmarks for key operations

### Contributing Guidelines

#### Pre-commit Hooks

The project uses pre-commit hooks to maintain code quality:

- **Pre-commit**: Automatically runs unit tests before each commit
- **Pre-push**: Automatically runs integration tests before pushing to remote

To bypass hooks when necessary:
```bash
# Skip pre-commit unit tests
git commit -m "your message" --no-verify

# Skip pre-push integration tests
git push --no-verify
```

See `p8fs/docs/pre-commit-hooks.md` for detailed setup and usage.

### Documentation Guidelines

- Factual, evidence-based documentation
- Simple, clear explanations without adjectives
- No emojis or decorative elements
- Focus on technical accuracy

### Separate standalone projects and libraries in python and rust

```
p8fs-modules/
├── p8fs-api/         # API endpoints and REST, CLI, MCP
├── p8fs-auth/        # Authentication and authorization - also includes encryption tools
├── p8fs-cluster/     # Cluster management and coordination
├── p8fs/        # The main percolate memory system with RAG/IR features and DB respositories
└── p8fs-node/        # Node is the core processing unit of this system and can run anywhere - it handles embeddings, inference e.g. transcription and manages all content processors e.g. pdf, wav etc.
```

### Module Dependency Graph

```
┌─────────────┐
│ p8fs-cluster│ ← Central configuration and environment management
└─────┬───────┘
      │
      ├─────────────────┬─────────────────┐
      │                 │                 │
      ▼                 │                 ▼
┌─────────────┐         │           ┌─────────────┐
│ p8fs(p8fs)   │         │           │ p8fs-node   │
└─────┬───────┘         │           └─────────────┘
      │                 │                 ▲
      │                 ▼                 │
      │           ┌─────────────┐         │
      │           │ p8fs-auth   │         │
      │           └─────┬───────┘         │
      │                 │                 │
      └─────────┬───────┘                 │
                │                         │
                ▼                         │
          ┌─────────────┐                 │
          │ p8fs-api    │─────────────────┘
          └─────────────┘
```

**Dependency Relationships:**
- **p8fs-cluster**: Foundation layer providing centralized configuration and environment management
- **p8fs**: Builds on cluster; can be loaded light (core only) or heavy (with p8fs-node for processing)
- **p8fs-auth**: Depends on both cluster (config) and core (data models)
- **p8fs-api**: Top layer depending on auth and light core; communicates with node for processing
- **p8fs-node**: Standalone processor depending only on cluster for configuration

**Core Loading Modes:**
- **Light Core** (API): Only database repositories, models, and business logic without media processing dependencies
- **Heavy Core** (Workers): Full core plus p8fs-node integration for embeddings, transcription, and content processing

The architecture allows independent development while maintaining clear dependency boundaries. UV packages can be configured for development synchronization, but each module remains independently deployable with different development timescales.

**uv Workspace Integration:**

The dependency structure is managed through uv workspaces with automatic editable installs:

1. **p8fs-api** (depends on: cluster, core, auth)
   - Uses `workspace = true` declarations for local dependencies  
   - Changes in dependencies immediately available via editable installs
   - uvicorn `--reload` provides service restart on file changes

2. **p8fs-node** (depends on: cluster)
   - Declares p8fs-cluster as workspace dependency
   - Changes in cluster config immediately available without reinstalls
   - CLI commands always use latest code via editable installs

3. **Library modules** (auth, core, cluster) 
   - Installed as editable workspace members automatically
   - No hot reload needed (they provide functionality to other modules)
   - Changes propagate immediately via uv's editable install mechanism

uv workspaces eliminate manual dependency management and package reinstalls entirely

## Future Development

### Kubernetes Integration

- Kind cluster setup for local development
- Kubernetes resource definitions

## Development Environment

### Docker Services

**IMPORTANT**: Always use the default `docker-compose.yaml` in p8fs for development and testing. This includes:

- **PostgreSQL** (port 5438): `percolationlabs/postgres-base:16` with pgvector extension pre-installed
- **TiDB** (port 4000): Single container with unistore for testing
- **SeaweedFS** (ports 9333, 8080, 8888): S3-compatible blob storage

Start services:
```bash
cd p8fs
docker-compose up postgres -d  # Just PostgreSQL
docker-compose up -d           # All services
```

Connection strings are automatically set:
- PostgreSQL: `postgresql://postgres:postgres@localhost:5438/app`
- TiDB: `mysql://root@localhost:4000/test`

### uv Workspace Development

The p8fs project uses uv workspaces for monorepo development, providing seamless integration between modules without manual dependency management. uv workspaces automatically handle editable installs, making changes immediately available across dependent modules.

#### How uv Workspaces Work

1. **Single Workspace Root**: The `p8fs-modules` directory serves as the workspace root with a master `pyproject.toml`
2. **Editable Members**: Each module (p8fs-api, p8fs-auth, etc.) is a workspace member with editable installs by default
3. **Shared Lockfile**: All modules share a single `uv.lock` file ensuring consistent dependency versions
4. **Automatic Updates**: Changes to any module are immediately available to dependent modules without reinstalls

#### Workspace Configuration

**TODO**: Create root `pyproject.toml` to enable uv workspace functionality:

```toml
[tool.uv.workspace]
members = [
    "p8fs-api",
    "p8fs-auth", 
    "p8fs",
    "p8fs-cluster",
    "p8fs-node"
]
```

Each module declares local dependencies:

```toml
# In p8fs-api/pyproject.toml
[project]
dependencies = [
    "fastapi>=0.100.0",
    "p8fs-auth",
    "p8fs"
]

[tool.uv.sources]
p8fs-auth = { workspace = true }
p8fs = { workspace = true }
```

#### Development Commands

```bash
# Install all workspace dependencies (editable by default)
uv sync

# Run API server with hot reload for service restarts
# IMPORTANT: ALWAYS use uv run and ALWAYS use --reload for development
cd p8fs-api
uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8000

# Run any module command
uv run -p p8fs-node p8fs-node process --help
```

#### Benefits Over Manual Path Management

**With uv Workspaces:**
- Change p8fs-cluster settings → Immediately available in p8fs-node  
- Modify p8fs-auth models → Instantly reflected in p8fs-api
- Update p8fs repositories → Available everywhere without reinstalls
- Proper Python import resolution without PYTHONPATH manipulation

**Hot Reload for Services:**
- uv workspaces provide editable installs (code changes immediately available)
- uvicorn `--reload` provides service restart on file changes
- Combined: modify any dependency and service automatically restarts with changes

## Configuration Architecture

### Centralized Configuration System

**CRITICAL**: All configuration must come from the single source of truth in `p8fs-cluster/src/p8fs_cluster/config/settings.py`. Never set individual environment variables for database connections or other settings.

#### Key Principles:

1. **Single Source of Truth**: All modules import configuration from `p8fs_cluster.config.settings`
2. **No Direct Environment Variables**: Never set `P8FS_PG_*` or individual connection parameters
3. **Provider Neutrality**: Providers get connection strings from centralized config, not from direct environment variables

#### Example Usage:

```python
# ✅ CORRECT - Use centralized config
from p8fs_cluster.config.settings import config

# Database connections come from centralized config
connection_string = config.pg_connection_string  # Built from pg_host, pg_port, etc.
provider = config.storage_provider  # "postgresql", "tidb", "rocksdb"

# ✅ CORRECT - Provider implementation
class PostgreSQLProvider:
    def connect_sync(self, connection_string: Optional[str] = None):
        # Always use centralized config as source of truth
        conn_str = connection_string or config.pg_connection_string
        return psycopg2.connect(conn_str)
```

```python
# ❌ WRONG - Don't set individual environment variables
# P8FS_PG_HOST=localhost
# P8FS_PG_PORT=5438
# P8FS_PG_DATABASE=test

# ❌ WRONG - Don't bypass centralized config
connection = psycopg2.connect("postgresql://postgres@localhost:5438/test")
```

#### Configuration Flow:

```
Environment Variables → P8FSConfig → Computed Properties → Providers
```

- Set high-level config: `P8FS_STORAGE_PROVIDER=postgresql`
- Config builds connection strings: `pg_connection_string` property
- Providers use centralized config: `config.pg_connection_string`

#### Test Configuration:

- **Integration Tests**: Use real centralized config (no mocking)
- **Unit Tests**: Mock config locally within specific test functions, not globally
- **Never**: Override config globally in `conftest.py` for integration tests

## Technical Stack

- **Storage**: SeaweedFS (S3-compatible)
- **Database**: TiDB/TiKV
- **Message Queue**: NATS JetStreams
- **Container Orchestration**: Kubernetes
- **Scaling**: KEDA
- **Authentication**: OAuth 2.1 with mobile-generated keypairs