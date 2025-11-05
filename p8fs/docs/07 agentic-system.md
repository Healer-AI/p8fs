# Agentic System - Structured Content Transformation with LLMs

## Overview

The P8FS Agentic System enables structured content transformation using LLM-powered agents. Agents are Pydantic models that act as intelligent parsers and transformers, taking input data (markdown or record collections) and producing validated structured output.

## System Architecture

### High-Level Component Flow

```mermaid
graph TB
    subgraph "Input Data"
        MD[Markdown Content]
        RC[Record Collections]
        RES[Resources from DB]
    end

    subgraph "Memory Proxy"
        MP[MemoryProxy]
        RUN[run - Single query]
        STREAM[stream - Streaming]
        BATCH[batch - Multiple inputs]
        PARSE[parse_content - Pagination]
    end

    subgraph "Agent-let Layer"
        AGENT[Pydantic Agent Model]
        SYS[System Prompt<br/>from docstring]
        FIELDS[Structured Fields<br/>output schema]
        TOOLS[Optional Functions<br/>custom tools]
        BUILTIN[Built-in Functions<br/>search_resources, query_moments]
    end

    subgraph "LLM Providers"
        CLAUDE[Claude Sonnet 4.5]
        GPT[GPT-4o]
    end

    subgraph "Output Data"
        STRUCT[Structured Output<br/>Pydantic validated]
        NEWRES[New Resources<br/>type: dreaming, moments]
    end

    MD --> MP
    RC --> MP
    RES --> MP

    MP --> RUN
    MP --> STREAM
    MP --> BATCH
    MP --> PARSE

    RUN --> AGENT
    STREAM --> AGENT
    BATCH --> AGENT
    PARSE --> AGENT

    AGENT --> SYS
    AGENT --> FIELDS
    AGENT --> TOOLS
    AGENT --> BUILTIN

    AGENT --> CLAUDE
    AGENT --> GPT

    CLAUDE --> STRUCT
    GPT --> STRUCT

    STRUCT --> NEWRES

    style MP fill:#e1f5ff
    style AGENT fill:#fff4e1
    style STRUCT fill:#e8f5e9
```

### Agent Components

Agents combine four key components:

1. **System Prompt**: Generated from class docstring
2. **Structured Output**: Defined by Pydantic fields with descriptions
3. **Optional Functions**: Custom tool methods on the agent class
4. **Built-in Functions**: Inherited from MemoryProxy (search_resources, query_moments)

### Memory Proxy Execution Modes

```mermaid
graph TB
    INPUT[Input Content]

    subgraph "run() - Single Query"
        R1[Single prompt]
        R2[Optional tool use]
        R3[Single response]
    end

    subgraph "stream() - Streaming"
        S1[Single prompt]
        S2[Incremental tokens]
        S3[Stream response]
    end

    subgraph "batch() - Multiple"
        B1[Multiple prompts]
        B2[Independent processing]
        B3[Multiple responses]
    end

    subgraph "parse_content() - Pagination"
        PC1[Auto chunk by tokens]
        PC2[Process each chunk]
        PC3[Merge results]
        PC4[Single validated output]
    end

    INPUT --> R1
    INPUT --> S1
    INPUT --> B1
    INPUT --> PC1

    R1 --> R2 --> R3
    S1 --> S2 --> S3
    B1 --> B2 --> B3
    PC1 --> PC2 --> PC3 --> PC4

    style R3 fill:#e1f5ff
    style S3 fill:#fff4e1
    style B3 fill:#e8f5e9
    style PC4 fill:#f3e5f5
```

## Core Principles

### 1. Agents as Pydantic Models

Agents extend `AbstractModel` and define:
- Class docstring (becomes system prompt)
- Pydantic fields (define output schema)
- Optional class methods (custom tools)

```python
from p8fs.models.base import AbstractModel
from pydantic import Field

class MyAgent(AbstractModel):
    """
    System prompt describing what this agent does.

    This docstring is automatically converted into the LLM's system prompt,
    providing context and instructions for the agent's behavior.
    """

    model_config = {
        'full_name': 'agents.MyAgent',
        'description': 'Brief description'
    }

    # Structured output fields
    summary: str = Field(description="Brief summary")
    entities: list[str] = Field(default_factory=list, description="Named entities")

    # Optional custom tool
    @classmethod
    def search_database(cls, query: str) -> list[dict]:
        """Custom tool method."""
        return []
```

