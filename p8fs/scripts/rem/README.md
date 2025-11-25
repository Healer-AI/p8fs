# REM Quality Validation Scripts

**CRITICAL QUALITY VALIDATION - NOT JUST EXCEPTION CHECKING**

These scripts validate the QUALITY of dreaming worker output and REM query results:
- Are moments extracted with logical temporal boundaries?
- Are present persons and speakers correctly identified?
- Do affinity edges connect semantically related resources?
- Are REM queries returning relevant results?
- Is the graph properly connected with valid relationships?

This is about data quality, not just "does it run without errors".

## Scripts

### Quality Validation Scripts

#### validate_moment_quality.py
**CRITICAL QUALITY CHECKS** for moment extraction.

Validates:
- Temporal boundaries (start < end, reasonable durations)
- Person extraction (meetings have persons, no duplicates)
- Speaker identification (speakers match present_persons, valid speaking times)
- Tag quality (emotion and topic tags are meaningful, not empty)
- Content quality (summaries exist and are shorter than content)
- Entity references (valid format and normalization)
- Temporal coverage (no excessive gaps)
- Moment type distribution (diverse types, not all "unknown")

**Usage:**
```bash
# Run all quality checks
python scripts/rem/validate_moment_quality.py --tenant dev-tenant-001

# Verbose output with all issues
python scripts/rem/validate_moment_quality.py --tenant dev-tenant-001 --verbose
```

**Exit code:** 0 if all checks pass, 1 if any fail

#### validate_affinity_quality.py
**CRITICAL QUALITY CHECKS** for resource affinity graph.

Validates:
- Edge existence (reasonable coverage, not too sparse)
- Edge format (valid paths, proper UUIDs)
- Semantic relevance (connected resources actually share content)
- Bidirectional edges (similar resources have reciprocal links)
- Entity connections (entity paths properly formatted and normalized)
- Graph connectivity (not too many isolated nodes, reasonable degree)
- Edge distribution (not extremely skewed)

**Usage:**
```bash
# Run all quality checks
python scripts/rem/validate_affinity_quality.py --tenant dev-tenant-001

# Verbose output with all issues
python scripts/rem/validate_affinity_quality.py --tenant dev-tenant-001 --verbose
```

**Exit code:** 0 if all checks pass, 1 if any fail

### Data Generation Scripts

#### seed_test_data.py
Seeds comprehensive test data for REM testing.

**Usage:**
```bash
# Seed PostgreSQL with 3 test tenants
python scripts/rem/seed_test_data.py --provider postgresql --tenants 3

# Seed TiDB
python scripts/rem/seed_test_data.py --provider tidb --tenants 3
```

**Creates:**
- 3 tenant scenarios (developer, product manager, researcher)
- 30-40 resources per tenant
- 15-30 moments per tenant
- Entities and relationships

### run_dreaming.py
Executes dreaming workers for moment extraction and resource affinity.

**Usage:**
```bash
# Run both modes
python scripts/rem/run_dreaming.py --tenant dev-tenant-001 --mode both

# Moments only
python scripts/rem/run_dreaming.py --tenant dev-tenant-001 --mode moments

# Affinity only with LLM
python scripts/rem/run_dreaming.py --tenant dev-tenant-001 --mode affinity --use-llm

# With verification
python scripts/rem/run_dreaming.py --tenant dev-tenant-001 --mode both --verify
```

**Options:**
- `--mode`: moments, affinity, or both
- `--lookback-hours`: Hours of data to process (default: 24)
- `--use-llm`: Enable LLM mode for affinity
- `--verify`: Verify results after processing
- `--provider`: postgresql or tidb

### test_rem_queries.py
Validates REM query functionality with predefined test questions.

**Usage:**
```bash
# Test all categories for one tenant
python scripts/rem/test_rem_queries.py --tenant dev-tenant-001

# Test specific category
python scripts/rem/test_rem_queries.py --tenant dev-tenant-001 --category temporal

# Test all tenants
python scripts/rem/test_rem_queries.py --all-tenants
```

**Categories:**
- temporal: Recent activity, time-based queries
- people: Person lookups and relationships
- content: Document queries
- semantic: Vector search
- entities: Entity lookups and mentions

