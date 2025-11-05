"""
Chat Completions API Routes

OpenAI-compatible chat completions endpoint with multiple interface modes:

1. **Standard OpenAI Endpoint**: `/v1/chat/completions`
   - Simple model-free memory proxy relay to LLM APIs
   - Can accept X-P8-Agent header to route to specific agent controller

2. **Agent-Specific Endpoint**: `/v1/agent/<name>/chat/completions`
   - Routes to agent controller with memory proxy for that specific agent
   - Supports tool calls, function calling, and agent-specific behaviors

3. **Simulation Mode**: `/v1/agent/p8-sim/chat/completions`
   - Special simulation mode that generates test responses instead of calling real LLMs
   - Useful for testing, demos, and development
   - Returns rich markdown responses with code examples, tables, and formatting

All endpoints support both streaming and non-streaming responses with proper SSE formatting.
Default model: gpt-4.1-mini with streaming enabled for optimal testing experience.

Authentication:
- All chat endpoints require a valid Bearer token
- Returns 401 if no token provided or token is invalid/expired
"""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

# New module structure imports
from ..middleware import get_optional_token, get_moment_id, TokenPayload
from p8fs.services.llm.models import CallingContext
from p8fs.models.llm import OpenAIRequest as ChatCompletionRequest
from p8fs.utils.inspection import load_entity as load_entity_by_name
from p8fs.services.llm.memory_proxy import MemoryProxy
from ..utils.simulation import (
    build_simulation_response,
    stream_simulation_response,
)
from p8fs.services.llm.utils import build_openai_response, create_sse_line

from p8fs_cluster.logging import get_logger

from ..utils.instrumentation import track_model_usage

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat/completions")
@track_model_usage(tenant_id_attr="current_user.tenant_id", model_attr="request.model")
async def chat_completions(
    request: ChatCompletionRequest,
    http_request: Request,
    current_user: TokenPayload | None = Depends(get_optional_token),
    x_p8_agent: str | None = Header(None, alias="X-P8-Agent"),
    x_chat_is_audio: str | None = Header(None, alias="X-Chat-Is-Audio"),
):
    """
    OpenAI-compatible chat completions endpoint.

    Simple model-free memory proxy relay to LLM APIs. If X-P8-Agent header
    is provided, routes to the specified agent controller for that agent.

    Headers:
        X-P8-Agent: Optional agent name to route to specific agent controller
        X-Chat-Is-Audio: If "true", first user message contains base64 audio to transcribe

    Examples:
        # Standard LLM relay
        POST /v1/chat/completions

        # Route to specific agent via header
        POST /v1/chat/completions
        X-P8-Agent: p8-research

        # With audio input
        POST /v1/chat/completions
        X-Chat-Is-Audio: true
    """
    # Check for X-P8-Agent header to route to specific agent
    agent_key = x_p8_agent or ""

    # Delegate to agent endpoint
    return await agent_chat_completions(
        agent_key=agent_key,
        request=request,
        http_request=http_request,
        current_user=current_user,
        x_chat_is_audio=x_chat_is_audio,
    )