### 2. Data Transformation Pattern

Agents act as parsers and transformers:

**Read → Transform → Generate**

- **Read**: Search resources, query time periods (built-in functions)
- **Transform**: Apply structured analysis and classification
- **Generate**: Create new resources from existing ones

### 3. Token-Aware Pagination

The system handles arbitrarily large inputs through intelligent pagination:

- Token-aware chunking fits minimal number of chunks within model context
- Smart boundary detection preserves record boundaries
- Automatic merging combines chunk results

### 4. Multiple Execution Modes

Different methods for different use cases:

- `run()`: Single query/response with optional tool use
- `stream()`: Streaming responses with incremental output
- `batch()`: Process multiple inputs independently
- `parse_content()`: Parse large content with automatic pagination

## Quick Start

### Basic Usage

```python
from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext
from p8fs.models.agentlets.dreaming import DreamModel

# Create proxy with agent model
proxy = MemoryProxy(model_context=DreamModel)

# Configure context
context = CallingContext(
    model="claude-sonnet-4-5",
    tenant_id="test",
    temperature=0.1,
    max_tokens=8000
)

# Parse content
result = await proxy.parse_content(
    content=diary_text,
    context=context,
    merge_strategy="last"
)

# Access validated results
print(result.executive_summary)
print(f"Goals: {len(result.goals)}")
```

### Large Content with Pagination

```python
# Token-aware chunking handles large inputs
result = await proxy.parse_content(
    content=year_of_resources,
    context=context,
    merge_strategy="merge"  # Combine all chunks
)

print(f"Total Goals: {len(result.goals)}")
print(f"Total Relationships: {len(result.entity_relationships)}")
```

### Creating Custom Agents

```python
from p8fs.models.base import AbstractModel
from pydantic import Field

class ResearchAgent(AbstractModel):
    """
    Research agent for analyzing academic content.

    This agent searches papers, extracts citations, and produces
    structured research summaries with confidence scores.
    """

    findings: list[dict] = Field(
        default_factory=list,
        description="Research findings with evidence"
    )

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score"
    )

    @classmethod
    def search_papers(cls, query: str, limit: int = 10) -> list[dict]:
        """Search academic papers by query."""
        # Implementation
        return []
```

## Production Use Cases

### Dream Worker: Resource Summarization

Scheduled worker that summarizes resources into "dreaming" type resources:

```python
@scheduled(hour="*/6")
async def dream_worker(tenant_id: str):
    """Run every 6 hours to create dream summaries."""

    # Search recent resources
    resources = await search_resources(
        tenant_id=tenant_id,
        days_back=7,
        limit=100
    )

    # Create agent and process
    proxy = MemoryProxy(model_context=DreamModel)
    result = await proxy.parse_content(
        content=resources,
        context=context
    )

    # Save as new resource
    await save_resource(
        tenant_id=tenant_id,
        type="dreaming",
        content=result.model_dump()
    )
```

**Output**: New resource with executive summary, goals, relationships, dreams, fears

### Moment Worker: Activity Classification

Scheduled worker that classifies time periods into activity moments:

```python
@scheduled(day="*/1")
async def moment_worker(tenant_id: str):
    """Run daily to classify activity moments."""

    # Query resources for specific time period
    resources = await query_moments(
        tenant_id=tenant_id,
        start_date="2025-01-13",
        days=3
    )

    # Create agent and classify
    proxy = MemoryProxy(model_context=MomentBuilder)
    moments = await proxy.parse_content(
        content=resources,
        context=context
    )

    # Save moment collection
    for moment in moments:
        await save_moment(
            tenant_id=tenant_id,
            start_time=moment.start_time,
            end_time=moment.end_time,
            activity=moment.name,
            resources=moment.resource_ids
        )
```

**Output**: Collection of moments with temporal boundaries, emotions, topics, present persons

