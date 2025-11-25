# P8FS Developer Experience

## Database Schema Management with Atlas

### Overview

We use Atlas for declarative, state-based database schema management. Instead of traditional migrations, Atlas compares the desired schema state (defined in SQL files) with the current database state and generates the necessary SQL to reconcile differences.

### Installing Atlas

```bash
# macOS
brew install ariga/tap/atlas

# Linux/WSL
curl -sSf https://atlasgo.sh | sh

# Or download from GitHub releases
# https://github.com/ariga/atlas/releases
```

### Schema Management Workflow

Our database schema is defined in `extensions/sql/` and applied to PostgreSQL containers. Atlas can help manage schema changes without manual migration files.

#### 1. Generate Target Schema from SQL Files

First, create a consolidated schema file from our SQL extensions:

```bash
# Combine all SQL files into a single schema definition
cat extensions/sql/*.sql > schema.sql

# Or use our Docker image to generate the schema
docker run --rm \
  -v $(pwd)/extensions/sql:/docker-entrypoint-initdb.d \
  -v $(pwd)/schema.sql:/schema.sql \
  percolationlabs/postgres-base:16 \
  sh -c "cat /docker-entrypoint-initdb.d/*.sql > /schema.sql"
```

#### 2. Compare Current Database with Target Schema

```bash
# Compare running database with target schema
atlas schema diff \
  --from "postgres://postgres:postgres@localhost:5438/app?sslmode=disable" \
  --to "file://schema.sql"

# Generate migration SQL
atlas schema diff \
  --from "postgres://postgres:postgres@localhost:5438/app?sslmode=disable" \
  --to "file://schema.sql" \
  --format "{{ sql . }}" > migrate.sql
```

#### 3. Apply Schema Changes

```bash
# Dry run - see what changes would be applied
atlas schema apply \
  --url "postgres://postgres:postgres@localhost:5438/app?sslmode=disable" \
  --to "file://schema.sql" \
  --dry-run

# Apply changes
atlas schema apply \
  --url "postgres://postgres:postgres@localhost:5438/app?sslmode=disable" \
  --to "file://schema.sql"
```

### Alternative: HCL Schema Definition

Instead of SQL files, you can define schemas using Atlas HCL:

```hcl
# schema.hcl
table "tenants" {
  schema = schema.public
  column "id" {
    type = uuid
    default = sql("gen_random_uuid()")
  }
  column "name" {
    type = varchar(255)
  }
  column "created_at" {
    type = timestamptz
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
}

table "engrams" {
  schema = schema.public
  column "id" {
    type = uuid
    default = sql("gen_random_uuid()")
  }
  column "tenant_id" {
    type = uuid
  }
  column "content" {
    type = text
  }
  column "embedding" {
    type = sql("vector(1536)")
  }
  foreign_key "fk_tenant" {
    columns = [column.tenant_id]
    ref_columns = [table.tenants.column.id]
  }
  index "idx_embedding" {
    on {
      column = column.embedding
      ops    = "vector_cosine_ops"
    }
  }
}
```

### Development Workflow Script

Create a script for common schema operations:

```bash
#!/bin/bash
# scripts/schema-sync.sh

# Load environment
source .env

# Database URL
DB_URL="postgres://postgres:postgres@localhost:5438/app?sslmode=disable"

# Generate current schema from SQL files
echo "Generating target schema..."
cat extensions/sql/*.sql > target-schema.sql

# Show diff
echo "Schema differences:"
atlas schema diff --from "$DB_URL" --to "file://target-schema.sql"

# Ask for confirmation
read -p "Apply changes? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    atlas schema apply --url "$DB_URL" --to "file://target-schema.sql"
    echo "Schema updated successfully"
else
    echo "Aborted"
fi
```

### CI/CD Integration

```yaml
# .github/workflows/schema-check.yml
name: Schema Check

on:
  pull_request:
    paths:
      - 'extensions/sql/**'

jobs:
  schema-diff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install Atlas
        run: curl -sSf https://atlasgo.sh | sh
      
      - name: Start PostgreSQL
        run: docker-compose up -d postgres
      
      - name: Generate Schema
        run: cat extensions/sql/*.sql > schema.sql
      
      - name: Check Schema Diff
        run: |
          atlas schema diff \
            --from "postgres://postgres:postgres@localhost:5438/app?sslmode=disable" \
            --to "file://schema.sql"
```

### Benefits Over Traditional Migrations

1. **No Migration Files**: Define desired state, not incremental changes
2. **Idempotent**: Can run repeatedly without side effects
3. **Clean History**: No accumulation of migration files
4. **Easy Rollback**: Just change the target schema and re-apply
5. **Multi-Environment**: Compare dev/staging/prod schemas easily

### TiDB Support

Atlas also supports TiDB (MySQL-compatible):

```bash
# TiDB schema operations
atlas schema apply \
  --url "mysql://root@localhost:4000/test" \
  --to "file://schema-tidb.sql"
```