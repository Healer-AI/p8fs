# P8FS Core Module

The main percolate memory system with RAG/IR features and database repositories for the P8FS smart content management system.
The core also provides pydantic models that describe the system. Pydantic is used to describe core database entities like Resources and Chat Sessions and also used to define how agents function. For example an agent is just a pydantic object with config, structure and callable functions.
The most important element of this library is the MemoryProxy which is agent execution framework that streams LLM conversations for any dialect (OpenAI, Anthropic, Google) and allows for agentic loops and agent context injection.
The second most important part of this library is the repository that provides an abstraction over databases for multi-modal content indexing and search (SQL, Vector, Graph, Key-Value). The underlying storage can be TiKV, Postgres or RocksDB.

## Installation

### Standard Installation

For basic p8fs functionality (repositories, models, MemoryProxy):

```bash
uv sync
```

### With Content Processing (Recommended for Development)

For file processing capabilities (PDF, audio, documents), install with the `workers` extras group which includes `p8fs-node`:

```bash
uv sync --extra workers
```

This installs additional dependencies needed for:
- Document processing (PDF, DOCX, etc.)
- Audio transcription (WAV, MP3, M4A)
- Content chunking and embedding generation
- Storage worker functionality

**Note**: The `workers` extras adds heavy dependencies like PyTorch, transformers, and media processing libraries. Only install this if you need file processing capabilities.

## Rebuilding Local Docker Environment

When making changes to the database schema (such as updating column types from TEXT to JSONB), you need to completely rebuild your local Docker environment to ensure a clean state:

### Complete Rebuild Process

```bash
# 1. Generate SQL from Python models
python scripts/compile_migrations.py --refresh

# 2. Stop all containers and remove volumes (WARNING: This deletes all data)
docker-compose down -v

# 3. Start fresh containers
docker-compose up -d

# 4. The database will be initialized with the new schema automatically
```

### When to Rebuild

**You normally don't need to do this.** Only rebuild when:
- Changing column types (e.g., TEXT to JSONB)
- Modifying primary keys or unique constraints
- Changing table structures significantly
- Resolving migration conflicts

### Migration Script Details

The `compile_migrations.py` script:
1. **With `--refresh` (default)**: Regenerates SQL from Python models using proper type mappings (dict → JSONB)
2. Copies the generated SQL to `extensions/sql/01_entity_schema.sql`
3. Compiles individual function files into `03_functions.sql`

This ensures your database schema stays in sync with your Python models.

## Embedding Tables Architecture

P8FS automatically generates embeddings for entities with embedding fields and stores them in dedicated embedding tables. The embedding tables follow this design pattern:

### Embedding Table Structure

For a main table named `resources`, an embedding table `embeddings.resources_embeddings` is created with:

- **Primary Key**: `id` (UUID, auto-generated)
- **Entity Reference**: `entity_id` (references main table primary key) 
- **Field Identifier**: `field_name` (which field the embedding represents)
- **Provider Info**: `embedding_provider` (which embedding model was used)
- **Vector Data**: `embedding_vector` (pgvector type with appropriate dimensions)
- **Metadata**: `vector_dimension`, `tenant_id`, `created_at`, `updated_at`

### Unique Constraint

**CRITICAL**: Embedding tables MUST include a unique constraint on `(entity_id, field_name, tenant_id)` to ensure:
- No duplicate embeddings for the same entity field
- Proper upsert behavior during updates
- Tenant isolation for multi-tenant systems

### Automatic Embedding Generation

When entities are inserted/updated via `TenantRepository.upsert()`:
1. Main entity data is saved to the primary table
2. For each field marked with `is_embedding: True` in the schema:
   - Text content is sent to the configured embedding provider (OpenAI, local, etc.)
   - Generated embedding vector is stored in the embedding table
   - Uses INSERT ... ON CONFLICT to handle updates

### Usage Example