### cluster_dreaming_test.sh
Cluster testing workflow for Kubernetes deployment.

**Usage:**
```bash
# Full workflow: seed + run + verify
./scripts/rem/cluster_dreaming_test.sh --seed-data --tenant dev-tenant-001 --verify

# Run for specific tenant
./scripts/rem/cluster_dreaming_test.sh --tenant dev-tenant-001

# Run for all test tenants
./scripts/rem/cluster_dreaming_test.sh --seed-data --verify
```

## Complete Quality Validation Workflow

### Local Testing (PostgreSQL)

```bash
# 1. Start PostgreSQL
cd p8fs
docker compose up postgres -d

# 2. Seed test data
python scripts/rem/seed_test_data.py --provider postgresql --tenants 3

# 3. Run dreaming workers
python scripts/rem/run_dreaming.py --tenant dev-tenant-001 --mode both

# 4. CRITICAL QUALITY CHECKS - Validate moment quality
python scripts/rem/validate_moment_quality.py --tenant dev-tenant-001 --verbose
# Exit code 0 = PASS, 1 = FAIL

# 5. CRITICAL QUALITY CHECKS - Validate affinity quality
python scripts/rem/validate_affinity_quality.py --tenant dev-tenant-001 --verbose
# Exit code 0 = PASS, 1 = FAIL

# 6. Test REM query results quality
python scripts/rem/test_rem_queries.py --tenant dev-tenant-001

# 7. Review actual generated data
# Check what moments were created
# Check what graph edges were created
# Manually inspect for quality
```

### Cluster Testing (TiDB)

```bash
# 1. Seed data on cluster
kubectl run rem-seed --image=p8fs-eco:latest --restart=Never --rm -it \
  --env="P8FS_STORAGE_PROVIDER=tidb" \
  -- python scripts/rem/seed_test_data.py --provider tidb --tenants 3

# 2. Run dreaming (or wait for scheduled task)
kubectl run dreaming-test --image=p8fs-eco:latest --restart=Never --rm -it \
  --env="P8FS_STORAGE_PROVIDER=tidb" \
  -- python scripts/rem/run_dreaming.py --tenant dev-tenant-001 --mode both

# 3. Test queries
kubectl run query-test --image=p8fs-eco:latest --restart=Never --rm -it \
  -- python scripts/rem/test_rem_queries.py --all-tenants --provider tidb
```

## Implementation Notes

### Fixed Issues

**LookupParameters table_name requirement:**
- Changed `table_name: str` to `table_name: str = "resources"` in QueryParameters base class
- Allows LOOKUP queries without specifying table name

**Repository methods:**
- Uses `repository.put(entity)` instead of non-existent `create_resource()`
- Requires passing model class to TenantRepository constructor
- Resources and Moments created as proper model instances

**Verification queries:**
- Uses repository select() instead of raw SQL
- Simplified to work with standard repository interface

## Test Data

### Tenants Created

1. **dev-tenant-001**: Software developer scenario
   - Projects: api-redesign, database-migration, auth-system
   - People: Alice Chen, Bob Martinez, Carol Kim, Dave Patel

2. **pm-tenant-002**: Product manager scenario
   - Projects: mobile-app-launch, feature-parity, user-onboarding
   - People: Emily Santos, Frank Wilson, Grace Lee

3. **research-tenant-003**: Academic researcher scenario
   - Projects: neural-networks-study, climate-modeling
   - People: Dr. James Smith, Jane Doe, Tom Anderson

### Expected Results

After seeding and dreaming:
- 30-40 resources per tenant
- 15-30 moments per tenant
- 30-50 graph edges per tenant
- All resources and moments have embeddings
- KV mappings for entity lookups

## Troubleshooting

**Import errors:**
- Ensure running from p8fs directory
- Check virtual environment activated

**Database connection errors:**
- Verify PostgreSQL/TiDB running
- Check `P8FS_STORAGE_PROVIDER` environment variable

**No results from queries:**
- Verify data seeded: check database directly
- Ensure correct tenant_id used
- Check embeddings generated

**Dreaming worker failures:**
- Verify LLM API keys set
- Check memory limits (256Mi minimum)
- Review worker logs for errors
