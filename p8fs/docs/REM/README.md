# REM (Resource-Entity-Moment) Documentation

REM is a unified memory infrastructure combining temporal narratives, semantic relationships, and structured knowledge.

## Success Metric

**REM queries get richer over time** as the graph matures:
- Stage 1 (Resources): 20% of questions answerable
- Stage 2 (Moments): 50% answerable
- Stage 3 (Affinity): 80% answerable
- Stage 4 (Mature): 100% answerable

This is not about scripts running without exceptions. It is about quality validation.

## Core Documentation

**[design.md](design.md)** - Architecture, data models, dreaming workflows, graph storage, REM queries

**[testing.md](testing.md)** - Testing philosophy, query evolution stages, quality validation, realistic test queries

**[deployment.md](deployment.md)** - Local setup, Kubernetes deployment, monitoring, troubleshooting

## Examples

**[examples/sample-01.md](examples/sample-01.md)** - 8 resources demonstrating entity graph construction

**[examples/sample-01-data.yaml](examples/sample-01-data.yaml)** - Complete data export with expected moments and affinity edges

**[examples/critical-assessment.md](examples/critical-assessment.md)** - Query evolution analysis (0% → 100% answerability)

## Quick Start

```bash
# 1. Seed test data
python scripts/rem/simple_seed.py

# 2. Run dreaming workers
python scripts/rem/run_dreaming.py --tenant demo-tenant-001 --mode both --lookback-hours 720

# 3. Validate quality
python scripts/rem/validate_moment_quality.py --tenant demo-tenant-001 --verbose
python scripts/rem/validate_affinity_quality.py --tenant demo-tenant-001 --verbose

# 4. Test REM queries
python scripts/rem/test_rem_queries.py --tenant demo-tenant-001
```

## Testing Principle

Test with USER-KNOWN information only:
- ✅ `LOOKUP "Sarah"` (what user types)
- ❌ `LOOKUP "sarah-chen"` (internal normalized ID)

System must resolve natural inputs to internal structures.

## Scripts

All scripts in `scripts/rem/`:
- `simple_seed.py` - Create test resources
- `run_dreaming.py` - Execute dreaming workers
- `validate_moment_quality.py` - 8 quality checks for moments
- `validate_affinity_quality.py` - 7 quality checks for affinity
- `test_rem_queries.py` - Test REM query functionality

## Configuration

Set environment variable for local testing:
```bash
export P8FS_DEFAULT_EMBEDDING_PROVIDER=text-embedding-3-small
```

All test scripts set this automatically via `os.environ.setdefault()`.

## Quality Validation

**Moment Quality**: Temporal validity, person extraction, speaker identification, tag quality, content quality, entity references, temporal coverage, type distribution

**Affinity Quality**: Edge existence, edge format, semantic relevance, bidirectional edges, entity connections, graph connectivity, edge distribution

Exit codes: 0 = pass, 1 = quality failures detected

## Action List: REM Memory Evolution Testing

### Goal
Create comprehensive case studies demonstrating how REM memory evolves over time through dreaming workflows, showing progressive question-answering capability from 0% to 100%.

### Test Data Sources
- **Chat Sessions**: User conversations (stored as resources)
- **Document Uploads**: PDFs, WAV files, images (stored as files, parsed into resources)
- **Structured Extractions**: Agent-derived entities stored in KV

### Database Schema
- **resources**: Primary content units (documents, conversations)
- **files**: File metadata and tracking
- **moments**: Temporal narratives (meetings, coding sessions)
- **kv_storage**: Entity mappings and structured extractions
- **Future schemas**: Extensible for domain-specific data

### Core Interface: REM Query Triplets

Maintain example table showing evolution of query capabilities:

| Natural Language Query | REM Dialect | Underlying Python | Stage |
|----------------------|-------------|-------------------|-------|
| "Show me everything about Sarah" | `LOOKUP sarah-chen` | `REMQueryPlan(QueryType.LOOKUP, LookupParameters(key="sarah-chen"))` | 1 |
| "Find documents about database migration" | `SEARCH "database migration tidb"` | `REMQueryPlan(QueryType.SEARCH, SearchParameters(query_text="database migration tidb"))` | 3 |
| "When did Sarah and Mike meet?" | `SELECT * FROM moments WHERE moment_type='meeting'` | `REMQueryPlan(QueryType.SQL, SQLParameters(table="moments", where="moment_type='meeting'"))` | 2 |
| "What work builds on the TiDB spec?" | `TRAVERSE tidb-migration-spec rel_type=builds-on` | `REMQueryPlan(QueryType.TRAVERSE, TraverseParameters(start="tidb-migration-spec", rel_type="builds-on"))` | 3 |

### Tasks

#### 1. Create Multiple Case Studies

**Case Study A: Software Team Project**
- Data: Technical documents, meeting recordings, code review sessions, chat logs
- Timeline: 2-week sprint
- Entities: Team members, technologies, projects, concepts
- Hard Questions: "Who reviewed Sarah's migration code?", "What concerns were raised about TiDB?", "Show the decision timeline for Redis vs TiKV"

