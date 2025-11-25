# SystemAgent REM Query Implementation

## Overview

SystemAgent (`p8-system`) is now the default agent for the completions endpoint with full REM (Resource-Entity-Moment) query capabilities.

## Implementation Summary

### 1. Default Agent Configuration

**File**: `p8fs-api/src/p8fs_api/routers/chat.py:86`

```python
# Default to p8-system if no agent specified
agent_key = x_p8_agent or "p8-system"
```

When no `X-P8-Agent` header is provided, the completions endpoint now automatically loads SystemAgent.

### 2. SystemAgent REM Tools

**File**: `p8fs/src/p8fs/models/system_agent.py`

SystemAgent provides two REM query tools:

#### ask_rem Tool (Natural Language Query Planner)

Converts natural language questions to optimized REM queries using an LLM query planner.

**Function Signature**:
```python
def ask_rem(question: str, table: str = "resources", provider: str = "postgresql") -> dict
```

**Examples**:
- "What did I work on yesterday?"
- "Show me recent moments about database work"
- "Find resources uploaded in the last week"
- "What meetings did I have with topic tag 'planning'?"

**Query Planning Logic**:
1. **Temporal queries** ("recent", "yesterday", "last week") → SQL with `created_at`/`modified_at`
2. **Tag-based queries** (for moments) → SQL with JSONB containment
3. **Content queries** ("about X", "containing Y") → SEARCH syntax
4. **Key lookups** (specific IDs) → LOOKUP syntax

#### rem_query Tool (Direct REM SQL Execution)

Executes REM SQL queries directly without query planning.

**Function Signature**:
```python
def rem_query(query: str, provider: str = "postgresql") -> dict
```

**Supported Query Types**:
- **LOOKUP**: `LOOKUP test-resource-1`
- **SEARCH**: `SEARCH "database work" IN moments`
- **SQL**: `SELECT * FROM moments WHERE topic_tags @> '["work"]'::jsonb`

### 3. Query Engine LLM Configuration

**File**: `p8fs-cluster/src/p8fs_cluster/config/settings.py`

Added Cerebras configuration for fast query planning:

```python
# API Keys
cerebras_api_key: str = ""

# Query Engine LLM Configuration (for REM query planning)
# Cerebras is recommended for fast query planning (~500ms vs Claude ~1800ms)
query_engine_provider: str = "cerebras"
query_engine_model: str = "llama3.3-70b"
query_engine_temperature: float = 0.1
```

**Environment Variables**:
```bash
export P8FS_CEREBRAS_API_KEY=csk-...
export P8FS_QUERY_ENGINE_PROVIDER=cerebras
export P8FS_QUERY_ENGINE_MODEL=llama3.3-70b
```

## Test Results

### Direct Integration Test

**File**: `/tmp/test_rem_tools_direct.py`

All tests passed successfully:

✅ **TEST 1: Work moments query**
```sql
SELECT name, topic_tags, emotion_tags, resource_timestamp
FROM moments
WHERE topic_tags @> '["work"]'::jsonb
ORDER BY resource_timestamp DESC
LIMIT 3
```
- **Success**: True
- **Count**: 3 results
- **Results**: Team Standup Meeting, Coding Session, Weekly Planning Session

✅ **TEST 2: Happy moments query**
```sql
SELECT name, emotion_tags FROM moments
WHERE emotion_tags @> '["happy"]'::jsonb
```
- **Success**: True
- **Count**: 1 result
- **Results**: Morning Run

✅ **TEST 3: Recent moments (last 7 days)**
```sql
SELECT name, moment_type, resource_timestamp
FROM moments
WHERE resource_timestamp > NOW() - INTERVAL '7 days'
ORDER BY resource_timestamp DESC
```
- **Success**: True
- **Count**: 5 results
- **Results**: All moments from test data within time range

## System Prompt

SystemAgent includes comprehensive documentation of the REM query dialect in its system prompt:

```
You are the P8 system agent with direct access to the user's memory vault.

**Main Memory Schema:**

1. **resources** - Generic content chunks (documents, notes, parsed files)
   - Searchable by: content (semantic), name, category, date

2. **moments** - Time-bounded memory segments with rich context
   - Searchable by: content (semantic), topic_tags, emotion_tags, date ranges
   - Fields: topic_tags (list), emotion_tags (list), moment_type, location, speakers

**Hybrid Queries:**
- Recent files: SELECT * FROM files ORDER BY upload_timestamp DESC LIMIT 10
- Recent moments about work: SELECT * FROM moments WHERE topic_tags @> ARRAY['work'] ORDER BY resource_timestamp DESC
```

