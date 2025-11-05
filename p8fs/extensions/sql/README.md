# P8FS PostgreSQL Extensions

This directory contains PostgreSQL extensions and SQL functions for the P8FS system. These functions provide graph-based KV storage, entity management, and advanced querying capabilities using the AGE extension.

## Overview

The P8FS PostgreSQL extensions leverage the Apache AGE graph database extension to provide:
- **Key-Value Storage**: Device authorization flows and temporary data
- **Entity Management**: Graph-based indexing of relational data via views
- **Graph Operations**: Cypher query execution and node management

## Installation

### Automatic Installation (Docker)

The SQL scripts are automatically installed when the PostgreSQL Docker container spins up. The installation process includes:

1. **Base Installation** (`00_install.sql`): Creates schemas, extensions, and base utilities
2. **Entity Schema** (`01_entity_schema.sql`): Creates table definitions from Pydantic models
3. **Functions** (`03_functions.sql`): Installs core P8FS functions for KV storage and entity management
4. **Test Data** (`10_test_data.sql`): Loads sample data for testing

**Testing Installation**: After container startup, verify installation completion by testing core functions:

```sql
-- Test KV storage
SELECT p8.put_kv('test:install', '{"status": "success"}'::jsonb);
SELECT p8.get_kv('test:install');

-- Test entity management  
SELECT jsonb_pretty(p8.get_entities(ARRAY['mercury-coder-small'])::jsonb);
```

### Manual Installation

For manual setup:
```bash
psql -f extensions/sql/00_install.sql
psql -f extensions/sql/01_entity_schema.sql  
psql -f extensions/sql/03_functions.sql
```

### Function Compilation

The SQL functions are organized as individual files in `extensions/sql/functions/` and compiled into monolithic files for deployment:

**Enhanced Compilation Process:**

The compilation script performs two critical tasks:

1. **Entity Schema Sync**: Copies latest migration to deployment schema
   ```bash
   cp extensions/migrations/postgres/install.sql extensions/sql/01_entity_schema.sql
   ```

2. **Function Compilation**: Compiles individual functions into monolithic deployment file
   ```bash
   # Compile migrations and functions for deployment
   python scripts/compile_migrations.py
   ```

**Why This Approach:**
- **Modular Development**: Individual functions are easier to edit, test, and maintain
- **Monolithic Deployment**: Single files are easier to deploy and install
- **Migration Sync**: Ensures entity schema stays in sync with latest Pydantic models
- **Version Control**: Individual functions provide better git diff and merge experience

**Development Workflow:**
- Edit individual functions in `extensions/sql/functions/`
- Test functions individually: `psql -f extensions/sql/functions/register_entities.sql`
- Compile before deployment: `python scripts/compile_migrations.py`
- Deploy compiled files: `psql -f extensions/sql/03_functions.sql`

### Schema Generation

Entity schemas are generated from Pydantic models and maintained through migrations:

**Process:**
1. **Pydantic Models**: Define in `src/p8fs/models/p8.py`
2. **Migration Generation**: Create migration from models
3. **Schema Copy**: Copy migration to `01_entity_schema.sql` during compilation

```bash
# Generate entity schema from Pydantic models in p8.py
python -m p8fs.models.p8 --generate-schema
```

The Pydantic models (`src/p8fs/models/p8.py`) define:

- Table structures with proper typing
- Key field mappings (`Config.key_field`)  
- Embedding field configurations
- Table naming conventions (lowercase snake_case plural)

## Core Functions

### KV Storage Operations

The KV storage system uses AGE graph nodes to store temporary key-value data, primarily for OAuth device authorization flows.

#### `p8.put_kv(key, value, ttl_seconds, userid)`
Stores a key-value pair in the graph with optional TTL.

```sql
-- Store device authorization request
SELECT p8.put_kv(
    'device-auth:abc123',
    '{"device_code": "abc123", "user_code": "A1B2", "status": "pending"}'::jsonb,
    600  -- 10 minutes TTL
);

-- Store without TTL
SELECT p8.put_kv('config:app', '{"theme": "dark"}'::jsonb);
```

**Parameters:**
- `key`: Unique identifier (text)
- `value`: JSON data to store (jsonb)
- `ttl_seconds`: Optional expiration time in seconds
- `userid`: Optional user filter for multi-tenant isolation

**Returns:** `boolean` - success/failure

#### `p8.get_kv(key, userid)`
Retrieves a value by key, automatically handling TTL expiration.

```sql
-- Get device auth data
SELECT p8.get_kv('device-auth:abc123');

-- Get with user filtering
SELECT p8.get_kv('user-pref:theme', 'user-123');
```

**Parameters:**
- `key`: Key to retrieve (text)
- `userid`: Optional user filter (text)

**Returns:** `jsonb` - stored value or NULL if not found/expired

