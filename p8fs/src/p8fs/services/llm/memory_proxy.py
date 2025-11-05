"""
Memory-enhanced proxy for LLM API calls with session management.

This module extends the base proxy to add memory and session management capabilities,
enabling context-aware conversations and function call handling.

In percolate we had a ModelRunner but we deprecated this because all it did was
- interface with the data repository (now data fusion over p8fs)
- register metadata from Models e.g. prompt and functions (which are now going to be built in this memory proxy)
- save user sessions (which are now going to be in this memory proxy)
- run an agentic loop (most important) which is now going to be in this memory proxy

the memory proxy builds intelligent messages stacks and
uses the function buffering streamer to interact with the data store and send results to users


Usage:
```
#this example has no agent context and simply relays questions to the LLM
proxy = MemoryProxy()
#this example uses the tools and prompt from the model
proxy = MemoryProxy(MyWeatherAgent)

#we can simply ask the question and use defaults such as the streaming option and our default model gpt-4.1-mini
proxy.run(question)
#or we can create a context object with tenant id, conversation ids etc
proxy.run(question, CallingContext.from_headers(content_headers_dict))
#instead of run we can also use stream() with the same args that iterates over SSE events that can be printed

```

When we run from the cli we can pass pseudo context headers such as model choice or streaming options
and when we run from the API we can header HTTP headers or request params into the context
Context identifies users, threads, channels such as slack and other useful context

## Percolate Architecture Compliance:

  - ✅ Every AbstractModel is an Agent: Any model with proper model_config
  works as an agent
  - ✅ Full Name Resolution: load_entity('p8.Agent') resolves to models with
   configured full names
  - ✅ Abstract → Executable: Metadata models become executable through
  MemoryProxy
  - ✅ System Prompts: Automatically built from agent descriptions via
  MessageStack.build_message_stack()
  - ✅ Function Registration: Auto-discovers and registers callable methods
  as functions
  - ✅ Execution: Models become executable agents when passed to MemoryProxy


## JSON Response Mode Support

To use JSON mode with MemoryProxy, pass response_format in context.metadata:

```python
context = CallingContext(
    model="claude-sonnet-4-5",
    tenant_id="test",
    metadata={"response_format": {"type": "json_object"}}
)
result = await proxy.run(question, context)
```

This works with both streaming and non-streaming modes.
"""

import json
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from p8fs.models.base import AbstractModel
from p8fs.models.llm import MessageStack
from p8fs.services.llm.models import CallingContext, BatchCallingContext
from p8fs.utils.functions import From_Callable
from p8fs_cluster.logging import get_logger
from p8fs.repository import TenantRepository

# todo remove relative imports
from .audit_mixin import AuditSessionMixin
from .base_proxy import BaseProxy
from .batch import BatchResponse
from .function_handler import FunctionHandler
from .language_model import LanguageModel
from .models import JobStatusResponse
from .utils import (
    FunctionCall,
    FunctionCallCollector,
    build_error_chunk,
    build_function_messages,
    convert_tool_calls_to_native_message,
)

logger = get_logger(__name__)

# Default tenant ID from centralized config
from p8fs_cluster.config.settings import config
DEFAULT_TENANT_ID = config.default_tenant_id


