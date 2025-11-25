# Dreaming Integration Test - README

## Overview

This directory contains sample data and integration tests for the P8FS dreaming workflow, which includes:

1. **First-Order Dreaming**: Moment extraction and inline entity discovery
2. **Second-Order Dreaming**: Semantic linking between resources via graph edges

## Sample Data

### Voice Memos (Transcripts)
- `morning_planning_2025_01_05.md` - Personal planning session
- `team_standup_2025_01_06.md` - Team meeting with multiple participants
- `client_call_acme_2025_01_07.md` - Client discussion about Project Alpha
- `reflection_evening_2025_01_08.md` - Evening reflection

### Documents
- `project_alpha_spec.md` - Detailed API specification for Project Alpha
- `acme_contract_2025.md` - Master services agreement contract

### Technical Documentation
- `architecture_overview.md` - Microservices migration architecture plan

### Chat Sessions
- `chat_project_alpha_discussion.json` - Multi-turn chat about Project Alpha

## Test Setup

### Prerequisites

1. **PostgreSQL with Apache AGE**
   ```bash
   cd /Users/sirsh/code/p8fs-modules/p8fs
   docker compose up postgres -d
   ```

2. **Environment Variables**
   ```bash
   export P8FS_STORAGE_PROVIDER=postgresql
   export OPENAI_API_KEY=sk-your-key-here
   export OPENAI_MODEL=gpt-4o-mini  # Or gpt-4o for better results
   ```

3. **Verify Database**
   ```bash
   docker exec percolate psql -U postgres -d app -c "SELECT version();"
   docker exec percolate psql -U postgres -d app -c "SELECT * FROM pg_extension WHERE extname = 'age';"
   ```

## Running the Test

### Quick Start

```bash
# From p8fs directory
cd /Users/sirsh/code/p8fs-modules/p8fs

# Ensure PostgreSQL is running
docker compose up postgres -d

# Set environment
export P8FS_STORAGE_PROVIDER=postgresql
export OPENAI_API_KEY=sk-your-key-here

# Run the end-to-end test
uv run pytest tests/integration/test_dreaming_end_to_end.py -v -s
```

### Test Phases

The test executes in 7 phases:

**Phase 1: Load Sample Data**
- Loads 7 resources (4 voice memos, 2 documents, 1 technical doc)
- Loads 1 chat session
- Verifies data loaded correctly

**Phase 2: Extract Moments (First-Order - Part 1)**
- Processes voice memos with MomentBuilder
- Extracts moments with:
  - Moment types (conversation, meeting, planning, reflection)
  - Emotion tags (focused, collaborative, stressed, optimistic)
  - Topic tags (project-alpha, acme-contract, api-design)
  - Temporal boundaries (start/end timestamps)
- Saves moments to database

**Phase 3: Extract Entities (First-Order - Part 2)**
- Processes all resources with EntityExtractorAgent
- Extracts entities:
  - People: john-smith, sarah-chen, jane-doe, david-wilson, lisa-martinez, mike-johnson
  - Organizations: acme-corp, tech-startup-xyz
  - Projects: project-alpha, microservices-migration
  - Concepts: oauth-2-1, api-design, vector-search, kubernetes
- Saves entities to resources.related_entities field

**Phase 4: Create Resource Edges (Second-Order Dreaming)**
- Uses ResourceEdgeBuilder to find semantically similar resources
- Creates SEE_ALSO graph edges with similarity scores
- Example edges:
  - project_alpha_spec ↔ client_call_acme (high similarity: ~0.85)
  - acme_contract ↔ client_call_acme (high similarity: ~0.90)
  - architecture_overview ↔ team_standup (medium similarity: ~0.70)

**Phase 5: Verify Graph Edges**
- Queries graph database for SEE_ALSO relationships
- Verifies edges were created correctly
- Displays sample edges with similarity scores

**Phase 6: Query Knowledge Graph**
- Demonstrates querying capabilities:
  - List moments with emotions and topics
  - Find resources by entity
  - Traverse graph edges
  - Summary statistics

**Phase 7: End-to-End Verification**
- Confirms all workflow steps completed
- Validates data integrity
- Reports success/failure

## Expected Results

### Moments Created
- **Count**: 4-6 moments
- **Types**: conversation, meeting, planning, reflection
- **Emotions**: focused, collaborative, stressed, optimistic, worried
- **Topics**: project-alpha, acme-corp, api-design, microservices, q1-planning

### Entities Extracted
- **Count**: 15-25 entities total
- **People**: john-smith, sarah-chen, jane-doe, david-wilson, lisa-martinez, mike-johnson
- **Organizations**: acme-corp, tech-startup-xyz
- **Projects**: project-alpha, microservices-migration
- **Concepts**: oauth-2-1, api-design, tidb, kubernetes, vector-search

### Graph Edges Created
- **Count**: 8-15 SEE_ALSO edges
- **Similarity Range**: 0.60-0.95
- **Example**: project_alpha_spec → acme_contract (similarity: 0.82)

## Verification Queries

### Check Resources
```sql
SELECT id, name, category, resource_type, resource_timestamp
FROM resources
WHERE tenant_id = 'tenant-test'
ORDER BY resource_timestamp;
```

