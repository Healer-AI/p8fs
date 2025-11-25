# REM Query CLI Guide

## Overview

The `p8fs rem` command executes REM (Resource-Entity-Moment) queries using a unified query string syntax across PostgreSQL and TiDB databases.

## Query String Syntax

REM queries are query strings that are parsed and executed by the query engine:

```
LOOKUP key                          # Type-agnostic key lookup (finds entity in ANY table)
LOOKUP table:key                    # Key lookup with optional table hint
SEARCH "query text" IN table        # Semantic search (SQL-like, requires embeddings)
SEARCH "query text"                 # Semantic search on default table (resources)
SELECT ... FROM table WHERE ...     # Standard SQL SELECT
```

### Key Concepts

**Type-Agnostic LOOKUP**: The entire point of LOOKUP is that you don't need to know what table an entity is in. Just provide the key and the reverse lookup index finds it across all entity types (resources, moments, entities, etc.).

**Quoted SEARCH Queries**: Use SQL-like quoted strings for SEARCH to handle complex queries and special characters. Escape quotes with backslash: `SEARCH "morning \"run\"" IN resources`

## Database Providers

### PostgreSQL (Local Development)

**Connection**: Runs on `localhost:5438` via Docker Compose

**Setup**:
```bash
cd p8fs
docker compose up postgres -d
```

### TiDB (Cluster/Production)

**Connection**: Requires port-forward to cluster

**Setup**:
```bash
# Port forward to TiDB cluster
kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000 &

# Set environment variables
export P8FS_TIDB_HOST=localhost
export P8FS_TIDB_PORT=4000
export P8FS_TIDB_DATABASE=public
```

## Command Reference

### General Syntax

```bash
p8fs rem "QUERY STRING" [OPTIONS]
```

### Options

- `--provider`: Database provider (`postgresql`, `postgres`, `tidb`) - default: `postgresql`
- `--table`: Default table for queries without table specified - default: `resources`
- `--tenant-id`: Tenant ID - default: `tenant-test`
- `--format`: Output format (`table`, `json`, `jsonl`) - default: `table`

### Query String from stdin

```bash
echo "QUERY STRING" | p8fs rem [OPTIONS]
# or
p8fs rem [OPTIONS]  # Then paste query and press Ctrl+D
```

## Proven Working Examples

All examples below have been tested and verified to work.

### PostgreSQL Examples

#### 1. LOOKUP - Type-Agnostic Entity Discovery

The power of LOOKUP is that you don't need to know what table the entity is in:

```bash
# Type-agnostic lookup - finds entity in ANY table
uv run python -m p8fs.cli rem "LOOKUP test-resource-1" --provider postgresql --format json

# Alternative syntax with table hint (only used as fallback if KV index empty)
uv run python -m p8fs.cli rem "LOOKUP resources:test-resource-1" --provider postgresql --format json
```

**Output**:
```json
[
  {
    "id": "test-resource-1",
    "tenant_id": "tenant-test",
    "name": "Morning Journal",
    "content": "Today I woke up early and went for a run. The weather was beautiful.",
    "category": "diary",
    "created_at": "2025-11-06 16:34:23.081939"
  }
]
```

**Why Type-Agnostic?** You can use generic keys without knowing the entity type. `LOOKUP user-123` finds the user whether it's in `users`, `profiles`, or any other table.

#### 2. SQL - Standard SQL Dialect

Use familiar SQL SELECT syntax for structured queries:

```bash
# Basic SELECT with WHERE
uv run python -m p8fs.cli rem "SELECT * FROM resources WHERE category='diary'" --provider postgresql --format json

# With LIMIT
uv run python -m p8fs.cli rem "SELECT * FROM resources WHERE category='diary' LIMIT 1" --provider postgresql --format json
```

**Output**:
```json
[
  {
    "id": "test-resource-1",
    "tenant_id": "tenant-test",
    "name": "Morning Journal",
    "content": "Today I woke up early and went for a run. The weather was beautiful.",
    "category": "diary",
    "created_at": "2025-11-06 16:34:23.081939"
  }
]
```

