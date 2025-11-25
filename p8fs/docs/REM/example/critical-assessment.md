# REM Query Evolution: Critical Assessment

## Success Metric

**Success is measured by whether REM queries get better over time.**

Not: "Do scripts run without exceptions?"

But: "Can I ask richer questions as the graph matures?"

## Query Evolution Across Maturity Stages

### Stage 0: No Data (0% Answerable)

Empty database. No resources, no entities, no moments.

**Test Questions** (0/10 answerable):
1. "Who is Sarah?"
2. "What resources mention TiDB?"
3. "When did Sarah and Mike meet?"
4. "Find documents about database migration"
5. "What happened this week?"
6. "Show me coding sessions"
7. "What's related to the technical spec?"
8. "Find similar documents to meeting notes"
9. "What connects planning to operations?"
10. "What topics are being discussed?"

**Result**: All queries return empty results.

### Stage 1: Resources Seeded (2/10 Answerable = 20%)

8 resources created with entity extraction complete.

**What works now**:
- Entity lookup via natural text
- SQL filtering by category/metadata

**Newly Answerable Questions**:

**Q1: "Who is Sarah?"**
```python
# User provides natural text (what they know)
REMQueryPlan(
    query_type=LOOKUP,
    parameters=LookupParameters(key="Sarah")  # Not "sarah-chen"
)
```
Expected: System normalizes "Sarah" → "sarah-chen", returns 7/8 resources

**Q2: "What resources mention TiDB?"**
```python
REMQueryPlan(
    query_type=LOOKUP,
    parameters=LookupParameters(key="TiDB")  # Not "tidb"
)
```
Expected: System normalizes "TiDB" → "tidb", returns 6/8 resources

**Still NOT Answerable** (no temporal data):
- "When did Sarah and Mike meet?" → No moments yet
- "What happened this week?" → No temporal boundaries
- "Show me coding sessions" → No moment types

**Still NOT Answerable** (no graph edges):
- "What's related to the technical spec?" → No affinity graph
- "Find similar documents" → No semantic edges
- "What connects planning to operations?" → No graph traversal

### Stage 2: Moments Extracted (5/10 Answerable = 50%)

First-order dreaming complete. Temporal narratives extracted.

**What works now**:
- Temporal range queries
- Moment type filtering
- Person co-occurrence queries

**Newly Answerable Questions**:

**Q3: "When did Sarah and Mike meet?"**
```python
REMQueryPlan(
    query_type=SQL,
    parameters=SQLParameters(
        table_name="moments",
        where_clause="moment_type = 'meeting'"
    )
)
```
Expected: Returns moments with both Sarah and Mike in present_persons

**Q4: "What happened between Nov 1-5?"**
```python
REMQueryPlan(
    query_type=SQL,
    parameters=SQLParameters(
        table_name="moments",
        where_clause="resource_timestamp >= '2025-11-01' AND resource_timestamp <= '2025-11-05'"
    )
)
```
Expected: Returns 3 moments (kickoff, standup, code review)

**Q5: "Show me coding sessions"**
```python
REMQueryPlan(
    query_type=SQL,
    parameters=SQLParameters(
        table_name="moments",
        where_clause="moment_type = 'coding'"
    )
)
```
Expected: Returns development sprint moment

**Still NOT Answerable** (no graph):
- "What's related to the technical spec?" → No affinity edges
- "Find similar documents" → No semantic similarity graph
- "What connects planning to operations?" → No multi-hop traversal

### Stage 3: Affinity Graph Built (8/10 Answerable = 80%)

Second-order dreaming complete. Semantic graph edges created.

**What works now**:
- Semantic similarity search
- Graph edge traversal
- Related resource discovery

**Newly Answerable Questions**:

**Q6: "Find documents about database migration"**
```python
REMQueryPlan(
    query_type=SEARCH,
    parameters=SearchParameters(
        table_name="resources",
        query_text="database migration tidb postgresql",
        limit=5
    )
)
```
Expected: Returns ranked results by semantic similarity:
1. TiDB Migration Technical Specification (0.95)
2. Code Review - Database Migration Module (0.88)
3. TiDB Operations Runbook (0.76)

**Q7: "What's related to the technical spec?"**
```python
# User provides natural text, not resource ID
REMQueryPlan(
    query_type=TRAVERSE,
    parameters=TraverseParameters(
        start_node="TiDB Migration Technical Specification",  # Natural name
        max_depth=1
    )
)
```
Expected: Returns resources connected via affinity edges:
- Code Review (complementary, 0.87 similarity)
- Operations Runbook (sequential, 0.75 similarity)

**Q8: "Find similar documents to meeting notes"**
```python
REMQueryPlan(
    query_type=SEARCH,
    parameters=SearchParameters(
        table_name="resources",
        query_text="Project Alpha Kickoff Meeting Notes",  # Natural name
        limit=3
    )
)
```
Expected: Returns semantically similar resources via embeddings

**Still NOT Answerable** (requires advanced reasoning):
- "What connects planning to operations?" → Multi-hop inference
- "What topics are trending?" → Temporal topic analysis

### Stage 4: Mature Graph (10/10 Answerable = 100%)

Multiple dreaming runs, rich historical data, pattern recognition.

**What works now**:
- Predictive queries
- Pattern inference
- Complex multi-hop reasoning

**Newly Answerable Questions**:

**Q9: "What connects planning to operations?"**
```python
# Multi-hop graph traversal
REMQueryPlan(
    query_type=TRAVERSE,
    parameters=TraverseParameters(
        start_node="Project Alpha Kickoff",
        end_node="TiDB Operations Runbook",
        max_depth=3
    )
)
```
Expected: Path discovered:
Kickoff → Technical Spec → Code Review → Operations Runbook