```python
# Model with embedding fields
class Document(AbstractModel):
    id: str
    title: str
    content: str  # Will be embedded
    summary: str  # Will be embedded
    
    @classmethod
    def to_sql_schema(cls):
        return {
            'table_name': 'documents',
            'embedding_fields': ['content', 'summary'],
            'embedding_providers': {you
                'content': 'text-embedding-3-small',
                'summary': 'text-embedding-3-small'
            },
            # ... field definitions
        }

# Automatic embedding generation
repo = TenantRepository(Document, tenant_id="my-tenant")
repo.upsert(document)  # Creates embeddings automatically
```

This lib will depend on p8fs-cluster for environment and logging dependencies


The API will have completions endpoints that call the Memory Proxy directly as a thing wrapper.

Use Jupyter to try out the MemoryProxy and agent tools

## CLI Usage

P8FS Core provides a command-line interface with two main commands:

### Agent Command

Run an AI agent using the MemoryProxy in streaming mode:

```bash
# Basic usage
uv run p8fs agent "What is the capital of France?"

# With custom model and agent
uv run p8fs agent --model gpt-4 --agent my-tenant "Analyze this data"

# From stdin
echo "Explain machine learning" | uv run p8fs agent
```

**Options:**
- `--agent`: Agent name/tenant ID (default: `p8-Resources`)
- `--model`: Model to use (default: `gpt-4`)

### Query Command

Execute SQL queries against the configured database:

```bash
# Basic query
uv run p8fs query "SELECT version();"

# With JSON output
uv run p8fs query --format=json "SELECT * FROM users LIMIT 5;"

# With different provider
uv run p8fs query --provider=tidb "SHOW TABLES;"

# From stdin
echo "SELECT COUNT(*) FROM documents;" | uv run p8fs query
```

**Options:**
- `--provider`: Database provider (`postgres`, `tidb`, `rocksdb`) (default: `postgres`)
- `--format`: Output format (`table`, `json`, `jsonl`) (default: `table`)

### Process Command

Process files and folders using p8fs-node content providers:

```bash
# Process a single file
uv run p8fs process document.pdf

# Process entire folder
uv run p8fs process ~/Documents/research/

# Sync folder - only process new or modified files
uv run p8fs process --sync ~/Documents/p8-node/

# Sync with limit for testing
uv run p8fs process --sync --limit 10 ~/Documents/

# Skip embedding generation
uv run p8fs process --no-generate-embeddings file.md

# Output chunks to file
uv run p8fs process -o chunks.txt document.pdf

# View chunks in terminal
uv run p8fs process -v document.md
```

**Options:**
- `--sync`: Only process new or modified files since last sync
- `--limit`: Limit number of files to process (useful for testing)
- `--generate-embeddings`: Generate embeddings for chunks (default: true)
- `--save-to-storage`: Save chunks to database (default: true)
- `--output/-o`: Save chunks to text file
- `--verbose/-v`: Print chunks to stdout
- `--tenant-id`: Tenant ID for storage isolation

**Supported File Types:**
- Documents: `.pdf`, `.docx`, `.doc`, `.odt`, `.rtf`
- Text: `.md`, `.txt`, `.rst`
- Audio: `.wav`, `.mp3`, `.m4a`

The sync feature tracks processed files by URI and modification time, making it efficient to keep large document collections up to date.

### Router Command

Create NATS JetStream infrastructure for tiered storage event routing:

```bash
# Run router with default settings
uv run python -m p8fs.cli router

# With custom worker ID
uv run python -m p8fs.cli router --worker-id=my-router

# Local testing with port-forward to cluster
kubectl port-forward -n p8fs svc/nats 4222:4222 &
kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000 &

P8FS_NATS_URL=nats://localhost:4222 \
P8FS_TIDB_HOST=localhost \
P8FS_TIDB_PORT=4000 \
P8FS_TIDB_DATABASE=public \
uv run python -m p8fs.cli router --worker-id=test-router
```

**What the Router Creates:**

The router sets up the complete NATS infrastructure for storage event processing:

