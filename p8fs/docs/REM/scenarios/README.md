# REM Scenarios - Testing Knowledge Graph Evolution

## Overview

This directory contains end-to-end scenarios that demonstrate how P8FS REM (Relational Entity Memory) builds a knowledge graph over time as users upload content and interact with their data.

## Purpose

Each scenario tests:
- **Graph Evolution**: How entities and relationships emerge from uploaded content
- **Temporal Linking**: Documents uploaded on different days becoming connected
- **Entity Extraction**: People, projects, and concepts becoming graph nodes
- **Query Capabilities**: REM LOOKUP and semantic queries answering increasingly complex questions
- **Narrative Recovery**: Reconstructing user's week from interconnected memories

## Testing Strategy

### Data Generation
1. **Use Engram Format**: Generate engrams following `/docs/04 engram-specification.md`
2. **Direct Database Upload**: Use engram processor to create seed data
3. **Realistic Timestamps**: Each engram has resource_timestamp matching scenario day
4. **Natural Relationships**: Graph edges created through content references and semantic similarity

### Environment Setup
```bash
# PostgreSQL provider with pgvector
export P8FS_STORAGE_PROVIDER=postgresql
export P8FS_DEFAULT_EMBEDDING_PROVIDER=text-embedding-3-small

# LLM keys (in .bash_profile or .env)
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...

# Start PostgreSQL
cd p8fs
docker compose up postgres -d
```

### Running a Scenario
```bash
# 1. Generate and upload engrams for each day
cd docs/REM/scenarios/scenario-01
python generate_engrams.py

# 2. Process engrams (creates resources, moments, graph edges)
for engram in engrams/*.yaml; do
    uv run python -m p8fs.models.engram.processor process_file "$engram" \
        --tenant-id tenant-test
done

# 3. Run REM queries
python test_queries.py

# 4. Visualize graph evolution
python visualize_graph.py
```

## Scenario Structure

Each scenario directory contains:

```
scenario-XX/
├── README.md                  # Scenario narrative and timeline
├── engrams/                   # Generated engram YAML files
│   ├── day1-morning.yaml
│   ├── day1-afternoon.yaml
│   ├── day2-meeting.yaml
│   └── ...
├── graphs/                    # Mermaid diagrams showing graph evolution
│   ├── day1-graph.md
│   ├── day2-graph.md
│   └── ...
├── queries/                   # REM query examples
│   ├── day1-queries.md
│   ├── day2-queries.md
│   └── ...
├── generate_engrams.py       # Script to generate scenario data
├── test_queries.py           # Script to test REM queries
└── visualize_graph.py        # Script to generate graph visualizations
```

## What Each Scenario Tests

### Graph Building
- **Day 1**: Initial entities and relationships from first uploads
- **Day 2-3**: Cross-references creating edges between earlier content
- **Day 4-5**: Semantic similarity linking related concepts
- **Day 6-7**: Rich graph enabling complex queries

### Query Evolution

**Early Days**: Simple lookups
```
Q: Who did I meet with?
Q: What projects did I mention?
```

**Mid-Week**: Cross-document queries
```
Q: How is the API migration related to the security audit?
Q: What did Sarah say about the Q4 roadmap?
```

**End of Week**: Narrative reconstruction
```
Q: Tell me about my week focusing on Project Alpha
Q: What were the key decisions made this week?
Q: Who are the main people I collaborated with?
```

### Graph Edge Types

Scenarios demonstrate all edge types:
- `semantic_similar`: AI-discovered content similarity
- `discusses`: Explicit references to entities
- `attended_by`: People at meetings/events
- `part_of`: Moments within larger resources
- `precedes`/`follows`: Temporal sequences
- `relates_to`: General associations

## Validation Criteria

Each scenario validates:
1. **Engram Processing**: All engrams processed without errors
2. **Graph Completeness**: Expected nodes and edges created
3. **Edge Timestamps**: created_at reflects when relationships formed
4. **Query Accuracy**: REM queries return expected results
5. **Narrative Coherence**: Story reconstructible from graph

## Current Scenarios

### Scenario 01: Product Manager's Week
A week in the life of a product manager working on a mobile app launch, demonstrating:
- Daily standups with team members
- Design reviews and technical discussions
- Meeting notes linking to prior decisions
- Voice memos during commute
- Weekend reflections tying the week together

Status: In Development

## Future Scenarios

### Scenario 02: Research Scientist's Month
Tracking research progress, paper reviews, experiment notes, and collaborations.

### Scenario 03: Startup Founder's Quarter
Board meetings, investor updates, product iterations, team growth.

### Scenario 04: Student's Semester
Lectures, assignments, study sessions, group projects, exam prep.

## Contributing Scenarios

To add a new scenario:

1. Create `scenario-XX` directory
2. Write narrative README describing the user and their week
3. Generate engrams with realistic content and timestamps
4. Define expected graph evolution per day
5. Create REM queries demonstrating capabilities
6. Validate with actual test run

## Metrics Tracked

For each scenario, we track:
- **Entities Created**: People, projects, concepts per day
- **Edges Created**: Relationships formed each day
- **Edge Types**: Distribution of relationship types
- **Query Performance**: Response times for different query types
- **Semantic Coverage**: How well queries match intent
- **Graph Density**: Connectivity evolution over time