class MemoryProxy(BaseProxy, AuditSessionMixin):
    """
    Memory-enhanced proxy for LLM API calls.

    This class extends BaseProxy to add:
    - Session management for maintaining conversation context
    - Memory storage and retrieval
    - Function call handling with buffering
    - Context-aware message preparation


    **Example usage**

    ```python
    from p8fs.models.p8 import Agent
    from p8fs.services.llm.memory_proxy import MemoryProxy

    a=MemoryProxy(Agent)
    await a.run("what can you do")
    ```

    """

    def __init__(self, model_context: AbstractModel = None, client=None):
        """
        Initialize the memory proxy.

        Args:
            model_context: Abstract model that defines functions and system prompt.
                          If None, the proxy acts as a simple LLM relay without agent context.
            client: Optional P8FSClient instance. If None, will be created internally
                    using tenant context from CallingContext when needed.
        """
        # Initialize base classes using cooperative inheritance
        super().__init__()

        # Apply Abstracted to ensure model is a class (not instance) with AbstractModel capabilities
        self._model_context = (
            AbstractModel.Abstracted(model_context) if model_context else None
        )
        self._message_buffer: list[dict[str, Any]] = []
        self._function_handler: FunctionHandler | None = None
        self._client = client
        self._last_context: CallingContext | None = None
        self._tenant_id: str | None = (
            None  # Will be set from context during agent loops
        )

        self._function_handler = FunctionHandler()

        self._register_builtin_functions()

        if self._model_context:
            self._register_model_functions()

        logger.info(
            f"Initialized MemoryProxy with model context: {self._model_context.get_model_full_name() if self._model_context else 'None'}"
        )

    @property
    def model_context(self) -> Any:
        """Get the current model context."""
        return self._model_context

    @property
    def client(self) -> Any:
        """Get the current client instance."""
        return self._client

    @property
    def registered_functions(self) -> dict[str, Any]:
        """Get all registered functions (callable objects)."""
        if hasattr(self, "_registered_functions_override"):
            return self._registered_functions_override
        if self._function_handler:
            return self._function_handler._functions.copy()
        return {}

    @registered_functions.setter
    def registered_functions(self, value: dict[str, Any]):
        """Set registered functions (for testing)."""
        self._registered_functions_override = value
        # Also register functions with the handler for execution
        if self._function_handler:
            for name, func in value.items():
                self._function_handler.register(name, func)

    def _get_available_tools(self) -> list[dict[str, Any]]:
        """Get all available tools/functions as OpenAI-style tool schemas."""
        if self._function_handler:
            return self._function_handler.get_schemas()
        return []

    async def _execute_function(self, function_name: str, args: dict[str, Any]) -> Any:
        """Execute a registered function by name with given arguments."""
        if self._function_handler:
            try:
                return await self._function_handler.execute(function_name, args)
            except Exception as e:
                # Return error in expected format for tests
                return {
                    "error": str(e),
                    "function": function_name,
                    "args": args
                }
        raise ValueError(f"Function '{function_name}' not found")

    def register_function(self, name: str = None, schema: dict[str, Any] = None):
        """
        Decorator to register a function for LLM calls.

        Args:
            name: Optional function name. If None, uses the function's __name__
            schema: Optional OpenAI function schema. If None, auto-generates from signature

        Returns:
            The decorator function

        Example:
            @proxy.register_function("get_entities")
            async def extract_entities(text: str) -> dict:
                return {"entities": ["example"]}
        """

        def decorator(func):
            function_name = name or func.__name__

            # Add schema as function attribute for testing
            if schema:
                func._llm_schema = schema

            self._function_handler.register(function_name, func, schema)
            return func

        return decorator

    def _get_tenant_bound_client(self) -> Any:
        """Get existing client or create one using context.
        Importantly tenant contexts are set in run methods and they are needed for tenant isolation
        """

        # Return existing client if available
        if self._client is not None:
            return self._client

        # Use the tenant from context, or fall back to default
        tenant_id = self._get_tenant_id()
        self._client = TenantRepository(self._model_context, tenant_id=tenant_id)
        return self._client

    def _get_tenant_id(self) -> str:
        """Get tenant ID from context with fallback to default."""
        if self._last_context and self._last_context.tenant_id:
            return self._last_context.tenant_id
        elif self._tenant_id:
            return self._tenant_id
        return DEFAULT_TENANT_ID

    def _register_builtin_functions(self):
        """Register built-in MemoryProxy functions for DataFusion integration."""
        try:
            self._function_handler.add_function(self.get_entities)
            self._function_handler.add_function(self.search_resources)
            self._function_handler.add_function(self.get_recent_tenant_uploads)
        except Exception as e:
            logger.warning(f"Failed to register built-in functions: {e}")

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

    async def run(
        self,
        question: str,
        context: CallingContext | None = None,
        max_iterations: int = 10,
    ) -> str:
        """
        Run the agentic loop with the given question and context.

        This method uses the streaming implementation internally and collects
        the final response. This ensures consistent behavior between streaming
        and non-streaming modes, including proper native dialect handling.

        Args:
            question: The user's question
            context: Calling context with model settings, tenant info, etc.
                    If None, uses default settings.
            max_iterations: Maximum number of agentic loop iterations

        Returns:
            The agent's final response as a string
        """
        final_content = ""
        saw_completion = False

        # Use the streaming implementation and collect all content
        async for chunk in self.stream(question, context, max_iterations):
            if isinstance(chunk, dict):
                # Check for completion event (contains final response)
                if chunk.get("type") == "completion":
                    final_response = chunk.get("final_response", "")
                    if final_response:
                        final_content = final_response
                    saw_completion = True
                    # Don't return early - let the generator complete so audit happens
                    continue

                # Skip processing after completion to allow generator cleanup
                if saw_completion:
                    continue

                # Collect content from streaming chunks (both OpenAI and Anthropic formats)
                elif "choices" in chunk:
                    # OpenAI format
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            final_content += delta["content"]

                elif chunk.get("type") == "content_block_delta" and "delta" in chunk:
                    # Anthropic format
                    delta = chunk.get("delta", {})
                    if delta.get("type") == "text_delta" and "text" in delta:
                        final_content += delta["text"]

                elif "candidates" in chunk:
                    # Google format
                    candidates = chunk.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        content = candidates[0]["content"]
                        if "parts" in content:
                            for part in content["parts"]:
                                if "text" in part:
                                    final_content += part["text"]

                # Handle errors
                elif chunk.get("type") == "error":
                    return f"Error: {chunk.get('error', 'Unknown error')}"

        # Return collected content or default message
        # Note: Auditing is handled by the streaming method that run() calls internally
        return (
            final_content if final_content else "I'm not sure how to respond to that."
        )

    def _setup_streaming_context(self, context: CallingContext) -> None:
        """Initialize streaming context and observability."""
        # Set observability context
        from p8fs.observability import set_tenant_id, set_user_id

        if context.tenant_id:
            set_tenant_id(context.tenant_id)
        if context.user_id:
            set_user_id(context.user_id)

        # Store context for built-in functions
        self._last_context = context

        # Update tenant_id from context
        if context.tenant_id:
            self._tenant_id = context.tenant_id

        # Ensure we have a client for session auditing
        if not self._client:
            self._client = self._get_tenant_bound_client()

    def _process_streaming_chunk(
        self,
        chunk: dict[str, Any],
        tool_call_buffer: dict,
        iteration_content: str,
        final_response_content: str,
    ) -> tuple[str, str, list, bool]:
        """
        Process a streaming chunk for content and tool calls.

        Returns:
            tuple: (updated_iteration_content, updated_final_content, complete_tool_calls, saw_completion)
        """
        complete_tool_calls = []
        saw_tool_call_complete = False

        # OpenAI format
        if isinstance(chunk, dict) and "choices" in chunk:
            choices = chunk.get("choices", [])
            if choices:
                choice = choices[0]
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")

                # Collect content
                if "content" in delta and delta["content"]:
                    content = delta["content"]
                    iteration_content += content
                    final_response_content += content

                # Buffer tool calls by index for complete argument assembly
                if "tool_calls" in delta:
                    self._buffer_tool_calls(delta["tool_calls"], tool_call_buffer)

                # Check for tool call completion
                if finish_reason == "tool_calls" and not saw_tool_call_complete:
                    # Tool calls are now complete, convert buffer to list
                    complete_tool_calls = list(tool_call_buffer.values())
                    saw_tool_call_complete = True

        # Anthropic format
        elif isinstance(chunk, dict) and chunk.get("type"):
            chunk_type = chunk.get("type")

            # Handle text content deltas
            if chunk_type == "content_block_delta":
                delta = chunk.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    iteration_content += text
                    final_response_content += text

            # Handle tool use blocks
            elif chunk_type == "content_block_start":
                content_block = chunk.get("content_block", {})
                if content_block.get("type") == "tool_use":
                    # Store tool call in buffer
                    # Anthropic provides input as dict, convert to JSON string for compatibility
                    import json
                    tool_id = content_block.get("id")
                    tool_input = content_block.get("input", {})
                    tool_call_buffer[tool_id] = {
                        "id": tool_id,
                        "type": "function",
                        "function": {
                            "name": content_block.get("name"),
                            "arguments": json.dumps(tool_input) if isinstance(tool_input, dict) else tool_input
                        }
                    }

            # Handle input_json deltas (streaming tool arguments)
            elif chunk_type == "content_block_delta" and chunk.get("delta", {}).get("type") == "input_json_delta":
                # Anthropic streams tool input incrementally
                # For now we get it complete in content_block_start, so skip
                pass

            # Check for completion signals
            elif chunk_type == "message_delta":
                delta = chunk.get("delta", {})
                stop_reason = delta.get("stop_reason")
                if stop_reason == "tool_use":
                    # Tool calls complete
                    complete_tool_calls = list(tool_call_buffer.values())
                    saw_tool_call_complete = True

        return (
            iteration_content,
            final_response_content,
            complete_tool_calls,
            saw_tool_call_complete,
        )

    def _buffer_tool_calls(self, tool_calls: list, tool_call_buffer: dict) -> None:
        """Buffer tool calls by index for complete argument assembly."""
        for tool_call in tool_calls:
            index = tool_call.get("index", 0)

            # Initialize or update tool call buffer
            if index not in tool_call_buffer:
                if "id" in tool_call:
                    # New tool call initialization
                    tool_call_buffer[index] = {
                        "id": tool_call["id"],
                        "type": tool_call.get("type", "function"),
                        "function": {
                            "name": tool_call.get("function", {}).get("name", ""),
                            "arguments": "",
                        },
                    }

            # Update arguments if present
            if "function" in tool_call and "arguments" in tool_call["function"]:
                args_delta = tool_call["function"]["arguments"]
                if index in tool_call_buffer:
                    tool_call_buffer[index]["function"]["arguments"] += args_delta

    async def _execute_function_calls(
        self, complete_tool_calls: list, messages: list, model_scheme: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute function calls and yield results."""
        import json
        from .utils import FunctionCall

        for tool_call in complete_tool_calls:
            func_name = tool_call.get("function", {}).get("name")
            arguments_str = tool_call.get("function", {}).get("arguments", "{}")

            if func_name:
                try:
                    # Yield function execution start
                    yield {
                        "type": "function_call_start",
                        "function_name": func_name,
                        "arguments": arguments_str,
                    }

                    # Parse arguments and execute
                    arguments = json.loads(arguments_str) if arguments_str else {}
                    result = await self._function_handler.execute(func_name, arguments)

                    # Add function result to messages in native dialect
                    func_call = FunctionCall.from_openai_tool_call(
                        tool_call, model_scheme
                    )
                    tool_response_message = func_call.create_tool_response_message(
                        result
                    )
                    messages.append(tool_response_message)

                    # Yield function execution result
                    yield {
                        "type": "function_call_complete",
                        "function_name": func_name,
                        "result": result,
                    }

                    logger.debug(
                        f"Function {func_name} executed successfully in streaming mode"
                    )

                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    # Add error response to messages in native dialect
                    func_call = FunctionCall.from_openai_tool_call(
                        tool_call, model_scheme
                    )
                    error_response_message = func_call.create_tool_response_message(
                        error_msg
                    )
                    messages.append(error_response_message)

                    # Yield function execution error
                    yield {
                        "type": "function_call_error",
                        "function_name": func_name,
                        "error": str(e),
                    }

                    logger.error(f"Function execution failed for {func_name}: {e}")

    async def stream(
        self,
        question: str,
        context: CallingContext | None = None,
        max_iterations: int = 10,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream the agentic loop response for the given question and context.

        This implements the streaming agentic loop that iterates until completion:
        - Streams responses in real-time
        - Handles function calls between streaming iterations
        - Continues loop until final response or max iterations
        - Audits the session when complete

        Args:
            question: The user's question
            context: Calling context with model settings, tenant info, etc.
                    If None, uses default settings.
            max_iterations: Maximum number of agentic loop iterations

        Yields:
            Streaming response chunks
        """
        if context is None:
            context = CallingContext()

        # Initialize streaming context
        self._setup_streaming_context(context)

        # Build initial message stack
        messages = self._build_message_stack(question)

        # Get function schemas
        function_schemas = None
        if self._function_handler:
            function_schemas = self._function_handler.get_schemas()

        # Get model scheme for native dialect conversion
        from .language_model import LanguageModel
        from .utils import convert_tool_calls_to_native_message

        tenant_id = context.tenant_id or "default"
        language_model = LanguageModel(context.model, tenant_id)
        model_scheme = language_model.params.get("scheme", "openai")

        final_response_content = ""
        saw_stop = False  # Track stop signal from LLM

        # Agentic loop - iterate until completion or max iterations
        for iteration in range(max_iterations):
            logger.debug(
                f"Streaming agentic loop iteration {iteration + 1}/{max_iterations}"
            )

            # Yield iteration start event
            yield {
                "type": "iteration_start",
                "iteration": iteration + 1,
                "max_iterations": max_iterations,
            }

            try:
                # Initialize iteration state
                iteration_content = ""
                complete_tool_calls = []
                tool_call_buffer = {}
                saw_tool_call_complete = False

                # Prepare parameters from context
                params = context.model_dump(include={"temperature", "max_tokens"})

                # Add response_format if present (from metadata or prefer_json)
                metadata = getattr(context, "metadata", None)
                if metadata and "response_format" in metadata:
                    params["response_format"] = metadata["response_format"]
                elif context.prefer_json:
                    params["response_format"] = {"type": "json_object"}

                # Stream the completion for this iteration
                async for chunk in self.stream_completion(
                    messages=messages,
                    model_name=context.model,
                    **params,
                    stream=True,  # Always stream in the streaming method
                    tools=function_schemas,
                ):
                    # Forward the chunk
                    yield chunk

                    # Check for stop signal in chunk
                    if isinstance(chunk, dict):
                        # OpenAI format
                        if "choices" in chunk:
                            choices = chunk.get("choices", [])
                            if choices:
                                finish_reason = choices[0].get("finish_reason")
                                if finish_reason == "stop":
                                    saw_stop = True
                        # Anthropic format
                        elif chunk.get("type") == "message_delta":
                            delta = chunk.get("delta", {})
                            stop_reason = delta.get("stop_reason")
                            if stop_reason == "end_turn":
                                saw_stop = True

                    # Process chunk for content and tool calls
                    (
                        iteration_content,
                        final_response_content,
                        chunk_tool_calls,
                        saw_completion,
                    ) = self._process_streaming_chunk(
                        chunk,
                        tool_call_buffer,
                        iteration_content,
                        final_response_content,
                    )

                    if chunk_tool_calls:
                        complete_tool_calls = chunk_tool_calls
                        saw_tool_call_complete = saw_completion

                        # Emit function announcements for better UX
                        for tool_call in complete_tool_calls:
                            if "function" in tool_call:
                                yield {
                                    "type": "function_announcement",
                                    "function_name": tool_call["function"]["name"],
                                    "arguments": tool_call["function"]["arguments"],
                                }

                # Execute function calls if we have them
                if complete_tool_calls:
                    # Add assistant message with tool calls to conversation in native dialect
                    assistant_message = convert_tool_calls_to_native_message(
                        complete_tool_calls,
                        model_scheme,
                        iteration_content if iteration_content else "",
                    )
                    messages.append(assistant_message)

                    # Execute all function calls
                    async for func_result in self._execute_function_calls(
                        complete_tool_calls, messages, model_scheme
                    ):
                        yield func_result

                    # Continue to next iteration after function execution
                    continue

                # No tool calls - check if LLM signaled stop
                if saw_stop:
                    # LLM explicitly finished with stop signal
                    break
                # Otherwise continue to next iteration

            except Exception as e:
                import traceback
                logger.error(
                    f"Error in streaming agentic loop iteration {iteration + 1}: {traceback.format_exc()}",
                    exc_info=True  # This will include the full stack trace
                )
                yield {"type": "error", "iteration": iteration + 1, "error": str(e)}
                break

        # Yield completion event
        yield {
            "type": "completion",
            "final_response": final_response_content,
            "total_iterations": iteration + 1,
        }

        # Audit the session
        logger.trace(
            f"Attempting to audit session - streaming: {context.prefers_streaming}, response length: {len(final_response_content)}"
        )
        await self._audit_session(context, question, final_response_content)

    def _build_message_stack(self, question: str) -> list[dict[str, Any]]:
        """
        Build a message stack for the given question.

        Args:
            question: The user's question

        Returns:
            List of messages including system prompt if available
        """
        messages = []

        if self._model_context:
            # Use MessageStack to build from the model context
            try:
                message_stack = MessageStack.build_message_stack(
                    abstracted_model=self._model_context,
                    question=question,
                    schema_format='yaml'  # Use YAML schema for better structured output
                )

                # Convert to list of dict messages using to_messages()
                messages.extend(message_stack.to_messages())

            except Exception as e:
                logger.warning(f"Failed to build message stack from model context: {e}")
                # Fallback to simple user message
                messages.append({"role": "user", "content": question})
        else:
            # Simple user message for LLM relay mode
            messages.append({"role": "user", "content": question})

        return messages

    async def _handle_function_calls_sync(
        self,
        messages: list[dict[str, Any]],
        assistant_message: dict[str, Any],
        context: CallingContext,
    ) -> str:
        """
        Handle function calls in non-streaming mode.

        Args:
            messages: Original messages
            assistant_message: Assistant message with tool calls
            context: Calling context

        Returns:
            Final response after function execution
        """
        if not self._function_handler:
            return assistant_message.get("content", "No function handler available")

        # Add assistant message to conversation
        messages.append(assistant_message)

        # Execute each function call
        for tool_call in assistant_message.get("tool_calls", []):
            func_name = tool_call.get("function", {}).get("name")
            arguments_str = tool_call.get("function", {}).get("arguments", "{}")

            if func_name:
                try:
                    arguments = json.loads(arguments_str) if arguments_str else {}
                    result = await self._function_handler.execute(func_name, arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "content": json.dumps(result,default=str),
                        }
                    )

                except Exception as e:
                    logger.error(f"Function execution failed for {func_name}: {e}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "content": f"Error: {str(e)}",
                        }
                    )

        # Get final response with function results
        try:
            final_response = await self.complete(
                messages=messages,
                model_name=context.model,
                **context.model_dump(include={"temperature", "max_tokens"}),
            )

            if isinstance(final_response, dict) and "choices" in final_response:
                return final_response["choices"][0]["message"].get(
                    "content", "No final response"
                )
            return str(final_response)

        except Exception as e:
            logger.error(f"Failed to get final response: {e}")
            return (
                "Function executed successfully, but failed to generate final response."
            )

    async def load_context(self, thread_id: str | None = None) -> list[dict[str, Any]]:
        """
        Load conversation context from memory.

        Args:
            thread_id: Thread identifier to load context for

        Returns:
            List of previous messages in the conversation
        """
        # For now, just return the message buffer
        # TODO: Implement data fusion query against the tenant's Conversations store
        # and query user data for summaries
        return self._message_buffer

    async def save_message(self, message: dict[str, Any], thread_id: str | None = None):
        """
        Save a message to memory.

        Note: This is WIP. Messages could be storing entities in the models table
        (e.g. Tasks) or adding edges to existing entities. For example, a user
        could add a comment to a resource. This needs to be more sophisticated.

        Args:
            message: Message dictionary to save
            thread_id: Thread identifier
        """
        self._message_buffer.append(message)

        # TODO: Use data fusion to store data in the appropriate location
        # This should store to the tenant's conversation/message store with thread_id

    async def chat_completion_with_memory(
        self,
        messages: list[dict[str, Any]],
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
        include_context: bool = True,
        **kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """

        TODO: THIS needs refactor - we want something like run(messages, context) and the rest is abstracted
        for example stream options and temperature etc are in the CallingContext object and tools are registered from wherever by the function manager

        Stream a chat completion with memory context.

        Args:
            messages: New messages to send
            model: Name of the model to use
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            tools: Available function/tool definitions
            stream: Whether to stream the response
            include_context: Whether to include conversation history
            **kwargs: Additional parameters

        Yields:
            Streaming response chunks with function call handling
        """
        # Load conversation context if requested
        context_messages = []
        if include_context:
            context_messages = await self.load_context()

        # Combine context with new messages
        all_messages = context_messages + messages

        # Save new user messages
        for msg in messages:
            if msg.get("role") in ["user", "system"]:
                await self.save_message(msg)

        # Prepare parameters
        params = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools": tools,
            "stream": stream,
            **kwargs,
        }

        # Stream with function call handling if tools are provided
        if tools and stream:
            async for chunk in self._stream_with_function_handling(
                all_messages, model, params
            ):
                yield chunk
        else:
            # Regular streaming or non-streaming
            if stream:
                collected_content = ""
                async for chunk in self.stream_completion(
                    all_messages, model, **params
                ):
                    yield chunk
                    # Collect content for saving
                    if "choices" in chunk and chunk["choices"]:
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta:
                            collected_content += delta["content"]

                # Save assistant response
                if collected_content:
                    await self.save_message(
                        {"role": "assistant", "content": collected_content}
                    )
            else:
                response = await self.complete(all_messages, model, **params)
                yield response

                # Save assistant response
                if "choices" in response and response["choices"]:
                    message = response["choices"][0]["message"]
                    await self.save_message(message)

    async def _stream_with_function_handling(
        self, messages: list[dict[str, Any]], model: str, params: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream response with function call detection and handling.

        Args:
            messages: Messages to send
            model: Model name
            params: Request parameters

        Yields:
            Response chunks with function results injected
        """
        collector = FunctionCallCollector()

        async for chunk in self.stream_completion(messages, model, **params):
            # Process chunk and check for function calls
            processed = await self._process_function_chunk(chunk, collector)

            if processed["type"] == "content":
                yield processed["chunk"]
            elif processed["type"] == "function_complete":
                # Handle the function call
                async for result_chunk in self._handle_function_call(
                    messages, model, params, processed["function_data"]
                ):
                    yield result_chunk
                collector.reset()
            elif processed["type"] == "complete":
                # Save final message if needed
                if collector.content_buffer:
                    await self.save_message(
                        {"role": "assistant", "content": collector.content_buffer}
                    )
            elif processed["type"] == "passthrough":
                yield chunk

    async def _process_function_chunk(
        self, chunk: dict[str, Any], collector: FunctionCallCollector
    ) -> dict[str, Any]:
        """
        Process a streaming chunk for function calls.

        Args:
            chunk: Streaming chunk
            collector: Function call collector

        Returns:
            Processing result with type and data
        """
        if "choices" not in chunk or not chunk["choices"]:
            return {"type": "passthrough", "chunk": chunk}

        delta = chunk["choices"][0].get("delta", {})
        finish_reason = chunk["choices"][0].get("finish_reason")

        # Process delta through collector
        content_chunk = collector.process_delta(delta)
        if content_chunk:
            # Build proper chunk structure
            yield_chunk = chunk.copy()
            yield_chunk["choices"][0]["delta"] = content_chunk["delta"]
            return {"type": "content", "chunk": yield_chunk}

        # Check for function completion
        if finish_reason == "function_call":
            function_data = collector.get_function_call()
            if function_data:
                return {"type": "function_complete", "function_data": function_data}

        # Check for normal completion
        if finish_reason == "stop":
            return {"type": "complete"}

        return {"type": "skip"}

    async def _handle_function_call(
        self,
        messages: list[dict[str, Any]],
        model: str,
        params: dict[str, Any],
        function_data: tuple[str, dict[str, Any], str],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Handle a detected function call.

        Args:
            messages: Original messages
            model: Model name
            params: Request parameters
            function_data: Tuple of (function_name, arguments, content)

        Yields:
            Response chunks from function execution
        """
        function_name, arguments, content = function_data

        try:
            # Execute the function
            result = await self.function_handler.execute(function_name, arguments)

            # Build and save function messages
            func_messages = build_function_messages(
                function_name, arguments, result, content
            )
            for msg in func_messages:
                await self.save_message(msg)

            # Continue conversation with function result
            messages_with_result = messages + func_messages

            # Stream the continuation
            async for cont_chunk in self.stream_completion(
                messages_with_result, model, **params
            ):
                yield cont_chunk

        except Exception as e:
            logger.error(f"Function execution failed: {e}")
            yield build_error_chunk(function_name, e)

    # deprecate?
    async def summarize_context(
        self, model: str = "gpt-4", max_summary_tokens: int = 500
    ) -> str:
        """
        Summarize the conversation context to manage token limits.

        Args:
            model: Model to use for summarization
            max_summary_tokens: Maximum tokens for summary

        Returns:
            Summarized context string
        """
        context = await self.load_context()
        if len(context) < 10:  # Don't summarize short conversations
            return ""

        # Prepare summarization prompt
        conversation_text = "\n".join(
            [f"{msg['role']}: {msg.get('content', '')}" for msg in context]
        )

        summary_prompt = [
            {
                "role": "system",
                "content": "Summarize the following conversation concisely, preserving key information:",
            },
            {"role": "user", "content": conversation_text},
        ]

        response = await self.complete(
            summary_prompt, model, max_tokens=max_summary_tokens, temperature=0.3
        )

        # Extract summary
        if "choices" in response and response["choices"]:
            return response["choices"][0]["message"]["content"]
        return ""

    # Built-in functions for DataFusion integration
    async def get_entities(
        self,
        keys: str | list[str] | None = None,
        entity_type: str | None = None,
        limit: int = 10,
        allow_fuzzy_match: bool = False,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Get entities from the P8FS store by keys or type.

        This function is tenant-scoped and can retrieve any entity within the tenant's data.

        Args:
            keys: Optional key or list of keys to lookup specific entities
            entity_type: Optional entity type to filter by (e.g., 'Agent', 'Session', 'LanguageModelApi')
            limit: Maximum number of entities to return
            allow_fuzzy_match: If True, uses fuzzy matching for keys

        Returns:
            List of entities from the repository
        """
        try:
            # Get or create client
            client = self._get_tenant_bound_client()

            # Get entities by keys
            if keys:
                # Normalize keys to list
                if isinstance(keys, str):
                    keys = [keys]

                # Call BaseRepository.get_entities which returns list of dicts
                return client.get_entities(keys)

            # For entity type queries, use find_by_type if available
            elif entity_type:
                # Use BaseRepository's find_by_type method
                results = await client.find_by_type(
                    entity_type=entity_type,
                    limit=limit
                )
                
                return results

            else:
                # Return empty list if no keys or entity_type specified
                return []

        except Exception as e:
            logger.error(f"Error in get_entities: {e}")
            raise

    def search_resources(
        self,
        questions: str | list[str],
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Search RESOURCES for the user using P8FS client with multiple questions.

        This implements the Percolate repository search pattern with tenant-scoped queries.

        Args:
            questions: Single question or list of questions to search
            user_id: Optional user identifier for access control
            entity_type: Optional entity type to filter search
            limit: Maximum number of results per question

        Returns:
            Dictionary containing search results for each question
        """
        from p8fs.models import Resources
        from p8fs.repository import Repository

        try:
            # Get or create client
            client = Repository(Resources, tenant_id=self._tenant_id)

            return client.semantic_search(questions)

        except Exception as e:
            logger.error(f"Error in search: {e}")
            return {"error": str(e), "results": []}

    def search(
        self,
        questions: str | list[str],
        user_id: str | None = None,
        entity_type: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """
        Search entities using P8FS client with multiple questions.

        This implements the Percolate repository search pattern with tenant-scoped queries.

        Args:
            questions: Single question or list of questions to search
            user_id: Optional user identifier for access control
            entity_type: Optional entity type to filter search
            limit: Maximum number of results per question

        Returns:
            Dictionary containing search results for each question
        """
        try:
            # Get or create client
            client = self._get_tenant_bound_client()

            return client.semantic_search(questions)

        except Exception as e:
            logger.error(f"Error in search: {e}")
            return {"error": str(e), "results": []}

    def get_recent_tenant_uploads(
        self,
        limit: int = 20,
        include_resource_names: bool = True,
    ) -> dict[str, Any]:
        """
        Get recently uploaded files for the current tenant with associated resource names.

        This function delegates to the Files model's get_recent_uploads_by_user method
        for cleaner separation of concerns.

        Args:
            limit: Maximum number of recent files to return (default: 20)
            include_resource_names: Whether to include resource names collection (default: True)

        Returns:
            Dictionary containing recent upload information from Files model
        """
        from p8fs.models import Files

        try:
            # Get tenant ID from context
            tenant_id = self._get_tenant_id()

            logger.debug(f"Getting recent uploads for tenant: {tenant_id}")

            # Delegate to Files model method
            return Files.get_recent_uploads_by_user(
                tenant_id=tenant_id,
                limit=limit,
                include_resource_names=include_resource_names,
            )

        except Exception as e:
            logger.error(f"Error in get_recent_tenant_uploads: {e}")
            return {"error": str(e), "files": [], "resource_names": []}

    async def _audit_session(
        self, context: CallingContext, question: str, response: str
    ) -> None:
        """
        Audit the user session by saving to TiKV storage.

        Args:
            context: Calling context with user/tenant info
            question: User's question
            response: Agent's response (truncated)
        """
        try:
            # Start the audit session with the query
            await self.start_audit_session(
                tenant_id=context.tenant_id or self._tenant_id or DEFAULT_TENANT_ID,
                model=context.model,
                provider="openai",
                streaming=getattr(context, "stream", context.prefers_streaming),
                user_id=context.user_id,
                temperature=context.temperature,
                query=question,  # Pass the question as the query
                moment_id=context.moment_id  # Link to moment if provided
            )
            
            # Track token usage if we have a response
            if response:
                # Simple token estimation - in production you'd use tiktoken
                prompt_tokens = len(question.split()) if question else 0
                completion_tokens = len(response.split())
                await self.track_usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens
                )
            
            # End the session
            await self.end_audit_session()

        except Exception as e:
            logger.error(f"Failed to audit session: {e}")
            # Don't raise - auditing shouldn't break the main flow


    async def process_audio_messages(
        self, messages: list[dict[str, Any]], has_audio: bool = False
    ) -> list[dict[str, Any]]:
        """
        Process messages that may contain audio content.

        Currently, audio processing is not supported.

        Args:
            messages: List of message dictionaries
            has_audio: Whether the first user message contains audio

        Returns:
            Original messages unchanged

        Raises:
            ValueError: If audio processing is requested
        """
        if has_audio:
            raise ValueError("Audio processing is not currently supported")

        return messages

    async def batch(
        self, q: str | list[str], context: BatchCallingContext, save_job: bool = False
    ) -> BatchResponse:
        """
        Process questions in batch mode with simplified, clean API.

        This is the main abstraction for batch processing that handles:
        - Model parameter validation (GPT-5 reasoning parameters, etc.)
        - Job persistence if requested
        - OpenAI Batch API or sequential processing
        - All configuration via BatchCallingContext

        Args:
            q: Single question or list of questions to process
            context: BatchCallingContext with all batch settings and model parameters
            save_job: Override context.save_job setting if needed

        Returns:
            BatchResponse model containing batch results, job info, and metadata

        Example:
            # Simple usage with quick batch
            ctx = BatchCallingContext.for_quick_batch(model="gpt-4o-mini")
            result = await mem_proxy.batch("What is AI?", ctx)

            # Comprehensive GPT-5 analysis with job tracking
            ctx = BatchCallingContext.for_comprehensive_batch(
                model="gpt-5",
                save_job=True,
                tenant_id="my-tenant",
                user_id="user-123"
            )
            result = await mem_proxy.batch(["Question 1", "Question 2"], ctx)

            # Get job status later
            job = await Job.get_job_status(result["job_id"], ctx.tenant_id)
        """
        from p8fs.models.p8 import Job, JobStatus
        from p8fs.repository import TenantRepository
        import uuid

        questions = [q] if isinstance(q, str) else q
        if not questions:
            raise ValueError("No question supplied to batch processor")

        # Override save_job if explicitly provided
        should_save_job = save_job or context.save_job

        # Generate batch ID if not provided
        if not context.batch_id:
            context.batch_id = f"batch_{uuid.uuid4().hex[:8]}"

        logger.info(
            f"Starting batch processing of {len(questions)} questions with model {context.model}"
        )

        # Create job record if requested
        job = None
        if should_save_job:
            # Get tenant_id from context, falling back to config default
            from p8fs_cluster.config.settings import config
            context_tenant_id = getattr(context, "tenant_id", None)
            tenant_id = context_tenant_id or config.default_tenant_id
            
            logger.debug(f"Job creation - context tenant_id: {context_tenant_id}, using: {tenant_id}")
            
            # Create job - it will use the same tenant_id we pass
            job = Job.create_batch_job(questions, context, tenant_id)
            
            logger.debug(f"Created job with tenant_id: {job.tenant_id}")

            # Save to repository with same tenant_id
            logger.debug(f"Creating TenantRepository with tenant_id: {tenant_id}")
            jobs_repo = TenantRepository(Job, tenant_id)
            await jobs_repo.upsert(job)
            logger.info(f"Created batch job {job.id} for {len(questions)} questions")

        try:
            batch_response = await self._process_openai_batch(questions, context)

            # Add job ID if we created one
            if job:
                batch_response.job_id = str(job.id)

                # Update job with batch info (always OpenAI Batch API)
                job.openai_batch_id = batch_response.openai_batch_id
                job.status = JobStatus.PENDING  # Mark as pending, not processing
                job.queued_at = datetime.now(timezone.utc)

                await self._update_job_record(job)

            return batch_response

        except Exception as e:
            # Update job with error if saved
            if job:
                job.status = JobStatus.FAILED
                job.error = f"{type(e).__name__}: {str(e)}"
                job.completed_at = datetime.now(timezone.utc)
                await self._update_job_record(job)
            raise

    def _apply_settings_to_context(
        self, context: CallingContext, settings: dict
    ) -> None:
        """Apply settings dictionary to calling context with validation"""
        from p8fs.models.batch import GPT5Settings

        # Handle GPT-5 specific settings
        if context.model.startswith("gpt-5") or context.model == "gpt-5":
            gpt5_keys = {"reasoning_effort", "verbosity"}
            gpt5_settings = {k: v for k, v in settings.items() if k in gpt5_keys}

            if gpt5_settings:
                # Validate GPT-5 settings
                validated_settings = GPT5Settings(**gpt5_settings)
                # Store in metadata for later use
                context.metadata.update(validated_settings.to_request_params())

        # Apply standard parameters
        if "temperature" in settings:
            context.temperature = float(settings["temperature"])
        if "max_tokens" in settings:
            context.max_tokens = int(settings["max_tokens"])
        if "model" in settings:
            context.model = settings["model"]

    # Job creation is now handled by Job.create_batch_job() factory method

    async def _update_job_record(self, job) -> None:
        """Update job record in repository"""
        from p8fs.repository import TenantRepository

        # Use the job's own tenant_id
        tenant_id = job.tenant_id
        jobs_repo = TenantRepository(type(job), tenant_id)
        await jobs_repo.upsert(job)
        logger.debug(f"Updated job {job.id} status to {job.status}")

    async def _process_openai_batch(
        self, questions: list[str], context: BatchCallingContext
    ) -> BatchResponse:
        """
        Process questions using OpenAI's Batch API for maximum cost savings.

        This submits a batch job to OpenAI and returns the batch job ID.
        Results must be retrieved later using the callback system.

        Args:
            questions: List of questions to process
            context: BatchCallingContext with all settings

        Returns:
            BatchResponse with batch job information
        """
        from datetime import datetime, timezone

        tenant_id = context.tenant_id or self._tenant_id or "default"
        language_model = LanguageModel(context.model, tenant_id)

        # Build message stacks for all questions
        message_stacks = [self._build_message_stack(question) for question in questions]

        # Get function schemas if available
        tools = None
        if self._function_handler:
            tools = self._function_handler.get_schemas()

        # Delegate to LanguageModel for batch processing - much cleaner API!
        try:
            batch_result = await language_model.process_batch(
                message_stacks=message_stacks, context=context, tools=tools
            )

            # Create BatchResponse from the result
            return BatchResponse(
                batch_id=context.batch_id,
                batch_type="openai_batch_api",
                status="submitted",
                questions_count=len(questions),
                openai_batch_id=batch_result["openai_batch_id"],
                openai_file_id=batch_result["openai_file_id"],
                estimated_completion="24 hours",
                cost_savings="50-95%",
                submitted_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(f"Failed to process batch: {e}")
            raise

    async def get_job(
        self,
        job_id: str,
        tenant_id: str = None,
        include_openai_status: bool = True,
        fetch_results: bool = False,
    ) -> "JobStatusResponse":
        """
        Get comprehensive job status including OpenAI batch details.

        Args:
            job_id: P8FS job ID or OpenAI batch ID
            tenant_id: Tenant identifier (if None, uses default)
            include_openai_status: Whether to fetch live OpenAI batch status
            fetch_results: Whether to download completed results

        Returns:
            JobStatusResponse with unified job information

        Raises:
            ValueError: If job not found
            Exception: If OpenAI API calls fail
        """
        from p8fs.models.batch import JobStatusResponse
        from p8fs.models.p8 import Job

        # Use default tenant if not provided
        if not tenant_id:
            tenant_id = "default"

        logger.info(f"Getting job status for {job_id} (tenant: {tenant_id})")

        try:
            # First, try to get local job record
            from p8fs.repository import TenantRepository
            from p8fs.models.p8 import Job

            jobs_repo = TenantRepository(Job, tenant_id)
            local_job = await jobs_repo.find_by_id(job_id)

            if not local_job:
                # Maybe it's an OpenAI batch ID, try to create minimal response
                if job_id.startswith("batch_"):
                    logger.info(
                        f"Job ID {job_id} looks like OpenAI batch ID, fetching directly"
                    )
                    openai_batch = await self._get_openai_batch_status(job_id)

                    return JobStatusResponse(
                        job_id=job_id,
                        tenant_id=tenant_id,
                        status="unknown",
                        job_type="batch_job",
                        is_complete=openai_batch.get("status")
                        in ["completed", "failed", "cancelled"],
                        is_running=openai_batch.get("status")
                        in ["in_progress", "validating", "finalizing"],
                        is_batch=True,
                        openai_batch_id=job_id,
                        openai_batch_status=openai_batch.get("status"),
                        openai_request_counts=openai_batch.get("request_counts"),
                        openai_output_file_id=openai_batch.get("output_file_id"),
                        openai_error_file_id=openai_batch.get("error_file_id"),
                        metadata=openai_batch.get("metadata"),
                    )
                else:
                    raise ValueError(f"Job {job_id} not found in tenant {tenant_id}")

            # Build response from local job
            progress_info = local_job.get_progress_info()

            response = JobStatusResponse(
                job_id=local_job.id,
                tenant_id=local_job.tenant_id,
                status=local_job.status.value,
                job_type=local_job.job_type.value,
                is_complete=local_job.is_complete(),
                is_running=local_job.is_running(),
                progress_percentage=progress_info.get("progress_percentage"),
                created_at=local_job.queued_at,
                started_at=local_job.started_at,
                completed_at=local_job.completed_at,
                is_batch=local_job.is_batch,
                batch_size=local_job.batch_size,
                items_processed=local_job.items_processed,
                openai_batch_id=local_job.openai_batch_id,
                metadata=local_job.metadata,
            )

            # Fetch OpenAI batch status if requested and available
            if include_openai_status and local_job.openai_batch_id:
                try:
                    logger.info(
                        f"Fetching OpenAI batch status for {local_job.openai_batch_id}"
                    )
                    openai_batch = await self._get_openai_batch_status(
                        local_job.openai_batch_id
                    )

                    response.openai_batch_status = openai_batch.get("status")
                    response.openai_request_counts = openai_batch.get("request_counts")
                    response.openai_output_file_id = openai_batch.get("output_file_id")
                    response.openai_error_file_id = openai_batch.get("error_file_id")

                    # Update local job if OpenAI status changed
                    if response.openai_batch_status != local_job.openai_batch_status:
                        local_job.openai_batch_status = response.openai_batch_status
                        await self._update_job_record(local_job)

                except Exception as e:
                    logger.warning(f"Failed to fetch OpenAI batch status: {e}")
                    response.openai_batch_status = "unknown"

            # Fetch results if requested and available
            if (
                fetch_results
                and response.is_openai_batch_complete()
                and response.openai_output_file_id
            ):
                try:
                    logger.info(
                        f"Downloading results from file {response.openai_output_file_id}"
                    )
                    results = await self._download_batch_results(
                        response.openai_output_file_id
                    )
                    response.results = results
                except Exception as e:
                    logger.warning(f"Failed to download batch results: {e}")
                    response.error_details = {"download_error": str(e)}

            return response

        except Exception as e:
            logger.error(f"Failed to get job status: {e}")
            raise

    async def _get_openai_batch_status(self, batch_id: str) -> dict[str, Any]:
        """Get OpenAI batch job status"""
        from p8fs.services.llm.openai_requests import create_openai_client
        from p8fs.services.llm.language_model import LanguageModel

        # Get OpenAI client
        language_model = LanguageModel("gpt-4.1")
        client = create_openai_client(
            api_key=language_model.params.get(
                "api_key", language_model.params.get("token")
            )
        )

        return await client.retrieve_batch(batch_id)

    async def _download_batch_results(self, file_id: str) -> list[dict[str, Any]]:
        """Download and parse batch results from OpenAI"""
        from p8fs.services.llm.openai_requests import create_openai_client
        from p8fs.services.llm.language_model import LanguageModel
        import json

        # Get OpenAI client
        language_model = LanguageModel("gpt-4.1")
        client = create_openai_client(
            api_key=language_model.params.get(
                "api_key", language_model.params.get("token")
            )
        )

        # Download file content
        content = await client.download_file(file_id)

        # Parse JSONL results
        results = []
        for line in content.strip().split("\n"):
            if line.strip():
                results.append(json.loads(line))

        return results

    async def parse_content(
        self,
        content: str | list,
        context: CallingContext | None = None,
        chunk_size: int = 4000,
        merge_strategy: str = "last",
        use_token_chunking: bool = True
    ) -> Any:
        """
        Parse large content using structured output with automatic pagination.

        Automatically detects list structures (e.g., list of dicts) and chunks by
        record boundaries to preserve data integrity.

        Args:
            content: Large content to parse (string or list)
            context: Calling context (must have prefer_json=True for structured output)
            chunk_size: Max characters per chunk (default: 4000, ignored if use_token_chunking=True)
            merge_strategy: How to merge results - 'last', 'first', or 'merge' (default: 'last')
            use_token_chunking: Use smart token-based chunking for optimal efficiency (default: True)

        Returns:
            Parsed and validated model instance (if model_context is set)
        """
        if not self._model_context:
            raise ValueError("parse_content requires a model_context")

        if context is None:
            context = CallingContext(prefer_json=True, max_iterations=1)
        elif not context.prefer_json:
            context.prefer_json = True

        # Detect if content is a list structure
        from p8fs.utils.list_chunking import is_list_content

        if is_list_content(content):
            # Use record-based chunking for lists
            from p8fs.utils.list_chunking import chunk_by_records
            chunks = chunk_by_records(content, model_name=context.model)
            logger.info(f"Using record-based chunking: {len(chunks)} chunks for list content")
        elif use_token_chunking:
            # Use token-based chunking for strings
            from p8fs.utils.token_chunking import chunk_by_tokens
            # Ensure content is string
            content_str = content if isinstance(content, str) else json.dumps(content)
            chunks = chunk_by_tokens(content_str, context.model)
            logger.info(f"Using token-based chunking: {len(chunks)} chunks for model {context.model}")
        else:
            # Fallback to character-based chunking
            content_str = content if isinstance(content, str) else json.dumps(content)
            chunks = self._chunk_content(content_str, chunk_size)
            logger.info(f"Using character-based chunking: {len(chunks)} chunks of {chunk_size} chars")

        # Process chunks
        results = []
        for i, chunk in enumerate(chunks):
            question = f"Analyze this content (part {i+1}/{len(chunks)}) and return only the structured JSON analysis without using any tools or functions.\n\n{chunk}"
            response = await self.run(question, context, max_iterations=1)

            # Parse JSON response
            parsed = self._extract_json(response)
            if parsed:
                results.append(parsed)
                logger.debug(f"Parsed chunk {i+1}/{len(chunks)}: {len(parsed)} keys")
            else:
                logger.warning(f"Failed to parse chunk {i+1}/{len(chunks)}, response length: {len(response)}, response: {response[:200]}")

        # Merge results
        merged = self._merge_results(results, merge_strategy)

        # Validate with model
        if merged and self._model_context:
            try:
                return self._model_context(**merged)
            except Exception as e:
                logger.warning(f"Failed to validate merged results with model: {e}")
                return merged

        return merged

    def _chunk_content(self, content: str, chunk_size: int) -> list[str]:
        """Split content into chunks by character count.

        Args:
            content: Content to chunk
            chunk_size: Max characters per chunk

        Returns:
            List of content chunks

        Note: This uses character-based chunking for simplicity.
        For token-based chunking, use _chunk_content_by_tokens instead.
        """
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

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from markdown or plain text response."""
        import re

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try markdown code block with json
        pattern1 = r'```json\s*(\{[\s\S]+\})\s*```'
        matches = re.findall(pattern1, text, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[-1])
            except json.JSONDecodeError:
                pass

        # Try markdown code block without language
        pattern2 = r'```\s*(\{[\s\S]+\})\s*```'
        matches = re.findall(pattern2, text, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[-1])
            except json.JSONDecodeError:
                pass

        # Try first { to last }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass

        return None

    def _merge_results(self, results: list[dict], strategy: str) -> dict:
        """Merge multiple result dictionaries based on strategy."""
        if not results:
            return {}

        if strategy == "first":
            return results[0]
        elif strategy == "last":
            return results[-1]
        elif strategy == "merge":
            merged = {}
            for result in results:
                for key, value in result.items():
                    if isinstance(value, list):
                        merged.setdefault(key, []).extend(value)
                    elif key not in merged:
                        merged[key] = value
            return merged
        else:
            raise ValueError(f"Unknown merge strategy: {strategy}")
