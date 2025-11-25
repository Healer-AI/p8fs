# P8FS Core Module

## Quick Start Guide

For complete walkthrough with examples, see `/Users/sirsh/code/p8fs-modules/how-to.md`

**Quick CLI reference:**

```bash
# Start PostgreSQL (from p8fs directory).
cd p8fs
docker compose up postgres -d

# Process a file (generates embeddings)
uv run python -m p8fs.cli process tests/sample_data/content/diary_sample.md

# Semantic search
uv run python -m p8fs.cli query --table resources --hint semantic "query text"

# AI analysis with DreamModel
uv run python -m p8fs.cli eval \
  --agent-model agentlets.dreaming.DreamModel \
  --file path/to/file.md \
  --model claude-sonnet-4-5 \
  --format yaml
```

## Module Overview

The P8FS Core module is the percolate memory system that handles RAG/IR features, database repositories, and content indexing. It provides the foundational services for AI memory management, supporting both PostgreSQL (development/test) and TiDB (production) backends with advanced vector, graph, and semantic search capabilities.

## Architecture

### Core Components

- **Memory Management System**: Vector and graph-based content indexing
- **Engram Processor**: Content chunking and semantic processing
- **LLM Service Abstractions**: Multi-provider language model integration
- **Repository Layer**: Multi-database support with consistent interfaces
- **Background Workers**: Async job processing and content ingestion
- **Job Queues**: NATS-based distributed task processing

### Key Features

- Dual database support (PostgreSQL/TiDB)
- Vector similarity search with pgvector
- Graph-based relationship mapping
- Streaming LLM responses
- Content processing pipelines
- Scalable worker architecture

## Development Standards

### Code Quality

- Write minimal, efficient code with clear intent
- Avoid workarounds; implement proper solutions
- Prioritize maintainability over quick fixes
- Keep implementations lean and purposeful
- No comments unless absolutely necessary for complex algorithms

### Testing Requirements

#### Unit Tests
- Mock external dependencies (database connections, LLM services)
- Test individual components in isolation
- Validate data transformations and business logic
- Test error handling and edge cases

#### Integration Tests
- Use real database services (PostgreSQL/TiDB)
- Test complete data flows end-to-end
- Validate cross-component interactions
- Test performance with realistic data volumes

### Configuration

All configuration must come from the centralized system in `p8fs_cluster.config.settings`. The core module uses computed connection strings and provider selection.

```python
# ✅ CORRECT - Use centralized config
from p8fs_cluster.config.settings import config

# Database provider selection based on centralized config
def get_database_provider():
    if config.storage_provider == "postgresql":
        from p8fs.providers.postgresql import PostgreSQLProvider
        return PostgreSQLProvider(config.pg_connection_string)
    elif config.storage_provider == "tidb":
        from p8fs.providers.tidb import TiDBProvider
        return TiDBProvider(config.tidb_connection_string)
    elif config.storage_provider == "rocksdb":
        from p8fs.providers.rocksdb import RocksDBProvider
        return RocksDBProvider(config.rocksdb_path)

# LLM service configuration
llm_service = LanguageModelService(
    provider=config.llm_provider,
    api_key=config.llm_api_key,
    model=config.llm_model
)
```

```python
# ❌ WRONG - Don't read environment variables directly
import os

# Don't do this in core module
db_url = os.getenv("DATABASE_URL")  # Wrong!
llm_key = os.getenv("OPENAI_API_KEY")  # Wrong!
```

## Architecture Patterns

### Repository Pattern
```python
from abc import ABC, abstractmethod
from typing import List, Optional
from p8fs.models.base import BaseModel

class BaseRepository(ABC):
    @abstractmethod
    async def create(self, entity: BaseModel) -> BaseModel:
        pass
    
    @abstractmethod
    async def find_by_id(self, entity_id: str) -> Optional[BaseModel]:
        pass
    
    @abstractmethod
    async def find_similar(self, embedding: List[float], limit: int) -> List[BaseModel]:
        pass

class TenantRepository(BaseRepository):
    def __init__(self, provider):
        self.provider = provider
    
    async def create(self, entity: BaseModel) -> BaseModel:
        return await self.provider.insert(entity)
    
    async def find_similar(self, embedding: List[float], limit: int) -> List[BaseModel]:
        return await self.provider.vector_search(embedding, limit)
```

