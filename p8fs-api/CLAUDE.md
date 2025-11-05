# P8FS API Module

## Module Overview

The P8FS API module provides FastAPI, MCP (Model Context Protocol) and CLI interfaces to the entire P8FS system. It serves as the primary entry point for client applications, development tools, and command-line interactions.

## Architecture

### Core Components

- **Auth Router**: OAuth 2.1 implementation with token management
- **Chat Router**: Streaming LLM endpoints for conversational AI
- **MCP Server**: Model Context Protocol server for IDE integration
- **Health Router**: System monitoring and health checks

### Key Features

- RESTful API endpoints with FastAPI
- Real-time streaming responses
- Rate limiting and CORS middleware
- Comprehensive error handling
- Development tool integration via MCP

## Development Standards

### Code Quality

- Write minimal, efficient code with clear intent
- Avoid workarounds; implement proper solutions
- Prioritize maintainability over quick fixes
- Keep implementations lean and purposeful
- No comments unless absolutely necessary for complex logic

### Testing Requirements

#### Unit Tests
- Mock external dependencies (database, LLM services)
- Test individual router endpoints in isolation
- Validate request/response models
- Test middleware functionality

#### Integration Tests
- Use real services (database, authentication)
- Test complete request flows
- Validate streaming endpoints
- Test MCP protocol compliance

### Configuration

All configuration must come from the centralized system in `p8fs_cluster.config.settings`. Never set individual environment variables for database connections or service endpoints.

```python
# ✅ CORRECT - Use centralized config
from p8fs_cluster.config.settings import config

# Access API-specific configuration
app_host = config.api_host
app_port = config.api_port
auth_settings = config.auth_settings

# ✅ CORRECT - Pass connection strings from config
database_url = config.pg_connection_string
```

```python
# ❌ WRONG - Don't set individual environment variables
# P8FS_API_HOST=localhost
# P8FS_API_PORT=8000

# ❌ WRONG - Don't hardcode configuration
app.run(host="localhost", port=8000)
```

### API Design Patterns

#### Router Structure
```python
# Minimal router implementation
from fastapi import APIRouter
from p8fs_cluster.config.settings import config

router = APIRouter(prefix="/api/v1")

@router.get("/health")
async def health_check():
    return {"status": "healthy"}
```

#### Streaming Endpoints
```python
from fastapi.responses import StreamingResponse

@router.post("/chat/stream")
async def stream_chat(request: ChatRequest):
    async def generate():
        async for chunk in chat_service.stream_response(request):
            yield f"data: {chunk}\n\n"
    
    return StreamingResponse(generate(), media_type="text/plain")
```

### Authentication Integration

The API module integrates with `p8fs-auth` for secure access:

```python
from p8fs_auth import verify_token, get_user_context

@router.post("/protected-endpoint")
async def protected_route(token: str = Depends(verify_token)):
    user_context = get_user_context(token)
    return process_request(user_context)
```

### MCP Server Implementation

The MCP server enables IDE integration:

```python
from mcp import MCPServer
from p8fs.services.llm import LanguageModelService

class P8FSMCPServer(MCPServer):
    def __init__(self):
        self.llm_service = LanguageModelService()
    
    async def handle_completion(self, request):
        return await self.llm_service.complete(request.prompt)
```

## Testing Approach

### Test Structure
```
tests/
├── unit/
│   ├── test_auth.py      # Auth router unit tests
│   ├── test_health.py    # Health endpoint tests
│   └── test_mcp.py       # MCP server unit tests
└── integration/
    └── test_mcp_integration.py  # End-to-end MCP tests
```

### Running Tests
```bash
# Unit tests with mocks
pytest tests/unit/ -v

# Integration tests with real services
pytest tests/integration/ -v

# All tests
pytest tests/ -v
```

### Example Test Patterns

#### Unit Test with Mocks
```python
from unittest.mock import Mock, patch
import pytest
from p8fs_api.routers.chat import router

@patch('p8fs_api.routers.chat.llm_service')
async def test_chat_endpoint(mock_llm_service):
    mock_llm_service.complete.return_value = "Test response"
    
    response = await client.post("/chat", json={"message": "Hello"})
    
    assert response.status_code == 200
    assert response.json()["response"] == "Test response"
```

#### Integration Test
```python
import pytest
from p8fs_cluster.config.settings import config

@pytest.mark.integration
async def test_chat_integration():
    # Uses real LLM service through centralized config
    response = await client.post("/chat", 
                               json={"message": "Hello"},
                               headers={"Authorization": f"Bearer {test_token}"})
    
    assert response.status_code == 200
    assert "response" in response.json()
```

## Dependencies

- **FastAPI**: Web framework
- **p8fs**: Core services and models
- **p8fs-auth**: Authentication and authorization
- **p8fs-cluster**: Configuration and logging

## Development Workflow

1. Start development services:
   ```bash
   cd ../p8fs
   docker-compose up postgres -d
   ```

2. Run the API server:
   ```bash
   # ALWAYS use uv for running the server
   # ALWAYS use --reload for development 
   # Be sure to check there is nothing already running on the port which could cause confusion e.g. 404s
   uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8001
   ```

3. Run tests:
   ```bash
   uv run pytest tests/ -v
   ```

4. Lint and type check:
   ```bash
   uv run ruff check src/
   uv run mypy src/
   ```

## Error Handling

Implement consistent error responses:

```python
from fastapi import HTTPException
from p8fs_api.models.responses import ErrorResponse

@router.post("/endpoint")
async def endpoint_handler():
    try:
        result = await service_call()
        return result
    except ServiceError as e:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(error=str(e), code="SERVICE_ERROR")
        )
```

## Performance Considerations

- Use async/await for I/O operations
- Implement proper connection pooling
- Add caching for frequently accessed data
- Monitor response times and optimize slow endpoints