**Case Study B: Research Paper Evolution**
- Data: Literature PDFs, research notes, experiment logs, draft revisions
- Timeline: 3-month research cycle
- Entities: Authors, papers, methodologies, findings
- Hard Questions: "Which papers influenced the methodology section?", "What experiments failed and why?", "Who collaborated on the statistical analysis?"

**Case Study C: Product Development**
- Data: Design docs, user interviews, prototypes, feedback sessions
- Timeline: Product launch cycle
- Entities: Features, users, stakeholders, metrics
- Hard Questions: "Which user feedback led to feature X?", "What trade-offs were discussed?", "Show the evolution of the pricing model"

#### 2. Holdout Question Set Design

Create challenging questions BEFORE seeing the data:
- **Entity Retrieval**: "Find all documents Sarah authored"
- **Temporal Reasoning**: "What happened between milestone A and B?"
- **Relationship Discovery**: "What documents reference both TiDB and performance?"
- **Causal Links**: "What problem led to this decision?"
- **Multi-hop Traversal**: "Find documents related to documents that Mike reviewed"
- **Negative Tests**: "Did Sarah ever work with Alice?" (answer: no)

#### 3. Dreaming Sequence Documentation

For each case study, document:
1. **Stage 0** (t=0): Raw resources only, 0% questions answerable
2. **Stage 1** (t+1h): After entity extraction, LOOKUP works, 20% answerable
3. **Stage 2** (t+6h): After moment generation, temporal queries work, 50% answerable
4. **Stage 3** (t+24h): After affinity matching, semantic/graph queries work, 80% answerable
5. **Stage 4** (t+72h): After multiple dreaming cycles, 100% answerable

#### 4. Knowledge Graph Visualization

Show graph construction at each stage:
- **Stage 1**: Entity nodes only (people, projects, concepts)
- **Stage 2**: + Temporal edges (happened_during, present_at)
- **Stage 3**: + Semantic edges (semantic_similar, builds-on, references)
- **Stage 4**: + Inferred edges (collaborates_with, influences, contradicts)

#### 5. REM Query Evolution Matrix

Document which REM dialects become available at each stage:

| REM Query Type | Stage 1 | Stage 2 | Stage 3 | Stage 4 |
|----------------|---------|---------|---------|---------|
| LOOKUP entity | ✓ | ✓ | ✓ | ✓ |
| SEARCH semantic | ✗ | ✗ | ✓ | ✓ |
| SQL temporal | ✗ | ✓ | ✓ | ✓ |
| TRAVERSE graph | ✗ | ✗ | ✓ | ✓ |
| AGGREGATE | ✗ | ✓ | ✓ | ✓ |

#### 6. Agent-Based Structured Extraction

Document how specialized agents enrich the graph:
- **EntityExtractor**: Extracts people/projects/concepts → stored in related_entities
- **RelationshipExtractor**: Identifies semantic relationships → creates edges
- **SummaryAgent**: Generates summaries → stored in resource.summary
- **FactExtractor**: Structured facts → stored in KV with entity keys
- **SentimentAgent**: Emotional context → stored as moment.emotion_tags

#### 7. Quality Metrics Per Stage

Track quality evolution:
- **Coverage**: % of holdout questions answerable
- **Precision**: % of correct answers
- **Recall**: % of relevant results returned
- **Graph Density**: avg edges per node
- **Temporal Completeness**: % of timeline covered by moments
- **Entity Connectivity**: % of entities with >1 edge

#### 8. Failure Case Documentation

Document expected failures at each stage:
- Stage 1: Can't answer "When did X happen?" (no moments)
- Stage 2: Can't answer "Find similar documents" (no affinity)
- Stage 3: Can't answer complex multi-hop queries (limited graph depth)
- Stage 4: Reduced failures but document remaining limitations

### Deliverables

1. **Case Study Files** (examples/case-study-{A,B,C}/)
   - `data.yaml` - Input resources
   - `questions.md` - Holdout question set with expected answers
   - `evolution.md` - Stage-by-stage progression
   - `graph-visualizations/` - Graph snapshots per stage

2. **REM Query Reference** (docs/REM/query-reference.md)
   - Complete triplet table (natural language → REM → Python)
   - Query examples for each dialect
   - Common patterns and anti-patterns

3. **Validation Scripts** (scripts/rem/validate_evolution.py)
   - Automated testing of question answering at each stage
   - Quality metric calculations
   - Regression detection

4. **Documentation Updates**
   - Update design.md with InlineEdge usage in dreaming ✓
   - Add query-reference.md
   - Update testing.md with evolution methodology

### Success Criteria

- 3 diverse case studies with realistic data
- 50+ holdout questions across different query types
- Documented progression from 0% → 100% answerability
- Clear REM query triplet examples for each dialect
- Reproducible scripts that run on fresh database