## Merge Strategies

When processing chunked content, results are merged based on strategy:

### "first" - Use First Chunk

```python
merge_strategy="first"
```

Returns the first chunk's results. Use when important information is at the beginning.

### "last" - Use Last Chunk (Default)

```python
merge_strategy="last"
```

Returns the last chunk's results. Use when later chunks have the most complete analysis.

### "merge" - Combine All Chunks

```python
merge_strategy="merge"
```

Intelligently merges all chunks:
- **Lists**: Concatenates (goals, dreams, entities, etc.)
- **Scalars**: Takes first non-null value (summary, confidence, etc.)

**Example**:
```python
# Chunk 1: {"goals": ["Launch product"], "summary": "Startup phase"}
# Chunk 2: {"goals": ["Raise funding"], "summary": None}
# Merged:  {"goals": ["Launch product", "Raise funding"], "summary": "Startup phase"}
```

## Pagination Implementation

### Automatic Chunking

Content is automatically chunked when it exceeds token limits:

```python
def _chunk_content(self, content: str, chunk_size: int) -> list[str]:
    """Split content into chunks by character count."""
    if len(content) <= chunk_size:
        return [content]

    chunks = []
    start = 0
    while start < len(content):
        end = start + chunk_size
        chunk = content[start:end]
        chunks.append(chunk)
        start = end

    return chunks
```

### Processing Chunks

Each chunk is processed with instructions to prevent tool use:

```python
for i, chunk in enumerate(chunks):
    question = f"Analyze this content (part {i+1}/{len(chunks)}) and return only the structured JSON analysis without using any tools or functions.\n\n{chunk}"

    response = await self.run(question, context, max_iterations=1)
    parsed = self._extract_json(response)
    if parsed:
        results.append(parsed)
```

### JSON Extraction

The system handles multiple response formats:

1. Direct JSON parsing
2. Markdown code block with `json` language
3. Markdown code block without language
4. First `{` to last `}`

```python
def _extract_json(self, text: str) -> dict | None:
    """Extract JSON from various response formats."""
    # Try direct parsing
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try markdown patterns
    patterns = [
        r'```json\s*(\{[\s\S]+\})\s*```',
        r'```\s*(\{[\s\S]+\})\s*```'
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[-1])
            except json.JSONDecodeError:
                pass

    # Try brace extraction
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass

    return None
```

## Tool Registration

See `08 function-registration.md` for complete documentation on registering custom tool methods.

### Registration Rules

**Included (Registered as Tools)**:
- User-defined class methods (`@classmethod`)
- User-defined instance methods
- Methods with `__qualname__` starting with agent class name

**Excluded (NOT Registered)**:
- AbstractModel base methods
- Pydantic utility methods
- Private methods (starting with `_`)
- Pydantic decorators (`@model_validator`, `@field_serializer`)

### Built-in Functions

All agents inherit built-in functions from MemoryProxy:

```python
# Built-in functions available to all agents:
search_resources(days_back: int = 7, limit: int = 100) -> list[dict]
query_moments(start_date: str, days: int = 3) -> list[dict]
```

These can be called by the LLM during agent execution to gather context.

## Performance

### Benchmarks

**Claude Sonnet 4.5** (11,700 chars, 3 chunks):
- Chunk 1: ~68 seconds
- Chunk 2: ~67 seconds
- Chunk 3: ~66 seconds
- Total: ~3.5 minutes

**GPT-4o** (3,000 chars, single chunk):
- Processing: ~22 seconds
- Cost: $0.0533 (520 prompt + 629 completion tokens)
- ~3x faster than Claude

### Optimization Tips

1. Use smaller chunks for faster feedback: `chunk_size=2000`
2. Use GPT-4o for speed: ~3x faster than Claude
3. Use "last" strategy for single summary: Avoids expensive merge
4. Reduce max_tokens: Lower `max_tokens` for faster responses

## Testing

### Basic Test

