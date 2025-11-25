# REM Testing

## Testing Philosophy

**Success metric**: REM queries get richer over time as the graph matures.

**NOT success**: Scripts run without exceptions.

**Critical principle**: Test with USER-KNOWN information, never internal IDs. Also: Do not use anything that is internal knowledge such as internal representations. We are testing the surface boundary i.e. queries under uncertainty. For example, a user might ask who is Sarah or who is SaRa and we need to match fuzzy or exactly entity lookups. IMPORTANT: The JUDGE must not use HOLD OUT information when constructing tests i.e. data used in sample data that a caller would not see initially. If this data is discovered with iterative queries then this IS legit. 

## Query Evolution Stages

### Stage 0: No Data (0% answerable)
No resources, no entities, no moments. All queries fail.

### Stage 1: Resources Seeded (20% answerable)
Resources with entity extraction complete.

**Answerable queries**:
- "Show resources about TiDB" → SQL query filtering by entity
- "Lookup Sarah" → Returns resources mentioning Sarah

**Not answerable**:
- "When did Sarah meet Mike?" → No temporal data
- "What's related to migration?" → No affinity graph

### Stage 2: Moments Extracted (50% answerable)
First-order dreaming complete.

**Newly answerable**:
- "When did Sarah meet Mike?" → Query moments with both present
- "What happened between Nov 1-5?" → Temporal range query
- "Find coding sessions" → Filter by moment_type

**Still not answerable**:
- "What connects planning to operations?" → No graph edges
- "Find resources similar to X" → No affinity

### Stage 3: Affinity Graph Built (80% answerable)
Second-order dreaming complete.

**Newly answerable**:
- "What's related to the technical spec?" → Traverse affinity graph
- "Find documents similar to meeting notes" → Semantic search
- "What connects planning to operations?" → Multi-hop graph query

**Still not answerable**:
- "What should I read next?" → Requires recommendation model

### Stage 4: Mature Graph (100% answerable)
Multiple dreaming runs with rich historical data.

**Newly answerable**:
- "What should I read next?" → Predictive queries based on patterns
- "Who works with whom?" → Inferred from co-occurrence patterns
- "What topics are trending?" → Temporal topic analysis
- "How did i spent my time yesterday" -> Query and summarize moments if available
## Test Data Requirements

### Sample 01: Project Alpha (8 resources, 14 days)

**People**: sarah-chen, mike-johnson, emily-santos
**Project**: project-alpha
**Concepts**: tidb, database-migration, api-performance, operations

**Note on entity IDs**: Current sample data uses hyphenated lowercase IDs (sarah-chen, project-alpha) which are technically internal representations. This is slightly flawed - entity labels should typically be user-friendly natural labels that appear in conversations ("Sarah Chen", "Project Alpha"). Future samples should use natural entity labels. Exceptions are acceptable for product codes, unique identifiers, file URIs/names where the technical representation is the natural form.

**Coverage expectations**:
- Core team members (Sarah, Mike): 85%+ of resources
- Central technology (TiDB): 75%+ of resources
- Project: 40%+ of resources

**Expected moments**: 4-5
- Meeting: Project kickoff
- Coding: Development sprint
- Meeting: Code review
- Conversation: Team celebration

**Expected affinity edges**: 15-20
- High similarity (>0.8): 5 pairs
- Medium similarity (0.6-0.8): 8 pairs
- Entity-based connections: 12+ edges

## Quality Validation

### Moment Quality (8 Checks)

**1. Temporal Validity**
- Start < end
- Duration: 1 min to 8 hours
- No null timestamps for temporal moments

**2. Person Extraction**
- Meetings have present_persons
- Person objects have id, name, role
- No duplicate persons

**3. Speaker Identification**
- Speakers match present_persons
- Speaking times > 0
- Total speaking time reasonable for duration

**4. Tag Quality**
- Emotion tags: 1-5 per moment
- Topic tags: 1-10 per moment
- Tags are meaningful (not generic)

**5. Content Quality**
- Summary exists and non-empty
- Summary length: 20-200 characters
- Summary matches moment content

**6. Entity References**
- Source resources exist
- Entity IDs normalized correctly
- No orphaned references

**7. Temporal Coverage**
- Good distribution across time period
- No massive gaps (>7 days)
- Activity clusters make sense

**8. Moment Type Distribution**
- Diverse types (meeting, coding, conversation)
- Types match content
- Not all moments same type

### Affinity Quality (7 Checks)

**1. Edge Existence**
- 70%+ resources have connections
- Not all isolated
- Not fully connected (too dense)

**2. Edge Format**
- Valid UUID paths
- Proper path structure
- No malformed edges

**3. Semantic Relevance**
- Connected resources share >10% word overlap
- Similar topics/entities
- Not randomly connected

**4. Bidirectional Edges**
- High-similarity pairs have reciprocal links
- Symmetry in graph

**5. Entity Connections**
- Entity-based paths valid
- Entity IDs normalized
- Connections make sense

**6. Graph Connectivity**
- Average degree: 2-3
- Few isolated nodes (<10%)
- Reasonable clustering

**7. Edge Distribution**
- Not too skewed (one resource with 100 edges)
- Balanced connectivity
- Follows power law distribution

## Test Scripts

### Seed Test Data
```bash
python scripts/rem/simple_seed.py
```
Creates 8 resources for demo-tenant-001.

### Run Dreaming Workers
```bash
# First-order (moments)
python scripts/rem/run_dreaming.py --tenant demo-tenant-001 --mode moments --lookback-hours 720

# Second-order (affinity)
python scripts/rem/run_dreaming.py --tenant demo-tenant-001 --mode affinity --lookback-hours 720

# Both
python scripts/rem/run_dreaming.py --tenant demo-tenant-001 --mode both --lookback-hours 720
```

