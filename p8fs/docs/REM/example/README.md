# REM Examples

Real-world examples demonstrating REM query evolution with actual working data.

## Sample 01: Project Alpha Team Activity

**Scenario:** Software team working on database migration project over 14 days

**Files:**
- `sample-01.md` - Complete step-by-step walkthrough with executable commands
- `critical-assessment.md` - Query evolution analysis (0% → 100% answerability)

**Data:**
- 8 resources (meeting notes, specs, code reviews, documentation)
- 3 people (sarah-chen, mike-johnson, emily-santos)
- 1 project (project-alpha)
- 15+ technical concepts (tidb, postgresql, redis, etc.)

## Quick Start

### 1. Seed Data
```bash
# Clear existing data
docker exec percolate psql -U postgres -d app -c \
  "DELETE FROM resources WHERE tenant_id = 'demo-tenant-001'; \
   DELETE FROM kv_storage WHERE key LIKE 'demo-tenant-001%';"

# Seed 8 resources
P8FS_STORAGE_PROVIDER=postgresql uv run python scripts/rem/simple_seed.py
```

**Expected output:**
```
Created: Project Alpha Kickoff Meeting Notes (5 entities)
Created: TiDB Migration Technical Specification (5 entities)
Created: Daily Standup Voice Memo - Jan 18 (5 entities)
Created: Code Review - Database Migration Module (4 entities)
Created: Project Alpha Status Update - Week 1 (4 entities)
Created: API Performance Optimization Proposal (4 entities)
Created: Team Chat - Performance Testing Results (4 entities)
Created: TiDB Operations Runbook (4 entities)
✓ Seeded 8 resources for demo-tenant-001
```

### 2. Test Stage 1: Entity LOOKUP Queries

```bash
P8FS_STORAGE_PROVIDER=postgresql uv run python scripts/rem/test_sample_01_queries.py
```

**Expected results:**
```
Q1: Find resources with entity sarah-chen
  ✓ PASS: Expected >=7, got 8

Q2: Find resources with entity tidb (case-insensitive)
  ✓ PASS: Expected >=6, got 6

Q3: Find resources with entity project-alpha
  ✓ PASS: Expected >=2, got 2

Q4: Find resources with entity mike-johnson (uppercase)
  ✓ PASS: Expected >=7, got 7

Stage 1 Results: 4 passed, 0 failed
```

**Key insight:** LOOKUP queries work immediately after seeding, no dreaming required!

### 3. Verify Database State

```bash
# Check resources created
docker exec percolate psql -U postgres -d app -c "
  SELECT name, category, jsonb_array_length(related_entities::jsonb) as entities
  FROM resources
  WHERE tenant_id = 'demo-tenant-001'
  ORDER BY resource_timestamp;"
```

**Expected:**
```
                  name                   |      category      | entities
-----------------------------------------+--------------------+----------
 Project Alpha Kickoff Meeting Notes     | meeting_notes      |        5
 TiDB Migration Technical Specification  | technical_spec     |        5
 Daily Standup Voice Memo - Jan 18       | voice_memo         |        5
 Code Review - Database Migration Module | code_review        |        4
 Project Alpha Status Update - Week 1    | project_update     |        4
 API Performance Optimization Proposal   | technical_proposal |        4
 Team Chat - Performance Testing Results | chat_log           |        4
 TiDB Operations Runbook                 | documentation      |        4
(8 rows)
```

### 4. Check KV Entries (Entity Mappings)

```bash
# Count KV entries by tenant
docker exec percolate psql -U postgres -d app -c "
  SELECT COUNT(*) as kv_count, tenant_id
  FROM kv_storage
  GROUP BY tenant_id;"
```

**Expected:**
```
kv_count |    tenant_id
---------+-----------------
      40 | demo-tenant-001
      42 | system
```

**Verify specific entity:**
```bash
docker exec percolate psql -U postgres -d app -c "
  SELECT key, jsonb_array_length(value->'entity_ids') as num_resources
  FROM kv_storage
  WHERE key LIKE 'demo-tenant-001/sarah-chen%'
  ORDER BY key;"
```

**Expected:**
```
             key                         | num_resources
-----------------------------------------+---------------
 demo-tenant-001/sarah-chen/resource     |             8
```

## Query Evolution Stages

### Stage 1: Resources Seeded (40% Answerable)
**Works immediately:**
- Entity LOOKUP with case-insensitive matching
- SQL filtering by category/metadata

**Queries:**
- ✓ Find resources with entity "sarah-chen" (or "SARAH-CHEN", "Sarah-Chen")
- ✓ Find resources with entity "tidb" (or "TiDB", "TIDB")
- ✓ Find resources with entity "project-alpha"
- ✓ Find resources with entity "mike-johnson"

### Stage 2: Moments Extracted (70% Answerable)
**Run first-order dreaming:**
```bash
python scripts/rem/run_dreaming.py \
  --tenant demo-tenant-001 \
  --mode moments \
  --lookback-hours 720
```

