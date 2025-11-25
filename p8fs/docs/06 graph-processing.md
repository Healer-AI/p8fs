# P8FS Graph Processing and Integration Tests

## Overview

P8FS uses Apache AGE (A Graph Extension) for PostgreSQL to provide graph database capabilities alongside traditional relational storage. This document outlines the graph processing features and comprehensive integration tests.

## Graph Functions

### Core Graph Operations

1. **cypher_query** - Execute Cypher queries against the graph
2. **get_entities** - Retrieve entities by their business keys
3. **get_graph_nodes_by_key** - Get graph nodes by their keys
4. **get_records_by_keys** - Get table records by keys
5. **register_entities** - Register tables for graph indexing
6. **insert_entity_nodes** - Add table records as graph nodes
7. **add_node** - Add individual nodes to the graph
8. **add_nodes** - Batch add nodes from tables

### KV Storage Operations

1. **put_kv** - Store key-value pairs with optional TTL
2. **get_kv** - Retrieve values by key
3. **delete_kv** - Delete key-value pairs
4. **scan_kv** - Scan for keys with a prefix
5. **get_kv_stats** - Get KV storage statistics
6. **cleanup_expired_kv** - Clean up expired entries

### Graph Relationship Operations

1. **create_association** - Create edges between nodes
2. **get_relationships** - Query relationships
3. **delete_relationship** - Remove edges

## Integration Test Suite

### Test 1: Language Model API Entity Retrieval
**File**: `test_integration_language_model_entities.py`
**Purpose**: Test get_entities with language_model_apis table
```python
def test_get_language_model_entities():
    # Test retrieving LLMs by name
    - Query for 'gpt-5', 'claude-3', 'llama-3'
    - Verify correct entity structure returned
    - Test with non-existent models
    - Test with multiple models in one query
```

### Test 2: KV Storage for Device Authorization
**File**: `test_integration_kv_device_auth.py`
**Purpose**: Test complete device auth flow using KV storage
```python
def test_device_auth_flow():
    # Test device authorization workflow
    - Store device auth request with TTL
    - Store user code mapping
    - Retrieve by device code and user code
    - Update status to approved
    - Test TTL expiration
    - Clean up expired entries
```

### Test 3: Graph Node Operations
**File**: `test_integration_graph_nodes.py`
**Purpose**: Test direct graph node manipulation
```python
def test_graph_node_operations():
    # Test node CRUD operations
    - Add configuration nodes
    - Add feature flag nodes
    - Query nodes by key
    - Update node properties
    - Delete nodes
```

### Test 4: Graph Relationships
**File**: `test_integration_graph_relationships.py`
**Purpose**: Test graph edge operations
```python
def test_graph_relationships():
    # Test relationship management
    - Create associations between entities
    - Query relationships by type
    - Query incoming/outgoing edges
    - Delete relationships
    - Test relationship metadata
```

### Test 5: Entity Registration and Indexing
**File**: `test_integration_entity_indexing.py`
**Purpose**: Test entity registration workflow
```python
def test_entity_registration():
    # Test registering tables with graph
    - Register language_model_apis table
    - Insert entity nodes from table
    - Verify graph nodes created
    - Test view generation
    - Query through views
```

### Test 6: KV Scan and Stats
**File**: `test_integration_kv_scan_stats.py`
**Purpose**: Test KV prefix scanning and statistics
```python
def test_kv_scan_and_stats():
    # Test scanning and statistics
    - Create multiple KV entries with prefixes
    - Scan by prefix (device-auth:, user-code:)
    - Get KV statistics
    - Test cleanup of expired entries
```

### Test 7: Concurrent Graph Operations
**File**: `test_integration_concurrent_graph.py`
**Purpose**: Test thread safety and concurrent access
```python
def test_concurrent_operations():
    # Test concurrent access patterns
    - Multiple threads updating same KV
    - Concurrent node additions
    - Parallel relationship creation
    - Race condition handling
```

### Test 8: Direct SQL Function Tests
**File**: `test_integration_sql_functions.py`
**Purpose**: Test each SQL function directly
```python
def test_all_sql_functions():
    # Direct SQL function testing
    - p8.cypher_query with various queries
    - p8.get_entities with edge cases
    - p8.add_node with different labels
    - p8.put_kv/get_kv with complex JSON
    - p8.scan_kv with limits
    - p8.cleanup_expired_kv
```