@router.post("/agent/{agent_key}/chat/completions")
async def agent_chat_completions(
    agent_key: str,
    request: ChatCompletionRequest,
    http_request: Request,
    current_user: TokenPayload | None = Depends(get_optional_token),
    x_chat_is_audio: str | None = Header(None, alias="X-Chat-Is-Audio"),
):
    """
    Agent-specific chat completions endpoint.

    Routes to agent controller with memory proxy for that specific agent.
    Supports tool calls, function calling, and agent-specific behaviors.

    Special case: agent_key="p8-sim" triggers simulation mode that generates
    test responses instead of calling real LLMs.

    Path Parameters:
        agent_key: Agent name (e.g., "p8-research", "p8-analysis", "p8-sim")

    Headers:
        X-Chat-Is-Audio: If "true", first user message contains base64 audio to transcribe

    Examples:
        # Research agent with function calling
        POST /v1/agent/p8-research/chat/completions

        # Simulation mode for testing
        POST /v1/agent/p8-sim/chat/completions
    """
    # Extract user question from last user message
    question = ""
    for message in reversed(request.messages):
        if message.get("role") == "user":
            question = message.get("content", "") or ""
            break

    if not question:
        raise HTTPException(400, "No user message found")

    # Special simulation mode for p8-sim agent
    if agent_key == "p8-sim":
        if request.stream:

            async def generate_sim():
                async for chunk in stream_simulation_response(question, request.model):
                    yield create_sse_line(chunk)
                yield "data: [DONE]\n\n"

            return StreamingResponse(generate_sim(), media_type="text/event-stream")
        else:
            # Non-streaming simulation response
            return await build_simulation_response(question, request.model)

    # Standard agent processing with MemoryProxy
    # Create headers dict and add agent name if provided
    headers = dict(http_request.headers)
    if agent_key:
        headers["x-agent-name"] = agent_key

    # Add moment_id to headers if present in context
    moment_id = get_moment_id()
    if moment_id:
        headers["x-moment-id"] = moment_id

    # Load agent if specified
    agent_instance = None
    if agent_key:
        try:
            # Load entity by name (supports p8-* naming convention)
            agent_class = load_entity_by_name(agent_key)
            logger.info(f"Loading agent: {agent_key} -> {agent_class.__name__}")

            # Create agent instance with default values
            # Most P8 models have these common fields
            agent_kwargs = {
                "id": f"api-{agent_key.replace('.', '-').lower()}-{hash(agent_key) % 10000}",
                "name": agent_key,
                "description": f"API instance of {agent_key}",
                "spec": {"source": "api", "type": "agent"},
            }

            # Try to create the agent instance
            try:
                agent_instance = agent_class(**agent_kwargs)
            except TypeError as e:
                # If the model doesn't accept these fields, try with minimal fields
                logger.debug(f"Failed with default fields, trying minimal: {e}")
                agent_instance = agent_class()

        except Exception as e:
            logger.warning(f"Failed to load agent '{agent_key}': {e}")
            # Continue without agent - will use simple LLM relay mode

    # Check authentication - require user for chat endpoints
    if not current_user:
        # Check if any auth token was supplied
        auth_header = http_request.headers.get("Authorization", "")
        if auth_header:
            logger.warning(
                f"Invalid or expired token provided for agent '{agent_key}' chat request"
            )
            raise HTTPException(
                status_code=401, detail="Invalid or expired authentication token"
            )
        else:
            logger.warning(
                f"No authentication token provided for agent '{agent_key}' chat request"
            )
            raise HTTPException(
                status_code=401,
                detail="Authentication required. Please provide a valid Bearer token",
            )

    # Log successful auth
    logger.debug(
        f"Authenticated chat request for agent '{agent_key}' from user: {getattr(current_user, 'sub', 'unknown')}"
    )

    # Create calling context from headers
    # Extract user info from current_user (TokenPayload object)
    tenant_id = None
    user_id = None

    # current_user is a TokenPayload object with 'tenant' not 'tenant_id'
    if hasattr(current_user, "tenant"):
        tenant_id = current_user.tenant
    elif isinstance(current_user, dict):
        tenant_id = current_user.get("tenant")

    if hasattr(current_user, "sub"):
        user_id = current_user.sub
    elif isinstance(current_user, dict):
        user_id = current_user.get("sub")

    context_kwargs = {
        "model": request.model,
        "temperature": request.temperature,
        "prefers_streaming": request.stream,
        "tenant_id": tenant_id,
        "user_id": user_id,
    }

    # Only add max_tokens if it's not None
    if request.max_tokens is not None:
        context_kwargs["max_tokens"] = request.max_tokens

    context = CallingContext.from_headers(headers, **context_kwargs)

    # Initialize MemoryProxy with loaded agent (if any)
    try:
        async with MemoryProxy(model_context=agent_instance) as memory_proxy:
            # Handle audio transcription if needed
            has_audio = x_chat_is_audio and x_chat_is_audio.lower() == "true"
            try:
                # Messages are already dicts in OpenAIRequest
                messages_dict = request.messages
                messages = await memory_proxy.process_audio_messages(
                    messages_dict, has_audio
                )

                # Update question if audio was transcribed
                if has_audio:
                    for message in reversed(messages):
                        if message.get("role") == "user":
                            question = message.get("content", "")
                            break

            except Exception as e:
                logger.error(f"Audio processing failed: {e}")
                raise HTTPException(400, f"Audio processing failed: {str(e)}")

            # Handle streaming
            if context.is_streaming:

                async def generate():
                    try:
                        # Collect chunks for building final response if needed
                        chunks = []

                        async for chunk in memory_proxy.stream(question, context):
                            # For standard streaming chunks, forward them
                            if isinstance(chunk, dict) and "choices" in chunk:
                                chunks.append(chunk)
                                yield create_sse_line(json.dumps(chunk))
                            # For other event types, forward as-is
                            else:
                                yield create_sse_line(chunk)

                        # Note: [DONE] is now only sent by UnifiedStreamAdapter when it sees finish_reason: "stop"
                        # This ensures proper handling of agentic loops with tool calls
                    except Exception as e:
                        logger.error(
                            f"Streaming error for agent '{agent_key}': {e}",
                            exc_info=True,
                        )
                        error_chunk = {
                            "error": {
                                "message": f"Streaming failed: {str(e)}",
                                "type": "streaming_error",
                                "code": 500,
                            }
                        }
                        yield create_sse_line(json.dumps(error_chunk))
                        yield "data: [DONE]\n\n"

                return StreamingResponse(generate(), media_type="text/event-stream")
            else:
                # Non-streaming - get response and format properly
                response_content = await memory_proxy.run(question, context)

                # Build proper OpenAI response format
                return build_openai_response(
                    content=response_content,
                    function_calls=[],
                    model=context.model,
                )
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            f"Chat completion failed for agent '{agent_key}': {e}", exc_info=True
        )
        # Include more details about the error
        error_info = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "agent_key": agent_key,
            "model": request.model,
            "streaming": request.stream
        }
        raise HTTPException(
            500, 
            detail={
                "message": f"Failed to initialize chat service: {str(e)}",
                "error_info": error_info
            }
        )


