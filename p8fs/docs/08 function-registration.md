# Function Registration for Agent Tools

## Overview

When creating agent models with `MemoryProxy`, you can register custom methods as LLM-callable tools. The system automatically discovers and registers eligible methods while filtering out base class utilities and Pydantic internals.

## Function Discovery Rules

When `MemoryProxy(AgentModel)` is initialized, methods are registered as LLM tools based on these rules:

### ✅ INCLUDED (Registered as Tools)

1. **User-defined class methods** decorated with `@classmethod`
2. **User-defined instance methods** (bound to the class)
3. **Methods with `__qualname__` starting with the agent class name**

### ❌ EXCLUDED (NOT Registered as Tools)

1. **AbstractModel base methods** (inherited from base class)
2. **Pydantic utility methods** (model_dump, model_validate, etc.)
3. **Private methods** (starting with `_`)
4. **Pydantic decorators** (@model_validator, @field_serializer, etc.)

## Implementation

The function registration uses `get_class_and_instance_methods()` from `p8fs.utils.typing` which correctly filters based on inheritance:

```python
def _register_model_functions(self):
    """Register functions from the model context using selective filtering."""
    if not self._model_context or not self._function_handler:
        return

    from p8fs.utils.typing import get_class_and_instance_methods
    from p8fs.models.base import AbstractModel

    # Use selective filtering to avoid registering AbstractModel base methods
    methods = get_class_and_instance_methods(self._model_context, inheriting_from=AbstractModel)

    for method in methods:
        try:
            self._function_handler.add_function(method)
            logger.debug(f"Registered function: {method.__name__}")
        except Exception as e:
            logger.warning(f"Failed to register function {method.__name__}: {e}")
```

## Best Practices

### 1. Define Tool Methods as Class Methods

For stateless operations that don't need model instance data:

```python
from p8fs.models.base import AbstractModel
from pydantic import Field

class MyAgent(AbstractModel):
    """Agent with tool methods."""

    summary: str = Field(description="Analysis summary")

    @classmethod
    def search_database(cls, query: str) -> list[dict]:
        """
        Search the database for relevant records.

        Args:
            query: Search query string

        Returns:
            List of matching records
        """
        # Tool implementation
        return []
```

### 2. Use Instance Methods for Stateful Operations

When you need access to the model's current state:

```python
class MyAgent(AbstractModel):
    """Agent with stateful methods."""

    context: list[str] = Field(default_factory=list)

    def add_to_context(self, item: str) -> str:
        """
        Add an item to the agent's context.

        Args:
            item: Item to add

        Returns:
            Confirmation message
        """
        self.context.append(item)
        return f"Added {item} to context. Total items: {len(self.context)}"
```

### 3. Make Pydantic Validators Private

Ensure Pydantic decorators use private naming to avoid registration:

```python
class MyAgent(AbstractModel):
    """Agent with validators."""

    score: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _validate_completeness(self):
        """Validate model completeness (private method)."""
        if self.score < 0.5:
            raise ValueError("Score too low")
        return self
```

### 4. Document Tool Methods

Always include clear docstrings for tool methods:

```python
@classmethod
def fetch_recent_data(cls, hours: int = 24, limit: int = 100) -> list[dict]:
    """
    Fetch recent data from the system.

    This method retrieves data created within the specified time window.
    The LLM can call this to gather context for analysis.

    Args:
        hours: Number of hours to look back (default: 24)
        limit: Maximum number of records to return (default: 100)

    Returns:
        List of data records with timestamps and content

    Example:
        >>> data = fetch_recent_data(hours=48, limit=50)
        >>> len(data)
        50
    """
    # Implementation
    return []
```

## Common Patterns

### Read-Only Tools

Tools that retrieve data without side effects:

```python
@classmethod
def get_user_preferences(cls, user_id: str) -> dict:
    """Retrieve user preferences."""
    return {}

@classmethod
def search_resources(cls, query: str, days_back: int = 7) -> list[dict]:
    """Search resources by query."""
    return []
```

### Write Tools

Tools that modify state or create records:

