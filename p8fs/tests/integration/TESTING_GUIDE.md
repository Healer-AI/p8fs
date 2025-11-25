# P8FS Integration Testing Guide

## Overview

This guide explains how to run the P8FS integration tests in the correct order to validate the dreaming workflow components.

## Test Sequence

The tests are designed to be run in order, with each test building on the previous ones:

### Test 1: Database Operations (No LLM)
**File**: `test_01_database_operations.py`

Tests basic database CRUD without any LLM calls:
- Save resources with metadata
- Save sessions
- Generate embeddings
- Verify data integrity
- Query resources by various filters

```bash
P8FS_STORAGE_PROVIDER=postgresql \
uv run pytest tests/integration/test_01_database_operations.py -v -s
```

**What to verify**:
- All 5 tests pass
- 3 resources saved
- 3 embeddings generated
- 2 sessions saved
- Resource-embedding joins work

---

### Test 2: Resource Affinity (No LLM)
**File**: `test_02_resource_affinity.py`

Tests semantic search and graph edge creation using existing embeddings:
- REM query provider semantic search
- Find similar resource pairs
- Create SEE_ALSO graph edges
- Query and traverse graph relationships

```bash
P8FS_STORAGE_PROVIDER=postgresql \
uv run pytest tests/integration/test_02_resource_affinity.py -v -s
```

**What to verify**:
- Semantic search returns results with similarity scores
- Similar resource pairs found (similarity > 0.5)
- Graph edges created successfully
- Bidirectional queries work

---

### Test 3: Entity Extraction (LLM Required)
**File**: `test_03_entity_extraction.py`

Tests LLM-based entity extraction:
- Extract people, organizations, projects, concepts
- Normalize entity IDs
- Save entities to resources
- Verify entity quality and structure

```bash
P8FS_STORAGE_PROVIDER=postgresql \
OPENAI_MODEL=gpt-4o-mini \
uv run pytest tests/integration/test_03_entity_extraction.py -v -s
```

**What to verify**:
- Entities extracted from content
- Multiple entity types (Person, Organization, Project, Concept)
- Entity IDs properly normalized (lowercase-hyphenated)
- Entities saved to resources.related_entities field

---

### Test 4: Moment Generation (LLM Required)
**File**: `test_04_moment_generation.py` *(To be created)*

Tests LLM-based moment extraction:
- Extract moments from voice memos
- Classify moment types
- Tag emotions and topics
- Set temporal boundaries

---

### Test 5: REM Queries
**File**: `test_05_rem_queries.py` *(To be created)*

Tests REM query provider:
- LOOKUP queries (key-based)
- SEARCH queries (semantic)
- SQL queries (structured)
- TRAVERSE queries (graph)

---

### Test 6: End-to-End Integration
**File**: `test_06_integration.py` *(To be created)*

Tests complete workflow:
- Load sample data
- First-order dreaming (moments + entities)
- Second-order dreaming (resource edges)
- Query knowledge graph

---

## Prerequisites

### 1. PostgreSQL with Extensions

```bash
cd /Users/sirsh/code/p8fs-modules/p8fs
docker compose up postgres -d

# Verify PostgreSQL is running
docker ps | grep percolate

# Verify pgvector extension
docker exec percolate psql -U postgres -d app -c \
  "SELECT * FROM pg_extension WHERE extname = 'vector';"

# Verify Apache AGE extension (for graph operations)
docker exec percolate psql -U postgres -d app -c \
  "SELECT * FROM pg_extension WHERE extname = 'age';"
```

### 2. Environment Variables

```bash
# Required for all tests
export P8FS_STORAGE_PROVIDER=postgresql

# Required for LLM tests (tests 3+)
export OPENAI_API_KEY=sk-your-key-here
export OPENAI_MODEL=gpt-4o-mini  # Or gpt-4o for better quality
```

### 3. Python Environment

```bash
cd /Users/sirsh/code/p8fs-modules/p8fs
uv sync
```

## Running Tests

### Run All Tests in Sequence

```bash
# Set environment
export P8FS_STORAGE_PROVIDER=postgresql
export OPENAI_API_KEY=sk-your-key-here
export OPENAI_MODEL=gpt-4o-mini

# Run tests in order
uv run pytest tests/integration/test_01_database_operations.py -v -s
uv run pytest tests/integration/test_02_resource_affinity.py -v -s
uv run pytest tests/integration/test_03_entity_extraction.py -v -s
```

### Run Individual Test

```bash
# Database operations only (no LLM needed)
P8FS_STORAGE_PROVIDER=postgresql \
uv run pytest tests/integration/test_01_database_operations.py -v -s

# Entity extraction (LLM required)
P8FS_STORAGE_PROVIDER=postgresql \
OPENAI_MODEL=gpt-4o-mini \
uv run pytest tests/integration/test_03_entity_extraction.py::TestEntityExtraction::test_01_extract_entities -v -s
```

