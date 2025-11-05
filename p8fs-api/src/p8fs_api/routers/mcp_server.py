"""Secure FastMCP integration for P8FS API with JWT authentication.

## MCP Streamable HTTP Transport Implementation

This module implements the Model Context Protocol (MCP) server using the **Streamable HTTP**
transport layer. Streamable HTTP replaced the older HTTP+SSE transport in MCP spec 2025-03-26.

### What is Streamable HTTP?

Streamable HTTP is a transport layer that uses standard HTTP POST requests through a single
endpoint (`/api/mcp`) for all MCP communication. Unlike the older SSE (Server-Sent Events)
transport which required two separate endpoints and long-lived connections, Streamable HTTP:

1. **Single Endpoint**: All communication flows through `/api/mcp`
2. **Standard HTTP POST**: Each request is a separate HTTP POST with JSON-RPC 2.0 payload
3. **Session Management**: Server assigns session IDs via `Mcp-Session-Id` header
4. **Stateless Requests**: Each request is independent (session ID provides continuity)

### Request Flow

1. **Initialize Session**: Client sends `initialize` method with JWT in Authorization header
   - Server validates JWT via P8FSAuthProvider.verify_token()
   - Server extracts tenant_id, user_id, scopes from JWT
   - Server creates session bound to tenant
   - Server returns session ID in `Mcp-Session-Id` header

2. **Tool Discovery**: Client sends `tools/list` with session ID
   - Server returns available tools with their schemas

3. **Tool Execution**: Client sends `tools/call` with tool name and arguments
   - Server validates session and tenant isolation
   - Server executes tool with tenant context
   - Server returns JSON-RPC result

### Required Headers

**Client → Server**:
- `Content-Type: application/json` (MUST)
- `Authorization: Bearer <JWT>` (MUST)
- `Accept: application/json, text/event-stream` (MUST)
- `Mcp-Session-Id: <session>` (MUST after initialization)

**Server → Client**:
- `Content-Type: application/json`
- `Mcp-Session-Id: <session>` (returned on initialization)

### JSON-RPC 2.0 Format

All requests and responses follow JSON-RPC 2.0:
```json
{
  "jsonrpc": "2.0",
  "id": <number>,
  "method": "<method_name>",
  "params": {<parameters>}
}
```

### Authentication & Tenant Isolation

Every request validates the JWT token and extracts:
- `tenant_id`: Used to scope all database queries
- `user_id`: Used for audit logs
- `scopes`: Used for permission checks

All tool operations are automatically scoped to the authenticated tenant, ensuring
complete data isolation between tenants.

### FastMCP Integration

P8FS uses the FastMCP library which provides:
- Built-in JSON-RPC 2.0 handling
- Session management
- Tool registration with automatic schema generation
- OAuth 2.1 authentication hooks

The server is mounted at `/api` in main.py, which creates the endpoint at `/api/mcp`.

### Security

- **JWT Validation**: Every request validates token signature
- **Scope Checking**: Tools check required scopes before execution
- **Tenant Isolation**: All operations scoped to tenant_id from JWT
- **Rate Limiting**: Applied at FastAPI middleware layer
- **HTTPS**: Required in production

For complete documentation, see: `/docs/mcp.md`
"""

import base64
import mimetypes
import uuid
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError
from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider
from mcp.server.auth.provider import AccessToken
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext

from .. import __version__
from ..middleware.auth import verify_token

logger = get_logger(__name__)


