# REM Design

REM (Resource-Entity-Moment) is a unified memory infrastructure combining temporal narratives, semantic relationships, and structured knowledge.

## Architecture

### Layers

**Resource Layer**: Base content units (documents, conversations, artifacts)
- Stored in `resources` table
- Tenant-isolated: `tenant_id` column
- Related entities extracted and stored in `related_entities` JSONB field
- Knowledge graph edges stored in `graph_paths` JSONB field as InlineEdge objects

**Entity Layer**: Normalized entities (people, projects, concepts)
- Entity IDs should be user-friendly natural labels ("Sarah Chen", "Project Alpha", file paths)
- Entity types: person, project, technology, concept, meeting_type
- Stored within resource metadata, no separate entity table
- IMPORTANT: KV lookups are designed to be schema agnostic e.g. test-entity can exist in both resources and moments. Ideally we can do fuzzy matching but may not be implemented over all providers (TODO). Lookups are designed to match unique entities or identifiers in text and then query them with LOOKUP. Fuzzy Lookup is a desirable fallback.
- IMPORTANT: Each entity has a neighbourhood of edges. LLMs can retrieve an entity and do entity lookups in the neighbourhood. This is a critical test.
- CRITICAL DESIGN PRINCIPLE: Graph edges should reference entity LABELS (natural language), not UUIDs. This allows LOOKUP operations on labels directly. The surface area is natural language, different from traditional database design where foreign keys use UUIDs. This enables conversational queries without requiring internal ID knowledge.

**Moment Layer**: Temporal narratives (meetings, coding sessions, conversations)
- Stored in `moments` table
- Temporal boundaries: `resource_timestamp` (start), `resource_ends_timestamp` (end)
- Present persons: List of Person objects with id, name, role
- Speakers: List of Speaker objects with name, speaking_time
- Tags: `emotion_tags` (happy, frustrated, focused), `topic_tags` (project names, concepts)
- Summaries: Natural language description of what happened

### Data Models

**Resources Table**:
```sql
CREATE TABLE resources (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    name TEXT NOT NULL,
    content TEXT,
    category VARCHAR(50),
    related_entities JSONB DEFAULT '[]',
    graph_paths JSONB DEFAULT '[]',  -- Stores InlineEdge objects
    resource_timestamp TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);
CREATE INDEX idx_resources_tenant ON resources(tenant_id);
CREATE INDEX idx_resources_timestamp ON resources(resource_timestamp);
CREATE INDEX idx_resources_entities ON resources USING GIN(related_entities);
CREATE INDEX idx_resources_graph_paths ON resources USING GIN(graph_paths);
```

**Moments Table**:
```sql
CREATE TABLE moments (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    name TEXT NOT NULL,
    moment_type VARCHAR(50),
    resource_timestamp TIMESTAMP,
    resource_ends_timestamp TIMESTAMP,
    present_persons JSONB DEFAULT '[]',
    speakers JSONB DEFAULT '[]',
    emotion_tags TEXT[] DEFAULT '{}',
    topic_tags TEXT[] DEFAULT '{}',
    summary TEXT,
    source_resource_ids TEXT[] DEFAULT '{}'
);
CREATE INDEX idx_moments_tenant ON moments(tenant_id);
CREATE INDEX idx_moments_time_range ON moments(resource_timestamp, resource_ends_timestamp);
```

### InlineEdge Structure

Knowledge graph edges use human-readable keys instead of UUIDs, enabling natural language queries.

**InlineEdge Model**:
```python
class InlineEdge:
    dst: str                    # Human-readable destination key (e.g., "tidb-migration-spec")
    rel_type: str              # Relationship type (e.g., "builds-on", "authored_by")
    weight: float              # Relationship strength 0.0-1.0
    properties: dict           # Rich metadata
    created_at: datetime       # Edge creation timestamp
```

**Edge Weight Guidelines**:
- 1.0: Primary/strong relationships (authored_by, owns, part_of)
- 0.8-0.9: Important relationships (depends_on, reviewed_by, implements)
- 0.5-0.7: Secondary relationships (references, related_to, inspired_by)
- 0.3-0.4: Weak relationships (mentions, cites)

**Entity Type Convention** (in properties.dst_entity_type):
- Format: `<schema>[/<category>]`
- Examples: `person/employee`, `document/rfc`, `system/api`, `project/internal`

**Example Edge**:
```json
{
  "dst": "tidb-migration-spec",
  "rel_type": "builds-on",
  "weight": 0.85,
  "properties": {
    "dst_name": "TiDB Migration Technical Specification",
    "dst_id": "550e8400-e29b-41d4-a716-446655440000",
    "dst_entity_type": "document/technical-spec",
    "match_type": "semantic-historical",
    "confidence": 0.92,
    "context": "References migration approach from technical spec"
  },
  "created_at": "2025-01-15T10:00:00Z"
}
```

