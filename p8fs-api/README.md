# P8FS API Module

REST API, CLI, and MCP (Model Context Protocol) interfaces for the P8FS smart content management system. The MCP server is mounted on the the FastAPI application at api/mcp and supports the Stremable HTTP protocol. WE use FastMCP 2.0+ see [their docs](https://gofastmcp.com/llms-full.txt).

## Overview

The p8fs-api module provides the primary interface layer for P8FS, exposing REST endpoints, command-line tools, and MCP server capabilities. This module handles HTTP requests, authentication middleware, and protocol translation between clients and the core P8FS services.

## Architecture

### Components to Port

#### 1. FastAPI Application (`src/p8fs/api/main.py`)
- Application initialization and configuration
- Middleware stack setup (authentication, encryption, observability) that uses the p8fs-auth library
- Route registration and dependency injection
- Lifespan management for startup/shutdown tasks

#### 2. API Routes (`src/p8fs/api/routes/`)
- **Authentication** (`auth.py`): OAuth 2.1 flows, token management
- **KV Storage** (`kv.py`): Key-value operations with TiKV
- **Query** (`query.py`): SQL and natural language query interfaces
- **Embeddings** (`embeddings.py`): Vector operations and similarity search
- **Chat** (`chat.py`): LLM integration and streaming responses / models endpoint as per OpenAI spec
- **Health** (`health.py`): Liveness and readiness probes

#### 3. Controllers (`src/p8fs/api/controllers/`)
- Business logic separation from route handlers
- Input validation and response formatting
- Error handling and status code management

#### 4. Middleware Stack (`src/p8fs/api/middleware/`)
- **Authentication**: JWT validation and user context (uses the p8fs-auth module)
- **Encryption**: Request/response encryption for sensitive data 
- **Authentication**: JWT validation and user context 
- **Logging**: Structured request logging with correlation IDs
- **Metrics**: Request metrics for Prometheus
- **Observability**: OpenTelemetry tracing integration

#### 5. MCP Server (`src/p8fs/api/mcp/`)
- Model Context Protocol implementation
- Tool registration for AI assistants
- Streaming response handlers
- Context window management

#### 6. CLI Interface (`src/p8fs/cli/`)
- Command structure using Click/Typer
- Configuration management commands
- File operations and queries
- Administrative functions

## Refactoring Plan

### Phase 1: Core API Structure
1. Set up FastAPI application with proper configuration
2. Implement base middleware classes with clean interfaces
3. Create route registration system with automatic OpenAPI documentation
4. Establish dependency injection patterns for services

### Phase 2: Authentication Integration
1. Create authentication middleware using p8fs-auth module
2. Implement OAuth 2.1 endpoints with proper state management
3. Add device registration endpoints for mobile clients
4. Set up JWT validation with key rotation support

### Phase 3: Route Implementation
1. Implement file operations routes with streaming support
2. Add KV storage endpoints with batch operations
3. Create query interfaces with SQL generation
4. Set up embedding endpoints with caching

### Phase 4: MCP Server
1. Port MCP server implementation with tool definitions
2. Add streaming support for real-time responses
3. Implement context management for conversations
4. Create tool execution framework

### Phase 5: CLI Development
1. Structure CLI commands with subcommand groups
2. Implement configuration management interface
3. Add file operation commands with progress tracking
4. Create query interface with output formatting

## Testing Strategy

### Unit Tests
- Route handler testing with mocked dependencies
- Middleware behavior verification
- Input validation and error handling
- MCP tool execution testing

### Integration Tests
- Full API request/response cycles
- Authentication flow testing
- File upload/download operations
- Database query execution

### Performance Tests
- Load testing for concurrent requests
- Streaming response performance
- Large file handling
- Query optimization verification

## Dependencies

### Local P8FS Module Dependencies

The API integrates with other P8FS modules using a two-pronged approach:

1. **Dependency Installation** - Modules are installed as local packages in `pyproject.toml`:
   ```toml
   dependencies = [
       # ... other dependencies ...
       "p8fs-cluster @ file:///Users/sirsh/code/p8fs-modules/p8fs-cluster",
       "p8fs @ file:///Users/sirsh/code/p8fs-modules/p8fs", 
       "p8fs-auth @ file:///Users/sirsh/code/p8fs-modules/p8fs-auth",
   ]
   ```

2. **Development PYTHONPATH** - The `.envrc` file adds modules to PYTHONPATH for development:
   ```bash
   export PYTHONPATH="${P8FS_MODULES_ROOT}/p8fs-cluster/src:..."
   ```

This dual approach ensures:
- All transitive dependencies are properly installed via `uv sync`
- Live code changes are reflected immediately during development
- No manual dependency management required
- Consistent behavior between development and production

### External Services
- p8fs-auth: Authentication and authorization
- p8fs: Core business logic and repositories
- p8fs-node: File processing and embeddings

### Key Libraries
- FastAPI: Web framework
- Hypercorn/Uvicorn: ASGI servers
- OpenTelemetry: Distributed tracing
- Prometheus: Metrics collection
- Pydantic: Data validation

## Configuration

Environment variables for API configuration:
- `P8FS_API_HOST`: API binding address
- `P8FS_API_PORT`: API port number
- `P8FS_AUTH_SERVICE`: Authentication service URL
- `P8FS_CORE_SERVICE`: Core service URL
- `P8FS_NODE_SERVICE`: Node service URL
- `P8FS_CORS_ORIGINS`: Allowed CORS origins
- `P8FS_MAX_UPLOAD_SIZE`: Maximum file upload size
- `P8FS_REQUEST_TIMEOUT`: Request timeout duration

### Critical Production Settings

When deploying to Kubernetes, these parameters must be explicitly set:

**Required**:
- `P8FS_STORAGE_PROVIDER`: Must be set to `tidb`, `postgresql`, or `rocksdb` (defaults to `postgresql` if not set)
- `P8FS_JWT_PRIVATE_KEY_PEM`: JWT signing private key (via Secret)
- `P8FS_JWT_PUBLIC_KEY_PEM`: JWT signing public key (via Secret)

**Required for TiDB**:
- `P8FS_TIDB_HOST`: TiDB server hostname
- `P8FS_TIKV_ENDPOINTS`: TiKV PD endpoints as JSON array

Generate JWT keys:
```bash
cd p8fs-api
uv run python scripts/dev/generate_server_jwt_signing_keys.py
```

## API Design Principles

1. **RESTful Design**: Consistent resource-based URLs
2. **Versioning**: API version in URL path (`/api/v1/`)
3. **Error Handling**: Consistent error response format
4. **Pagination**: Cursor-based pagination for large datasets
5. **Streaming**: Server-sent events for real-time data
6. **Documentation**: Auto-generated OpenAPI specifications

## Security Considerations

- All endpoints require authentication except health checks
- Request signing for sensitive operations
- Rate limiting per user/device
- Input sanitization and validation
- SQL injection prevention in query endpoints
- File type validation for uploads

## Implementation Status

### Completed Components

#### Core Infrastructure
- **FastAPI Application**: Production-ready ASGI app with structured logging
- **Configuration**: Environment-based settings with Pydantic validation
- **Middleware Stack**: Authentication, CORS, rate limiting, security headers
- **Error Handling**: Comprehensive exception handling with structured responses
- **Request Logging**: Structured JSON logging with correlation IDs

#### Authentication System
- **JWT Middleware**: Token validation with user context injection
- **OAuth 2.1 Endpoints**: All required endpoints with placeholder implementations
  - `POST /oauth/token` - Token exchange endpoint
  - `POST /oauth/device/code` - Device authorization initiation
  - `POST /oauth/device/token` - Device token polling
  - `POST /oauth/revoke` - Token revocation
  - `GET /oauth/userinfo` - User information
- **Mobile Authentication**: Device registration and verification flows
- **Rate Limiting**: Configurable per-endpoint rate limits

#### Chat API (OpenAI Compatible)
- **Chat Completions**: Both streaming and non-streaming responses
- **Models Endpoint**: List and retrieve model information
- **OpenAI Compatibility**: Standard request/response formats
- **Streaming Support**: Server-sent events for real-time responses

#### MCP Server (Model Context Protocol)
- **HTTP-based MCP**: Full MCP server implementation
- **Tool Registration**: Pre-configured tools for AI assistants
  - `search_files` - File search functionality
  - `get_file_content` - File content retrieval
  - `query_memory` - Memory system queries
- **Resource Management**: Dynamic resource listing
- **Batch Requests**: Support for multiple MCP requests

#### Health & Monitoring
- **Health Checks**: Kubernetes-compatible liveness/readiness probes
- **Metrics Integration**: Prometheus metrics support (configured)
- **OpenTelemetry**: Distributed tracing setup (configured)
- **Security Headers**: OWASP recommended security headers

### Implementation Notes

#### Controllers (Placeholder Implementation)
All controllers return placeholder responses and require integration with actual services:

```python
# AuthController - delegates to p8fs-auth service
# ChatController - delegates to p8fs and p8fs-node
# MCPServer - delegates to p8fs for tool execution
```

#### Required Integrations
1. **p8fs-auth Service**: JWT validation, OAuth flows, device management
2. **p8fs Service**: Memory queries, file operations, repositories
3. **p8fs-node Service**: Content processing, embeddings, ML inference

#### Environment Configuration
Copy `.env.example` to `.env` and configure:
- JWT signing keys
- Service endpoints
- CORS origins
- Rate limiting settings

## Quick Start

### Development Environment Setup

The project uses `direnv` for automatic environment setup:

```bash
# Install direnv (if not already installed)
brew install direnv  # macOS
apt-get install direnv  # Ubuntu/Debian

# Enable direnv in your shell (add to ~/.bashrc or ~/.zshrc)
eval "$(direnv hook bash)"   # for bash
eval "$(direnv hook zsh)"    # for zsh

# Allow the environment in this directory
cd /path/to/p8fs-api
direnv allow
```

The `.envrc` file automatically:
- Sets up PYTHONPATH for all P8FS modules
- Configures development environment variables
- Creates/activates a Python virtual environment

### Development Setup
```bash
# Install dependencies (includes local P8FS modules)
uv sync --dev

# Run development server with auto-reload
uv run python -m p8fs_api --reload

# The server will start with:
# - Auto-reload enabled for code changes
# - Interactive API docs at http://localhost:8000/docs
# - ReDoc at http://localhost:8000/redoc
```

### Running the API

```bash
# Development with auto-reload (recommended)
uv run python -m p8fs_api --reload

# Production mode (no reload, multiple workers)
uv run python -m p8fs_api --workers 4

# Custom host/port
uv run python -m p8fs_api --host 0.0.0.0 --port 8080

# View all options
uv run python -m p8fs_api --help
```

### Docker Production Deployment

For production, use Docker with Hypercorn:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .
CMD ["hypercorn", "p8fs_api.main:app", "--bind", "0.0.0.0:8000"]
```

### Production Deployment
```bash
# Install production dependencies
uv sync

# Run with Hypercorn
hypercorn p8fs_api.main:app --bind 0.0.0.0:8000 --workers 4
```

### API Testing
```bash
# Run unit tests
uv run pytest tests/unit/ -v

# Run all tests with coverage
uv run pytest --cov=p8fs_api

# Run specific test file
uv run pytest tests/unit/test_health.py -v

# Test API endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/mcp/capabilities

# Test API with Python script
uv run python scripts/test_api.py
```

## API Endpoint Reference

### Core System Endpoints

| Endpoint | Method | Description | Auth Required | Status |
|----------|--------|-------------|---------------|---------|
| `/` | GET | API information and version | No | Implemented |
| `/health` | GET | System health check | No | Implemented |
| `/ready` | GET | Kubernetes readiness probe | No | Implemented |
| `/live` | GET | Kubernetes liveness probe | No | Implemented |

### Authentication Endpoints (OAuth 2.1 Compliant)

| Endpoint | Method | Description | Auth Required | Status |
|----------|--------|-------------|---------------|---------|
| `/oauth/authorize` | GET | Authorization endpoint with PKCE | No | Placeholder |
| `/oauth/token` | POST | Token exchange (auth code, refresh, device) | No | Implemented |
| `/oauth/revoke` | POST | Token revocation | No | Implemented |
| `/oauth/introspect` | POST | Token introspection | No | Missing |
| `/oauth/userinfo` | GET | OpenID Connect UserInfo | Yes | Implemented |
| `/oauth/device/code` | POST | Device authorization (RFC 8628) | No | Implemented |
| `/oauth/device/token` | POST | Device token polling | No | Implemented |
| `/oauth/device/approve` | POST | Mobile device approval | Yes | Implemented |
| `/oauth/device/api-key` | POST | Temporary API key generation | Yes | Missing |

### Mobile Authentication (Advanced)

| Endpoint | Method | Description | Auth Required | Status |
|----------|--------|-------------|---------------|---------|
| `/oauth/device/register` | POST | Mobile device registration | No | Implemented |
| `/oauth/device/verify` | POST | Email verification | No | Implemented |
| `/api/v1/auth/keypair/rotate` | POST | Ed25519 key rotation | Yes | Missing |
| `/api/v1/auth/devices` | GET | List registered devices | Yes | Missing |
| `/api/v1/auth/devices/{id}` | DELETE | Revoke device access | Yes | Missing |
| `/api/v1/auth/email/add` | POST | Add additional email | Yes | Missing |
| `/api/v1/auth/email/verify` | POST | Verify additional email | Yes | Missing |

### Chat API (OpenAI Compatible)

| Endpoint | Method | Description | Auth Required | Status |
|----------|--------|-------------|---------------|---------|
| `/api/v1/chat/completions` | POST | Chat completions (streaming/non-streaming) | Yes | Implemented |
| `/api/v1/models` | GET | List available models | No | Implemented |
| `/api/v1/models/{id}` | GET | Get specific model information | No | Implemented |
| `/api/v1/agent/{agent_key}/chat/completions` | POST | Agent-specific chat endpoint | Yes | Missing |

### File Management (TUS Protocol)

| Endpoint | Method | Description | Auth Required | Status |
|----------|--------|-------------|---------------|---------|
| `/api/v1/files/` | POST | Create upload session (TUS) | Yes | Missing |
| `/api/v1/files/{upload_id}` | HEAD | Get upload info | Yes | Missing |
| `/api/v1/files/{upload_id}` | PATCH | Upload file chunks | Yes | Missing |
| `/api/v1/files/{upload_id}` | DELETE | Delete upload session | Yes | Missing |
| `/api/v1/files/{upload_id}/status` | GET | Upload progress status | Yes | Missing |

### Data Storage & Querying

| Endpoint | Method | Description | Auth Required | Status |
|----------|--------|-------------|---------------|---------|
| `/api/v1/kv/{key}` | PUT | Store key-value pair | Yes | Missing |
| `/api/v1/kv/{key}` | GET | Retrieve value by key | Yes | Missing |
| `/api/v1/kv/{key}` | DELETE | Delete key-value pair | Yes | Missing |
| `/api/v1/kv/` | GET | List keys with filtering | Yes | Missing |
| `/api/v1/kv/bulk` | POST | Bulk KV operations | Yes | Missing |
| `/api/v1/query/sql` | POST | Execute SQL queries | Yes | Missing |
| `/api/v1/query/vector-search` | POST | Vector similarity search | Yes | Missing |
| `/api/v1/query/hybrid` | POST | Hybrid multi-index queries | Yes | Missing |

### MCP Server (Model Context Protocol)

| Endpoint | Method | Description | Auth Required | Status |
|----------|--------|-------------|---------------|---------|
| `/api/mcp/` | POST | Main MCP endpoint (batch requests) | Optional | Implemented |
| `/api/mcp/capabilities` | GET | Server capabilities and info | No | Implemented |
| `/api/mcp/tools` | GET | Available MCP tools | No | Implemented |

## Recommended Request Headers

### Authentication Headers
```http
# Standard JWT authentication
Authorization: Bearer <jwt_token>

# API key authentication (alternative)
X-API-Key: pk_live_<api_key>

# Tenant isolation (multi-tenant deployments)
X-Tenant-ID: <tenant_uuid>
```

### Chat & Agent Headers
```http
# Agent routing for specialized endpoints
X-P8-Agent: p8-research | p8-analysis | p8-sim

# Audio message processing
X-Chat-Is-Audio: true

# Session management
X-Chat-Session-ID: <session_uuid>

# Device context for personalization
X-Device-ID: <device_uuid>
X-Device-Type: mobile | desktop | api
```

### File Upload Headers (TUS Protocol)
```http
# TUS protocol version
Tus-Resumable: 1.0.0

# File size for upload
Upload-Length: <bytes>

# Current upload position
Upload-Offset: <bytes>

# File metadata (base64 encoded key-value pairs)
Upload-Metadata: filename dGVzdC5wZGY=,filetype YXBwbGljYXRpb24vcGRm
```

### Content Type Headers
```http
# Standard API requests
Content-Type: application/json

# File uploads
Content-Type: application/octet-stream

# Streaming responses
Content-Type: text/event-stream

# Form data (OAuth endpoints)
Content-Type: application/x-www-form-urlencoded
```

### Security Headers
```http
# Request signing (for sensitive operations)
X-Signature: <ed25519_signature>

# Request timestamp (replay protection)
X-Timestamp: <unix_timestamp>

# Request nonce (replay protection)
X-Nonce: <random_string>
```

## Chat Completions Enhanced Features

### Audio Message Support
When sending audio messages, include the `X-Chat-Is-Audio: true` header. The system will:
- Transcribe audio using Faster Whisper
- Process transcription as chat input
- Support speaker diarization for multi-speaker audio

### Session Management
Use `X-Chat-Session-ID` header to maintain conversation context across requests:
- Persistent memory across chat interactions
- Context window management
- Conversation history retrieval

### Device-Specific Features
Include device headers for enhanced functionality:
- **Mobile**: Optimized responses for mobile UI
- **Desktop**: Full-featured responses with rich formatting
- **API**: Structured data responses for programmatic access

### Agent Routing
Use `X-P8-Agent` header to route to specialized agents:
- **p8-research**: Research and analysis tasks
- **p8-analysis**: Data analysis and insights
- **p8-sim**: Simulation mode for testing without LLM costs

## Security Features

- **JWT Authentication**: HS256/RS256 token validation
- **Rate Limiting**: Per-endpoint and per-user limits
- **CORS Protection**: Configurable origin restrictions
- **Security Headers**: OWASP recommended headers
- **Request Validation**: Pydantic-based input validation
- **Error Sanitization**: No sensitive data in error responses

## Reference Implementation Comparison

### Current Implementation Status
**Completed**: 15 endpoints covering basic OAuth 2.1, chat completions, MCP server, health checks  
**Placeholder**: Controllers return mock data, ready for service integration  
**Missing**: 25+ advanced endpoints from reference implementation

### Key Differences from Reference

#### Missing Critical Features
1. **File Upload System**: Complete TUS protocol implementation for resumable uploads
2. **Advanced Authentication**: Ed25519 cryptographic authentication, device management
3. **Data Storage APIs**: Key-value store, entity management, SQL/vector queries
4. **Agent System**: Multi-agent routing (p8-research, p8-analysis, p8-sim)
5. **Audio Processing**: `X-Chat-Is-Audio` header support with transcription
6. **Mobile Features**: QR code pairing, device key rotation, multi-email support

#### Architecture Gaps
- **Multi-Tenant**: No tenant isolation headers or routing
- **Encryption**: Missing Ed25519 signatures and request signing
- **Session Management**: No persistent chat sessions or context
- **Memory System**: No integration with percolate memory proxy
- **Job Processing**: No async job management system

#### Security Differences
- **Current**: Basic JWT with HS256
- **Reference**: Ed25519 + JWT + device attestation + request signing

### Implementation Priority

#### Phase 1: Essential Missing Endpoints
1. `POST /oauth/introspect` - Token introspection
2. `POST /oauth/device/api-key` - API key generation  
3. `GET /api/v1/auth/devices` - Device management
4. `POST /api/v1/agent/{agent}/chat/completions` - Agent routing

#### Phase 2: File & Data Management
1. TUS file upload endpoints (`POST`, `PATCH`, `HEAD`, `DELETE /api/v1/files/*`)
2. Key-value storage (`GET`, `PUT`, `DELETE /api/v1/kv/*`)
3. Query endpoints (`POST /api/v1/query/*`)

#### Phase 3: Advanced Features
1. Audio processing with transcription
2. Session management and persistence
3. Ed25519 cryptographic authentication
4. Multi-tenant architecture

## Testing the Streaming Chat API

### JWT Token Generation

The API requires JWT tokens for authentication. Use the `p8fs-auth` CLI tool to generate test tokens:

```bash
# Generate a test JWT token
cd /Users/sirsh/code/p8fs-modules/p8fs-auth
uv run p8fs-auth generate-token -u test-user -s read -s write --output token

# The token will be output to stdout, e.g.:
# eyJhbGciOiJFUzI1NiIsImtpZCI6Ij...q2ieSbQStw5uqBdIlmhQ
```

For development, you can also use the `get_dev_jwt.py` script:

```bash
# Set the development secret
export P8FS_DEV_TOKEN_SECRET='p8fs-dev-dHMZAB_dK8JR6ps-zLBSBTfBeoNdXu2KcpNywjDfD58'

# Generate and save JWT to ~/.p8fs/auth/token.json
cd /Users/sirsh/code/p8fs-modules/p8fs-api
python scripts/dev/get_dev_jwt.py

# Extract the token
TOKEN=$(jq -r '.access_token' ~/.p8fs/auth/token.json)
```

### Testing Non-Streaming Chat

Test the non-streaming chat endpoint with curl:

```bash
# Set your JWT token
TOKEN="your-jwt-token-here"

# Test non-streaming request
curl -X POST http://localhost:8000/api/v1/agent/p8-sim/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello, how are you?"}],
    "stream": false
  }'
```

**Example Response:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "gpt-4",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Hello! I'm a simulated AI assistant. How can I help you today?"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 5,
    "completion_tokens": 13,
    "total_tokens": 18
  }
}
```

### Testing Streaming Chat

Test the streaming endpoint to receive Server-Sent Events (SSE):

```bash
# Test streaming request with curl -N (no buffering)
curl -N -X POST http://localhost:8000/api/v1/agent/p8-sim/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Count from 1 to 5"}],
    "stream": true
  }'
```

**Example Streaming Response:**
```
data: {"id":"chatcmpl-xyz789","object":"chat.completion.chunk","created":1234567890,"model":"gpt-4","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-xyz789","object":"chat.completion.chunk","created":1234567890,"model":"gpt-4","choices":[{"index":0,"delta":{"content":"Thank"},"finish_reason":null}]}

data: {"id":"chatcmpl-xyz789","object":"chat.completion.chunk","created":1234567890,"model":"gpt-4","choices":[{"index":0,"delta":{"content":" you"},"finish_reason":null}]}

data: {"id":"chatcmpl-xyz789","object":"chat.completion.chunk","created":1234567890,"model":"gpt-4","choices":[{"index":0,"delta":{"content":" for"},"finish_reason":null}]}

[... more chunks ...]

data: {"id":"chatcmpl-xyz789","object":"chat.completion.chunk","created":1234567890,"model":"gp4","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### Python Client Example

Here's how to test streaming with Python:

```python
import httpx
import json
import asyncio

async def test_streaming():
    token = "your-jwt-token-here"
    
    async with httpx.AsyncClient() as client:
        # Streaming request
        async with client.stream(
            "POST",
            "http://localhost:8000/api/v1/agent/p8-sim/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Write a haiku"}],
                "stream": True
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0
        ) as response:
            
            full_content = ""
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    
                    if data_str == "[DONE]":
                        print("\nStreaming complete!")
                        break
                    
                    try:
                        chunk = json.loads(data_str)
                        if "choices" in chunk and chunk["choices"]:
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                content = delta["content"]
                                full_content += content
                                print(content, end="", flush=True)
                    except json.JSONDecodeError:
                        pass
            
            print(f"\n\nFull response: {full_content}")

# Run the test
asyncio.run(test_streaming())
```

### Testing with Standard Endpoint

The standard OpenAI-compatible endpoint also supports agent routing via headers:

```bash
# Route to simulation agent using X-P8-Agent header
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-P8-Agent: p8-sim" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```

### Simulation Mode Testing

The `p8-sim` agent provides deterministic responses for testing without calling real LLMs:

```bash
# Test various prompt types
curl -N -X POST http://localhost:8000/api/v1/agent/p8-sim/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "write code"}],
    "stream": true
  }'
```

The simulation agent provides different response types based on keywords:
- "hello/hi/hey" → Greeting response
- "code/program/function" → Code example with syntax highlighting
- "table/data/comparison" → Formatted table
- "list/steps/how to" → Numbered list
- Other → Generic response acknowledging the question

### Verifying SSE Format

The streaming responses follow the Server-Sent Events (SSE) specification:
- Each data line starts with `data: ` 
- JSON chunks contain OpenAI-compatible streaming format
- Empty line separates each event
- Final message is `data: [DONE]`

### Authentication Testing

Test that authentication is properly enforced:

```bash
# Request without token (should return 401)
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'

# Response:
# {
#   "error": "unauthorized",
#   "message": "Authentication required. Please provide a valid Bearer token",
#   "status_code": 401
# }
```

## Next Steps

1. **File Upload Priority**: Implement TUS protocol for resumable uploads
2. **Agent System**: Add agent routing for specialized chat endpoints
3. **Authentication Enhancement**: Upgrade to Ed25519 + device management
4. **Data Layer**: Implement KV store and query endpoints
5. **Audio Support**: Add transcription pipeline integration
6. **Service Integration**: Connect to p8fs-auth, p8fs, p8fs-node services
7. **Observability**: Enable Prometheus metrics and OpenTelemetry tracing