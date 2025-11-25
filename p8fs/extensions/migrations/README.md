# P8FS Entity Management System

This directory contains SQL migration scripts for the P8FS entity management system, which provides a unified graph-based indexing layer over relational data.

## System Architecture

The P8FS entity management system bridges relational tables with Apache AGE graph database functionality, providing a unified interface for data retrieval through business keys while maintaining the flexibility to store data in different providers.

## Core Components

### Entity Registration (`register_entities`)

The registration process creates a bridge between relational tables and graph nodes:

1. **Table Analysis**: Analyzes the target table schema to identify the business key field
2. **Graph Label Creation**: Creates graph labels using `schema__table` naming convention  
3. **View Generation**: Creates standardized views that expose business keys as `key` column
4. **Graph Preparation**: Creates reference nodes in the AGE graph for entity types

### Key Naming Conventions

- **Business Keys**: Natural identifiers from your data (e.g., `mercury-coder-small`, UUIDs, URIs)
- **Graph Labels**: `schema__table` format (e.g., `public__language_model_apis`)  
- **View Names**: `p8.vw_schema_table` format (e.g., `p8.vw_public_language_model_apis`)
- **Key Fields**: Configurable per entity - defaults to `name` → `key` → `id` priority

### Node Management Views

Created views provide a standardized interface that abstracts key field differences:

- **Standardized `key` Column**: Maps any business key field to unified `key` interface
- **Graph Metadata**: Includes `gid`, `node_uid`, `node_key` for graph integration
- **Tenant Isolation**: Supports `userid` filtering for multi-tenant scenarios
- **Consistent Schema**: All views expose same columns regardless of underlying table structure

### Entity Retrieval (`get_entities`)

The retrieval workflow uses graph indexing for performance:

1. **Graph Lookup**: Queries AGE graph nodes by business keys using `get_graph_nodes_by_key`
2. **Entity Grouping**: Groups results by entity type (graph labels)
3. **View Queries**: Retrieves full records from standardized views using `get_records_by_keys`
4. **Result Assembly**: Combines data into JSON structure keyed by entity type

## Structure

- `postgres/` - PostgreSQL-specific migrations with pgvector support
- `tidb/` - TiDB-specific migrations with vector functions  
- `rocksdb/` - RocksDB/TiKV key-value schema documentation

## Usage Workflow

### 1. Entity Registration

Register tables for graph integration using the business key field:

```sql
-- Register with custom key field (e.g., 'name' for language_model_apis)
SELECT * FROM p8.register_entities('language_model_apis', 'name', false, 'p8graph');

-- Register with UUID key field (e.g., 'id' for most models)  
SELECT * FROM p8.register_entities('resources', 'id', false, 'p8graph');

-- Register with URI key field (e.g., 'uri' for files)
SELECT * FROM p8.register_entities('files', 'uri', false, 'p8graph');
```

This creates:
- Graph labels in `schema__table` format
- Standardized views that expose business keys as `key` column
- Reference nodes in AGE graph database

### 2. Node Population

Populate graph nodes from registered entities:

```sql
-- Create graph nodes from entity data
SELECT * FROM p8.insert_entity_nodes('language_model_apis');
SELECT * FROM p8.insert_entity_nodes('resources');
SELECT * FROM p8.insert_entity_nodes('files');
```

This creates graph nodes with `key` (business key), `uid` (primary key), and `user_id` properties.

### 3. Entity Retrieval

Query entities by business keys through graph indexing:

```sql
-- Get entities by business keys (cross-entity-type query)
SELECT * FROM p8.get_entities(ARRAY['mercury-coder-small', 'some-resource-name', 'file.pdf']);

-- Results are grouped by entity type:
-- {
--   "public__language_model_apis": {"data": [...]},
--   "public__resources": {"data": [...]}, 
--   "public__files": {"data": [...]}
-- }
```

## Migration Management

### Generate Migration Scripts

Generate SQL migrations from Python models using the provider-specific scripts:

```bash
# Generate PostgreSQL migrations (from p8fs directory)
cd p8fs
uv run python scripts/generate_sql_from_models.py

# Output: extensions/migrations/postgres/install.sql

# Generate TiDB migrations
uv run python scripts/generate_tidb_sql_from_models.py

# Output: extensions/migrations/tidb/install.sql
```

These scripts read all models from `p8fs.models.p8` and generate complete CREATE TABLE statements with:
- Main table definitions
- Embedding tables (with VECTOR support for TiDB 8.0+)
- Provider-specific optimizations
- Proper tenant isolation

### Local Development Setup

#### PostgreSQL (Recommended for Development)

PostgreSQL is the primary development database with full support for pgvector, Apache AGE graphs, and automatic migrations.

```bash
# Start PostgreSQL container (from p8fs directory)
cd p8fs
docker compose up postgres -d

# Migrations run automatically on container startup via /docker-entrypoint-initdb.d/
# The container is configured to execute all SQL files in extensions/sql/:
#   - 00_install.sql: Extensions and base setup
#   - 01_entity_schema.sql: All table definitions
#   - 03_functions.sql: Stored procedures and graph functions

# Verify tables were created
docker exec percolate psql -U postgres -d app -c "\dt public.*"

# Check AGE graph setup
docker exec percolate psql -U postgres -d app -c "SELECT * FROM ag_catalog.ag_graph;"
```