### Run Specific Test Method

```bash
P8FS_STORAGE_PROVIDER=postgresql \
uv run pytest tests/integration/test_02_resource_affinity.py::TestResourceAffinity::test_01_semantic_search -v -s
```

## Test Output

### Successful Test Output

```
================================ test session starts =================================
tests/integration/test_01_database_operations.py::TestDatabaseOperations::test_01_save_resources

======================================================================
TEST: Save Resources
======================================================================
✓ Saved: Project Alpha Specification (abc-123...)
✓ Saved: Team Meeting Notes (def-456...)
✓ Saved: Architecture Overview (ghi-789...)

Saved 3 resources
PASSED

tests/integration/test_01_database_operations.py::TestDatabaseOperations::test_02_query_resources
Found 3 total resources
Found 1 technical resources
Found 2 resources after Jan 6
✓ All query tests passed
PASSED

... (more tests)

======================================================================
DATABASE OPERATIONS TEST COMPLETE ✓
======================================================================

============================== 5 passed in 3.45s =================================
```

### Failed Test

If a test fails, you'll see:
```
FAILED tests/integration/test_01_database_operations.py::TestDatabaseOperations::test_03_generate_embeddings
AssertionError: Should have 3 embeddings
```

Check:
1. Database connection working?
2. Embeddings table exists?
3. OpenAI API key valid (for LLM tests)?

## Debugging

### Check Database State

```bash
# Connect to PostgreSQL
docker exec -it percolate psql -U postgres -d app

# List resources
SELECT id, name, category FROM resources WHERE tenant_id LIKE 'tenant-test%';

# List embeddings
SELECT entity_id, vector_dimension FROM embeddings.resources_embeddings
WHERE tenant_id LIKE 'tenant-test%';

# List graph edges (if Apache AGE installed)
SELECT * FROM p8.cypher_query(
    'MATCH (a)-[r:SEE_ALSO]->(b) RETURN a.uid, type(r), b.uid LIMIT 10',
    'from_uid text, rel_type text, to_uid text',
    'p8graph'
);
```

### Clean Up Test Data

```bash
# Remove all test data
docker exec percolate psql -U postgres -d app -c \
  "DELETE FROM resources WHERE tenant_id LIKE 'tenant-test%';"

docker exec percolate psql -U postgres -d app -c \
  "DELETE FROM sessions WHERE tenant_id LIKE 'tenant-test%';"

# Or restart database
docker compose down
docker compose up postgres -d
```

### View Logs

```bash
# PostgreSQL logs
docker compose logs postgres | tail -50

# Test output with more detail
uv run pytest tests/integration/test_01_database_operations.py -vvs --log-cli-level=DEBUG
```

## Common Issues

### Issue: OpenAI API Errors

```
Error: Authentication failed
```

**Solution**:
```bash
# Verify API key
echo $OPENAI_API_KEY

# Test API access
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Issue: Database Connection Refused

```
Error: Connection refused (localhost:5432)
```

**Solution**:
PostgreSQL runs on port 5438 in docker-compose:
```bash
# Check container is running
docker ps | grep percolate

# Restart if needed
docker compose restart postgres
```

### Issue: Apache AGE Not Found

```
Error: function p8.cypher_query does not exist
```

**Solution**:
Apache AGE may not be installed. Graph tests will be skipped or fail. Install AGE extension:
```bash
# Check extensions
docker exec percolate psql -U postgres -d app -c "SELECT * FROM pg_extension;"

# If AGE missing, see: p8fs/extensions/migrations/postgres/install.sql
```

### Issue: Import Errors

```
ModuleNotFoundError: No module named 'p8fs'
```

**Solution**:
```bash
# Reinstall dependencies
cd /Users/sirsh/code/p8fs-modules/p8fs
uv sync

# Run test with uv run
uv run pytest tests/integration/test_01_database_operations.py -v
```

## Test Isolation

Each test uses a unique tenant ID to avoid conflicts:
- `test_01`: `tenant-test-db`
- `test_02`: `tenant-test-affinity`
- `test_03`: `tenant-test-entities`

Tests clean up their data in fixtures, but manual cleanup may be needed if tests are interrupted.

## Next Steps

After all tests pass:

1. **Review test output** to understand component behavior
2. **Examine database** to see how data is structured
3. **Run end-to-end test** once created
4. **Deploy to cluster** for production testing
5. **Set up cron jobs** for periodic dreaming processing

## Support

- Check test files for inline documentation
- Review planning docs in `p8fs/docs/`
- Examine sample data in `tests/integration/sample_data/dreaming/`