**Usage in graph_paths**:
```python
resource.graph_paths = [
    {
        "dst": "sarah-chen",
        "rel_type": "authored_by",
        "weight": 1.0,
        "properties": {
            "dst_name": "Sarah Chen",
            "dst_entity_type": "person/employee"
        },
        "created_at": "2025-01-15T10:00:00Z"
    },
    {
        "dst": "tidb-migration-spec",
        "rel_type": "references",
        "weight": 0.7,
        "properties": {
            "dst_name": "TiDB Migration Technical Specification",
            "dst_entity_type": "document/technical-spec",
            "semantic_similarity": 0.88
        },
        "created_at": "2025-01-15T10:05:00Z"
    }
]
```

## Core Design Principle: Iterated Retrieval for LLM-Database Interaction

### The Paradigm Shift

Traditional databases assume **single-shot queries**: the client knows what to ask for and receives complete results in one round trip. This model fails for LLM-augmented retrieval where:

1. **LLMs don't know internal IDs**: They work with natural language, not UUIDs or foreign keys
2. **Information needs emerge incrementally**: Initial queries reveal what to ask next
3. **Multi-stage exploration is essential**: Find entity → explore neighborhood → traverse relationships → refine search

REM is architected specifically for **iterated retrieval**: LLMs conduct multi-turn conversations with the database, refining queries based on intermediate results. This is a fundamentally new usage pattern that did not exist in the pre-LLM era.

### Database-Facilitated Iteration

REM provides explicit primitives to support iterative exploration:

#### 1. Stage Tracking and Memos

Queries return not just data but **execution context** for the next iteration:

```python
# Turn 1: Initial exploration
response = rem_query(
    query_type="traverse",
    parameters={
        "initial_query": "sarah chen",
        "max_depth": 0,  # PLAN mode
        "plan_memo": "Goal: map org chart. Step 1: analyze edges"
    }
)

# Response includes stage info
{
    "nodes": [...],
    "stages": [
        {
            "depth": 0,
            "executed": "LOOKUP sarah chen",
            "found": {"nodes": 1, "edges": 3},
            "plan_memo": "Goal: map org chart. Step 1: analyze edges"
        }
    ],
    "edge_summary": [
        ["sarah-chen", "manages", "bob-smith"],
        ["sarah-chen", "manages", "alice-jones"],
        ["sarah-chen", "reports-to", "cto"]
    ]
}

# Turn 2: LLM sees edges, decides to traverse "manages"
response = rem_query(
    query_type="traverse",
    parameters={
        "initial_query": "sarah chen",
        "edge_types": ["manages"],
        "max_depth": 1,
        "plan_memo": "Goal: map org. Step 2: get direct reports"
    }
)

# Turn 3: LLM decides to go deeper
response = rem_query(
    query_type="traverse",
    parameters={
        "initial_query": "sarah chen",
        "edge_types": ["manages"],
        "max_depth": 2,
        "plan_memo": "Goal: map org. Step 3: complete hierarchy"
    }
)
```

#### 2. PLAN Mode (Depth 0)

Explicit support for **query planning without full execution**:

```python
# LLM can "peek" at available edges before committing to traversal
TRAVERSE WITH LOOKUP sarah DEPTH 0
# Returns: Edge analysis, no traversal
# LLM decides which edges to follow based on analysis
```

This is fundamentally different from traditional databases where you must know the full query upfront.

#### 3. Incremental Depth Control

LLMs control how deep to explore based on intermediate results:

```python
# Start shallow
TRAVERSE manages WITH LOOKUP sarah DEPTH 1  # Direct reports only

# Go deeper if needed
TRAVERSE manages WITH LOOKUP sarah DEPTH 2  # Full team hierarchy

# Adaptive depth based on results
if len(nodes) < 5:
    # Small team, go deeper
    DEPTH 3
else:
    # Large team, stay shallow
    DEPTH 1
```

#### 4. Edge Filtering by Iteration

LLMs discover edge types through iteration, then filter subsequent queries:

```python
# Turn 1: Discover what edges exist
response = rem_query("LOOKUP sarah DEPTH 0")
# Returns: ["manages", "reports-to", "mentors", "collaborates-with"]

# Turn 2: LLM filters based on user intent
response = rem_query("TRAVERSE manages,mentors WITH LOOKUP sarah DEPTH 2")
```

### Natural Language Surface Area

REM exposes **natural language labels**, not internal IDs, enabling LLMs to query without database schema knowledge:

```python
# ✅ LLM-friendly: Natural language
LOOKUP "Sarah Chen"
TRAVERSE manages WITH LOOKUP "Project Alpha"

# ❌ Traditional DB: Requires schema knowledge
SELECT * FROM employees WHERE employee_id = 'e12345'
SELECT * FROM projects WHERE project_uuid = '550e8400-...'
```

This enables conversational iteration:
```
User: "Who works on Project Alpha?"
LLM: LOOKUP "Project Alpha"
→ Finds project-alpha entity with edges to contributors

LLM: TRAVERSE contributed_by WITH LOOKUP "Project Alpha"
→ Returns: Sarah Chen, Bob Smith, Alice Jones

User: "What else has Sarah worked on?"
LLM: LOOKUP "Sarah Chen"
LLM: TRAVERSE authored_by,contributed_to WITH LOOKUP "Sarah Chen"
→ Returns: Sarah's project history
```