#### 4. SQL - With ORDER BY

```bash
uv run python -m p8fs.cli rem "SELECT * FROM resources ORDER BY created_at DESC LIMIT 2" --provider postgresql --format json
```

#### 5. Query from stdin

```bash
# Using echo
echo "LOOKUP resources:test-resource-2" | uv run python -m p8fs.cli rem --provider postgresql --format json

# Interactive (paste query, then Ctrl+D)
uv run python -m p8fs.cli rem --provider postgresql --format json
# Paste: LOOKUP resources:test-resource-1
# Press Ctrl+D
```

### TiDB Examples

**Prerequisites**: Port forward must be active
```bash
kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000 &
```

#### 1. LOOKUP - Type-Agnostic Entity Discovery

```bash
# Type-agnostic lookup (no table hint needed)
P8FS_TIDB_HOST=localhost \
P8FS_TIDB_PORT=4000 \
P8FS_TIDB_DATABASE=public \
uv run python -m p8fs.cli rem "LOOKUP test-resource-1" --provider tidb --format json
```

**Output**:
```json
[
  {
    "id": "test-resource-1",
    "tenant_id": "tenant-test",
    "name": "Morning Journal",
    "content": "Today I woke up early and went for a run. The weather was beautiful.",
    "category": "diary",
    "created_at": "2025-11-06 16:38:12"
  }
]
```

#### 2. SQL - Standard SQL Dialect

```bash
P8FS_TIDB_HOST=localhost \
P8FS_TIDB_PORT=4000 \
P8FS_TIDB_DATABASE=public \
uv run python -m p8fs.cli rem "SELECT * FROM resources WHERE category='diary' LIMIT 1" --provider tidb --format json
```

#### 3. Query from stdin

```bash
echo "LOOKUP test-resource-3" | \
P8FS_TIDB_HOST=localhost \
P8FS_TIDB_PORT=4000 \
P8FS_TIDB_DATABASE=public \
uv run python -m p8fs.cli rem --provider tidb --format json
```

### SEARCH Examples (Semantic)

**Note**: SEARCH requires embeddings to be generated for the content and a valid OpenAI API key.

#### PostgreSQL SEARCH

```bash
# Basic semantic search
uv run python -m p8fs.cli rem 'SEARCH "what did I do today?" IN resources' --provider postgresql --format json

# Search with default table (resources)
uv run python -m p8fs.cli rem 'SEARCH "morning activities"' --provider postgresql --format json

# Complex query with escaped quotes
uv run python -m p8fs.cli rem 'SEARCH "what did I \"achieve\" today?" IN resources' --provider postgresql --format json
```

#### TiDB SEARCH

```bash
P8FS_TIDB_HOST=localhost \
P8FS_TIDB_PORT=4000 \
P8FS_TIDB_DATABASE=public \
uv run python -m p8fs.cli rem 'SEARCH "diary entries" IN resources' --provider tidb --format json
```

## Query Syntax Reference

### LOOKUP Syntax

Type-agnostic key-based lookup. Finds entity across all tables without needing to know the schema.

```
LOOKUP key              # Type-agnostic - scans all entity types
LOOKUP table:key        # With optional table hint for fallback
GET key                 # Alternative keyword
```

**Examples**:
- `LOOKUP test-1` (finds test-1 in ANY table - resources, moments, entities, etc.)
- `LOOKUP resources:test-1` (hint: fallback to resources table if KV index empty)
- `GET user-123` (finds user-123 regardless of table)

### SEARCH Syntax

SQL-like syntax with quoted strings for semantic search:

```
SEARCH "query text" IN table
SEARCH "query text"              # Uses default table (resources)
SEARCH 'query text' IN table     # Single quotes also supported
```

**Escaping quotes**: Use backslash to escape quotes within the search string:
```
SEARCH "morning \"run\"" IN resources
```

