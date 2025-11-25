# P8FS Core Utilities

The P8FS Core utilities provide a comprehensive framework for type inspection, SQL mapping, and function tool generation. These utilities enable seamless integration between Pydantic models, multiple SQL providers, and LLM tool calling interfaces.

## Architecture Overview

The utilities are organized into focused modules:

- **Models**: AbstractModel base classes with self-describing capabilities
- **Repository**: Multi-tenant, multi-storage repository pattern
- **Utils**: Type inspection, function analysis, and SQL generation
- **Providers**: Database-specific SQL dialect implementations

## Core Components

### AbstractModel System

The AbstractModel provides a declarative foundation for all P8FS data models:

```python
from p8fs.models import AbstractModel

class Document(AbstractModel):
    title: str
    content: str
    embedding: Optional[List[float]] = None
    
    class Config:
        key_field = "title"
        embedding_fields = ["content"]
        table_name = "documents"
```

**Key Features:**
- Automatic schema generation for SQL tables
- Self-describing models with metadata extraction
- Namespace resolution from module structure
- Embedding field mapping and vector storage

### Repository Pattern

Multi-tenant repositories with hybrid storage (TiKV + TiDB):

```python
from p8fs.repository import TenantRepository

class DocumentRepository(TenantRepository[Document]):
    def __init__(self, tenant_id: str):
        super().__init__(Document, tenant_id)
    
    # Inherits all CRUD operations with tenant isolation
```

**Supported Operations:**
- Key-value operations (TiKV): `get`, `put`, `delete`, `scan`  
- SQL operations (TiDB): `select`, `upsert`, `execute`
- Vector search: `semantic_search`, `similarity_search`
- Batch operations: `bulk_upsert`, `bulk_delete`

### Function Tool Generation

Convert Python functions to LLM-compatible tools:

```python
from p8fs.utils.functions import FunctionInspector

def search_documents(query: str, limit: int = 10) -> List[Document]:
    """Search documents by semantic similarity."""
    pass

# Generate tool schema
inspector = FunctionInspector()
tool_spec = inspector.generate_tool_spec(search_documents)

# Supports OpenAI, Anthropic, and custom tool formats
```

### SQL Provider System

Database-agnostic SQL generation with dialect-specific optimizations:

```python
from p8fs.providers import TiDBProvider, PostgreSQLProvider

# TiDB with vector search capabilities
tidb_provider = TiDBProvider()
create_sql = tidb_provider.create_table_sql(Document)
vector_sql = tidb_provider.vector_search_sql(Document, query_vector)

# PostgreSQL with pgvector extensions  
postgres_provider = PostgreSQLProvider()
create_sql = postgres_provider.create_table_sql(Document)
```

## Type Mapping Conventions

### Pydantic to SQL Mapping

| Pydantic Type | TiDB Type | PostgreSQL Type | Notes |
|---------------|-----------|-----------------|-------|
| `str` | `TEXT` | `TEXT` | Configurable max length |
| `int` | `BIGINT` | `BIGINT` | |
| `float` | `DOUBLE` | `DOUBLE PRECISION` | |
| `bool` | `BOOLEAN` | `BOOLEAN` | |
| `datetime` | `TIMESTAMP` | `TIMESTAMP` | |
| `UUID` | `CHAR(36)` | `UUID` | String format in TiDB |
| `List[float]` | `JSON` | `vector` | Embeddings |
| `Dict` | `JSON` | `JSONB` | |
| `Union[A, B]` | Based on primary type | Based on primary type | Uses first non-None type |

### Field Metadata Configuration

```python
class Document(AbstractModel):
    title: str = Field(..., max_length=500, description="Document title")
    content: str = Field(..., embedding=True, description="Main content")
    metadata: Dict[str, Any] = Field(default_factory=dict, json_column=True)
    
    class Config:
        key_field = "title"           # Used for ID generation
        embedding_fields = ["content"] # Auto-embed these fields
        table_name = "documents"      # Custom table name
        tenant_isolated = True        # Enable tenant isolation
```

## Function Inspection Features

### Type Analysis

```python
from p8fs.utils.typing import TypeInspector

inspector = TypeInspector()

# Extract all types from complex signatures
def process_data(items: List[Dict[str, Union[str, int]]]) -> Optional[Document]:
    pass

type_info = inspector.analyze_function(process_data)
# Returns: parameter types, return type, nested types
```

### Multi-Dialect Tool Generation

Support for different LLM tool formats:

```python
from p8fs.utils.functions import ToolGenerator

generator = ToolGenerator()

# OpenAI format
openai_spec = generator.to_openai_tool(search_documents)

# Anthropic format  
anthropic_spec = generator.to_anthropic_tool(search_documents)

# Custom format
custom_spec = generator.to_custom_tool(search_documents, format="custom")
```

## Repository Operations

### Basic CRUD

```python
repo = DocumentRepository("tenant-123")

# Create/Update
document = Document(title="Test", content="Hello world")
await repo.upsert(document)

# Read
doc = await repo.get("Test")
docs = await repo.select(limit=10)

# Delete
await repo.delete("Test")
```

### Advanced Queries

```python
# Semantic search
results = await repo.semantic_search("machine learning", limit=5)

# SQL queries with parameters
results = await repo.execute(
    "SELECT * FROM documents WHERE created_at > %s",
    (datetime.now() - timedelta(days=7),)
)

# Batch operations
documents = [Document(...) for _ in range(100)]
await repo.bulk_upsert(documents)
```

### Tenant Isolation

All operations are automatically tenant-scoped:

```python
# Tenant A
repo_a = DocumentRepository("tenant-a")
await repo_a.upsert(Document(title="doc1", content="Content A"))

# Tenant B (cannot see tenant A's data)
repo_b = DocumentRepository("tenant-b") 
docs = await repo_b.select()  # Returns only tenant B documents
```

## Testing Strategy

Comprehensive test coverage focusing on:

- **Type mapping edge cases**: Union types, nested generics, optional fields
- **SQL generation validation**: Syntax correctness across providers
- **Function inspection accuracy**: Complex signatures, decorators, async functions
- **Repository operations**: Multi-tenant isolation, concurrent access
- **Provider compatibility**: TiDB, PostgreSQL dialect differences

## Design Principles

1. **Type Safety**: Full typing support with runtime validation
2. **Provider Agnostic**: Work with multiple SQL databases seamlessly  
3. **Tenant Isolation**: Built-in multi-tenancy at the data layer
4. **Schema Evolution**: Support for model versioning and migrations
5. **Performance**: Optimized for high-throughput, low-latency operations
6. **Simplicity**: Clean APIs without unnecessary complexity or workarounds
