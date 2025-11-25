# P8FS Core Utils - Type Mapping Reference

This document provides comprehensive mapping rules between Pydantic field types and SQL types across different database providers. These mappings are critical for testing type conversion accuracy and ensuring consistent schema generation.

## Basic Type Mappings

| Pydantic Type | PostgreSQL | MySQL/TiDB | Notes |
|---------------|------------|-------------|-------|
| `str` | `TEXT` | `TEXT` | Default unlimited text |
| `str` (with `max_length=n`) | `VARCHAR(n)` | `VARCHAR(n)` | Length-constrained string |
| `int` | `BIGINT` | `BIGINT` | 64-bit signed integer |
| `float` | `DOUBLE PRECISION` | `DOUBLE` | Double precision float |
| `bool` | `BOOLEAN` | `BOOLEAN` | Boolean true/false |
| `datetime` | `TIMESTAMP` | `TIMESTAMP` | Timestamp with timezone |
| `date` | `DATE` | `DATE` | Date only |
| `time` | `TIME` | `TIME` | Time only |
| `Decimal` | `NUMERIC(p,s)` | `DECIMAL(p,s)` | Exact decimal precision |
| `bytes` | `BYTEA` | `BLOB` | Binary data |

## UUID Type Handling

| Pydantic Type | PostgreSQL | MySQL/TiDB | Testing Considerations |
|---------------|------------|-------------|------------------------|
| `UUID` | `UUID` | `CHAR(36)` | PostgreSQL has native UUID type |
| `UUID` (as string) | `CHAR(36)` | `CHAR(36)` | When stored as string format |

**Testing Notes:**
- Test UUID string format consistency: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- Verify round-trip conversion: Python UUID ” SQL storage ” Python UUID
- Test NULL handling for Optional[UUID]

## Collection Type Mappings

### List Types

| Pydantic Type | PostgreSQL | MySQL/TiDB | Usage |
|---------------|------------|-------------|-------|
| `List[str]` | `TEXT[]` | `JSON` | String arrays |
| `List[int]` | `INTEGER[]` | `JSON` | Integer arrays |
| `List[float]` | `DOUBLE PRECISION[]` | `JSON` | Numeric arrays |
| `List[float]` (embeddings) | `vector(n)` | `JSON` | Vector embeddings with pgvector |
| `List[Dict[str, Any]]` | `JSONB` | `JSON` | Complex nested structures |
| `List[UUID]` | `UUID[]` | `JSON` | UUID arrays |

**Testing Notes:**
- PostgreSQL: Test native array operations vs JSONB storage
- MySQL/TiDB: Ensure JSON array format consistency
- Vector embeddings: Test with pgvector operations vs TiDB VEC_* functions
- Empty list handling: `[]` should serialize consistently

### Dictionary Types

| Pydantic Type | PostgreSQL | MySQL/TiDB | Usage |
|---------------|------------|-------------|-------|
| `Dict[str, str]` | `JSONB` | `JSON` | String-to-string mapping |
| `Dict[str, Any]` | `JSONB` | `JSON` | Generic key-value store |
| `Dict[str, int]` | `JSONB` | `JSON` | String-to-integer mapping |
| `Dict[str, List[str]]` | `JSONB` | `JSON` | Nested collections |

**Testing Notes:**
- PostgreSQL JSONB vs JSON: Test query performance and operators
- Key ordering: JSONB may reorder keys, JSON preserves order
- Nested dictionary depth limits
- NULL value handling in dictionaries

## Optional and Union Type Rules

### Optional Types

| Pydantic Type | SQL Constraint | PostgreSQL | MySQL/TiDB |
|---------------|----------------|------------|-------------|
| `Optional[str]` | `NULL` allowed | `TEXT` | `TEXT` |
| `Optional[int]` | `NULL` allowed | `BIGINT` | `BIGINT` |
| `Optional[List[str]]` | `NULL` allowed | `TEXT[]` | `JSON` |
| `Optional[Dict[str, Any]]` | `NULL` allowed | `JSONB` | `JSON` |

**Testing Notes:**
- Verify NULL vs empty value handling: `None` vs `""` vs `[]` vs `{}`
- Test database NULL constraints are properly set/unset
- Optional field serialization consistency

### Union Types

| Pydantic Type | Resolution Rule | PostgreSQL | MySQL/TiDB | Testing Strategy |
|---------------|-----------------|------------|-------------|------------------|
| `Union[str, int]` | First type wins | `TEXT` | `TEXT` | Test with string and int inputs |
| `Union[str, None]` | Same as Optional | `TEXT` | `TEXT` | Test NULL handling |
| `Union[List[str], Dict[str, Any]]` | First type wins | `TEXT[]` | `JSON` | Test with both input types |
| `Union[str, int, float]` | First type wins | `TEXT` | `TEXT` | Test type coercion |

**Testing Notes:**
- Test data loss scenarios when non-primary types are used
- Validate serialization/deserialization round-trips
- Test union type discrimination in complex nested structures

## Enum Type Handling

| Pydantic Type | PostgreSQL | MySQL/TiDB | Implementation |
|---------------|------------|-------------|----------------|
| `Enum` (string-based) | `VARCHAR(max_length) CHECK (value IN (...))` | `ENUM(...)` or `VARCHAR(max_length)` | Native enum support varies |
| `IntEnum` | `INTEGER CHECK (value IN (...))` | `INTEGER` | Integer-based enums |