**Examples**:
- `SEARCH "what did I do today?" IN resources`
- `SEARCH "diary entries"` (uses default table)
- `SEARCH "morning activities" IN moments`
- `SEARCH "complex \"quoted\" phrase" IN resources`

### SQL Syntax

#### Standard SQL SELECT

```
SELECT fields FROM table WHERE condition ORDER BY field LIMIT n
```

**Examples**:
- `SELECT * FROM resources WHERE category='diary'`
- `SELECT id,name FROM resources WHERE created_at > '2025-01-01' LIMIT 10`
- `SELECT * FROM resources ORDER BY created_at DESC LIMIT 5`

## Environment Variables

### PostgreSQL
```bash
# Default values (already configured in docker-compose)
P8FS_PG_HOST=localhost
P8FS_PG_PORT=5438
P8FS_PG_DATABASE=app
P8FS_PG_USER=postgres
P8FS_PG_PASSWORD=postgres
P8FS_STORAGE_PROVIDER=postgresql
```

### TiDB
```bash
# For cluster access via port-forward
P8FS_TIDB_HOST=localhost
P8FS_TIDB_PORT=4000
P8FS_TIDB_DATABASE=public
P8FS_TIDB_USER=root
P8FS_TIDB_PASSWORD=""
```

## Output Formats

### Table Format (Default)

```bash
uv run python -m p8fs.cli rem "SELECT * FROM resources WHERE category='diary'" --provider postgresql
```

Displays nicely formatted table in terminal.

### JSON Format

```bash
uv run python -m p8fs.cli rem "SELECT * FROM resources WHERE category='diary'" --provider postgresql --format json
```

Outputs pretty-printed JSON array.

### JSONL Format

```bash
uv run python -m p8fs.cli rem "SELECT * FROM resources WHERE category='diary'" --provider postgresql --format jsonl
```

Outputs one JSON object per line (newline-delimited JSON).

## Testing Database Setup

### Setup Test Data

Create sample data for testing:

```bash
# PostgreSQL
cd p8fs
uv run python ../scripts/setup_test_data.py

# TiDB (with port-forward active)
cd p8fs
P8FS_TIDB_HOST=localhost \
P8FS_TIDB_PORT=4000 \
P8FS_STORAGE_PROVIDER=tidb \
P8FS_TIDB_DATABASE=public \
uv run python ../scripts/setup_test_data.py
```

This creates three test resources:
- `test-resource-1`: Morning Journal (category: diary)
- `test-resource-2`: Evening Reflection (category: diary)
- `test-resource-3`: Meeting Notes (category: note)

## Troubleshooting

### PostgreSQL Connection Issues

```bash
# Verify PostgreSQL is running
docker compose ps | grep postgres

# Should show: Up (healthy)

# Restart if needed
docker compose restart postgres
```

### TiDB Connection Issues

```bash
# Verify port-forward is active
lsof -i :4000

# Should show kubectl process

# Restart port-forward if needed
pkill -f "port-forward.*tidb"
kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000 &
```

### Connection Pool Issues

If you see connection pool errors:

```bash
# Disable pooling temporarily
P8FS_DB_POOL_ENABLED=false uv run python -m p8fs.cli rem "QUERY" ...
```

### Empty Results

If queries return no results:

```bash
# Verify data exists - PostgreSQL
docker exec percolate psql -U postgres -d app -c \
  "SELECT COUNT(*) FROM public.resources WHERE tenant_id = 'tenant-test';"

# Verify data exists - TiDB (with port-forward)
kubectl run mysql-client --rm -i --restart=Never --image=mysql:8.0 -- \
  mysql -h fresh-cluster-tidb.tikv-cluster.svc.cluster.local -P 4000 -u root public -e \
  "SELECT COUNT(*) FROM resources WHERE tenant_id = 'tenant-test';"
```

## Advanced Usage

### Piping Results