### Test 9: Performance and Scale
**File**: `test_integration_graph_performance.py`
**Purpose**: Test performance with larger datasets
```python
def test_graph_performance():
    # Performance testing
    - Add 1000+ nodes
    - Create 5000+ relationships
    - Query performance with large graphs
    - KV storage with 10k+ entries
    - Bulk operations
```

### Test 10: Error Handling and Edge Cases
**File**: `test_integration_graph_errors.py`
**Purpose**: Test error conditions and edge cases
```python
def test_error_handling():
    # Error and edge case testing
    - Non-existent keys
    - Invalid Cypher syntax
    - Null/empty values
    - Special characters in keys
    - Transaction rollback
```

## Running Integration Tests

### Prerequisites
1. PostgreSQL with AGE extension installed
2. Database migrations applied
3. Graph functions loaded

### Setup
```bash
# Start PostgreSQL
docker compose up -d postgres

# Load base extensions and functions
PGPASSWORD=postgres psql -h localhost -p 5438 -U postgres -d app -f extensions/sql/00_install.sql
PGPASSWORD=postgres psql -h localhost -p 5438 -U postgres -d app -f extensions/sql/03_functions.sql

# Run all graph tests
python tests/integration/run_graph_tests.py

# Or run specific test categories
pytest tests/integration/test_kv_functionality.py -v  # KV storage tests
pytest tests/integration/test_integration_language_model_entities.py -v  # Entity retrieval
```

### Current Test Status

| Test File | Status | Tests Passing | Notes |
|-----------|--------|---------------|-------|
| test_kv_functionality.py | ✅ | 7/7 | All KV operations working |
| test_integration_language_model_entities.py | ✅ | 4/5 | Entity retrieval working |
| test_kv_round_trip_verification.py | ⚠️ | 5/7 | Special character handling issues |
| test_graph_kv_and_entities.py | ⚠️ | 2/4 | Some node operations need AGE setup |
| test_integration_graph_relationships.py | ⚠️ | 2/18 | Relationship operations need fixes |

### Test Data
Each test should:
- Create its own test data
- Clean up after completion
- Use unique keys to avoid conflicts
- Handle existing data gracefully

## Common Test Patterns

### Entity Retrieval Pattern
```python
# Register entity if needed
provider.execute("SELECT * FROM p8.register_entities('public.language_model_apis', 'name')")

# Insert nodes
provider.execute("SELECT * FROM p8.insert_entity_nodes('public.language_model_apis')")

# Query entities
results = provider.get_entities(['gpt-5', 'claude-3'])
assert 'public.language_model_apis' in results
```

### KV Storage Pattern
```python
# Store with TTL
kv.put('device-auth:123', {'status': 'pending'}, ttl_seconds=600)

# Retrieve
data = kv.get('device-auth:123')
assert data['status'] == 'pending'

# Scan prefix
devices = kv.scan('device-auth:', limit=100)
```

### Graph Relationship Pattern
```python
# Create association
association = GraphAssociation(
    from_entity_id='user-123',
    to_entity_id='doc-456',
    relationship_type='OWNS',
    metadata={'created_at': '2025-01-01'}
)
graph.create_association(association)

# Query relationships
rels = graph.get_relationships(from_entity_id='user-123')
```

## Troubleshooting

### Common Issues

1. **AGE not loaded**: Ensure `CREATE EXTENSION age` is run
2. **Graph not found**: Create with `SELECT create_graph('p8graph')`
3. **Functions missing**: Load with `psql -f extensions/sql/03_functions.sql`
4. **Search path issues**: Set `search_path = ag_catalog, "$user", public`

### Debug Queries
```sql
-- Check if AGE is installed
SELECT * FROM pg_extension WHERE extname = 'age';

-- Check if graph exists
SELECT * FROM ag_catalog.ag_graph;

-- Check loaded functions
SELECT proname FROM pg_proc WHERE pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'p8');

-- Direct Cypher test
SELECT * FROM ag_catalog.cypher('p8graph', $$ MATCH (n) RETURN count(n) $$) AS (count agtype);
```