**Testing Notes:**
- Test all enum values can be stored and retrieved
- Test invalid enum value rejection
- Test enum value case sensitivity
- Test enum serialization to/from JSON

## Field Metadata and Constraints

### Length Constraints

```python
# Pydantic field definition
name: str = Field(..., max_length=100, description="User name")
```

| Constraint | PostgreSQL | MySQL/TiDB | Testing |
|------------|------------|-------------|---------|
| `max_length=100` | `VARCHAR(100)` | `VARCHAR(100)` | Test boundary values: 99, 100, 101 chars |
| `max_length=65535` | `TEXT` | `TEXT` | Test large text handling |
| No max_length | `TEXT` | `TEXT` | Test unlimited text |

### Other Constraints

| Pydantic Constraint | SQL Effect | Testing Approach |
|---------------------|------------|------------------|
| `unique=True` | `UNIQUE` constraint | Test duplicate insertion failures |
| `index=True` | Database index | Verify index creation in schema |
| `nullable=False` | `NOT NULL` constraint | Test NULL insertion failures |
| `ge=0` (greater equal) | `CHECK (field >= 0)` | Test boundary value validation |

## Complex Type Testing Scenarios

### Nested Complex Types

```python
# Complex nested structure for testing
class ComplexModel(AbstractModel):
    metadata: Dict[str, Union[str, int, List[str]]] = Field(
        default_factory=dict,
        description="Complex nested metadata"
    )
    
    tags: Optional[List[Union[str, int]]] = Field(
        None,
        description="Mixed type tags"
    )
    
    embeddings: Optional[List[float]] = Field(
        None, 
        embedding=True,
        description="Vector embeddings"
    )
```

**Testing Requirements:**

| Test Case | PostgreSQL Expected | MySQL/TiDB Expected |
|-----------|-------------------|-------------------|
| `metadata` storage | `JSONB` | `JSON` |
| `tags` with mixed types | `JSONB` | `JSON` |
| `embeddings` vector storage | `vector(n)` or `JSONB` | `JSON` |
| NULL handling | All fields nullable | All fields nullable |

### Forward References and Recursive Types

```python
# Self-referencing model for testing
class TreeNode(AbstractModel):
    name: str
    children: Optional[List['TreeNode']] = None
    parent: Optional['TreeNode'] = None
```

**Testing Considerations:**
- Forward reference resolution
- Circular reference handling
- JSON serialization depth limits
- Foreign key vs JSON storage decisions

## Provider-Specific Testing Requirements

### PostgreSQL-Specific Tests

**JSONB Operators:**
```python
# Test JSONB query capabilities
WHERE metadata @> '{"status": "active"}'  # Contains
WHERE metadata ? 'key'                    # Key exists
WHERE metadata #> '{nested,key}'         # Path extraction
```

**Array Operations:**
```python
# Test array query capabilities  
WHERE tags && ARRAY['important', 'urgent']  # Array overlap
WHERE 'important' = ANY(tags)               # Array membership
```

**Vector Operations (pgvector):**
```python
# Test vector similarity queries
WHERE embedding <-> query_vector < 0.3     # L2 distance
WHERE embedding <=> query_vector < 0.3     # Cosine distance
```

### MySQL/TiDB-Specific Tests

**JSON Functions:**
```python
# Test JSON query capabilities
WHERE JSON_EXTRACT(metadata, '$.status') = 'active'
WHERE JSON_CONTAINS(metadata, '{"key": "value"}')
WHERE JSON_VALID(metadata)
```

**Vector Functions (TiDB):**
```python
# Test TiDB vector operations
WHERE VEC_COSINE_DISTANCE(embedding, query_vector) < 0.3
WHERE VEC_L2_DISTANCE(embedding, query_vector) < 0.5
```

## Error Scenarios to Test

### Type Conversion Failures

| Scenario | Expected Behavior |
|----------|------------------|
| Invalid UUID string | Validation error, not silent truncation |
| Malformed JSON in Dict fields | Parse error with helpful message |
| Integer overflow | Error or documented truncation behavior |
| Invalid enum value | Validation error with valid options |
| Circular reference in recursive types | Detection and graceful handling |

### Database Constraint Violations

| Scenario | Expected SQL Error |
|----------|------------------|
| Violate max_length constraint | `VALUE TOO LONG` |
| Violate unique constraint | `DUPLICATE KEY VALUE` |
| Violate NOT NULL constraint | `NULL VALUE NOT ALLOWED` |
| Invalid CHECK constraint | `CHECK CONSTRAINT VIOLATED` |

## Performance Testing Considerations

### Large Data Scenarios

| Test Case | Metrics to Measure |
|-----------|-------------------|
| Very long text fields (1MB+) | Storage size, query performance |
| Large JSON objects (10,000+ keys) | Parse time, index effectiveness |
| High-dimensional vectors (1536+ dims) | Storage efficiency, similarity search speed |
| Deep nested structures (10+ levels) | Serialization time, query complexity |

### Bulk Operations

| Operation | PostgreSQL Focus | MySQL/TiDB Focus |
|-----------|------------------|-------------------|
| Bulk INSERT | COPY performance | Batch INSERT optimization |
| Bulk UPDATE | Index maintenance | Transaction throughput |
| JSON field updates | JSONB modification costs | JSON function performance |
| Vector similarity searches | pgvector index types | TiFlash analytics performance |

This comprehensive type mapping reference should guide all testing efforts to ensure consistent, reliable type conversion across database providers while maintaining data integrity and performance.