## Usage Examples

### Via API (with Authentication)

```bash
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4.1-mini",
    "messages": [
      {
        "role": "user",
        "content": "Show me recent work moments from the last 3 days"
      }
    ]
  }'
```

The SystemAgent will automatically:
1. Receive the question
2. Use `ask_rem` tool to plan the query
3. Execute the planned REM query
4. Return results to the user

### Via MemoryProxy (Integration Tests)

```python
from p8fs.models.system_agent import SystemAgent
from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext

agent = SystemAgent
context = CallingContext(
    model="gpt-4.1-mini",
    tenant_id="tenant-test"
)

async with MemoryProxy(model_context=agent) as proxy:
    response = await proxy.run(
        "Show me work moments from last week",
        context
    )
```

### Direct Method Calls (Unit Tests)

```python
from p8fs.models.system_agent import SystemAgent

agent = SystemAgent()

# Direct SQL query
result = agent.rem_query(
    "SELECT * FROM moments WHERE topic_tags @> '[\"work\"]'::jsonb",
    provider="postgresql"
)

print(f"Found {result['count']} results")
```

## Architecture

```
User Question
     │
     ▼
SystemAgent (p8-system)
     │
     ├──> ask_rem() ──> Query Planner LLM ──> Optimized REM SQL
     │                   (Cerebras ~500ms)
     │
     └──> rem_query() ──> REMQueryParser ──> REMQueryProvider ──> PostgreSQL/TiDB
                              │                    │
                              │                    └──> Execute Query
                              │
                              └──> LOOKUP / SEARCH / SQL
```

## Future Enhancements

### Planned Features

1. **Structured Query Plans**: Instead of string output, return structured QueryPlan objects from query planner
2. **Multi-hop Queries**: Support graph traversal with TRAVERSE syntax
3. **Confidence Scoring**: Add confidence scores to query plans
4. **Fallback Queries**: Support primary + fallback query execution
5. **Query Optimization**: Cache common query patterns

### Percolate-Rocks Integration

The percolate-rocks project has a more advanced query planner with:
- Strict JSON schema for Cerebras
- QueryPlan objects with confidence scores
- Multi-stage query execution
- Edge extraction for knowledge graphs

These features can be incrementally adopted into p8fs-modules.

## Configuration Reference

### Environment Variables

```bash
# OpenAI for completions (or Anthropic/Google)
export P8FS_OPENAI_API_KEY=sk-...
export P8FS_LLM_PROVIDER=openai
export P8FS_DEFAULT_MODEL=gpt-4.1

# Cerebras for fast query planning (recommended)
export P8FS_CEREBRAS_API_KEY=csk-...
export P8FS_QUERY_ENGINE_PROVIDER=cerebras
export P8FS_QUERY_ENGINE_MODEL=llama3.3-70b
export P8FS_QUERY_ENGINE_TEMPERATURE=0.1

# Database provider
export P8FS_STORAGE_PROVIDER=postgresql
export P8FS_PG_HOST=localhost
export P8FS_PG_PORT=5438
export P8FS_PG_DATABASE=app
```

### Alternative Query Engine Providers

**Claude Sonnet 4.5** (slower but higher quality):
```bash
export P8FS_QUERY_ENGINE_PROVIDER=anthropic
export P8FS_QUERY_ENGINE_MODEL=claude-sonnet-4-5
export P8FS_ANTHROPIC_API_KEY=sk-ant-...
```

**OpenAI** (moderate speed and quality):
```bash
export P8FS_QUERY_ENGINE_PROVIDER=openai
export P8FS_QUERY_ENGINE_MODEL=gpt-4.1-mini
```

## Related Documentation

- [REM Query CLI Guide](/Users/sirsh/code/p8fs-modules/docs/REM_QUERY_CLI_GUIDE.md)
- [SystemAgent Source](/Users/sirsh/code/p8fs-modules/p8fs/src/p8fs/models/system_agent.py)
- [MemoryProxy Integration](/Users/sirsh/code/p8fs-modules/p8fs/src/p8fs/services/llm/memory_proxy.py)
- [Chat Router](/Users/sirsh/code/p8fs-modules/p8fs-api/src/p8fs_api/routers/chat.py)
