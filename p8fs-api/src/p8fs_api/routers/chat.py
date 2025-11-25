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
    # Default to p8-system if no agent specified
    agent_key = x_p8_agent or "p8-system"

    # TODO: Remove this mapping once p8-resources agent is implemented
    # For now, map p8-resources requests to p8-system
    if agent_key == "p8-resources":
        agent_key = "p8-system"

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
        X-Session-ID: Optional session ID to reload conversation history

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
            # Note: load_entity_by_name returns an INSTANCE, not a class
            agent_instance = load_entity_by_name(agent_key)
            logger.info(f"Loading agent: {agent_key} -> {type(agent_instance).__name__}")

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

    # Create context without messages first
    context = CallingContext.from_headers(headers, **context_kwargs)

    # Initialize MemoryProxy with loaded agent (if any)
    try:
        async with MemoryProxy(model_context=agent_instance) as memory_proxy:
            # Check for session reload
            session_id = http_request.headers.get("x-session-id")
            historical_messages = []

            if session_id:
                logger.info(f"Attempting to reload session: {session_id}")
                from p8fs.models.user_context import UserContext

                # Reload session thread and conversation history
                reloaded_session, historical_messages = await memory_proxy.reload_session(
                    thread_id=session_id,  # session_id from header is actually thread_id
                    tenant_id=tenant_id,
                    decompress_messages=False  # Keep compressed for context efficiency
                )

                if reloaded_session:
                    logger.info(f"Reloaded session {session_id} with {len(historical_messages)} historical messages")

                    # Load user context from p8fs-user-info Resource
                    user_context_dict = await UserContext.load_or_create(tenant_id)
                    user_context_msg = UserContext.to_context_message(user_context_dict)

                    # Combine: user context + historical messages + new request messages
                    historical_messages = [user_context_msg] + historical_messages
                else:
                    logger.warning(f"Session {session_id} not found, starting new session")

            # Handle audio transcription if needed
            has_audio = x_chat_is_audio and x_chat_is_audio.lower() == "true"
            try:
                # Messages are already dicts in OpenAIRequest
                messages_dict = request.messages
                messages = await memory_proxy.process_audio_messages(
                    messages_dict, has_audio
                )

                # Prepend historical messages if session was reloaded
                if historical_messages:
                    messages = historical_messages + messages
                    logger.debug(f"Combined {len(historical_messages)} historical + {len(request.messages)} new messages")

                # Add context hint message with date and user info lookup
                from datetime import datetime
                today = datetime.now().strftime("%Y-%m-%d")
                context_hint = {
                    "role": "user",
                    "content": f"Today's date: {today}. You can silently REM LOOKUP p8fs-user-info if you need user preferences or context, but only when relevant. Do not mention this lookup to the user."
                }
                messages = [context_hint] + messages

                # Store message history for MemoryProxy to incorporate AFTER system prompt
                # MemoryProxy will build system prompt from agent model, then merge these messages
                context.messages = messages

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


@router.get("/chat/messages")
async def search_chat_messages(
    query: str | None = None,
    moment_id: str | None = None,
    include_moment_messages: bool = True,
    limit: int = 10,
    current_user: TokenPayload | None = Depends(get_optional_token),
):
    """
    Search chat messages with optional filtering.

    This endpoint allows searching through chat message history, with options to
    filter by moment ID and exclude/include moment-associated messages.

    Query Parameters:
        query: Optional search query text for semantic search
        moment_id: Optional moment ID to filter messages
        include_moment_messages: Include messages with moment_id (default: True)
                                 When False, filters out messages that have a moment_id set
        limit: Maximum number of results to return (default: 10)

    Returns:
        List of matching messages with relevance scores

    Example:
        GET /v1/chat/messages?query=meeting+notes&moment_id=moment-123&limit=5
        GET /v1/chat/messages?include_moment_messages=false&limit=10
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

        # Build filters based on parameters
        filters = {}

        # Filter by specific moment_id if provided
        if moment_id:
            filters["moment_id"] = moment_id

        # Filter based on include_moment_messages
        if not include_moment_messages:
            # When False, only return messages that DO NOT have a moment_id set
            # This requires filtering for NULL moment_id
            filters["moment_id"] = None

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