### Multi-Stage Retrieval Patterns

#### Pattern 1: Explore-Then-Traverse

```python
# Stage 1: Find entry point
SEARCH "database migration"
→ Returns: 10 relevant documents

# Stage 2: Extract entities from results
# LLM reads documents, identifies key entities: "tidb-migration-spec", "sarah-chen"

# Stage 3: Traverse relationships
TRAVERSE builds-on,references WITH LOOKUP "tidb-migration-spec"
→ Returns: Related technical specs and implementation docs
```

#### Pattern 2: Progressive Refinement

```python
# Stage 1: Broad semantic search
SEARCH "team performance" LIMIT 20

# Stage 2: LLM identifies relevant entities
# Extracts: "Q4-retrospective", "team-velocity-metrics"

# Stage 3: Refine with entity lookup
LOOKUP "Q4-retrospective"
→ Returns: Specific moment with present_persons, emotion_tags

# Stage 4: Expand to related moments
TRAVERSE temporal_proximity WITH LOOKUP "Q4-retrospective" DEPTH 1
→ Returns: Moments before/after retrospective
```

#### Pattern 3: Entity Neighborhood Exploration

```python
# Stage 1: Find entity
LOOKUP "sarah chen"

# Stage 2: Analyze neighborhood (PLAN mode)
TRAVERSE WITH LOOKUP "sarah chen" DEPTH 0
→ Returns: Edge summary without full traversal
# Edges: manages(2), reports-to(1), authored_by(15), mentors(3)

# Stage 3: LLM selects relevant edges
TRAVERSE authored_by WITH LOOKUP "sarah chen" DEPTH 1 LIMIT 5
→ Returns: Sarah's top 5 recent documents

# Stage 4: Follow reference chain
# LLM identifies document "api-design-v2" in results
TRAVERSE references,builds-on WITH LOOKUP "api-design-v2" DEPTH 2
→ Returns: Design lineage and dependencies
```

### Why This Matters

Traditional databases optimize for:
- **Known queries**: Client knows exactly what to retrieve
- **Single-shot execution**: Get all data in one query
- **Schema knowledge**: Client understands table structure and foreign keys

REM optimizes for:
- **Emergent queries**: Information needs discovered through exploration
- **Multi-turn retrieval**: Each query informs the next
- **Schema-free interface**: Natural language labels replace internal IDs

This architectural choice enables LLMs to act as **intelligent database explorers** rather than requiring humans to manually construct complex queries. The database becomes a conversational partner in information retrieval, not just a passive data store.

### Implementation Guarantees for Iteration

1. **Stateless Queries**: Each query is independent; LLM maintains conversation state
2. **Stage Echo**: Query responses echo the `plan_memo` for LLM context continuity
3. **Edge Metadata**: Every response includes edge summary for next-step planning
4. **Depth Flexibility**: LLMs can PLAN (depth 0), test (depth 1), or explore deeply (depth N)
5. **Label Stability**: Entity labels are persistent, enabling cross-session iteration

## Dreaming Workflows

### First-Order Dreaming: Moment Extraction

Extracts temporal narratives from resources.

**Input**: Resources within lookback window (e.g., last 24 hours)

For example users interact both via Chat Sessions or Via file uploads. Collectively these can be used to construct classified time periods when the user was caring about X.

**Process**:
1. Query resources by tenant and time range
2. For each resource, LLM extracts:
   - Temporal boundaries (start/end timestamps)
   - Present persons (who was involved)
   - Speakers (who spoke, how long)
   - Emotion tags (team sentiment)
   - Topic tags (what was discussed)
   - Natural language summary
3. Store moment in `moments` table

**Output**: Moments with temporal structure and metadata

**Execution Modes**:
- `batch`: NATS message queue for worker scaling
- `direct`: Synchronous execution for testing
- `scheduled`: Kubernetes CronJob (every 6 hours)

### Second-Order Dreaming: Resource Affinity

Creates semantic graph edges between resources.

**Input**: Resources and their embeddings

**Process**:
1. Query resources by tenant
2. For each resource:
   - Find semantically similar resources via vector search
   - Identify entity-based connections (shared people, projects)
   - Calculate similarity scores
3. Build graph edges in `graph_paths` field
4. Always UPSERT i.e. do not overwrite graph paths but use a merge strategy. (TODO critical test)

**Output**: Resource affinity graph for traversal queries

**Graph Path Format**:
```
/resources/{source_name}/related/{target_name}
/resources/{source_name}/entity/{entity_label}/{target_name}
```

**CRITICAL**: Graph edges use natural language labels (resource names, entity labels), NOT UUIDs. This differs from traditional database design but is essential for conversational interface. Users can LOOKUP by label without knowing internal IDs. Example: `/resources/Project Alpha Kickoff/entity/Sarah Chen/TiDB Technical Spec` allows direct label-based traversal.

**Execution Modes**:
- `batch`: NATS workers process affinity jobs
- `direct`: Synchronous execution for testing
- `scheduled`: Kubernetes CronJob (daily at 2 AM)

## Graph Storage

### JSONB Paths (Current Implementation)