### Provider Pattern
```python
from p8fs.providers.base import BaseProvider
import psycopg2.extras

class PostgreSQLProvider(BaseProvider):
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
    
    async def vector_search(self, embedding: List[float], limit: int) -> List[dict]:
        async with self.get_connection() as conn:
            async with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                await cur.execute("""
                    SELECT id, content, embedding <-> %s as distance
                    FROM engrams 
                    ORDER BY embedding <-> %s 
                    LIMIT %s
                """, (embedding, embedding, limit))
                return await cur.fetchall()
```

### KV Storage Provider

Each main provider includes a `kv` property for temporary key-value storage used in authentication flows:

```python
from p8fs.providers import get_provider
from p8fs.models.device_auth import PendingDeviceRequest, store_pending_request

# Get configured provider (PostgreSQL/TiDB/RocksDB)
provider = get_provider()

# Access KV storage for temporary data
kv = provider.kv

# Device authorization flow example
pending_request = PendingDeviceRequest.create_pending_request(
    device_code="abc123",
    user_code="A1B2-C3D4", 
    client_id="desktop_app",
    ttl_seconds=600
)

# Store with TTL
await store_pending_request(kv, pending_request, ttl_seconds=600)

# Retrieve for approval
request = await get_pending_request_by_user_code(kv, "A1B2-C3D4")

# Approve and update
request.approve(tenant_id="tenant-123", access_token="jwt_token")
await update_pending_request(kv, request)

# Consume token and cleanup
access_token = request.consume()
await delete_pending_request(kv, request.device_code, request.user_code)
```

#### KV Provider Implementations

**PostgreSQL KV**: Uses `kv_storage` table with JSON columns and TTL
**TiKV**: Direct key-value storage with TTL (production)
**RocksDB**: Embedded key-value storage (development)

#### KV Methods
- `put(key, value, ttl_seconds)`: Store with optional TTL
- `get(key)`: Retrieve value (None if expired/missing)
- `delete(key)`: Remove key
- `scan(prefix, limit)`: Find keys by prefix
- `find_by_field(field, value)`: Search within values

### Engram Processing
```python
from p8fs.models.engram.processor import EngramProcessor
from p8fs.services.llm import LanguageModelService

class ContentProcessor:
    def __init__(self):
        self.engram_processor = EngramProcessor()
        self.llm_service = LanguageModelService()
    
    async def process_content(self, content: str, source: str) -> List[dict]:
        # Chunk content into engrams
        chunks = await self.engram_processor.chunk_content(content)
        
        engrams = []
        for chunk in chunks:
            # Generate embedding
            embedding = await self.llm_service.embed(chunk['text'])
            
            engram = {
                'content': chunk['text'],
                'embedding': embedding,
                'source': source,
                'metadata': chunk['metadata']
            }
            engrams.append(engram)
        
        return engrams
```

## Testing Approach

### Test Structure
```
tests/
├── unit/
│   ├── models/
│   │   ├── test_engram_processor.py
│   │   └── agentlets/
│   │       ├── test_memory_proxy.py
│   │       └── test_dreaming_model.py
│   ├── services/
│   │   └── llm/
│   │       ├── test_language_model.py
│   │       └── test_memory_proxy.py
│   ├── test_postgresql_provider.py
│   └── test_tidb_provider.py
├── integration/
│   ├── test_repository_comprehensive.py
│   ├── test_embedding_integration.py
│   ├── test_tenant_repository_postgres.py
│   └── test_tenant_repository_tidb.py
└── sample_data/
    ├── test_resources.json
    └── llm_responses/
```

### Running Tests
```bash
# Unit tests with mocks
pytest tests/unit/ -v

# Integration tests with real databases
pytest tests/integration/ -v

# Specific provider tests
pytest tests/integration/test_tenant_repository_postgres.py -v
pytest tests/integration/test_tenant_repository_tidb.py -v

# All tests
./run_tests.sh
```

### Example Test Patterns

#### Unit Test with Repository Mocking
```python
from unittest.mock import Mock, AsyncMock
import pytest
from p8fs.repository.TenantRepository import TenantRepository

@pytest.fixture
def mock_provider():
    provider = Mock()
    provider.insert = AsyncMock(return_value={'id': '123'})
    provider.vector_search = AsyncMock(return_value=[])
    return provider

async def test_repository_create(mock_provider):
    repo = TenantRepository(mock_provider)
    entity = {'content': 'test', 'embedding': [0.1, 0.2]}
    
    result = await repo.create(entity)
    
    mock_provider.insert.assert_called_once_with(entity)
    assert result['id'] == '123'
```