```python
@classmethod
def create_reminder(cls, text: str, due_date: str) -> dict:
    """Create a new reminder."""
    return {"id": "123", "text": text, "due_date": due_date}

@classmethod
def update_status(cls, task_id: str, status: str) -> bool:
    """Update task status."""
    return True
```

### Analysis Tools

Tools that perform computations:

```python
@classmethod
def calculate_similarity(cls, text1: str, text2: str) -> float:
    """Calculate semantic similarity between two texts."""
    return 0.85

@classmethod
def extract_entities(cls, text: str) -> list[str]:
    """Extract named entities from text."""
    return ["Entity1", "Entity2"]
```

## Troubleshooting

### Method Not Being Registered

**Problem**: Your method isn't available as a tool in the LLM.

**Solutions**:
1. Ensure method doesn't start with `_` (private methods are excluded)
2. Check method is defined directly on your agent class, not inherited from AbstractModel
3. Verify method has a proper docstring
4. Use `@classmethod` decorator for class-level methods

### Pydantic Methods Appearing as Tools

**Problem**: Seeing errors about `model_dump` or other Pydantic methods.

**Solutions**:
1. Make sure validators use private naming: `_validate_...`
2. Check you're using `get_class_and_instance_methods()` with `inheriting_from=AbstractModel`
3. Update to latest version with proper filtering

### Tool Execution Failures

**Problem**: LLM calls a tool but execution fails.

**Solutions**:
1. Check tool method signature matches LLM expectations
2. Ensure return types are serializable (dict, list, str, int, float, bool)
3. Add error handling within tool methods
4. Review tool docstring for clarity

## Example: Complete Agent with Tools

```python
from p8fs.models.base import AbstractModel
from pydantic import Field, model_validator
from datetime import datetime

class ResearchAgent(AbstractModel):
    """
    Agent for conducting research and analysis.

    This agent can search databases, analyze content,
    and generate structured research reports.
    """

    model_config = {
        'full_name': 'agents.ResearchAgent',
        'description': 'Research and analysis agent'
    }

    # Output fields
    findings: list[dict] = Field(
        default_factory=list,
        description="Research findings"
    )
    summary: str | None = Field(
        None,
        description="Research summary"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score"
    )

    # Tool methods (registered automatically)
    @classmethod
    def search_papers(cls, query: str, limit: int = 10) -> list[dict]:
        """
        Search academic papers.

        Args:
            query: Search query
            limit: Max results

        Returns:
            List of paper records
        """
        # Implementation
        return []

    @classmethod
    def fetch_citations(cls, paper_id: str) -> list[str]:
        """
        Fetch citations for a paper.

        Args:
            paper_id: Paper identifier

        Returns:
            List of citation IDs
        """
        # Implementation
        return []

    @classmethod
    def calculate_impact_score(cls, paper_id: str) -> float:
        """
        Calculate paper impact score.

        Args:
            paper_id: Paper identifier

        Returns:
            Impact score (0.0 to 1.0)
        """
        # Implementation
        return 0.0

    # Private validator (NOT registered as tool)
    @model_validator(mode="after")
    def _validate_research_quality(self):
        """Validate research completeness."""
        if self.confidence > 0.8 and len(self.findings) == 0:
            raise ValueError("High confidence requires findings")
        return self
```

## Usage with MemoryProxy

```python
from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext

# Create proxy with agent model
proxy = MemoryProxy(model_context=ResearchAgent)

# LLM can now call: search_papers, fetch_citations, calculate_impact_score
context = CallingContext(
    model="claude-sonnet-4-5",
    tenant_id="test"
)

response = await proxy.run(
    "Research recent papers on quantum computing",
    context
)

# Agent uses registered tools during research
print(response)
```

## Related Documentation

- **Agentic Parser**: `07 agentic-parser.md` - Complete agent system overview
- **Memory Proxy**: `02 memory-proxy.md` - MemoryProxy usage guide
- **Type Utilities**: `utils.md` - Type inspection utilities

## Implementation Files

- `src/p8fs/services/llm/memory_proxy.py:1647-1769` - Function registration
- `src/p8fs/utils/typing.py` - `get_class_and_instance_methods()`
- `src/p8fs/services/llm/function_handler.py` - Function execution
- `src/p8fs/models/agentlets/dreaming.py` - Example agent with tools