**Implementation Notes:**
- Uses direct AGE cypher queries with `::text` casting for type safety
- Automatically removes expired entries when accessed
- Returns JSON data as PostgreSQL jsonb type

#### `p8.scan_kv(key_prefix, limit, userid)`
Scans for keys matching a prefix pattern.

```sql
-- Find all device auth entries
SELECT * FROM p8.scan_kv('device-auth:', 50);

-- Find user codes
SELECT * FROM p8.scan_kv('user-code:', 10);
```

**Parameters:**
- `key_prefix`: Prefix to match (text)
- `limit`: Maximum results (integer, default 100)
- `userid`: Optional user filter (text)

**Returns:** Table with columns:
- `key`: The key (text)
- `value`: The stored value (jsonb)
- `created_at`: Creation timestamp (text)
- `expires_at`: Expiration timestamp (text, empty if no TTL)

### Graph Operations

#### `p8.cypher_query(cypher_query, return_columns, graph_name)`
Executes Cypher queries against the P8 graph database.

```sql
-- Create nodes
SELECT * FROM p8.cypher_query('CREATE (n:TestNode {key: "test"}) RETURN n');

-- Query nodes
SELECT * FROM p8.cypher_query('MATCH (n) WHERE n.key = "test" RETURN n');
```

**Parameters:**
- `cypher_query`: Cypher query string (text)
- `return_columns`: Column definitions (text, default 'result agtype')
- `graph_name`: Graph name (text, default 'p8graph')

**Returns:** Table with `result` column (jsonb)

### Entity Management

The entity management system provides graph-based indexing of relational data through a sophisticated view-based abstraction layer.

#### Architecture Overview

1. **Pydantic Models** define table structure and key fields in `src/p8fs/models/p8.py`
2. **Entity Registration** creates views that map business keys to graph nodes
3. **Graph Indexing** stores entity keys as nodes for fast lookup
4. **get_entities** queries through views for complete abstraction

#### Key Design Principles

- **Entity Type = Table Name**: `language_model_apis`, `resources`, etc.
- **Graph Labels = Schema__Table**: `public__language_model_apis` in graph
- **Views Standardize Interface**: All views expose `key`, `uid`, and table data
- **Business Key Abstraction**: Views handle mapping from `name`, `id`, or any field to standardized `key`

#### `p8.register_entities(table_name, plan, graph_name, key_field)`
Registers relational tables for graph integration with proper key field mapping.

```sql
-- Register language_model_apis using 'name' as business key
SELECT * FROM p8.register_entities('language_model_apis', false, 'p8graph', 'name');

-- Register resources using 'id' as business key (default)
SELECT * FROM p8.register_entities('resources', false, 'p8graph', 'id');

-- Plan mode (preview without executing)
SELECT * FROM p8.register_entities('language_model_apis', true, 'p8graph', 'name');
```

**Critical Parameters:**
- `table_name`: Table name (defaults to public schema if no dot)
- `key_field`: Business key field from Pydantic model (`Config.key_field`)
- `plan`: Preview mode flag (boolean, default false)
- `graph_name`: Target graph name (text, default 'p8graph')

**What it creates:**
- **Reference Node**: `public__language_model_apis` label in graph
- **View**: `p8.vw_public_language_model_apis` with standardized interface:
  - `key` = business key value (e.g., `'mercury-coder-small'`)
  - `uid` = primary key (UUID)
  - `gid` = graph node ID
  - All table columns plus graph metadata

#### `p8.insert_entity_nodes(table_name)`
Creates graph nodes from existing table data through the view system.

```sql
-- Create graph nodes for all language_model_apis records
SELECT p8.insert_entity_nodes('language_model_apis');
```

**Process:**
1. Queries `p8.vw_public_language_model_apis` view
2. Creates `public__language_model_apis` nodes with:
   - `key`: business key from view (`'mercury-coder-small'`)
   - `uid`: primary key from view (UUID)
   - `user_id`: tenant isolation if present

#### `p8.get_entities(keys, userid)`
Retrieves entities by business keys using the complete view-based system.

```sql
-- Get language model API by business key (name)
SELECT jsonb_pretty(p8.get_entities(ARRAY['mercury-coder-small'])::jsonb);

-- Get multiple entities of different types
SELECT * FROM p8.get_entities(ARRAY['mercury-coder-small', 'some-resource-name']);
```

**How it works:**
1. **Graph Lookup**: Finds nodes by `key` property in graph
2. **Entity Type Mapping**: Maps `public__language_model_apis` → view `p8.vw_public_language_model_apis`  
3. **View Query**: Queries view using standardized `key` column
4. **Complete Data**: Returns table data + graph metadata through view abstraction