@router.get("/chats/search")
async def search_chats(
    query: str,
    moment_id: str | None = None,
    limit: int = 10,
    current_user: TokenPayload | None = Depends(get_optional_token),
):
    """
    Search chat sessions semantically with optional moment filtering.

    This endpoint allows searching through chat session history, optionally
    filtering by a specific moment ID to find conversations related to
    that moment.

    Query Parameters:
        query: Search query text for semantic search
        moment_id: Optional moment ID to filter sessions
        limit: Maximum number of results to return (default: 10)

    Returns:
        List of matching sessions with relevance scores

    Example:
        GET /v1/chats/search?query=meeting+notes&moment_id=moment-123&limit=5
    """
    if not current_user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required for chat search"
        )

    tenant_id = current_user.tenant

    # Build search parameters
    from p8fs.repository import TenantRepository
    from p8fs.models.p8 import Session

    try:
        # Initialize repository for sessions
        repo = TenantRepository(Session, tenant_id=tenant_id)

        # Build simple query filtering by moment_id
        # For now, skip semantic search and just filter by moment_id
        if moment_id:
            filters = {"moment_id": moment_id}
        else:
            filters = {}

        # Use repository's select method for simpler querying
        results = await repo.select(filters=filters, limit=limit, offset=0)

        # Format results - results is a list of Session objects
        sessions = []
        if results:
            for session in results:
                # Session is a Pydantic model, convert to dict
                session_dict = session.model_dump() if hasattr(session, 'model_dump') else session
                sessions.append({
                    "id": session_dict.get("id"),
                    "name": session_dict.get("name"),
                    "query": session_dict.get("query"),
                    "moment_id": session_dict.get("moment_id"),
                    "created_at": session_dict.get("created_at"),
                    "userid": session_dict.get("userid"),
                })

        return {
            "query": query,
            "moment_id": moment_id,
            "limit": limit,
            "results": sessions,
            "count": len(sessions),
        }

    except Exception as e:
        logger.error(f"Chat search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


# Export both router variants for compatibility
protected_router = router
public_router = router