#### Integration Test with Real Database
```python
import pytest
from p8fs_cluster.config.settings import config
from p8fs.providers.postgresql import PostgreSQLProvider

@pytest.mark.integration
async def test_postgresql_vector_search():
    # Uses real database through centralized config
    provider = PostgreSQLProvider(config.pg_connection_string)
    
    # Insert test data
    test_embedding = [0.1, 0.2, 0.3]
    await provider.insert({
        'content': 'test content',
        'embedding': test_embedding
    })
    
    # Test vector search
    results = await provider.vector_search(test_embedding, limit=5)
    assert len(results) > 0
    assert 'distance' in results[0]
```

## Database Setup

### PostgreSQL Development
```bash
cd p8fs
docker-compose up postgres -d
```

The PostgreSQL container includes:
- pgvector extension pre-installed
- Default database: `app`
- Connection: `postgresql://postgres:postgres@localhost:5438/app`

### TiDB Production
```bash
cd p8fs
docker-compose up tidb -d
```

The TiDB container provides:
- MySQL-compatible interface
- Vector index support
- Connection: `mysql://root@localhost:4000/test`

### Running Migrations
```bash
# PostgreSQL migrations
psql -h localhost -p 5438 -U postgres -d app -f extensions/migrations/postgres/20250906_161207_create_p8fs_tables.sql

# TiDB migrations
mysql -h localhost -P 4000 -u root test < extensions/migrations/tidb/20250906_160204_create_p8fs_tables.sql
```

## LLM Integration

### Service Abstraction
```python
from p8fs.services.llm.language_model import LanguageModelService
from p8fs_cluster.config.settings import config

llm_service = LanguageModelService(
    provider=config.llm_provider,  # "openai", "anthropic", "google"
    api_key=config.llm_api_key,
    model=config.llm_model
)

# Streaming completion
async for chunk in llm_service.stream_complete(prompt):
    yield chunk

# Embedding generation
embedding = await llm_service.embed("content to embed")
```

### Memory Proxy Pattern
```python
from p8fs.services.llm import MemoryProxy

class ChatHandler:
    def __init__(self):
        self.memory = MemoryProxy()
    
    async def handle_chat(self, user_input: str, context: dict) -> str:
        # Retrieve relevant memories
        relevant_memories = await self.memory.recall(user_input)
        
        # Generate response with context
        response = await self.llm_service.complete(
            prompt=user_input,
            context=relevant_memories
        )
        
        # Store interaction as new memory
        await self.memory.store(user_input, response)
        
        return response
```

## Worker Architecture

### Background Workers
```python
from p8fs.workers.storage import StorageWorker
from p8fs.workers.dreaming import DreamingWorker

# Content processing worker
storage_worker = StorageWorker()
await storage_worker.process_file_upload(file_path, user_id)

# Memory consolidation worker
dreaming_worker = DreamingWorker()
await dreaming_worker.consolidate_memories(user_id)
```

### Queue Integration
```python
from p8fs.services.nats.client import NATSClient
from p8fs.workers.queues.storage_worker import process_storage_event

nats_client = NATSClient(config.nats_url)

# Subscribe to storage events
await nats_client.subscribe("storage.events", process_storage_event)

# Publish processing job
await nats_client.publish("processing.jobs", {
    'type': 'embed_content',
    'content': content,
    'user_id': user_id
})
```

## Performance Considerations

### Vector Search Optimization
- Use appropriate vector dimensions (typically 768 or 1536)
- Implement index strategies for large datasets
- Batch embedding operations
- Use connection pooling for database access

### Memory Management
- Implement proper cleanup for large content processing
- Use streaming for large file uploads
- Cache frequently accessed embeddings
- Monitor memory usage in workers

### Scaling Patterns
- Horizontal scaling with KEDA
- Separate read/write database connections
- Async processing for all I/O operations
- Queue-based job distribution

## Dependencies

- **psycopg2-binary**: PostgreSQL driver
- **pymysql**: MySQL/TiDB driver
- **asyncpg**: Async PostgreSQL support
- **numpy**: Vector operations
- **openai**: LLM integration
- **nats-py**: Message queue client
- **p8fs-cluster**: Configuration and logging

## Development Workflow

1. Start development services:
   ```bash
   docker-compose up postgres -d
   ```

2. Run migrations:
   ```bash
   ./scripts/test_setup.sh
   ```

3. Run tests:
   ```bash
   ./run_tests.sh
   ```

4. Start development server:
   ```bash
   python -m p8fs.cli
   ```

## Task Scheduler

The P8FS Core module includes a modular task scheduler for automated job execution. The scheduler discovers tasks marked with the `@scheduled` decorator and executes them via NATS workers or direct execution.