**Returns:** JSONB object with entities grouped by type:
```json
{
  "public__language_model_apis": {
    "data": [
      {
        "key": "mercury-coder-small",
        "uid": "3848a898-af16-463e-9864-f4fdf4e18b04",
        "name": "mercury-coder-small",
        "scheme": "openai",
        "completions_uri": "https://api.inceptionlabs.ai/v1/chat/completions",
        "gid": "2814749767106565",
        "node_key": "mercury-coder-small",
        "node_uid": "3848a898-af16-463e-9864-f4fdf4e18b04",
        "created_at": "2025-09-07T08:31:31.401708+00:00",
        "updated_at": "2025-09-07T08:32:05.414887+00:00"
      }
    ]
  }
}
```

**Parameters:**
- `keys`: Array of business keys to retrieve (text[])
- `userid`: Optional user filter (text)

#### View-Based Abstraction Layer

The view system is the critical abstraction that makes entity management work:

**Problem Solved:**
- Different entities use different key fields (`name` vs `id` vs `uri`)
- Graph needs standardized interface for all entity types
- Queries should be agnostic to key field variations

**Solution:**
- Views standardize interface: always expose `key` column as business key
- `get_entities` always queries views using `key` column  
- View internally handles mapping from actual key field (`name`, `id`, etc.)
- No need for `get_entities` to know key field per entity type

**Example View Structure:**
```sql
CREATE VIEW p8.vw_public_language_model_apis AS (
  SELECT t.name AS key,           -- Business key standardized as 'key'
         t.id::VARCHAR(50) AS uid, -- Primary key as 'uid'
         t.updated_at,
         t.created_at,
         t.tenant_id AS userid,
         G.gid,                   -- Graph metadata
         G.node_uid,
         G.node_key
  FROM public.language_model_apis t
  LEFT JOIN graph_nodes G ON t.id = G.node_uid
);
```

## Device Authorization Flow Example

The KV storage functions are designed to support OAuth 2.1 device authorization flows:

```sql
-- 1. Store device authorization request
SELECT p8.put_kv(
    'device-auth:abc123',
    '{"device_code": "abc123", "user_code": "A1B2", "status": "pending", "client_id": "app"}'::jsonb,
    600  -- 10 minutes
);

-- 2. Store user code reference for lookup
SELECT p8.put_kv(
    'user-code:A1B2',
    '{"device_code": "abc123"}'::jsonb,
    600
);

-- 3. User enters code, lookup device
SELECT p8.get_kv('user-code:A1B2');
-- Returns: {"device_code": "abc123"}

-- 4. Get device auth details
SELECT p8.get_kv('device-auth:abc123');
-- Returns: {"device_code": "abc123", "user_code": "A1B2", "status": "pending", ...}

-- 5. User approves, update status
SELECT p8.put_kv(
    'device-auth:abc123',
    '{"device_code": "abc123", "status": "approved", "access_token": "jwt_here"}'::jsonb,
    300  -- 5 minutes to consume
);

-- 6. Device polls and gets approved token
SELECT p8.get_kv('device-auth:abc123');
-- Returns: {"device_code": "abc123", "status": "approved", "access_token": "jwt_here"}
```

## Technical Implementation

### AGE Graph Integration
- Uses Apache AGE extension for graph operations
- Stores KV data as `KVStorage` nodes in the `p8graph` graph
- Node properties: `key`, `value`, `created_at`, `updated_at`, `expires_at`, `user_id`

### Type Handling
- AGE returns `agtype` which requires careful conversion
- Uses `::text` casting followed by jsonb parsing
- Handles quoted strings by trimming quotes
- Direct cypher queries avoid problematic wrapper functions

### Performance Considerations
- KV operations are optimized for temporary data (device auth flows)
- TTL cleanup happens on access, not background processes
- Prefix scanning supports efficient key-based queries
- Graph indexing provides fast entity lookups

### Error Handling
- Functions return NULL for missing/expired keys
- Boolean returns indicate operation success/failure
- TTL expiration is handled transparently
- Type conversion errors are caught and handled gracefully

## Known Limitations

- **Deletion**: Key deletion not supported, use TTL for automatic expiration
- **get_kv_stats function**: Disabled due to cypher_query wrapper issues  
- **TTL expiration**: Manual cleanup on access, no background expiration
- **Special characters**: Some characters in keys may cause issues
- **Concurrent access**: No explicit locking, last write wins

## Testing

Comprehensive integration tests are available in:
```
tests/integration/test_kv_functionality.py
```

Tests cover:
- Basic put/get operations
- Device authorization flows  
- Concurrent access patterns
- Large value handling
- Edge cases and error conditions

## Future Enhancements

- Background TTL cleanup process
- Improved error handling for special characters
- Performance optimization for high-volume operations
- Enhanced stats and monitoring functions
- Distributed graph operations