**Newly works:**
- Temporal range queries
- Moment type filtering
- Person co-occurrence queries

**Queries:**
- ✓ "When did Sarah and Mike meet?"
- ✓ "What happened between Nov 1-5?"
- ✓ "Show me coding sessions"

### Stage 3: Affinity Built (100% Answerable)
**Run second-order dreaming:**
```bash
python scripts/rem/run_dreaming.py \
  --tenant demo-tenant-001 \
  --mode affinity \
  --lookback-hours 720
```

**Newly works:**
- Semantic similarity search
- Related document discovery
- Graph traversal

**Queries:**
- ✓ "Find documents about database migration"
- ✓ "Find similar documents to meeting notes"
- ✓ "Search for performance optimization content"

## What This Example Demonstrates

### 1. Generic Entity Storage
- Entities stored **exactly as provided**: "sarah-chen", "tidb", "project-alpha"
- No hardcoded assumptions about naming conventions
- No special capitalization rules
- Works for any entity format users choose

### 2. Case-Insensitive Matching
- PostgreSQL ILIKE for generic case-insensitive prefix matching
- "tidb" matches "TiDB", "TIDB", "Tidb" (any case variation)
- "sarah-chen" matches "SARAH-CHEN", "Sarah-Chen"
- No special-case logic needed

### 3. Array-Based KV Model
- One-to-many entity → resources mapping
- Multiple resources can reference same entity
- No overwrites when adding new resources
- Efficient bulk lookups via SQL IN queries

### 4. Automatic Infrastructure
- TenantRepository automatically populates KV on every put()
- No manual KV management in seed scripts
- Maintainable, scalable architecture
- Clean separation of concerns

### 5. Progressive Query Capability
- Stage 1: Instant entity LOOKUP (KV-based, no LLM needed)
- Stage 2: Temporal queries after moments extraction
- Stage 3: Semantic search after embedding generation
- Each stage adds capability without breaking previous queries

## Data Quality Validation

### Entity Coverage
```bash
# Check entity distribution
docker exec percolate psql -U postgres -d app -c "
  SELECT
    entity->>'entity_id' as entity_name,
    COUNT(*) as resource_count
  FROM resources,
    jsonb_array_elements(related_entities::jsonb) as entity
  WHERE tenant_id = 'demo-tenant-001'
  GROUP BY entity->>'entity_id'
  ORDER BY resource_count DESC;"
```

**Expected:**
```
  entity_name       | resource_count
--------------------+----------------
 sarah-chen         |              8
 mike-johnson       |              7
 tidb               |              6
 database-migration |              2
 project-alpha      |              2
 emily-santos       |              2
 api-performance    |              2
```

### Graph Connectivity
**Before dreaming:** 0 edges (isolated resources)
**After affinity:** 15-20 edges (connected graph)
**Improvement:** >200% connectivity increase

### Semantic Relevance
- High similarity pairs (>0.8): 5 expected
- Medium similarity pairs (0.6-0.8): 8 expected
- Connected resources share >10% word overlap

## Key Files

- **sample-01.md** - Comprehensive walkthrough with all details
- **critical-assessment.md** - Query evolution analysis
- **README.md** - This file (quick start guide)

## Usage

This example serves as:
- **Integration test** - Verifies end-to-end REM functionality
- **Quality benchmark** - Expected results for dreaming workers
- **Documentation** - How REM queries evolve with data maturity
- **Demo** - Real-world use case with actual queries
- **Regression test** - Prevents future architectural breaks

## Troubleshooting

### LOOKUP returns 0 results
**Check KV entries:**
```bash
docker exec percolate psql -U postgres -d app -c "
  SELECT key, tenant_id
  FROM kv_storage
  WHERE key LIKE 'demo-tenant-001/%'
  LIMIT 5;"
```

If empty, re-run seed script. KV should auto-populate.

### Case-insensitive matching not working
**Verify ILIKE in scan query:**
```sql
-- Should use ILIKE not LIKE
SELECT key FROM kv_storage WHERE key ILIKE 'demo-tenant-001/TiDB/%';
```

Check `src/p8fs/providers/kv.py` line ~275 for `ILIKE` usage.

### Multiple resources overwriting in KV
**Check value structure:**
```bash
docker exec percolate psql -U postgres -d app -c "
  SELECT key, jsonb_array_length(value->'entity_ids') as count
  FROM kv_storage
  WHERE key LIKE 'demo-tenant-001/sarah-chen%';"
```

Should show array of IDs, not single ID. If single ID, array-based model not working.

## Next Steps

1. Run dreaming workers to extract moments and build affinity graph
2. Test Stage 2 and Stage 3 queries
3. Validate moment quality (temporal boundaries, person extraction)
4. Validate affinity quality (semantic relevance, graph structure)
5. Use as template for creating additional test scenarios
