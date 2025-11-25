# Pydantic to SQL Type Mappings

This document defines the comprehensive mapping rules between Pydantic field types and various SQL database types. These mappings are essential for generating accurate DDL statements and ensuring proper data serialization/deserialization.

## Core Type Mappings

| Pydantic Type | TiDB/MySQL Type | PostgreSQL Type | PyArrow Type | Notes |
|---------------|-----------------|-----------------|--------------|-------|
| `str` | `TEXT` | `TEXT` | `string` | Default text storage |
| `str` (with max_length ≤ 255) | `VARCHAR(n)` | `VARCHAR(n)` | `string` | Length-constrained strings |
| `str` (with max_length > 255) | `TEXT` | `TEXT` | `string` | Large text fields |
| `int` | `BIGINT` | `BIGINT` | `int64` | 64-bit integers |
| `float` | `DOUBLE` | `DOUBLE PRECISION` | `float64` | Double precision floats |
| `bool` | `BOOLEAN` | `BOOLEAN` | `bool` | Boolean values |
| `datetime` | `TIMESTAMP` | `TIMESTAMP` | `timestamp[ns]` | Timestamp with timezone |
| `date` | `DATE` | `DATE` | `date32` | Date only |
| `time` | `TIME` | `TIME` | `time64[ns]` | Time only |
| `UUID` | `CHAR(36)` | `UUID` | `string` | UUID storage |
| `Decimal` | `DECIMAL(p,s)` | `NUMERIC(p,s)` | `decimal128` | Precise decimal numbers |
| `bytes` | `BLOB` | `BYTEA` | `binary` | Binary data |

## Collection Type Mappings

| Pydantic Type | TiDB/MySQL Type | PostgreSQL Type | PyArrow Type | Notes |
|---------------|-----------------|-----------------|--------------|-------|
| `List[T]` | `JSON` | `JSONB` | `list[T]` | Generic lists as JSON |
| `List[float]` (embeddings) | `JSON` | `vector` | `list[float64]` | Vector embeddings |
| `List[str]` | `JSON` | `TEXT[]` | `list[string]` | String arrays |
| `Dict[str, Any]` | `JSON` | `JSONB` | `struct` | Generic dictionaries |
| `Dict[str, str]` | `JSON` | `JSONB` | `map[string, string]` | String-to-string maps |
| `Set[T]` | `JSON` | `JSONB` | `list[T]` | Sets stored as JSON arrays |
| `Tuple[T, ...]` | `JSON` | `JSONB` | `struct` | Tuples as structured data |

## Optional and Union Type Rules

| Pydantic Type | SQL Constraint | Conversion Rule | Notes |
|---------------|----------------|-----------------|-------|
| `Optional[T]` | `NULL` allowed | Use base type `T` mapping | Optional fields are nullable |
| `Union[T, None]` | `NULL` allowed | Use base type `T` mapping | Same as Optional[T] |
| `Union[T, U]` | `NOT NULL` | Use first type `T` mapping | Priority to first non-None type |
| `Union[T, U, None]` | `NULL` allowed | Use first type `T` mapping | Optional union uses first type |
| `Union[str, int]` | `TEXT` | Store as text | Mixed types default to text |
| `Union[int, float]` | `DOUBLE` | Use most general numeric type | Preserve precision |

## Special Field Metadata

| Field Attribute | SQL Effect | Example | Notes |
|------------------|------------|---------|-------|
| `max_length=n` | `VARCHAR(n)` | `name: str = Field(max_length=100)` | Enforces length constraint |
| `unique=True` | `UNIQUE` | `email: str = Field(unique=True)` | Unique constraint |
| `index=True` | `INDEX` | `user_id: str = Field(index=True)` | Database index |
| `primary_key=True` | `PRIMARY KEY` | `id: str = Field(primary_key=True)` | Primary key constraint |
| `embedding=True` | Vector table | `content: str = Field(embedding=True)` | Creates embedding table |
| `searchable=True` | FTS index | `title: str = Field(searchable=True)` | Full-text search index |
| `json_column=True` | Force JSON | `data: dict = Field(json_column=True)` | Explicit JSON storage |

## Complex Type Examples

### Embedding Fields
```python
class Document(AbstractModel):
    content: str = Field(embedding=True)  # Creates embedding table
    # → documents_embeddings table with vector storage
```

### Union Type Resolution
```python
class FlexibleModel(AbstractModel):
    value: Union[str, int]  # → TEXT (first type wins)
    optional_value: Optional[Union[str, int]]  # → TEXT NULL
    mixed_list: List[Union[str, int]]  # → JSON
```

### Nested Collections
```python
class ComplexModel(AbstractModel):
    tags: List[str]  # → JSON in TiDB, TEXT[] in PostgreSQL
    metadata: Dict[str, Any]  # → JSON/JSONB
    coordinates: List[float] = Field(embedding=True)  # → vector table
    nested: List[Dict[str, str]]  # → JSON/JSONB
```

## Vector Storage Strategy

### TiDB Vector Storage
- Embeddings stored as JSON arrays: `[0.1, 0.2, 0.3, ...]`
- Uses VEC_COSINE_DISTANCE(), VEC_L2_DISTANCE() functions
- Requires TiFlash replica for performance
- Separate embedding table pattern

### PostgreSQL Vector Storage  
- Uses pgvector extension: `vector(1536)` type
- Native vector operators: `<->`, `<=>`, `<#>`
- HNSW and IVFFlat indexes supported
- Integrated with main table or separate embedding table

### PyArrow Vector Storage
- Native list[float64] arrays
- Optimized for analytical workloads
- Memory-efficient columnar storage
- Compatible with ML frameworks

## Special Cases and Edge Cases

### Enum Handling
```python
class Status(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class Model(AbstractModel):
    status: Status  # → VARCHAR(20) with CHECK constraint
```

### Generic Types
```python
class GenericModel(AbstractModel, Generic[T]):
    data: T  # → Resolved at model creation time
    items: List[T]  # → JSON with type validation
```

### Recursive Types
```python
class TreeNode(AbstractModel):
    children: List['TreeNode']  # → JSON with forward reference
    parent: Optional['TreeNode']  # → Foreign key or JSON
```

## Database-Specific Optimizations

### TiDB Optimizations
- Use CLUSTERED PRIMARY KEY for better performance
- Vector columns get TiFlash replicas automatically
- JSON functions optimized for analytical queries
- Placement rules for data locality

### PostgreSQL Optimizations
- JSONB preferred over JSON for query performance
- GIN indexes on JSONB columns
- Partial indexes for filtered queries
- Vector indexes (HNSW/IVFFlat) for embeddings

### PyArrow Optimizations
- Columnar storage reduces memory overhead
- Vectorized operations on arrays
- Zero-copy integration with Pandas/NumPy
- Efficient serialization with Arrow format

## Testing Requirements

Each type mapping must be tested for:

1. **Round-trip consistency**: Python → SQL → Python
2. **Null handling**: Optional types and None values  
3. **Constraint validation**: Length, uniqueness, foreign keys
4. **Performance**: Index usage and query optimization
5. **Edge cases**: Empty collections, special values
6. **Migration safety**: Type changes and schema evolution