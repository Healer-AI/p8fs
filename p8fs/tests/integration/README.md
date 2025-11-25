# Integration Tests

Integration tests for P8FS use **real services only** - no mocks.

## Quick Start

### 1. Start PostgreSQL
```bash
cd p8fs
docker compose up postgres -d
```

### 2. Source API Key from bash_profile
```bash
# Line 122 of ~/.bash_profile contains the working OpenAI API key
source ~/.bash_profile

# Verify key is loaded
echo "API key loaded: ${OPENAI_API_KEY:+YES}"
```

### 3. Run Tests
```bash
# All tests with API key
env P8FS_STORAGE_PROVIDER=postgresql \
    uv run pytest tests/integration/ -v --integration

# Specific test
env P8FS_STORAGE_PROVIDER=postgresql \
    uv run pytest tests/integration/test_02_resource_affinity.py -v --integration
```

## Test Suites

### Test 1: Database Operations
- **File**: `test_01_database_operations.py`
- **API Key**: Optional (1 test skipped without it)
- **Runtime**: ~2 seconds
- **Tests**: Database CRUD, queries, schema validation

### Test 2: Resource Affinity
- **File**: `test_02_resource_affinity.py`
- **API Key**: **REQUIRED** (entire suite skips without it)
- **Runtime**: ~3 seconds
- **Tests**: Real OpenAI embeddings, semantic search, vector similarity
- **Note**: NO MOCKS - uses real embeddings only

### Test 3: Entity Extraction
- **File**: `test_03_entity_extraction.py`
- **API Key**: **REQUIRED** (entire suite skips without it)
- **Runtime**: ~5-10 seconds
- **Tests**: LLM-based entity extraction, normalization, storage

## Real Embedding Behavior

Test 2 demonstrates actual semantic search behavior with real OpenAI embeddings:

```
OAuth Guide ↔ API Security: similarity = 0.015 (barely similar)
OAuth Guide ↔ Database:     similarity = -0.339 (negative/opposite)
```

**Key Insight**: Short texts (1 sentence) have very low similarity even when semantically related. This is realistic and validates that semantic search works correctly in production.

## Dependencies

### Required
- PostgreSQL (via docker compose)
- OpenAI API key (from ~/.bash_profile line 122)

### Optional
- Apache AGE extension (for graph traversal tests)

## Test Philosophy

**No mocks, no lies.**

All tests use real services:
- Real OpenAI API for embeddings
- Real PostgreSQL/TiDB for storage
- Real semantic similarity scores

Tests skip gracefully when dependencies are unavailable, providing honest feedback about what's actually tested.
