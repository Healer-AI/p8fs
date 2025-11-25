# P8FS Core Testing Strategy

## Testing Philosophy

We maintain strict separation between unit and integration tests, always executing tests in the `uv` environment. Unit tests are isolated and use mocks when necessary, while integration tests never mock and always use real services via Docker, Kind clusters, or live APIs. The `sample_data` directory contains curated samples for testing LLM API requests/responses, serialization, and special data handling cases.

Tets should follow the structure of the repo e.g. sub folders matching modules.

## Test Design Principles

### Lean and Focused Testing
Tests should be concise and test actual functionality in the codebase rather than generating excessive code and bloat. Always ask: "Is there a utility in the correct module that makes this test simpler?" Avoid creating boilerplate code in tests as this is hard to maintain and fails to properly test the core library.

### Use Existing Utilities
For tests involving LLMs (especially integration tests), use LLM clients already in the codebase rather than writing superfluous test code. This ensures we test real functionality and maintain consistency.

## Unit Testing Strategy

### TypeInspector Testing
Critical areas requiring comprehensive unit test coverage:

**Type Detection Methods:**
- `is_optional_type()`: Test with `Optional[T]`, `Union[T, None]`, `T | None`
- `is_union_type()`: Test with `Union[A, B]`, `Union[A, B, C]`, nested unions
- `is_list_type()`: Test with `List[T]`, `list[T]`, `typing.List`
- `is_dict_type()`: Test with `Dict[K, V]`, `dict[K, V]`, `typing.Dict`
- `is_vector_type()`: Test with `List[float]`, `List[int]` (should be false), nested lists
- `is_json_type()`: Test with complex types that should serialize to JSON

**Type Unwrapping and Analysis:**
- `get_non_none_type()`: Test Optional unwrapping, complex Union handling
- `get_primary_union_type()`: Test first-type extraction from unions
- `get_json_schema_type()`: Test schema generation for all supported types
- `extract_nested_types()`: Test recursive type extraction

**Edge Cases to Test:**
```python
# Complex nested types
List[Dict[str, Union[str, int, None]]]
Optional[Union[List[str], Dict[str, Any]]]
Union[str, int, List[float], None]

# Generic types
T = TypeVar('T')
Generic[T]

# Forward references
"List['SelfReference']"

# Callable types
Callable[[str, int], bool]
```

### Function Analysis Testing

**FunctionInspector Coverage:**
- Signature analysis with various parameter combinations
- Docstring extraction (with/without docstring_manager)
- Async vs sync function detection
- Parameter default handling
- Type annotation extraction

**From_Callable Testing:**
- Schema generation from function signatures
- Tool format conversion (OpenAI, Anthropic, Google)
- Callable wrapper functionality
- Error handling when type inspection fails
- Argument validation

**Test Function Samples:**
```python
# Simple function
def basic_func(name: str, age: int = 25) -> str: pass

# Complex types
def complex_func(
    items: List[Dict[str, Any]], 
    options: Optional[Union[str, int]] = None
) -> Union[List[str], Dict[str, int]]: pass

# Async function with docstring
async def documented_func(query: str, limit: int = 10) -> List[str]:
    """Search documents by query.
    
    Args:
        query: Search query string
        limit: Maximum results to return
        
    Returns:
        List of matching document IDs
    """
    pass
```

## Integration Testing Strategy

### LLM Provider Integration
Test tool generation and execution with real LLM APIs:

**Required Environment Variables:**
```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=claude-...
GOOGLE_API_KEY=AIza...
```

**Test Scenarios:**
- Generate OpenAI tool specs from functions and make actual API calls
- Test Anthropic Claude tool calling with generated schemas
- Validate Google Gemini function declarations
- Test streaming responses with tool calls
- Verify error handling with malformed tool schemas

**Shared LLM Client Pattern:**
```python
# Use existing clients from codebase
from p8fs.models.llm import OpenAIRequest, CallingContext
from p8fs.utils import From_Callable

def test_openai_tool_integration():
    func_wrapper = From_Callable(sample_function)
    tool_spec = func_wrapper.to_openai_tool()
    
    # Use existing client utilities, not custom test code
    context = CallingContext(model="gpt-4", tools=[tool_spec])
    # Test with real API call
```

### Database Integration

**Kind Cluster Requirements:**
For Kubernetes-based testing, the Kind cluster should include:
```yaml
# kind-config.yaml for testing
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  extraMounts:
  - hostPath: ./test-data
    containerPath: /test-data
```

**Database Containers:**
```yaml
# docker-compose.test.yml
services:
  tidb:
    image: pingcap/tidb:latest
    ports: ["4000:4000"]
    environment:
      - TIDB_HOST=0.0.0.0
    
  postgresql:
    image: postgres:15
    environment:
      POSTGRES_DB: p8fs_test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports: ["5432:5432"]
    
  tikv:
    image: pingcap/tikv:latest
    ports: ["20160:20160"]
```

**Integration Test Categories:**

1. **SQL Provider Integration:**
   - Type mapping accuracy across TiDB, PostgreSQL
   - Schema generation and table creation
   - Vector operations (TiDB VEC_* functions, pgvector)
   - Query generation and execution

2. **Repository Integration:**
   - TenantRepository with real storage backends
   - Multi-tenant isolation verification  
   - Embedding generation and similarity search
   - Batch operations and performance

3. **Model Integration:**
   - AbstractModel schema generation
   - Field metadata handling
   - Validation and serialization
   - Cross-provider compatibility

### Environment Setup for Integration Tests

**Required Infrastructure:**
- Docker or Kind cluster access
- Network connectivity for LLM APIs
- Persistent storage for test databases
- Environment variables for credentials

**Test Data Management:**
```
tests/
├── sample_data/
│   ├── functions/          # Sample functions for testing
│   ├── llm_requests/       # LLM API request samples
│   ├── llm_responses/      # Expected response formats
│   ├── type_samples/       # Complex type definitions
│   └── schemas/            # Expected JSON schemas
├── integration/
│   ├── test_llm_providers.py
│   ├── test_database_providers.py
│   └── test_repository_operations.py
└── unit/
    ├── test_type_inspector.py
    ├── test_function_inspector.py
    └── test_from_callable.py
```

**Continuous Integration Considerations:**
- Use GitHub Actions or similar for automated testing
- Separate test suites: `uv run pytest tests/unit` vs `uv run pytest tests/integration`  
- Integration tests require additional services and longer timeouts
- Mock external APIs only for rate limiting, never for functionality testing

## Performance and Load Testing

**Areas Requiring Performance Tests:**
- Type inspection on large, complex type hierarchies
- Function schema generation for functions with many parameters
- Repository bulk operations
- Vector similarity searches at scale
- SQL query generation performance

**Benchmarking Strategy:**
Use existing performance utilities in the codebase rather than custom benchmark code. Focus on real-world usage patterns and identify performance regressions early.