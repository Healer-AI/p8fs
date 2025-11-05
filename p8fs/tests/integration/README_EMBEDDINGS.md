# Embeddings End-to-End Test

This integration test verifies the complete embedding pipeline from resource insertion through semantic search.

## What It Tests

The `test_embeddings_e2e.py` test performs the following critical verifications:

### 1. Resource Insertion
- Creates 5 sample resources with embedding-enabled fields (content, description)
- Verifies all resources are inserted with correct metadata
- Confirms tenant isolation is working

### 2. Embedding Table Structure
- Verifies `embeddings` schema is created
- Checks `resources_embeddings` table exists with correct columns
- Validates indexes for performance

### 3. Embedding Generation
- Confirms embedding infrastructure is ready
- Checks embedding table is queryable
- Validates vector dimensions are set

### 4. Semantic Search
- Tests SQL generation for vector similarity queries
- Validates JOIN between main and embedding tables
- Confirms tenant isolation in searches

## Sample Resources

The test uses 5 carefully crafted resources covering different technical topics:

1. **Machine Learning Guide** - AI/ML fundamentals
2. **Python Best Practices** - Programming patterns
3. **Distributed Systems Architecture** - System design
4. **Vector Databases Overview** - Embedding storage
5. **API Design Guidelines** - REST/GraphQL patterns

These resources are saved in `tests/sample_data/test_resources.json` for consistency.

## Running the Test

### Prerequisites

1. PostgreSQL with pgvector extension:
```bash
docker-compose -f docker-compose.test.yml up -d
```

2. Environment setup:
```bash
export SKIP_INTEGRATION_TESTS=false
export P8FS_PG_CONNECTION_STRING="postgresql://postgres:postgres@localhost:5432/p8fs_test"
```

### Run Test
```bash
# Run just the embedding test
pytest tests/integration/test_embeddings_e2e.py -v -s

# Or use the test runner
./run_tests.sh --integration
```

### Verify Results
```bash
# Check database state after test
python tests/integration/verify_embeddings.py
```

## Expected Output

### Success Case (with embedding service):
```
Step 1: Inserting 5 resources...
Step 2: Verifying resources in database...
Step 3: Checking embedding table structure...
✓ Embedding table has correct structure with 9 columns
Step 4: Checking for embeddings...
✓ Embedding table is queryable (found 10 embeddings)
✓ Embedding dimensions: [1536]
Step 5: Testing semantic search...
✓ Found 3 results for 'machine learning neural networks'
✅ All tests passed! Embedding pipeline is working correctly.
```

### Partial Success (without embedding service):
```
Step 1: Inserting 5 resources...
Step 2: Verifying resources in database...
Step 3: Checking embedding table structure...
✓ Embedding table has correct structure with 9 columns
Step 4: Checking for embeddings...
✓ Embedding table is queryable (found 0 embeddings)
Step 5: Testing semantic search...
⚠️ Semantic search not available (no embedding service)
✓ Semantic search SQL generation is correct
```

## Critical Failure Points

The test will **FAIL** if any of these conditions occur:

1. ❌ Resources fail to insert into database
2. ❌ Embedding schema/tables are not created
3. ❌ Embedding table structure is incorrect
4. ❌ Semantic search SQL generation is broken
5. ❌ Tenant isolation is not working

## Database Schema

After successful test, the database should have:

```sql
-- Main table
public.resources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    content TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    metadata JSONB,
    tenant_id TEXT NOT NULL,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
)

-- Embedding table
embeddings.resources_embeddings (
    id UUID PRIMARY KEY,
    entity_id TEXT NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    vector_dimension INTEGER,
    tenant_id TEXT NOT NULL,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    FOREIGN KEY (entity_id) REFERENCES resources(id)
)
```

## Troubleshooting

### pgvector not installed
```sql
-- Connect to database and run:
CREATE EXTENSION vector;
```

### Embedding table missing
Check model registration:
```python
success = repo.register_model(Resource, plan=False)
```

### No embeddings generated
- Check embedding service is configured
- Verify embedding fields are marked in model schema
- Check background workers if using async processing

### Semantic search fails
- Verify pgvector extension is loaded
- Check embedding dimensions match
- Confirm vector indexes are created