The PostgreSQL setup includes:
- **pgvector**: Native vector operations for embeddings
- **Apache AGE**: Graph database capabilities
- **Automatic initialization**: All migrations run on first startup

#### TiDB (Production-Compatible Testing)

TiDB provides a production-compatible environment with VECTOR support (v8.0+) for testing auth flows and distributed features.

```bash
# Start TiDB container with v8.5.0 (from p8fs directory)
cd p8fs
docker compose up tidb -d

# Wait for TiDB to be ready
sleep 5

# Apply migrations (from p8fs-modules root)
cd ..
uv run python -c "
import pymysql
from pathlib import Path

# Read migration
migration = Path('p8fs/extensions/migrations/tidb/install.sql').read_text()

# Connect and execute
conn = pymysql.connect(host='localhost', port=4000, user='root', autocommit=True)
cursor = conn.cursor()

for statement in [s.strip() for s in migration.split(';') if s.strip() and not s.strip().startswith('--')]:
    try:
        cursor.execute(statement)
    except Exception as e:
        print(f'Warning: {e}')

cursor.close()
conn.close()
print('✅ TiDB migration complete')
"

# Verify tables
uv run python -c "
import pymysql
conn = pymysql.connect(host='localhost', port=4000, user='root', database='public')
cursor = conn.cursor()
cursor.execute('SHOW TABLES')
tables = cursor.fetchall()
print(f'Tables in public: {len(tables)}')
for t in tables: print(f'  ✅ {t[0]}')
cursor.close()
conn.close()
"
```

**TiDB Features:**
- **VECTOR Type**: Native vector operations (v8.0+)
- **TiFlash**: Columnar storage for analytics (requires cluster setup)
- **MySQL Compatible**: Standard MySQL client/driver support
- **Distributed**: Horizontal scalability (cluster mode)

**Connection Strings:**
- PostgreSQL: `postgresql://postgres:postgres@localhost:5438/app`
- TiDB: `mysql://root@localhost:4000/public`

### Regenerating Migrations

When you modify models in `p8fs.models.p8`, regenerate migrations:

```bash
cd p8fs

# Regenerate PostgreSQL migrations
uv run python scripts/generate_sql_from_models.py

# Regenerate TiDB migrations
uv run python scripts/generate_tidb_sql_from_models.py

# Compile into deployment files
uv run python scripts/compile_migrations.py
```

The `compile_migrations.py` script:
1. Optionally regenerates SQL from models (`--refresh`)
2. Copies PostgreSQL migration to `extensions/sql/01_entity_schema.sql`
3. Compiles function files into `extensions/sql/03_functions.sql`

## Migration Files

Migration files are automatically timestamped with format: `YYYYMMDD_HHMMSS_create_p8fs_tables.sql`

Each migration file contains:
- Main table creation SQL
- Embedding table creation SQL (if models have embedding fields)
- Provider-specific indexes and optimizations
- Comments and metadata

## Provider Features

### PostgreSQL
- Uses `pgvector` extension for native vector operations
- JSONB fields with GIN indexes
- Full-text search capabilities
- UPSERT with ON CONFLICT handling

### TiDB
- JSON-based vector storage with VEC_* functions
- TiFlash replicas for analytics workloads
- MySQL-compatible syntax
- REPLACE INTO for upserts

### RocksDB
- Key-value schema documentation
- TiKV compatibility notes
- Application-level vector search patterns
- Prefix-based scanning strategies

## Multi-Tenant Considerations

**TODO**: Current implementation uses PostgreSQL in single-tenant mode. For multi-tenant deployments, tenant isolation can be implemented by:

### Proposed Multi-Tenant Strategy

1. **Graph Node Key Prefixing**: Modify node creation to include tenant-id in graph node keys
   - Current: `key: "mercury-coder-small"`
   - Multi-tenant: `key: "tenant123:mercury-coder-small"`

2. **Repository-Level Key Qualification**: Update repository layer to automatically prefix keys
   - Application calls: `get_entities(['mercury-coder-small'])`
   - Repository adds tenant: `get_entities(['tenant123:mercury-coder-small'])`

3. **View Modifications**: Update entity views to handle tenant-aware key mapping
   - Views expose tenant-qualified keys while maintaining application transparency
   - Tenant context managed at repository layer, not in business logic

4. **Graph Label Isolation**: Optionally create tenant-specific graph labels
   - Single-tenant: `public__language_model_apis`
   - Multi-tenant: `tenant123__public__language_model_apis`

### Implementation Benefits

- **Transparent to Application Logic**: Business code continues using natural keys
- **Database-Level Isolation**: Tenant data completely separated at graph level
- **Performance Maintained**: Graph indexing efficiency preserved with prefixed keys
- **Migration Path**: Can be implemented incrementally without breaking existing functionality

The entity management system's view abstraction makes this transition straightforward since key handling is already centralized in the view layer.