Fast 1-hop queries using array operations.

**Storage**: `graph_paths TEXT[]` column in `resources` table

**Query Example** (find resources related to resource A):
```sql
SELECT * FROM resources
WHERE graph_paths && ARRAY['/resources/{A}/related/*'];
```

**Performance**: O(1) lookup for direct connections, no multi-hop support

### Apache AGE (PostgreSQL Local)

Cypher query support for multi-hop traversal.

**Storage**: Graph nodes/edges in AGE extension

**Query Example**:
```cypher
MATCH (r:Resource {id: 'A'})-[:RELATED*1..3]-(connected)
RETURN connected;
```

**Performance**: Supports complex traversals, slower than JSONB for simple queries

### TiKV Graph (Cluster)

Distributed graph storage for production.

**Storage**: Key-value pairs in TiKV with graph encoding

**Status**: Research phase, not yet implemented

## REM Queries

### Query Contract

**CRITICAL**: All REM providers MUST implement these performance and schema guarantees. Providers that cannot meet these requirements break the REM contract.

| Query Type | Performance | Schema | Multi-Match | Required |
|------------|-------------|--------|-------------|----------|
| LOOKUP | **O(1)** | Agnostic | Yes | ✅ MANDATORY |
| FUZZY | **Indexed** | Agnostic | Yes | ✅ MANDATORY |
| SEARCH | **Indexed** | Specific | Yes | ✅ MANDATORY |
| SQL | O(n) | Specific | No | ✅ MANDATORY |
| TRAVERSE | **O(k)** where k=keys | Agnostic | Yes | ✅ MANDATORY |

**Contract Violations**:
- ❌ KV scan for LOOKUP (must be O(1) indexed lookup, not scan)
- ❌ Table scan for FUZZY (must use inverted index or FTS)
- ❌ Requiring table name for LOOKUP (must be schema-agnostic)
- ❌ Linear scan for SEARCH (must use vector index)

### Query Types

**LOOKUP**: O(1) schema-agnostic entity resolution
- **Performance**: O(1) - Single key lookup, not scan
- **Schema**: Agnostic - No table name required
- **Multi-match**: Returns entities from ALL tables with matching key
- **Parameter**: `key` (entity identifier)
- **Use case**: "Who is Sarah?" → Find all entities named "sarah" across all tables
- **Why it matters**: LOOKUP is the only way to find entities without knowing which table they're in. If you know the table, use SQL instead.

**Provider Implementations**:
- PostgreSQL: AGE graph `get_entities(keys)` → O(1) graph vertex lookup
- TiDB: TiKV reverse mapping `{tenant}/{key}/{type}` → O(1) KV get + binary key access

**SEARCH**: Indexed semantic vector search
- **Performance**: Indexed - Vector index required (e.g., IVF, HNSW)
- **Schema**: Table-specific - Requires table name
- **Parameter**: `query_text`, `table_name`
- **Use case**: "database migration" → Find semantically similar resources

**Provider Implementations**:
- PostgreSQL: pgvector with IVF/HNSW index
- TiDB: Vector index with VEC_COSINE_DISTANCE()

**FUZZY**: Indexed fuzzy text matching
- **Performance**: Indexed - FTS or trigram index required
- **Schema**: Agnostic - Searches across all entity names
- **Multi-match**: Returns entities from ALL tables matching fuzzy pattern
- **Parameters**: `query_text`, `threshold` (default: 0.5), `limit` (default: 5)
- **Use case**: "find afternoon" → Matches "Friday Afternoon", "Monday Afternoon"

**Provider Implementations**:
- PostgreSQL: pg_trgm GIN index on AGE graph vertices
- TiDB: FULLTEXT index on kv_entity_mapping.entity_name with FTS_MATCH_WORD()

**SQL**: Direct table queries (provider dialect)
- **Performance**: O(n) - Table scan with optional indexes
- **Schema**: Table-specific - Requires table name and column knowledge
- **Parameter**: `table_name`, `where_clause`
- **Use case**: Filter resources by category, date range, metadata
- **Provider-specific**: Uses native SQL dialect (PostgreSQL, MySQL/TiDB)

**TRAVERSE**: Iterative O(1) lookups on graph edges
- **Performance**: O(k) where k = number of keys traversed
- **Schema**: Agnostic - Follows graph edges across tables
- **Multi-match**: Returns nodes from multiple tables via edges
- **Implementation**: Iterative LOOKUP calls on edge destinations
- **Syntax**: `TRAVERSE {edge_filter} WITH [REM_QUERY] DEPTH [0-N]`
- **Use case**: "Who reports to Sally?" → `TRAVERSE reports-to WITH LOOKUP sally DEPTH 2`

**Provider Implementations**:
- PostgreSQL: AGE Cypher traversal or iterative get_entities()
- TiDB: Iterative TiKV reverse mapping lookups

### Why the Contract Matters

**Schema-Agnostic Operations Are the Core Value Proposition**

The REM contract exists to enable a fundamentally different query model than SQL:

1. **LOOKUP without knowing the schema**
   - Traditional: "I need to query resources table for name='sarah'" (requires schema knowledge)
   - REM: "Find all entities named 'sarah'" (no schema knowledge needed)
   - **Value**: LLMs can query data without knowing table structure

2. **O(1) performance guarantee**
   - Traditional: Full table scans or complex joins
   - REM: Direct index access via reverse mapping
   - **Value**: Predictable performance regardless of data size

3. **Multi-table results**
   - Traditional: Union queries across known tables
   - REM: Single LOOKUP returns entities from all tables
   - **Value**: Discover entities across heterogeneous schemas

**Contract-Compliant vs Contract-Violating**

✅ **Compliant PostgreSQL LOOKUP**:
```sql
-- O(1) via AGE graph index
SELECT * FROM p8.get_entities(ARRAY['sarah'], 'tenant-id');
-- Returns: sarah from resources, moments, agents, files (all tables)
-- Performance: O(1) per entity via graph vertex index
```

❌ **Violating "LOOKUP"** (actually just SQL):
```sql
-- O(n) table scan
SELECT * FROM resources WHERE tenant_id = %s AND name LIKE '%sarah%';
-- Returns: Only resources table
-- Performance: O(n) - scans entire table
-- Schema: Requires knowing table name
```

✅ **Compliant TiDB LOOKUP**:
```python
# O(1) via TiKV reverse mapping
prefix = f"{tenant_id}/{entity_name}/"
mappings = tikv.scan(prefix)  # Finds all entity types
for mapping in mappings:
    entity = get_by_binary_key(mapping['tidb_key'])  # O(1) access
# Returns: sarah from resources, moments, agents (all tables)
# Performance: O(1) per entity type via KV index
```

❌ **Violating TiDB "FUZZY"** (slow scan):
```python
# O(n) - scans all KV entries
for key, value in tikv.scan_all():  # Scans entire keyspace!
    if similarity(key, search_term) > threshold:
        results.append(value)
# Performance: O(n) - violates contract
```

✅ **Compliant TiDB FUZZY**:
```sql
-- Uses FULLTEXT index on kv_entity_mapping
SELECT * FROM kv_entity_mapping
WHERE tenant_id = %s
AND FTS_MATCH_WORD(%s, entity_name) > 0
ORDER BY FTS_MATCH_WORD(%s, entity_name) DESC;
-- Performance: Indexed - uses inverted index
```

### Contract Implementation Checklist

Before deploying a REM provider, verify:

- [ ] **LOOKUP**: Can find entity without table name
- [ ] **LOOKUP**: O(1) performance (not table scan)
- [ ] **LOOKUP**: Returns entities from multiple tables
- [ ] **FUZZY**: Uses inverted index (not KV scan)
- [ ] **FUZZY**: Schema-agnostic (searches all entity names)
- [ ] **SEARCH**: Uses vector index (not table scan)
- [ ] **TRAVERSE**: O(k) where k=keys (iterative LOOKUP, not recursive SQL)
- [ ] **SQL**: Supports provider-specific dialect

### TRAVERSE Query Details

TRAVERSE orchestrates multi-hop graph traversal by combining an initial REM query with iterative edge following.

#### Syntax

```
TRAVERSE {edge_filter}
WITH [REM_QUERY]
DEPTH [0-N]
ORDER BY [field] [ASC|DESC]
LIMIT N
```

#### Components

1. **Edge Filter** (Optional)
   - Comma-separated list of edge types: `manages`, `reports-to,manages`
   - Default: `*` (all edge types)
   - Filters which edges to follow during traversal

2. **WITH Clause** (Required)
   - Initial query to find entry nodes
   - Can be any REM query: `LOOKUP key`, `SEARCH "text"`, `SELECT * FROM table WHERE ...`
   - Default if omitted: `LOOKUP`

3. **DEPTH** (Optional)
   - `0`: PLAN mode (analyze edges without traversal)
   - `1`: Single-hop traversal (default)
   - `N`: Multi-hop traversal (N hops from source)

4. **ORDER BY** (Optional)
   - Field to order results: `edge.created_at`, `node.name`, `edge.weight`
   - Direction: `ASC` or `DESC`
   - Default: `edge.created_at DESC`

5. **LIMIT** (Optional)
   - Maximum nodes to return
   - Default: `9`
   - Applied after traversal and ordering

#### Response Structure

```json
{
  "nodes": [
    {
      "id": "uuid",
      "name": "sally",
      "category": "person",
      "_traverse_depth": 0,
      "_traverse_path": ["sally"],
      "content": "...",
      "graph_paths": [...]
    }
  ],
  "stages": [
    {
      "depth": 0,
      "executed": "LOOKUP sally",
      "found": {"nodes": 1, "edges": 3},
      "plan_memo": "Goal: Map Sally's team. Step 1: Found Sally with 3 edges"
    },
    {
      "depth": 1,
      "executed": "LOOKUP bob, alice (via manages edges)",
      "found": {"nodes": 2, "edges": 5},
      "plan_memo": "Goal: Map Sally's team. Step 2: Found 2 direct reports"
    }
  ],
  "source_nodes": ["sally"],
  "edge_summary": [
    ["sally", "manages", "bob"],
    ["sally", "manages", "alice"]
  ],
  "metadata": {
    "total_nodes": 3,
    "total_edges": 5,
    "unique_nodes": 3,
    "node_uniqueness_guaranteed": true,
    "max_depth_reached": 1,
    "edge_filter": ["manages"],
    "order_by": "edge.created_at DESC",
    "limit_applied": 9
  }
}
```