### Validate Quality
```bash
# Moment quality (exit 0 = pass, 1 = fail)
python scripts/rem/validate_moment_quality.py --tenant demo-tenant-001 --verbose

# Affinity quality
python scripts/rem/validate_affinity_quality.py --tenant demo-tenant-001 --verbose
```

### Test REM Queries
```bash
# All test questions
python scripts/rem/test_rem_queries.py --tenant demo-tenant-001

# Specific category
python scripts/rem/test_rem_queries.py --tenant demo-tenant-001 --category temporal
```

## Realistic Test Queries

**User-known queries** (what users actually provide):

```python
# ✅ CORRECT - User provides natural text
LOOKUP "Sarah"  # Not "sarah-chen"
LOOKUP "Project Alpha"  # Not "project-alpha"
LOOKUP "Sarah", "Mike", "Emily"  # Multiple keys (comma-separated)
LOOKUP Sarah, Mike  # Multiple keys without quotes
GET doc1, doc2, doc3  # GET alias also supports multiple keys
SEARCH "database migration to TiDB"  # Natural language
SQL "category = 'meeting_notes'"  # Observable field
TRAVERSE "Kickoff Meeting"  # Natural document name

# ❌ WRONG - Judge knows internal IDs
LOOKUP "sarah-chen"  # User doesn't know normalization
LOOKUP "project-alpha"  # User doesn't know hyphenation
SEARCH "entity_id = 'tidb'"  # Internal structure
TRAVERSE uuid.uuid4()  # System UUID
```

**System responsibilities**:
- Normalize "Sarah" → "sarah-chen" (or ideally keep as "Sarah Chen")
- Resolve "Project Alpha" → "project-alpha" (or ideally keep as "Project Alpha")
- Handle variations (Sarah Chen, sarah chen, SARAH)
- Map document names to internal references

## Critical Design Observation: Natural Language Surface

**Traditional database design**: Foreign keys use UUIDs for referential integrity
```
resources.id = uuid
edges.source_id = uuid (foreign key)
edges.target_id = uuid (foreign key)
```

**REM design**: Graph edges use natural language labels, NOT UUIDs
```
graph_paths = [
  "/resources/Project Alpha Kickoff/entity/Sarah Chen/Technical Spec",
  "/resources/Meeting Notes/related/Status Update"
]
```

**Why this matters**:
- Users can LOOKUP by label without knowing internal IDs
- Conversational interface: "What's related to the Kickoff Meeting?" works directly
- Graph traversal uses human-readable paths
- Entity neighborhoods are label-based: retrieve "Sarah Chen" → get all connected resources via labels

**Testing implication**: Validate that edges reference labels (names, entity labels), not UUIDs. This is testable by inspecting `graph_paths` arrays and confirming they contain natural language, not hex strings.

## Example Test Cases

### Example 1: Single Key Lookup

**User query**: "Who is Sarah?"

**REM query construction** (via ask_rem):
1. User provides: "Who is Sarah?"
2. LLM generates: `REMQueryPlan(query_type=LOOKUP, parameters=LookupParameters(key="Sarah"))`
3. System normalizes: "Sarah" → "sarah-chen"
4. Query executes: Find all resources where `related_entities` contains entity with `entity_id="sarah-chen"`
5. Return results

**Judge validation**:
- Provide "Sarah" (what user knows)
- Expect system to find sarah-chen (internal)
- Validate results contain correct resources
- Check entity information returned

### Example 2: Multiple Key Lookup

**User query**: "Show me everything about Sarah, Mike, and Emily"

**REM query construction** (via ask_rem):
1. User provides: "Show me everything about Sarah, Mike, and Emily"
2. LLM generates: `REMQueryPlan(query_type=LOOKUP, parameters=LookupParameters(key=["Sarah", "Mike", "Emily"]))`
3. System normalizes: ["Sarah", "Mike", "Emily"] → ["sarah-chen", "mike-johnson", "emily-santos"]
4. Query executes: Find all resources mentioning ANY of these people (union of results)
5. Return aggregated results from all three lookups

**Judge validation**:
- Provide natural names (what user knows)
- Expect system to find all three entities
- Validate results contain resources for each person
- Verify no duplicate results
- Check all entity information returned

**Not valid**:
- Provide normalized IDs directly ("sarah-chen", "mike-johnson")
- Assume judge knows normalization rules
- Test internal data structures directly

## Validation Exit Codes

Scripts return exit codes for CI/CD:

```bash
# Exit 0: All quality checks pass
# Exit 1: Quality failures detected

python scripts/rem/validate_moment_quality.py --tenant demo-tenant-001
echo $?  # 0 or 1

python scripts/rem/validate_affinity_quality.py --tenant demo-tenant-001
echo $?  # 0 or 1
```

## Integration Testing

See `docs/REM/examples/critical-assessment.md` for:
- Complete query evolution analysis
- 10 test questions across maturity stages
- Expected results at each stage
- Quality failure analysis

Run full integration test:
```bash
cd docs/REM/examples
python scripts/rem/simple_seed.py
python scripts/rem/run_dreaming.py --tenant demo-tenant-001 --mode both --lookback-hours 720
python scripts/rem/validate_moment_quality.py --tenant demo-tenant-001 --verbose
python scripts/rem/validate_affinity_quality.py --tenant demo-tenant-001 --verbose
python scripts/rem/test_rem_queries.py --tenant demo-tenant-001
```