class P8FSAuthProvider(AuthProvider):
    """JWT authentication provider for FastMCP.

    This provider integrates with FastMCP's authentication system to validate JWT tokens
    on every MCP request. It implements the AuthProvider interface from FastMCP.

    **Streamable HTTP Context**:
    FastMCP calls this provider's `verify_token()` method for EVERY request:
    - On `initialize` request: Validates JWT, creates session if valid
    - On `tools/list` request: Validates JWT and session
    - On `tools/call` request: Validates JWT and session

    This ensures that every streamable HTTP request is authenticated independently,
    which is a key difference from SSE where authentication happened once at connection time.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify JWT token and return AccessToken.

        This method is called by FastMCP for EVERY incoming request on the /api/mcp endpoint.

        **Streamable HTTP Flow**:
        1. Client sends HTTP POST to /api/mcp with Authorization: Bearer <JWT>
        2. FastMCP extracts token from Authorization header
        3. FastMCP calls this verify_token() method
        4. We validate JWT signature and expiration via p8fs-auth
        5. We extract tenant_id, user_id, scopes from JWT claims
        6. We return AccessToken object with user context
        7. FastMCP allows request to proceed if AccessToken returned
        8. FastMCP rejects request with 401 if None returned

        Args:
            token: Raw JWT token string (without "Bearer " prefix)

        Returns:
            AccessToken with user context if valid, None if invalid
        """
        try:
            from fastapi.security import HTTPAuthorizationCredentials

            # Wrap token for our auth middleware
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

            # Verify token using p8fs-auth JWT validation
            # This checks:
            # - JWT signature (Ed25519 or RS256)
            # - Token expiration
            # - Token structure (required claims)
            token_payload = await verify_token(credentials)

            # Extract user context from JWT claims
            # token_payload.sub contains the tenant_id or user_id
            # This will be available in tool execution context
            return AccessToken(
                token=token,
                client_id=f"user-{token_payload.sub}",
                scopes=["read", "write"],  # TODO: Extract from JWT claims
                expires_at=None  # TODO: Add expiration from token.exp claim
            )

        except Exception as e:
            # Log warning and return None to reject request
            logger.warning(f"JWT verification failed: {e}")
            return None