#### Examples

**Basic single-hop**:
```
TRAVERSE manages WITH LOOKUP sally
```
Returns Sally + her direct reports (bob, alice)

**Multi-hop with limit**:
```
TRAVERSE manages WITH LOOKUP sally DEPTH 2 LIMIT 5
```
Returns Sally + team hierarchy (depth 2), top 5 nodes

**PLAN mode (depth 0)**:
```
TRAVERSE WITH LOOKUP sally DEPTH 0
```
Returns edge analysis without full traversal

**Custom ordering**:
```
TRAVERSE reports-to WITH SELECT * FROM resources WHERE category = 'person' ORDER BY node.name ASC
```
Returns reporting hierarchy ordered by name

**Multiple edge types**:
```
TRAVERSE manages,mentors WITH LOOKUP sally DEPTH 3 LIMIT 10
```
Follows both "manages" and "mentors" edges up to 3 hops

#### Implementation Guarantees

1. **Node Uniqueness**: Visited keys tracked to prevent duplicates
2. **Edge Ordering**: Edges sorted by `created_at DESC` before following
3. **Stage Information**: Captures query execution details for LLM interaction
4. **Edge Shorthand**: Returns `(src, type, dst)` tuples for analysis
5. **Depth 0 = PLAN**: Equivalent to edge analysis without traversal

### Query Interface

Users interact via:
1. **Direct REM queries**: Construct REMQueryPlan objects
2. **ask_rem()**: Natural language to REM query conversion (LLM-powered)

**Critical constraint**: Users provide what they KNOW (natural text), not internal IDs.

Example:
- User query: "Who is Sarah?"
- REM query: `LOOKUP "Sarah"` (not "sarah-chen")
- System resolves to normalized entity ID

### Agent Scratchpad: Stage Memos

**Important**: REM does NOT inject intelligence. Stage info is **agent-maintained memory**.

**Purpose**: Agents maintain a terse scratchpad across multi-turn traversals to track:
- Goal: Where I'm trying to get
- Progress: What I've executed so far
- Next: What I plan to do next

**Structure** (kept TERSE for fast token generation):
```python
TraverseParameters(
    initial_query="sarah chen",
    max_depth=1,
    plan_memo="Goal: org chart. Step 1: find CEO"  # Agent's scratchpad
)
```

**Response echoes agent's memo**:
```json
{
  "stages": [
    {
      "depth": 0,
      "executed": "LOOKUP sarah chen",
      "found": {"nodes": 1, "edges": 3},
      "plan_memo": "Goal: org chart. Step 1: find CEO"  // Agent's memo echoed
    }
  ]
}
```

**Multi-turn pattern**:
```
Turn 1: plan_memo="Goal: org. PLAN mode"
        → System returns edge analysis + memo

Turn 2: plan_memo="Goal: org. Step 2: depth=1 on reports-to"
        → System returns nodes at depth 1 + memo

Turn 3: plan_memo="Goal: org. Step 3: depth=2, complete"
        → System returns full hierarchy + memo
```

### ask_rem() with Staged Planning

The REM agent (LLM-powered natural language interface) can generate:
1. **query**: The REM query to execute
2. **staged_plan**: Terse multi-step plan for continuation

**Example**:
```python
# User: "Show me Sarah's organization chart"
ask_rem("Show me Sarah's organization chart")

# Returns:
{
  "query": {
    "query_type": "traverse",
    "parameters": {
      "initial_query": "sarah chen",
      "edge_types": ["reports-to", "manages"],
      "max_depth": 0,  # Start with PLAN
      "plan_memo": "Goal: Sarah's org chart. Step 1: analyze edges"
    }
  },
  "staged_plan": [
    "Step 1: PLAN mode (depth=0) - analyze available edges",
    "Step 2: depth=1 - find direct reports",
    "Step 3: depth=2 - complete hierarchy"
  ]
}
```

**Note**: Keep staged_plan TERSE (3-5 words per step) to minimize token generation latency.

## Performance Characteristics

**Resource Retrieval**: 10-50ms (indexed tenant + timestamp)
**Entity Lookup**: 5-20ms (GIN index on JSONB)
**Vector Search**: 50-200ms (depends on embedding count)
**Graph Traversal (JSONB)**: 10-30ms (1-hop)
**Graph Traversal (AGE)**: 100-500ms (multi-hop)
**Moment Extraction**: 2-5s per resource (LLM latency)
**Affinity Calculation**: 5-10s per resource (vector + LLM)

## Future: Schema Registry and Ontology Discovery

### Current Design Assumptions

REM currently operates on two core schema types:

- **Resources**: Base content units (documents, conversations, artifacts)
- **Moments**: Temporal narratives (meetings, coding sessions, conversations)