```bash
# Count results
uv run python -m p8fs.cli rem "resources WHERE category='diary'" --provider postgresql --format jsonl | wc -l

# Extract specific fields with jq
uv run python -m p8fs.cli rem "SELECT * FROM resources" --provider postgresql --format json | jq '.[].name'

# Filter with jq
uv run python -m p8fs.cli rem "SELECT * FROM resources" --provider postgresql --format json | \
  jq '.[] | select(.category == "diary")'
```

### Batch Processing

```bash
# Query multiple entities (type-agnostic)
for id in test-resource-1 test-resource-2 test-resource-3; do
  echo "=== $id ==="
  uv run python -m p8fs.cli rem "LOOKUP $id" --provider postgresql --format json | jq '.[] | {name, category}'
done
```

### Shell Aliases

```bash
# PostgreSQL aliases
alias remq='uv run python -m p8fs.cli rem --provider postgresql'
alias remqj='uv run python -m p8fs.cli rem --provider postgresql --format json'

# Usage
remqj "LOOKUP test-1"
remqj "SELECT * FROM resources WHERE category='diary'"

# TiDB aliases (with port-forward)
alias remqt='P8FS_TIDB_HOST=localhost P8FS_TIDB_PORT=4000 P8FS_TIDB_DATABASE=public uv run python -m p8fs.cli rem --provider tidb'
alias remqtj='P8FS_TIDB_HOST=localhost P8FS_TIDB_PORT=4000 P8FS_TIDB_DATABASE=public uv run python -m p8fs.cli rem --provider tidb --format json'

# Usage
remqtj "LOOKUP test-1"
remqtj "SELECT * FROM resources WHERE category='diary'"
```

## Reference

### Complete Help

```bash
uv run python -m p8fs.cli rem --help
```

### Quick Reference Card

```bash
# PostgreSQL
p8fs rem "LOOKUP key" --provider postgresql                              # Type-agnostic lookup
p8fs rem "SELECT * FROM table WHERE condition" --provider postgresql     # Standard SQL
p8fs rem 'SEARCH "query text" IN table' --provider postgresql            # Semantic search

# TiDB (set env vars)
export TIDB_ENV="P8FS_TIDB_HOST=localhost P8FS_TIDB_PORT=4000 P8FS_TIDB_DATABASE=public"

$TIDB_ENV p8fs rem "LOOKUP key" --provider tidb                          # Type-agnostic lookup
$TIDB_ENV p8fs rem "SELECT * FROM table WHERE condition" --provider tidb # Standard SQL
$TIDB_ENV p8fs rem 'SEARCH "query text" IN table' --provider tidb        # Semantic search

# From stdin
echo "QUERY" | p8fs rem --provider postgresql
```

## Implementation Details

### Query Parser

The REM query parser (`p8fs.query.rem_parser.REMQueryParser`) parses query strings into executable query plans:

1. **LOOKUP**: Parses `LOOKUP key` (type-agnostic) or `LOOKUP table:key` (with hint)
2. **SEARCH**: Parses SQL-like `SEARCH "query text" IN table` with quoted strings and escape handling
3. **SQL**: Parses standard SQL `SELECT ...` statements
4. **Implicit SEARCH**: Plain text defaults to search on default table

**Quote Handling**: SEARCH queries support both single (`'`) and double (`"`) quotes with proper escaping:
- `SEARCH "simple query" IN resources`
- `SEARCH "escaped \"quotes\" inside" IN resources`

### Query Execution Flow

```
Query String → Parser → Query Plan → Provider → Results
```

1. Parse query string into `REMQueryPlan`
2. Determine query type (LOOKUP, SEARCH, SQL, TRAVERSE)
3. Create appropriate parameters (LookupParameters, SearchParameters, etc.)
4. Execute through REMQueryProvider (PostgreSQL) or TiDBREMQueryProvider (TiDB)
5. Format and return results

### Files

```
p8fs/src/p8fs/
├── query/
│   ├── __init__.py
│   └── rem_parser.py          # Query string parser
├── providers/
│   ├── rem_query.py            # PostgreSQL REM provider
│   └── rem_query_tidb.py       # TiDB REM provider
└── cli_commands/
    └── rem.py                  # CLI command handler
```