**Q10: "What topics are being discussed?"**
```python
# Aggregate topic tags across moments
REMQueryPlan(
    query_type=SQL,
    parameters=SQLParameters(
        table_name="moments",
        select_clause="unnest(topic_tags) as topic, count(*) as frequency",
        group_by_clause="topic"
    )
)
```
Expected: Topic frequency analysis showing tidb, project-alpha, performance trending

## Query Complexity Growth

**Stage 1 Queries**: Simple lookups
- "Who is Sarah?" → Entity ID resolution
- Single table, direct match

**Stage 2 Queries**: Temporal reasoning
- "When did Sarah meet Mike?" → Join resources + moments
- Time range filtering

**Stage 3 Queries**: Graph traversal
- "What's related to X?" → Follow affinity edges
- Semantic similarity ranking

**Stage 4 Queries**: Predictive reasoning
- "What should I read next?" → Pattern analysis
- Multi-hop inference, trend detection

## Critical Testing Principle

**Test with what USERS know, not what SYSTEM stores.**

### Correct Testing Approach

```python
# ✅ User provides natural text
LOOKUP "Sarah"                    # What user types
LOOKUP "Project Alpha"            # Natural project name
SEARCH "database migration"       # User's description
TRAVERSE "Kickoff Meeting"        # Document title user remembers

# System responsibilities:
# - Normalize "Sarah" → "sarah-chen"
# - Resolve "Project Alpha" → "project-alpha"
# - Handle variations (SARAH, sarah chen, Sarah Chen)
# - Map document titles to UUIDs
```

### Flawed Testing Approach

```python
# ❌ Testing with internal structures (what judge knows, not user)
LOOKUP "sarah-chen"               # Internal normalized ID
LOOKUP "project-alpha"            # Internal hyphenated format
SQL "entity_id = 'tidb'"          # Internal entity structure
TRAVERSE uuid.uuid4()             # System UUID, not user-facing

# This creates false confidence:
# - Tests pass but user experience fails
# - Validates system internals, not user interface
# - Hides normalization/resolution bugs
```

## Test Data Quality Analysis

### Actual Database Results (Stage 1)

**Entity coverage**:
- sarah-chen: 8/8 resources (100%) - Core team member
- mike-johnson: 7/8 resources (87.5%) - Frequent collaborator
- tidb: 6/8 resources (75%) - Central technology
- project-alpha: 3/8 resources (37.5%) - Project context
- emily-santos: 2/8 resources (25%) - External stakeholder

**Observations**:
- High-frequency entities (Sarah, Mike, TiDB) support rich queries
- Single-occurrence entities (Redis, PostgreSQL) are graph dead-ends
- Good team collaboration pattern (Sarah + Mike in 7/8)

### Expected Moments (Stage 2)

**Temporal distribution**:
- 4 moments across 14-day period
- Good coverage: kickoff, development, review, celebration
- Logical progression: planning → coding → review → success

**Moment quality expectations**:
- Temporal boundaries: start < end, 1 min to 8 hour duration
- Person extraction: 2-3 persons per meeting moment
- Speaker identification: speaking times > 0, total reasonable for duration
- Tag diversity: 3-5 emotion tags, 3-8 topic tags per moment

### Expected Affinity Graph (Stage 3)

**Graph metrics**:
- 15-20 edges expected for 8 resources
- Average degree: 2-3 (not too sparse, not too dense)
- High-similarity pairs (>0.8): 5 expected
- Medium-similarity pairs (0.6-0.8): 8 expected

**Semantic relevance**:
- Connected resources should share >10% word overlap
- Entity-based connections should have valid shared entities
- Bidirectional edges for symmetric relationships

## Quality Failure Modes

**Stage 1 Failures**:
- Entity normalization inconsistent ("Sarah" vs "sarah-chen" vs "Sarah Chen")
- Entity types misclassified (person tagged as concept)
- Coverage too low (<50% for core entities)

**Stage 2 Failures**:
- Temporal boundaries invalid (start >= end)
- Present persons missing or duplicated
- Speakers don't match present persons
- Tags generic or meaningless ("good", "interesting")

**Stage 3 Failures**:
- Unrelated resources connected (random graph)
- All similarity scores 1.0 or 0.0 (no discrimination)
- No bidirectional edges (broken symmetry)
- Graph too sparse (<1.5 avg degree) or too dense (>4 avg degree)

## Validation Scripts

```bash
# Stage 1: Seed data and test entity LOOKUP queries
python scripts/rem/simple_seed.py
python scripts/rem/test_sample_01_queries.py

# Stage 2: Extract moments and validate quality
python scripts/rem/run_dreaming.py --tenant demo-tenant-001 --mode moments --lookback-hours 720
python scripts/rem/validate_moment_quality.py --tenant demo-tenant-001 --verbose
python scripts/rem/test_sample_01_queries.py  # Rerun to test temporal queries

# Stage 3: Build affinity and validate graph
python scripts/rem/run_dreaming.py --tenant demo-tenant-001 --mode affinity --lookback-hours 720
python scripts/rem/validate_affinity_quality.py --tenant demo-tenant-001 --verbose
python scripts/rem/test_sample_01_queries.py  # Rerun to test SEARCH and TRAVERSE
```

**test_sample_01_queries.py** tests actual LOOKUP, SEARCH, and TRAVERSE queries:
- Stage 1: Entity lookups with natural language ("Sarah" not "sarah-chen")
- Stage 2: Temporal/moment queries
- Stage 3: Semantic SEARCH and graph TRAVERSE
- Graph tests: Validate edges use labels (not UUIDs)

Exit codes: 0 = all queries passed, 1 = queries failed/skipped