This is sufficient for personal memory and knowledge management but limits enterprise applications with domain-specific data models.

### Schema Registry Extension

#### Concept

Enable tenants to register custom schemas beyond resources and moments:

```python
# Example: Enterprise schema registration
schema_registry.register(
    tenant_id="acme-corp",
    schema_name="customer_interactions",
    fields={
        "customer_id": "string",
        "interaction_type": "enum(call,email,meeting)",
        "outcome": "string",
        "sentiment": "float",
        "related_entities": "jsonb",
        "graph_paths": "jsonb"  # Graph capabilities preserved
    },
    entity_types=["customer", "product", "support_agent"],
    graph_enabled=True
)
```

#### Design Principles

1. **Preserve Graph Semantics**: All registered schemas inherit:
   - `related_entities` JSONB field for entity tracking
   - `graph_paths` JSONB field for InlineEdge storage
   - Label-based graph traversal (not UUID-based)

2. **No Joins, Only Traversal**: Schema registry does NOT support traditional SQL joins. Related data is accessed via:
   - LOOKUP operations on entity labels
   - TRAVERSE queries following graph edges
   - Entity neighborhood exploration

3. **Tenant Isolation**: Each tenant maintains independent schema registry entries

4. **JSONB Flexibility**: Custom fields stored as JSONB metadata, avoiding schema migration overhead

#### Implementation Model

```python
class SchemaDefinition:
    tenant_id: str
    schema_name: str
    base_fields: dict  # Core typed fields
    metadata_schema: dict  # JSONB validation schema
    entity_types: List[str]  # Valid entity types for this schema
    edge_types: List[str]  # Valid edge relationship types
    graph_enabled: bool = True

# Dynamic table generation
CREATE TABLE {tenant_id}_{schema_name} (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    name TEXT NOT NULL,
    related_entities JSONB DEFAULT '[]',  -- Always present
    graph_paths JSONB DEFAULT '[]',       -- Always present
    metadata JSONB DEFAULT '{}'           -- Schema-specific fields
);
```

### Ontology Discovery Tools

#### PostgreSQL Schema Introspection

Tool to analyze existing PostgreSQL databases and generate REM schema registry entries:

```python
# Example: Discover schema from existing database
discovered_schema = ontology_discovery.introspect_postgres(
    connection_string="postgresql://...",
    tables=["customers", "orders", "support_tickets"],
    extract_relationships=True
)

# Auto-generate schema registration
schema_registry.register_from_discovery(
    tenant_id="acme-corp",
    discovered_schema=discovered_schema,
    entity_mapping={
        "customers.customer_id": "customer",
        "orders.product_id": "product",
        "support_tickets.agent_id": "support_agent"
    }
)
```

#### Discovery Capabilities

1. **Table Structure**: Extract columns, types, constraints
2. **Foreign Key Relationships**: Convert to REM graph edges (label-based, not FK-based)
3. **Entity Identification**: Detect entity columns via heuristics (name patterns, uniqueness)
4. **Edge Type Inference**: Map FK relationships to edge types (e.g., `customer_id` → `belongs_to` edge)

#### Graph Edge Generation

Traditional foreign keys become label-based graph edges:

```python
# SQL Foreign Key:
# orders.customer_id → customers.id

# Becomes REM Edge:
{
    "dst": "customer-12345",  # Label, not UUID
    "rel_type": "belongs_to",
    "weight": 1.0,
    "properties": {
        "dst_entity_type": "customer",
        "dst_name": "Acme Corporation",
        "source_fk": "customer_id"
    }
}
```

**Critical Difference**: Graph edges reference entity LABELS (natural identifiers like customer names, product SKUs) instead of internal UUIDs. This preserves REM's conversational query model.

### No Joins Philosophy

#### Why No Joins

1. **Graph Traversal is Sufficient**: Multi-hop TRAVERSE queries replace complex JOIN operations
2. **Entity Labels > Foreign Keys**: Natural language labels enable conversational queries without knowing internal IDs
3. **Performance**: JSONB array operations + GIN indexes outperform joins for 1-2 hop queries
4. **Scalability**: Graph-based approach distributes better across TiKV than relational joins

#### Query Pattern Migration

```sql
-- Traditional SQL JOIN
SELECT c.name, o.total, p.name
FROM customers c
JOIN orders o ON c.id = o.customer_id
JOIN products p ON o.product_id = p.id
WHERE c.customer_id = 12345;

-- REM TRAVERSE (no joins)
TRAVERSE belongs_to,contains
WITH LOOKUP customer-12345
DEPTH 2
```

#### Benefits

- Natural language query interface (LOOKUP by label)
- No schema migration overhead when adding relationships
- Horizontal scaling via graph partitioning
- Entity neighborhoods cached for fast neighborhood queries

### Implementation Roadmap

#### Phase 1: Schema Registry Core

- Tenant schema registration API
- Dynamic JSONB metadata validation
- Schema versioning support

#### Phase 2: PostgreSQL Discovery

- Table introspection tool
- Foreign key to edge mapping
- Entity label extraction heuristics

#### Phase 3: Advanced Discovery