### Architecture

The scheduler is built with separated concerns:

- **Decorator** (`scheduler/decorator.py`): `@scheduled` decorator for marking functions
- **Discovery** (`scheduler/discovery.py`): Task discovery from configured packages  
- **Executor** (`scheduler/executor.py`): Task execution via NATS or direct calls
- **Scheduler** (`scheduler/scheduler.py`): Main coordinator using APScheduler

### Configuration

Scheduler settings are centralized in `p8fs_cluster.config.settings`:

```python
# Scheduler Configuration
scheduler_enabled: bool = True
scheduler_timezone: str = "UTC"
scheduler_discovery_package: str = "p8fs.workers.scheduler.tasks"
scheduler_force_inline: bool = False
scheduler_default_worker_type: str = "default_worker"
scheduler_default_memory: str = "256Mi"
```

### Creating Scheduled Tasks

Create scheduled tasks in `scheduler/tasks/` directory:

```python
# scheduler/tasks/maintenance.py
from p8fs.workers.scheduler import scheduled
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

@scheduled(
    hour="*/1",  # Every hour
    description="Hourly system status check",
    worker_type="status_worker",
    envs=["development", "production"]
)
async def hourly_status_check():
    """Run system status check every hour."""
    logger.info("Running hourly system status check")
    logger.info("All systems operational")

@scheduled(
    minute="*/15",  # Every 15 minutes  
    description="Memory cleanup task",
    worker_type="cleanup_worker",
    envs=["development"]
)
async def memory_cleanup():
    """Clean up memory caches every 15 minutes."""
    logger.info("Running memory cleanup task")
    logger.info("Memory cleanup completed")

@scheduled(
    day="*/1",  # Daily
    hour="3",   # At 3 AM
    minute="0",
    description="Daily maintenance and optimization",
    worker_type="maintenance_worker", 
    memory="512Mi",
    envs=["production"]
)
async def daily_maintenance():
    """Run daily maintenance tasks."""
    logger.info("Running daily maintenance tasks")
    logger.info("Daily maintenance completed")
```

### Scheduler Decorator Parameters

- **minute/hour/day**: Cron expressions (e.g., `"*/15"`, `"0"`, `"*/1"`)
- **envs**: List of environments where task should run (default: `["development", "production"]`)
- **worker_type**: NATS worker type to handle the task (default: from config)
- **memory**: Memory requirement for the worker (default: from config)  
- **description**: Human-readable task description

### Running the Scheduler

#### List Discovered Tasks

```bash
# List all discovered scheduled tasks
uv run python -m p8fs.cli scheduler --list-tasks

# Output:
# Discovered 2 scheduled tasks:
#   📋 hourly_status_check (p8fs.workers.scheduler.tasks.example)
#       Description: Hourly system status check
#       Schedule: minute=None, hour=*/1, day=None
#       Worker: status_worker (256Mi)
#       Environments: development, production
```

#### Run Scheduler

```bash
# Run scheduler with default settings
uv run python -m p8fs.cli scheduler

# Run with custom tenant ID
uv run python -m p8fs.cli scheduler --tenant-id=system
```

#### Container Deployment

```bash
# Run scheduler in container
docker run -d \
  -e P8FS_SCHEDULER_ENABLED=true \
  -e P8FS_ENVIRONMENT=production \
  -e P8FS_NATS_URL=nats://nats-server:4222 \
  p8fs \
  python -m p8fs.cli scheduler --tenant-id=system
```

### Execution Modes

The scheduler supports multiple execution modes:

1. **NATS Execution** (preferred): Sends jobs to NATS worker queues
2. **Direct Execution** (fallback): Executes tasks directly when NATS unavailable
3. **Forced Inline** (development): Set `P8FS_SCHEDULER_FORCE_INLINE=true`

### Environment-Based Task Filtering

Tasks are filtered based on the current environment (`P8FS_ENVIRONMENT`):

```python
@scheduled(
    hour="*/6",
    envs=["production"]  # Only runs in production
)
async def production_only_task():
    pass

@scheduled(
    minute="*/1", 
    envs=["development", "staging"]  # Runs in dev and staging
)
async def dev_task():
    pass
```

### Integration with NATS Workers

When NATS is available, the scheduler sends messages to worker queues:

```json
{
  "tenant_id": "system",
  "task_name": "hourly_status_check",
  "module": "p8fs.workers.scheduler.tasks.example",
  "function_name": "hourly_status_check",
  "worker_type": "status_worker",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

Workers can subscribe to subjects like `jobs.status_worker` to process scheduled tasks.