1. **4 Streams**:
   - `P8FS_STORAGE_EVENTS` - Main stream for incoming events
   - `P8FS_STORAGE_EVENTS_SMALL` - Events for 0-100MB files
   - `P8FS_STORAGE_EVENTS_MEDIUM` - Events for 100MB-1GB files
   - `P8FS_STORAGE_EVENTS_LARGE` - Events for 1GB+ files

2. **3 Consumers**:
   - `small-workers` on `P8FS_STORAGE_EVENTS_SMALL`
   - `medium-workers` on `P8FS_STORAGE_EVENTS_MEDIUM`
   - `large-workers` on `P8FS_STORAGE_EVENTS_LARGE`

3. **Message Routing**: Routes events from main stream to size-specific streams

**Options:**
- `--worker-id`: Unique identifier for router instance (default: auto-generated)

The router must be running for storage workers to function properly. It can run as a CLI command (development) or as a Kubernetes deployment (production).

### Configuration

The CLI uses configuration from p8fs-cluster, including:
- PostgreSQL: `P8FS_PG_HOST`, `P8FS_PG_PORT`, `P8FS_PG_USER`, `P8FS_PG_PASSWORD`, `P8FS_PG_DATABASE`
- OpenAI API key: `OPENAI_API_KEY`
- Other provider-specific settings

## Overview

The p8fs module implements the central memory vault functionality, providing advanced information retrieval, vector search, graph relationships, and multi-modal content indexing. This module manages the core data repositories and implements the percolate memory system that enables intelligent content organization and retrieval. it is also the agentic framework for p8fs.

## Architecture

### Components to Port

### 0. Core Models
- Pydantic is used to define core types and extensible agent framework

#### 1. Repository Layer 
- The p8fs repository provides an abstraction over databases like TiKV or postgres.
- It is pydnatic model based 
- We provide SQL helpers for different dialects like TIDB or Postgres.
- We provide interface methods for registering, selecting, upserting models and entity lookup, embedding creation, graph query and indexing and more


### 2. Memory Proxy
- The memory proxy is the pydantic base agent runner 



## Contracts / Tests
- Can convert requests and responses for LLMs between all three dialects
- Can run agentic loops with function calling (buffered)
- Can operated in streaming, non streming and batch job submission mode in all dialects
- Can eval fucntions on agentic models
- Can register tables in underlying storages (postgres, TiDB, RockDB)

## Testing

### Running Tests

P8FS uses pytest for testing with separate unit and integration test suites:

```bash
# Run all unit tests (fast, uses mocks)
uv run pytest tests/unit/ -v

# Run all integration tests (requires database, skips LLM tests)
uv run pytest tests/integration/ -v

# Run integration tests WITH LLM API calls (requires API keys)
uv run pytest tests/integration/ -v --with-llm

# Run specific LLM test with API calls
uv run pytest tests/integration/test_natural_language_sql.py -v --with-llm
```

### LLM Test Flag

Integration tests that make real LLM API calls are marked with `@pytest.mark.llm` and are **skipped by default** to prevent:
- Hanging tests when API keys are missing
- Expensive API calls during regular testing
- Slow test execution

Use the `--with-llm` flag to run these tests when you have valid API keys configured:
- `OPENAI_API_KEY` for OpenAI tests
- `ANTHROPIC_API_KEY` for Claude tests  
- `GOOGLE_API_KEY` for Gemini tests

### Test Categories

- **Unit tests** (`tests/unit/`): Fast, isolated, use mocks, no external dependencies
- **Integration tests** (`tests/integration/`): Test complete workflows with real databases
- **LLM integration tests**: Integration tests that make real API calls (use `--with-llm`)

## Contributing

### Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality:

- **Pre-commit**: Automatically runs unit tests before each commit
- **Pre-push**: Automatically runs integration tests (with database startup) before pushing to remote

To bypass hooks when necessary:
```bash
# Skip pre-commit unit tests
git commit -m "your message" --no-verify

# Skip pre-push integration tests
git push --no-verify
```

For detailed setup and usage, see `docs/pre-commit-hooks.md`.