- MySQL/TiDB schema discovery
- MongoDB collection schema inference
- Snowflake/data warehouse introspection

#### Phase 4: Ontology Management

- Schema evolution tools
- Entity type taxonomy management
- Edge type standardization across tenants

### Research Questions

1. **Schema Versioning**: How to handle schema evolution without breaking existing queries?
2. **Cross-Schema Traversal**: Can edges span different schema types (e.g., customer → moment)?
3. **Entity Resolution**: How to unify entities discovered from different source databases?
4. **Performance at Scale**: Do JSONB graph paths scale to enterprise datasets (millions of entities)?

### Example Use Case: CRM Integration

```python
# Discover existing CRM schema
crm_schema = ontology_discovery.introspect_postgres(
    connection_string=crm_db_url,
    tables=["contacts", "accounts", "opportunities"]
)

# Register as REM schema
schema_registry.register(
    tenant_id="sales-team",
    schema_name="crm_data",
    discovered_schema=crm_schema,
    entity_mapping={
        "contacts.email": "contact",
        "accounts.account_name": "account",
        "opportunities.deal_name": "opportunity"
    }
)

# Query via REM (no joins)
query = """
TRAVERSE owns,associated_with
WITH LOOKUP john.doe@example.com
DEPTH 2
"""

# Returns: Contact → Accounts → Opportunities via graph traversal
```

This approach enables REM to serve as a universal query layer over existing enterprise databases without requiring schema migration or complex ETL pipelines.

## Future Optimizations

### TRAVERSE Performance Optimization (TODO)

**Current State** (as of 2025-11-16):
- Python-layer implementation with batched SQL queries
- Performance: ~1.5s (depth 2), ~2.5s (depth 3), ~3s (depth 4)
- Batching optimization achieved 3x improvement (from ~5-9s to ~1.5-3s)
- Status: Meets depth 4 SLA (<3s), close to depth 2/3 targets

**Remaining Bottlenecks**:
1. KV scans still sequential (one per key)
2. Python-layer graph traversal overhead
3. JSON parsing of graph_paths at each hop
4. Network round trips between application and database

**Future Optimization Opportunities**:

#### 1. Database Push-Down (High Impact)
Implement TRAVERSE as a database-level function to eliminate round trips.

**PostgreSQL Example**:
```sql
CREATE OR REPLACE FUNCTION traverse_graph(
    p_tenant_id TEXT,
    p_start_key TEXT,
    p_max_depth INT,
    p_edge_types TEXT[]
) RETURNS TABLE(
    entity JSONB,
    depth INT,
    path TEXT[]
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE graph_traversal AS (
        -- Base case: Initial lookup from KV
        SELECT
            r.data::JSONB as entity,
            0 as depth,
            ARRAY[p_start_key] as path
        FROM kv_lookup(p_tenant_id, p_start_key) kv
        JOIN resources r ON r.id = kv.entity_id

        UNION ALL

        -- Recursive case: Follow edges
        SELECT
            next.data::JSONB,
            gt.depth + 1,
            gt.path || edge.dst
        FROM graph_traversal gt
        CROSS JOIN LATERAL (
            SELECT jsonb_array_elements(gt.entity->'graph_paths') as edge_data
        ) edges
        CROSS JOIN LATERAL (
            SELECT
                edge_data->>'dst' as dst,
                edge_data->>'rel_type' as rel_type
        ) edge
        JOIN kv_lookup(p_tenant_id, edge.dst) kv ON true
        JOIN resources next ON next.id = kv.entity_id
        WHERE gt.depth < p_max_depth
          AND (p_edge_types IS NULL OR edge.rel_type = ANY(p_edge_types))
          AND NOT (edge.dst = ANY(gt.path))  -- Cycle detection
    )
    SELECT * FROM graph_traversal;
END;
$$ LANGUAGE plpgsql;
```

**Expected Impact**: 10-100x improvement (eliminates Python overhead and round trips)

#### 2. Parallel KV Scans (Medium Impact)
Use ThreadPoolExecutor to parallelize KV scans for multiple keys.

**Implementation**:
```python
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(kv.scan, f"{tenant_id}/{key}/"): key for key in keys}
    results = [future.result() for future in concurrent.futures.as_completed(futures)]
```

**Expected Impact**: 2-5x improvement for multi-key lookups

#### 3. Connection Pooling Optimization (Low Impact)
Ensure efficient connection reuse across batched queries.

**Expected Impact**: 10-20% improvement

#### 4. Result Caching (Medium Impact)
Cache frequently traversed subgraphs to avoid repeated computation.

**Expected Impact**: 5-10x for repeated queries

#### 5. Breadth Limiting (Low Impact)
Limit number of edges followed per node to prevent exponential growth.

**Expected Impact**: Predictable performance, prevents worst-case scenarios

**Priority Order** (when ready to optimize):
1. Database push-down (PostgreSQL, TiDB, RocksDB implementations)
2. Parallel KV scans
3. Result caching
4. Connection pooling refinement
5. Breadth limiting

**Note**: Current Python-layer implementation with batching is acceptable for testing and validation. Database push-down should be implemented when moving to production scale.