```python
import asyncio
from pathlib import Path
from p8fs.models.agentlets.dreaming import DreamModel
from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext

async def test_parse_content():
    # Read sample content
    sample_file = Path("tests/sample_data/content/diary_sample.md")
    content = sample_file.read_text()

    # Create proxy
    proxy = MemoryProxy(model_context=DreamModel)

    # Parse with pagination
    context = CallingContext(
        model="claude-sonnet-4-5",
        tenant_id="test",
        temperature=0.1,
        max_tokens=8000
    )

    result = await proxy.parse_content(
        content=content * 3,  # Duplicate for chunking test
        context=context,
        chunk_size=4000,
        merge_strategy="last"
    )

    # Validate results
    assert isinstance(result, DreamModel)
    assert result.executive_summary is not None
    assert len(result.goals) > 0

    print(f"✅ Parsed successfully")
    print(f"   Goals: {len(result.goals)}")
    print(f"   Relationships: {len(result.entity_relationships)}")

if __name__ == "__main__":
    asyncio.run(test_parse_content())
```

### CLI Evaluation

```bash
# Evaluate agent on file input
export ANTHROPIC_API_KEY=your-key
uv run python -m p8fs.cli eval \
  --agent-model agentlets.moments.MomentBuilder \
  --file tests/sample_data/moment_samples/tenant_1/transcript_2025-01-13T09-00-00Z_input.json \
  --model claude-sonnet-4-5 \
  --format yaml
```

### Integration Tests

```bash
# Run integration tests with real LLM
export ANTHROPIC_API_KEY=your-key
uv run pytest tests/integration/test_moment_builder.py -v
```

## Architecture Decisions

### 1. Prompting-Based Tool Control

**Problem**: LLMs might call registered tools instead of returning structured output.

**Solution**: Add instruction to user query rather than programmatically disabling tools.

```python
question = f"Analyze this content and return only the structured JSON analysis without using any tools or functions.\n\n{chunk}"
```

**Benefits**:
- Keeps tools available (orthogonal concerns)
- Uses natural language instruction
- Works across different providers
- Maintains clean architecture

### 2. YAML Schema Format

System prompts use YAML schema format for better readability:

```yaml
executive_summary:
  type: string
  description: Brief summary of current situation

goals:
  type: array
  items:
    type: object
  description: Goals and aspirations mentioned
```

Both Claude and GPT handle YAML schemas effectively.

### 3. Character-Based Chunking

Current implementation uses simple character count splitting:
- Default chunk size: 4000 characters
- Simple and reliable
- Works well in practice

**Future**: Token-based chunking with tiktoken for more accurate context window management.

## API Reference

### MemoryProxy.parse_content()

```python
async def parse_content(
    self,
    content: str,
    context: CallingContext | None = None,
    chunk_size: int = 4000,
    merge_strategy: str = "last"
) -> Any:
    """
    Parse large content using structured output with automatic pagination.

    Args:
        content: Large content to parse
        context: Calling context (will auto-set prefer_json=True)
        chunk_size: Max characters per chunk (default: 4000)
        merge_strategy: How to merge results - 'last', 'first', or 'merge'

    Returns:
        Parsed and validated model instance

    Raises:
        ValueError: If no model_context was provided to MemoryProxy
    """
```

### Utility Methods

```python
def _chunk_content(self, content: str, chunk_size: int) -> list[str]:
    """Split content into chunks by character count."""

def _extract_json(self, text: str) -> dict | None:
    """Extract JSON from markdown or plain text response."""

def _merge_results(self, results: list[dict], strategy: str) -> dict:
    """Merge multiple result dictionaries based on strategy."""
```

## Related Documentation

- **Function Registration**: `08 function-registration.md` - Tool registration guide
- **Memory Proxy**: `02 memory-proxy.md` - MemoryProxy usage
- **Document Parsers**: `09 doc-parsers.md` - Advanced document processing

## Implementation Files

- `src/p8fs/services/llm/memory_proxy.py:1647-1769` - Core implementation
- `src/p8fs/models/base.py` - AbstractModel base class
- `src/p8fs/models/agentlets/dreaming.py` - Example dream agent
- `src/p8fs/models/agentlets/moments.py` - Example moment agent
- `src/p8fs/utils/typing.py` - Type inspection utilities