### Check Moments
```sql
SELECT id, name, moment_type, emotion_tags, topic_tags,
       resource_timestamp, resource_ends_timestamp
FROM moments
WHERE tenant_id = 'tenant-test'
ORDER BY resource_timestamp;
```

### Check Entities
```sql
SELECT name, category, jsonb_array_length(related_entities) as entity_count,
       related_entities
FROM resources
WHERE tenant_id = 'tenant-test' AND related_entities IS NOT NULL
ORDER BY entity_count DESC;
```

### Check Graph Edges
```sql
-- Using Apache AGE Cypher
SELECT * FROM p8.cypher_query(
    'MATCH (a:public__Resource)-[r:SEE_ALSO]->(b:public__Resource)
     RETURN a.uid as from_id, b.uid as to_id, properties(r) as metadata
     LIMIT 20',
    'from_id text, to_id text, metadata agtype',
    'p8graph'
);
```

### Entity Distribution
```sql
-- Extract and count entities by type
SELECT
    r.name,
    COUNT(*) FILTER (WHERE entity->>'entity_type' = 'Person') as people,
    COUNT(*) FILTER (WHERE entity->>'entity_type' = 'Organization') as orgs,
    COUNT(*) FILTER (WHERE entity->>'entity_type' = 'Project') as projects,
    COUNT(*) FILTER (WHERE entity->>'entity_type' = 'Concept') as concepts
FROM resources r, jsonb_array_elements(r.related_entities) as entity
WHERE r.tenant_id = 'tenant-test'
GROUP BY r.name;
```

## Manual Testing

### Load Data Only
```bash
cd /Users/sirsh/code/p8fs-modules/p8fs
uv run python tests/integration/sample_data/dreaming/load_sample_data.py
```

### Test Individual Components

```python
# In Python REPL
from p8fs.providers import get_provider
from p8fs.repository.TenantRepository import TenantRepository

provider = get_provider()
provider.connect_sync()
repo = TenantRepository(provider, tenant_id="tenant-test")

# Get resources
resources = provider.execute(
    "SELECT * FROM resources WHERE tenant_id = 'tenant-test'"
)

print(f"Found {len(resources)} resources")
```

## Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL is running
docker ps | grep percolate

# Restart if needed
docker compose down
docker compose up postgres -d

# Wait for startup
sleep 5

# Test connection
docker exec percolate psql -U postgres -d app -c "SELECT 1;"
```

### Apache AGE Not Installed
If graph queries fail, Apache AGE may not be installed:

```bash
# Check extension
docker exec percolate psql -U postgres -d app -c \
  "SELECT * FROM pg_extension WHERE extname = 'age';"

# If not installed, see migration scripts:
# p8fs/extensions/migrations/postgres/install.sql
```

### OpenAI API Errors
```bash
# Verify API key
echo $OPENAI_API_KEY

# Test API access
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# Use cheaper model for testing
export OPENAI_MODEL=gpt-4o-mini
```

### Import Errors
```bash
# Reinstall dependencies
cd /Users/sirsh/code/p8fs-modules/p8fs
uv sync

# Check Python path
uv run python -c "import sys; print('\n'.join(sys.path))"
```

## Cleanup

```bash
# Remove test data
docker exec percolate psql -U postgres -d app -c \
  "DELETE FROM resources WHERE tenant_id = 'tenant-test';"

docker exec percolate psql -U postgres -d app -c \
  "DELETE FROM moments WHERE tenant_id = 'tenant-test';"

docker exec percolate psql -U postgres -d app -c \
  "DELETE FROM sessions WHERE tenant_id = 'tenant-test';"

# Or restart database
docker compose down
docker compose up postgres -d
```

## Next Steps

After successful local testing:

1. **Cluster Deployment**: Deploy dreaming workers to Kubernetes cluster
2. **Cron Job Setup**: Schedule periodic dreaming processing for all tenants
3. **Performance Optimization**: Tune batch sizes and thresholds
4. **Model Selection**: Test with better models (gpt-4o, claude-sonnet-4)
5. **Monitoring**: Add metrics and alerting for dreaming jobs

## File Structure

```
tests/integration/sample_data/dreaming/
├── README.md                          # This file
├── load_sample_data.py                # Data loader script
├── resources/
│   ├── voice_memos/
│   │   ├── morning_planning_2025_01_05.md
│   │   ├── team_standup_2025_01_06.md
│   │   ├── client_call_acme_2025_01_07.md
│   │   └── reflection_evening_2025_01_08.md
│   ├── documents/
│   │   ├── project_alpha_spec.md
│   │   └── acme_contract_2025.md
│   └── technical/
│       └── architecture_overview.md
└── sessions/
    └── chat_project_alpha_discussion.json

../test_dreaming_end_to_end.py         # Main integration test
```

## Support

For issues or questions:
- Check logs: `docker compose logs postgres`
- Review test output: Run with `-v -s` flags
- Check documentation: `/Users/sirsh/code/p8fs-modules/p8fs/docs/first-second-order-dreaming-test-plan.md`