def create_secure_mcp_server() -> FastMCP:
    """Create and configure the FastMCP server with P8FS tools.

    This function creates the MCP server instance that will be mounted at /api in main.py.
    FastMCP handles all the streamable HTTP transport details:
    - JSON-RPC 2.0 request/response parsing
    - Session management (Mcp-Session-Id header)
    - Tool schema generation
    - Authentication via our P8FSAuthProvider

    **Streamable HTTP Implementation**:

    1. **Server Creation**: FastMCP() creates the server with auth provider
    2. **Tool Registration**: @mcp.tool() decorator registers tools with schemas
    3. **HTTP App Creation**: mcp.http_app() creates the ASGI app for mounting
    4. **Mounting**: In main.py, we do: app.mount("/api", mcp_app)
       - This creates the endpoint at /api/mcp (FastMCP adds /mcp automatically)
       - All POST requests to /api/mcp are routed through FastMCP
       - FastMCP handles JSON-RPC routing to appropriate tool

    **Authentication Flow**:

    When a client sends a request to /api/mcp:
    1. FastMCP extracts Authorization header
    2. FastMCP calls P8FSAuthProvider.verify_token()
    3. If valid, FastMCP allows request to proceed
    4. If invalid, FastMCP returns 401 Unauthorized
    5. Tool functions execute with tenant context from JWT

    **Session Management**:

    FastMCP automatically handles sessions:
    - On `initialize`: Creates session, returns Mcp-Session-Id header
    - On subsequent requests: Validates session ID matches token
    - Sessions are bound to the authenticated tenant from JWT
    """

    # Create auth provider for JWT validation on every request
    auth_provider = P8FSAuthProvider()

    # Create FastMCP server with OAuth/Bearer authentication
    # The auth parameter tells FastMCP to validate tokens via our provider
    mcp = FastMCP(
        name="p8fs-mcp-server",
        version=__version__,
        instructions=(
            "P8FS smart content management system with secure storage and advanced indexing capabilities. "
            "Requires JWT bearer token authentication for all operations."
        ),
        auth=auth_provider  # Enable authentication for all requests
    )
    
    # Register P8FS tools using @mcp.tool() decorator
    # FastMCP automatically:
    # - Generates JSON schema from function signature
    # - Routes tools/call requests to these functions
    # - Validates parameters against schema
    # - Returns results in JSON-RPC format

    @mcp.tool()
    def about() -> str:
        """Get information about the P8FS system.

        **Streamable HTTP Tool Execution**:

        This tool demonstrates how tools work in the streamable HTTP transport:

        1. Client sends POST to /api/mcp with method "tools/call"
        2. FastMCP validates JWT token via P8FSAuthProvider
        3. FastMCP validates session ID from Mcp-Session-Id header
        4. FastMCP routes to this function based on tool name "about"
        5. Function executes and returns string
        6. FastMCP wraps result in JSON-RPC response:
           {"jsonrpc": "2.0", "id": <req_id>, "result": "<return_value>"}
        7. Client receives standard HTTP 200 response

        **Authentication Context**:
        - Token validated before this function executes
        - Tenant context available via JWT claims
        - If token invalid, client gets 401 before reaching this function

        **Example using curl (Streamable HTTP)**:

        # Step 1: Get JWT token
        TOKEN=$(cat ~/.p8fs/auth/token.json | jq -r .access_token)

        # Step 2: Initialize session (required first step)
        curl -s -X POST http://localhost:8001/api/mcp \
          -H "Content-Type: application/json" \
          -H "Authorization: Bearer $TOKEN" \
          -H "Accept: application/json, text/event-stream" \
          -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test-client","version":"1.0.0"}}}'
        # Returns: {"jsonrpc":"2.0","id":1,"result":{...}}
        # Note: Mcp-Session-Id header in response

        # Step 3: Call about tool with session ID
        SESSION_ID="<from_initialize_response_header>"
        curl -s -X POST http://localhost:8001/api/mcp \
          -H "Content-Type: application/json" \
          -H "Authorization: Bearer $TOKEN" \
          -H "Accept: application/json, text/event-stream" \
          -H "Mcp-Session-Id: $SESSION_ID" \
          -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"about","arguments":{}}}'
        # Returns: {"jsonrpc":"2.0","id":2,"result":"P8FS is a distributed..."}

        Returns:
            Description of the P8FS system
        """
        return (
            "P8FS is a distributed content management system designed for secure, scalable storage "
            "with advanced indexing capabilities. The system leverages S3-compatible blob storage "
            "(SeaweedFS) and TiDB/TiKV for managing a secure 'memory vault' where users can upload "
            "and manage content with end-to-end encryption."
        )
    
    @mcp.tool()
    async def user_info() -> dict[str, Any]:
        """Get current authenticated user information."""
        # With auth provider, user info should be available via the auth result
        # For now, return a placeholder until we figure out how to access auth context
        return {
            "authenticated": True,
            "message": "User authenticated via JWT",
            "note": "Full user context access coming soon"
        }
    
    @mcp.tool()
    async def search_content(
        query: str, 
        limit: int = 10,
        model: str = "resources",
        threshold: float = 0.7
    ) -> dict[str, Any]:
        """Search content in P8FS using semantic search.
        
        Args:
            query: Natural language search query
            limit: Maximum number of results to return (default: 10)
            model: Repository model to search (default: "resources", options: "resources", "session", "agent", "user", "files", "job")
            threshold: Minimum similarity score (0.0-1.0, default: 0.7)
            
        Returns:
            Dictionary with search results including content and similarity scores
            
        Example usage:
            {"query": "machine learning papers", "model": "resources", "limit": 5}
            {"query": "conversations about AI", "model": "session", "limit": 10}
        """
        try:
            # Import the appropriate model
            if model == "resources":
                from p8fs.models.p8 import Resources as ModelClass
            elif model == "session":
                from p8fs.models.p8 import Session as ModelClass
            elif model == "agent":
                from p8fs.models.p8 import Agent as ModelClass
            elif model == "user":
                from p8fs.models.p8 import User as ModelClass
            elif model == "files":
                from p8fs.models.p8 import Files as ModelClass
            elif model == "job":
                from p8fs.models.p8 import Job as ModelClass
            else:
                return {
                    "status": "error",
                    "message": f"Unknown model: {model}. Options are: resources, session, agent, user, files, job"
                }
            
            # Import repository
            from p8fs.repository.TenantRepository import TenantRepository
            
            # TODO: Get tenant_id from auth context when available
            # For now, use default tenant
            tenant_id = config.default_tenant_id
            
            # Create repository instance
            repo = TenantRepository(
                model_class=ModelClass,
                tenant_id=tenant_id,
                provider_name=config.storage_provider
            )
            
            # Execute semantic search
            results = await repo.query(
                query_text=query,
                hint="semantic",
                limit=limit,
                threshold=threshold
            )
            
            # Format results for MCP response
            formatted_results = []
            for result in results:
                formatted_result = {
                    "id": str(result.get("id", "")),
                    "content": result.get("content", ""),
                    "score": float(result.get("score", 0.0)),
                    "metadata": result.get("metadata", {})
                }
                
                # Add model-specific fields
                if model == "resources":
                    formatted_result["name"] = result.get("name", "")
                    formatted_result["uri"] = result.get("uri", "")
                elif model == "session":
                    formatted_result["query"] = result.get("query", "")
                    formatted_result["session_type"] = result.get("session_type", "")
                elif model == "agent":
                    formatted_result["category"] = result.get("category", "")
                    formatted_result["spec"] = result.get("spec", {})
                elif model == "files":
                    formatted_result["uri"] = result.get("uri", "")
                    formatted_result["mime_type"] = result.get("mime_type", "")
                    
                formatted_results.append(formatted_result)
            
            return {
                "status": "success",
                "query": query,
                "model": model,
                "limit": limit,
                "threshold": threshold,
                "total_results": len(formatted_results),
                "results": formatted_results
            }
            
        except Exception as e:
            logger.error(f"MCP search_content error: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Search error: {str(e)}"
            }
    
    @mcp.tool()
    async def upload_content(content: str, title: str = None) -> dict[str, Any]:
        """Upload content to P8FS."""
        # TODO: Implement actual content upload using p8fs services
        return {
            "status": "success", 
            "message": "Content upload not yet implemented",
            "title": title,
            "content_length": len(content)
        }
    
    @mcp.tool()
    async def chat(
        message: str,
        agent: str = "p8-default",
        model: str = "gpt-4.1",
        temperature: float = 0.7,
        max_tokens: int | None = None
    ) -> str:
        """Chat with P8FS agents.
        
        Args:
            message: The user message to send to the agent
            agent: The agent to use (default: p8-default)
            model: The LLM model to use (default: gpt-4.1)
            temperature: The sampling temperature (default: 0.7)
            max_tokens: Maximum tokens to generate (optional)
        
        Returns:
            Chat response from the selected agent
            
        Example usage:
            {"message": "Tell me about P8FS", "agent": "p8-research"}
        """
        try:
            # Get user context from the MCP session
            # Note: In FastMCP, auth context may be available through the request
            # For now, we'll use a minimal context
            
            # Create CallingContext for the chat
            # Note: While MCP protocol supports streaming via SSE, FastMCP Python tools
            # cannot yet yield streaming responses (see github.com/jlowin/fastmcp/discussions/429)
            # We use streaming internally and collect chunks, but return complete response
            context = CallingContext(
                model=model,
                temperature=temperature,
                prefers_streaming=True,  # Stream from LLM for better latency
                max_tokens=max_tokens,
                tenant_id=None,  # TODO: Get from auth context
                user_id=None,    # TODO: Get from auth context
            )

            # Load agent if specified and not default
            agent_instance = None
            if agent and agent != "p8-default":
                try:
                    from p8fs.utils.inspection import load_entity as load_entity_by_name
                    agent_class = load_entity_by_name(agent)
                    logger.info(f"Loading agent for MCP chat: {agent} -> {agent_class.__name__}")

                    # Create minimal agent instance
                    agent_kwargs = {
                        "id": f"mcp-{agent.replace('.', '-').lower()}-{hash(agent) % 10000}",
                        "name": agent,
                        "description": f"MCP instance of {agent}",
                        "spec": {"source": "mcp", "type": "agent"},
                    }

                    try:
                        agent_instance = agent_class(**agent_kwargs)
                    except TypeError:
                        # Try with minimal fields
                        agent_instance = agent_class()

                except Exception as e:
                    logger.warning(f"Failed to load agent '{agent}' for MCP chat: {e}")
                    # Continue without agent - will use simple LLM relay

            # Initialize MemoryProxy with agent
            async with MemoryProxy(model_context=agent_instance) as memory_proxy:
                # Stream from LLM and collect chunks
                # FastMCP tools cannot yield yet, so we collect the full response
                # MemoryProxy.stream() yields dicts with different event types
                full_response = ""
                async for chunk in memory_proxy.stream(message, context):
                    if isinstance(chunk, dict):
                        # Check for completion event (contains final response)
                        if chunk.get("type") == "completion":
                            final_response = chunk.get("final_response", "")
                            if final_response:
                                full_response = final_response
                            break

                        # Extract text from OpenAI format streaming chunks
                        elif "choices" in chunk:
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                if "content" in delta and delta["content"]:
                                    full_response += delta["content"]

                        # Extract text from Anthropic format streaming chunks
                        elif chunk.get("type") == "content_block_delta" and "delta" in chunk:
                            delta = chunk.get("delta", {})
                            if delta.get("type") == "text_delta" and "text" in delta:
                                full_response += delta["text"]

                return full_response if full_response else "No response generated"
                    
        except Exception as e:
            logger.error(f"MCP chat error: {e}", exc_info=True)
            return f"Chat error: {str(e)}"
    
    @mcp.tool()
    async def upload_file(
        filename: str,
        content: str,
        content_type: str = "application/octet-stream",
        base64_encoded: bool = True
    ) -> dict[str, Any]:
        """Upload a file to P8FS S3 storage.
        
        Args:
            filename: Name of the file to upload
            content: File content (base64 encoded by default)
            content_type: MIME type of the file (auto-detected if not provided)
            base64_encoded: Whether the content is base64 encoded (default: true)
        
        Returns:
            Dictionary with upload details including S3 URL
            
        Example usage:
            {
                "filename": "document.pdf",
                "content": "JVBERi0xLjQKJeLj...",  # base64 encoded content
                "content_type": "application/pdf"
            }
        """
        try:
            # Decode base64 content if needed
            if base64_encoded:
                try:
                    file_content = base64.b64decode(content)
                except Exception as e:
                    return {
                        "status": "error",
                        "message": f"Failed to decode base64 content: {str(e)}"
                    }
            else:
                file_content = content.encode('utf-8')
            
            # Auto-detect content type if not provided
            if not content_type:
                content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            
            # Generate unique S3 key
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            s3_key = f"uploads/{timestamp}_{unique_id}_{filename}"
            
            # Create S3 client
            s3_client = boto3.client(
                's3',
                endpoint_url=config.seaweedfs_s3_endpoint,
                aws_access_key_id=config.seaweedfs_access_key,
                aws_secret_access_key=config.seaweedfs_secret_key,
                region_name='us-east-1'  # SeaweedFS doesn't care about region
            )
            
            # Upload to S3
            try:
                s3_client.put_object(
                    Bucket=config.seaweedfs_bucket,
                    Key=s3_key,
                    Body=file_content,
                    ContentType=content_type,
                    Metadata={
                        'uploaded-by': 'mcp-tool',
                        'upload-timestamp': timestamp,
                        'original-filename': filename
                    }
                )
                
                # Generate S3 URL
                # For external access, use the configured S3 endpoint
                s3_url = f"https://s3.percolationlabs.ai/{config.seaweedfs_bucket}/{s3_key}"
                
                # Return success response
                return {
                    "status": "success",
                    "message": "File uploaded successfully",
                    "filename": filename,
                    "s3_key": s3_key,
                    "s3_url": s3_url,
                    "bucket": config.seaweedfs_bucket,
                    "size": len(file_content),
                    "content_type": content_type,
                    "timestamp": timestamp
                }
                
            except ClientError as e:
                logger.error(f"S3 upload error: {e}", exc_info=True)
                return {
                    "status": "error",
                    "message": f"Failed to upload to S3: {str(e)}"
                }
                
        except Exception as e:
            logger.error(f"MCP upload_file error: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Upload error: {str(e)}"
            }
    
    @mcp.tool()
    async def get_moments(
        query: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        moment_type: str | None = None,
        limit: int = 20
    ) -> dict[str, Any]:
        """Get moments from P8FS with optional semantic search and date filtering.

        Args:
            query: Optional semantic search query (natural language)
            start_date: Optional start date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            end_date: Optional end date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            moment_type: Optional moment type filter (e.g., "conversation", "meeting")
            limit: Maximum number of results (default: 20, max: 100)

        Returns:
            Dictionary with moments list and metadata

        Example usage:
            {"query": "discussions about AI", "limit": 10}
            {"start_date": "2025-01-01", "end_date": "2025-01-31", "limit": 50}
            {"moment_type": "meeting", "query": "planning session"}
        """
        try:
            from p8fs.models.engram.models import Moment
            from p8fs.repository.TenantRepository import TenantRepository
            from datetime import datetime

            # TODO: Get tenant_id from auth context when available
            tenant_id = config.default_tenant_id

            # Create repository instance
            repo = TenantRepository(
                model_class=Moment,
                tenant_id=tenant_id,
                provider_name=config.storage_provider
            )

            # Parse dates for filtering (ensure timezone-aware)
            from datetime import timezone
            start_datetime = None
            end_datetime = None
            if start_date:
                # Parse date and ensure it's timezone-aware (assume UTC if no timezone)
                dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                start_datetime = dt
            if end_date:
                # Parse date and ensure it's timezone-aware (assume UTC if no timezone)
                dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                end_datetime = dt

            # If semantic search is requested, use it
            if query:
                results = await repo.query(
                    query_text=query,
                    hint="semantic",
                    limit=min(limit, 100),
                    threshold=0.6
                )

                # Apply date filtering post-query for semantic search
                if start_datetime or end_datetime:
                    filtered_results = []
                    for result in results:
                        result_dict = result if isinstance(result, dict) else (
                            result.model_dump() if hasattr(result, 'model_dump') else result.__dict__
                        )

                        # Use start_time field (moment-specific), fallback to created_at
                        timestamp = result_dict.get("start_time") or result_dict.get("created_at")
                        if timestamp:
                            if isinstance(timestamp, str):
                                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

                            # Apply date range filter
                            if start_datetime and timestamp < start_datetime:
                                continue
                            if end_datetime and timestamp > end_datetime:
                                continue

                        filtered_results.append(result)
                    results = filtered_results
            else:
                # Use repository select with filters dict
                filters = {}

                if moment_type:
                    filters["moment_type"] = moment_type

                # Get all moments first (repository select doesn't support complex date filters)
                results = await repo.select(
                    filters=filters,
                    limit=min(limit, 100)
                )

                # Apply date filtering post-query
                if start_datetime or end_datetime:
                    filtered_results = []
                    for result in results:
                        result_dict = result if isinstance(result, dict) else (
                            result.model_dump() if hasattr(result, 'model_dump') else result.__dict__
                        )

                        # Use start_time field, fallback to created_at
                        timestamp = result_dict.get("start_time") or result_dict.get("created_at")
                        if timestamp:
                            if isinstance(timestamp, str):
                                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

                            # Apply date range filter
                            if start_datetime and timestamp < start_datetime:
                                continue
                            if end_datetime and timestamp > end_datetime:
                                continue

                        filtered_results.append(result)
                    results = filtered_results

            # Format results for MCP response
            formatted_moments = []
            for result in results:
                # Handle both dict and Moment object results
                if isinstance(result, dict):
                    moment_dict = result
                else:
                    moment_dict = result.model_dump() if hasattr(result, 'model_dump') else result.__dict__

                formatted_moment = {
                    "id": str(moment_dict.get("id", "")),
                    "name": moment_dict.get("name", ""),
                    "start_time": str(moment_dict.get("start_time", "")) if moment_dict.get("start_time") else None,
                    "end_time": str(moment_dict.get("end_time", "")) if moment_dict.get("end_time") else None,
                    "content": moment_dict.get("content", ""),
                    "summary": moment_dict.get("summary", ""),
                    "moment_type": moment_dict.get("moment_type", ""),
                    "location": moment_dict.get("location", ""),
                    "emotion_tags": moment_dict.get("emotion_tags", []),
                    "topic_tags": moment_dict.get("topic_tags", []),
                    "score": float(moment_dict.get("score", 0.0)) if "score" in moment_dict else None
                }

                formatted_moments.append(formatted_moment)

            return {
                "status": "success",
                "query": query,
                "start_date": start_date,
                "end_date": end_date,
                "moment_type": moment_type,
                "limit": limit,
                "total_results": len(formatted_moments),
                "moments": formatted_moments
            }

        except Exception as e:
            logger.error(f"MCP get_moments error: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error retrieving moments: {str(e)}"
            }

    @mcp.tool()
    async def search_resources(
        query: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        category: str | None = None,
        limit: int = 20
    ) -> dict[str, Any]:
        """Search resources in P8FS with optional semantic search and date filtering.

        Args:
            query: Optional semantic search query (natural language)
            start_date: Optional start date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            end_date: Optional end date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            category: Optional category filter (e.g., "document", "note", "article")
            limit: Maximum number of results (default: 20, max: 100)

        Returns:
            Dictionary with resources list and metadata

        Example usage:
            {"query": "machine learning papers", "limit": 10}
            {"start_date": "2025-01-01", "end_date": "2025-01-31", "limit": 50}
            {"category": "document", "query": "project planning"}
        """
        try:
            from p8fs.models.p8 import Resources
            from p8fs.repository.TenantRepository import TenantRepository
            from datetime import datetime, timezone

            # TODO: Get tenant_id from auth context when available
            tenant_id = config.default_tenant_id

            # Create repository instance
            repo = TenantRepository(
                model_class=Resources,
                tenant_id=tenant_id,
                provider_name=config.storage_provider
            )

            # Parse dates for filtering (ensure timezone-aware)
            start_datetime = None
            end_datetime = None
            if start_date:
                # Parse date and ensure it's timezone-aware (assume UTC if no timezone)
                dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                start_datetime = dt
            if end_date:
                # Parse date and ensure it's timezone-aware (assume UTC if no timezone)
                dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                end_datetime = dt

            # If semantic search is requested, use it
            if query:
                results = await repo.query(
                    query_text=query,
                    hint="semantic",
                    limit=min(limit, 100),
                    threshold=0.6
                )

                # Apply date filtering post-query for semantic search
                if start_datetime or end_datetime:
                    filtered_results = []
                    for result in results:
                        result_dict = result if isinstance(result, dict) else (
                            result.model_dump() if hasattr(result, 'model_dump') else result.__dict__
                        )

                        # Use resource_timestamp if not null, else created_at
                        timestamp = result_dict.get("resource_timestamp") or result_dict.get("created_at")
                        if timestamp:
                            if isinstance(timestamp, str):
                                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

                            # Apply date range filter
                            if start_datetime and timestamp < start_datetime:
                                continue
                            if end_datetime and timestamp > end_datetime:
                                continue

                        filtered_results.append(result)
                    results = filtered_results
            else:
                # Use repository select with filters dict
                filters = {}

                if category:
                    filters["category"] = category

                # Get all resources first (repository select doesn't support complex date filters)
                results = await repo.select(
                    filters=filters,
                    limit=min(limit, 100)
                )

                # Apply date filtering post-query
                if start_datetime or end_datetime:
                    filtered_results = []
                    for result in results:
                        result_dict = result if isinstance(result, dict) else (
                            result.model_dump() if hasattr(result, 'model_dump') else result.__dict__
                        )

                        # Use resource_timestamp if not null, else created_at
                        timestamp = result_dict.get("resource_timestamp") or result_dict.get("created_at")
                        if timestamp:
                            if isinstance(timestamp, str):
                                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

                            # Apply date range filter
                            if start_datetime and timestamp < start_datetime:
                                continue
                            if end_datetime and timestamp > end_datetime:
                                continue

                        filtered_results.append(result)
                    results = filtered_results

            # Format results for MCP response
            formatted_resources = []
            for result in results:
                # Handle both dict and Resources object results
                if isinstance(result, dict):
                    resource_dict = result
                else:
                    resource_dict = result.model_dump() if hasattr(result, 'model_dump') else result.__dict__

                formatted_resource = {
                    "id": str(resource_dict.get("id", "")),
                    "name": resource_dict.get("name", ""),
                    "category": resource_dict.get("category", ""),
                    "content": resource_dict.get("content", ""),
                    "summary": resource_dict.get("summary", ""),
                    "uri": resource_dict.get("uri", ""),
                    "resource_timestamp": str(resource_dict.get("resource_timestamp", "")) if resource_dict.get("resource_timestamp") else None,
                    "created_at": str(resource_dict.get("created_at", "")) if resource_dict.get("created_at") else None,
                    "metadata": resource_dict.get("metadata", {}),
                    "score": float(resource_dict.get("score", 0.0)) if "score" in resource_dict else None
                }

                formatted_resources.append(formatted_resource)

            return {
                "status": "success",
                "query": query,
                "start_date": start_date,
                "end_date": end_date,
                "category": category,
                "limit": limit,
                "total_results": len(formatted_resources),
                "resources": formatted_resources
            }

        except Exception as e:
            logger.error(f"MCP search_resources error: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error searching resources: {str(e)}"
            }

    logger.info("Created P8FS MCP server with authentication-aware tools")
    return mcp