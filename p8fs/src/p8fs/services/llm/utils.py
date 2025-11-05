"""
Utility functions for LLM streaming and response handling.

This module provides helper functions for:
- SSE (Server-Sent Events) parsing and creation
- Background auditing of LLM interactions
- Formatting tool calls for different providers
"""

import json
import typing
import uuid
from datetime import datetime
import sys

# Python 3.11+ has UTC, earlier versions need timezone.utc
if sys.version_info >= (3, 11):
    from datetime import UTC
else:
    from datetime import timezone
    UTC = timezone.utc

from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


def parse_sse_line(line: str) -> dict | None:
    """
    Parse a Server-Sent Event line into a dictionary.

    Args:
        line: The SSE line to parse (e.g., "data: {...}")

    Returns:
        Parsed JSON data or None if parsing fails
    """
    if not line or not line.startswith("data: "):
        return None

    data_str = line[6:].strip()
    if data_str == "[DONE]":
        return {"type": "done"}

    try:
        return json.loads(data_str)
    except json.JSONDecodeError:
        logger.debug(f"Failed to parse SSE line: {line}")
        return None


def create_sse_line(data: dict | str) -> str:
    """
    Create a Server-Sent Event line from data.

    Args:
        data: Dictionary to convert to JSON or string data

    Returns:
        SSE formatted line
    """
    if isinstance(data, dict):
        return f"data: {json.dumps(data)}\n\n"
    else:
        return f"data: {data}\n\n"


def format_tool_calls_for_openai(tool_calls: list[dict]) -> list[dict]:
    """
    Format tool calls for OpenAI API format.

    Args:
        tool_calls: List of tool call dictionaries

    Returns:
        Formatted tool calls for OpenAI
    """
    formatted_calls = []
    for tool_call in tool_calls:
        # Ensure proper structure
        formatted_call = {
            "id": tool_call.get("id", f"call_{str(uuid.uuid4())[:16]}"),
            "type": "function",
            "function": {
                "name": tool_call.get("function", {}).get("name", ""),
                "arguments": tool_call.get("function", {}).get("arguments", "{}"),
            },
        }
        formatted_calls.append(formatted_call)

    return formatted_calls


class BackgroundAudit:
    """
    Background auditing for LLM interactions.

    This class handles asynchronous auditing of user sessions and AI responses
    without blocking the main response stream.
    """

    def __init__(self):
        """Initialize the background auditor."""
        self.pending_audits = []

    def audit_user_session(
        self,
        session_id: str,
        user_id: str | None = None,
        channel_id: str | None = None,
        query: str | None = None,
        **kwargs,
    ) -> None:
        """
        Audit a user session asynchronously.

        Args:
            session_id: The session identifier
            user_id: The user identifier
            channel_id: The channel/thread identifier
            query: The user's query
            **kwargs: Additional session metadata
        """
        # In a production system, this would queue the audit for background processing
        # For now, we just log it
        audit_data = {
            "session_id": session_id,
            "user_id": user_id,
            "channel_id": channel_id,
            "query": query,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        logger.debug(f"Auditing user session: {session_id}")
        self.pending_audits.append(audit_data)

        # TODO: Implement actual background processing with asyncio or celery

    def audit_ai_response(
        self,
        session_id: str,
        content: str,
        tool_calls: list[dict] | None = None,
        usage: dict | None = None,
        **kwargs,
    ) -> None:
        """
        Audit an AI response asynchronously.

        Args:
            session_id: The session identifier
            content: The AI response content
            tool_calls: Any tool calls made
            usage: Token usage information
            **kwargs: Additional response metadata
        """
        audit_data = {
            "session_id": session_id,
            "content": content,
            "tool_calls": tool_calls or [],
            "usage": usage or {},
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        logger.debug(f"Auditing AI response for session: {session_id}")
        self.pending_audits.append(audit_data)

    def flush(self):
        """
        Flush pending audits (for testing or shutdown).

        In production, this would ensure all pending audits are processed.
        """
        if self.pending_audits:
            logger.info(f"Flushing {len(self.pending_audits)} pending audits")
            # TODO: Process pending audits
            self.pending_audits.clear()


class LLMStreamIterator:
    """
    Iterator wrapper for LLM streaming responses.

    This class wraps a streaming generator and provides:
    - Content aggregation
    - Usage tracking
    - Tool call collection
    - Audit integration
    """

    def __init__(
        self,
        stream_generator: typing.Generator[tuple[str, dict], None, None],
        model: str = "unknown",
        session_id: str | None = None,
        audit_on_flush: bool = False,
    ):
        """
        Initialize the stream iterator.

        Args:
            stream_generator: The underlying stream generator
            model: The model name
            session_id: Optional session ID for auditing
            audit_on_flush: Whether to audit when the stream completes
        """
        self._generator = stream_generator
        self.model = model
        self.session_id = session_id
        self.audit_on_flush = audit_on_flush

        # State tracking
        self.content = ""
        self.ai_responses = []
        self._usage = None
        self._is_consumed = False
        self._tool_calls = []

    def iter_lines(self) -> typing.Generator[str, None, None]:
        """
        Iterate over the raw SSE lines while tracking state.

        Yields:
            Raw SSE lines
        """
        try:
            for raw_line, chunk in self._generator:
                # Track content
                if isinstance(chunk, dict) and "choices" in chunk:
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        if "content" in delta:
                            self.content += delta["content"]

                        # Track tool calls
                        if "tool_calls" in delta:
                            for tool_call in delta["tool_calls"]:
                                self._tool_calls.append(tool_call)

                # Track usage
                if isinstance(chunk, dict) and "usage" in chunk:
                    self._usage = chunk["usage"]

                # Yield the raw line
                yield raw_line

            self._is_consumed = True

            # Perform audit if requested
            if self.audit_on_flush and self.session_id:
                self._perform_audit()

        except Exception as e:
            logger.error(f"Error in stream iterator: {e}")
            self._is_consumed = True
            raise

    def _perform_audit(self):
        """Perform audit of the completed stream."""
        auditor = BackgroundAudit()
        auditor.audit_ai_response(
            session_id=self.session_id,
            content=self.content,
            tool_calls=self._tool_calls,
            usage=self._usage,
        )

    def __iter__(self):
        """Make the iterator iterable."""
        return self.iter_lines()

    @property
    def tool_calls(self):
        """Get the collected tool calls."""
        return self._tool_calls


class FunctionCall:
    """
    Represents a function call request from an LLM with native dialect support.
    """

    def __init__(
        self, name: str, arguments: dict[str, typing.Any], id: str | None = None, scheme: str = "openai"
    ):
        """
        Initialize a function call.

        Args:
            name: Function name
            arguments: Function arguments as a dictionary
            id: Optional function call ID
            scheme: LLM provider scheme (openai, anthropic, google)
        """
        self.name = name
        self.arguments = arguments
        self.id = id or f"call_{str(uuid.uuid4())[:16]}"
        self.scheme = scheme

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments)
                if isinstance(self.arguments, dict)
                else self.arguments,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FunctionCall":
        """Create from dictionary format."""
        function_data = data.get("function", {})
        arguments = function_data.get("arguments", "{}")

        # Parse arguments if they're a JSON string
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"raw": arguments}

        return cls(
            name=function_data.get("name", ""), arguments=arguments, id=data.get("id")
        )

    def __str__(self):
        """String representation."""
        return f"FunctionCall(name={self.name}, arguments={self.arguments}, scheme={self.scheme})"

    def get_tool_response_role(self) -> str:
        """
        Get the role name for tool responses in the message stack.
        
        Returns:
            Role name for tool responses based on provider scheme
        """
        if self.scheme == "anthropic":
            return "user"
        elif self.scheme == "google":
            return "user"  # Google uses "user" for tool responses
        else:  # OpenAI default
            return "tool"

    def to_assistant_message(self) -> dict[str, typing.Any]:
        """
        Convert the function call to an assistant message in the native dialect.
        
        This is critical for maintaining message stack consistency - the LLM
        must see tool calls in its native format, not the OpenAI format used
        for streaming.
        
        Returns:
            Assistant message formatted for the provider's native dialect
        """
        if self.scheme == "anthropic":
            return self._to_anthropic_assistant_format()
        elif self.scheme == "google":
            return self._to_google_assistant_format()
        else:  # Default to OpenAI format
            return self._to_openai_assistant_format()

    def _to_openai_assistant_format(self) -> dict[str, typing.Any]:
        """Format as OpenAI assistant message with tool_calls"""
        args_str = (
            json.dumps(self.arguments)
            if isinstance(self.arguments, dict)
            else str(self.arguments)
        )
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": self.id,
                    "type": "function",
                    "function": {"name": self.name, "arguments": args_str},
                }
            ],
        }

    def _to_anthropic_assistant_format(self) -> dict[str, typing.Any]:
        """Format as Anthropic assistant message with tool_use content"""
        return {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": self.id,
                    "name": self.name,
                    "input": self.arguments,
                }
            ],
        }

    def _to_google_assistant_format(self) -> dict[str, typing.Any]:
        """Format as Google assistant message with functionCall parts"""
        return {
            "role": "model",
            "parts": [{"functionCall": {"name": self.name, "args": self.arguments}}],
        }

    def create_tool_response_message(self, result: typing.Any) -> dict[str, typing.Any]:
        """
        Create a tool response message in the native dialect.
        
        Args:
            result: The result from executing the function
            
        Returns:
            Tool response message formatted for the provider's native dialect
        """
        if self.scheme == "anthropic":
            return self._create_anthropic_tool_response(result)
        elif self.scheme == "google":
            return self._create_google_tool_response(result)
        else:  # OpenAI default
            return self._create_openai_tool_response(result)

    def _create_openai_tool_response(self, result: typing.Any) -> dict[str, typing.Any]:
        """Create OpenAI format tool response"""
        return {
            "role": "tool",
            "tool_call_id": self.id,
            "content": json.dumps(result) if not isinstance(result, str) else result,
        }

    def _create_anthropic_tool_response(self, result: typing.Any) -> dict[str, typing.Any]:
        """Create Anthropic format tool response"""
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": self.id,
                    "content": json.dumps(result) if not isinstance(result, str) else result,
                }
            ],
        }

    def _create_google_tool_response(self, result: typing.Any) -> dict[str, typing.Any]:
        """Create Google format tool response"""
        return {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": self.name,
                        "response": result if isinstance(result, dict) else {"result": result}
                    }
                }
            ],
        }

    @classmethod
    def from_openai_tool_call(
        cls, 
        tool_call: dict[str, typing.Any], 
        scheme: str = "openai"
    ) -> "FunctionCall":
        """
        Create a FunctionCall from an OpenAI format tool call.
        
        Args:
            tool_call: OpenAI format tool call dict
            scheme: Target provider scheme
            
        Returns:
            FunctionCall instance with proper scheme
        """
        function_data = tool_call.get("function", {})
        arguments = function_data.get("arguments", "{}")
        
        # Parse arguments if they're a JSON string
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"raw": arguments}
        
        return cls(
            id=tool_call.get("id"),
            name=function_data.get("name", ""),
            arguments=arguments,
            scheme=scheme
        )


def convert_tool_calls_to_native_message(
    tool_calls: list[dict[str, typing.Any]], 
    scheme: str = "openai",
    content: str = ""
) -> dict[str, typing.Any]:
    """
    Convert a list of OpenAI format tool calls to a single native assistant message.
    
    This is a convenience function for converting buffered tool calls from
    the UnifiedStreamAdapter back to native format for the message stack.
    
    Args:
        tool_calls: List of OpenAI format tool call dicts
        scheme: Target provider scheme
        content: Optional content to include with the tool calls
        
    Returns:
        Single assistant message in native format containing all tool calls
    """
    if not tool_calls:
        return {"role": "assistant", "content": content or ""}
    
    # For OpenAI, return a single message with multiple tool_calls
    if scheme == "openai":
        message = {
            "role": "assistant",
            "content": content or "",
            "tool_calls": tool_calls
        }
        return message
    
    # For Anthropic, combine all tool_use blocks into one message
    elif scheme == "anthropic":
        content_blocks = []
        
        # Add text content if present
        if content:
            content_blocks.append({
                "type": "text",
                "text": content
            })
        
        # Add tool use blocks
        for tool_call in tool_calls:
            func_call = FunctionCall.from_openai_tool_call(tool_call, scheme)
            # Extract the tool_use block from the assistant message
            assistant_msg = func_call.to_assistant_message()
            content_blocks.extend(assistant_msg["content"])
        
        return {
            "role": "assistant",
            "content": content_blocks
        }
    
    # For Google, create a single message with multiple functionCall parts
    elif scheme == "google":
        parts = []
        
        # Add text content if present
        if content:
            parts.append({
                "text": content
            })
        
        # Add function call parts
        for tool_call in tool_calls:
            func_call = FunctionCall.from_openai_tool_call(tool_call, scheme)
            # Extract the functionCall part from the model message
            model_msg = func_call.to_assistant_message()
            parts.extend(model_msg["parts"])
        
        return {
            "role": "model",
            "parts": parts
        }
    
    else:
        # Default to OpenAI format
        return {
            "role": "assistant", 
            "content": content or "",
            "tool_calls": tool_calls
        }


class MessageStackFormatter:
    """
    Formatter for message stack operations and function responses.
    """

    @staticmethod
    def format_function_response(
        function_call: FunctionCall,
        result: typing.Any,
        context: typing.Any | None = None,
    ) -> str:
        """
        Format a successful function response.

        Args:
            function_call: The function call that was executed
            result: The function result
            context: Optional context for formatting

        Returns:
            Formatted response string
        """
        if isinstance(result, dict) or isinstance(result, (list, tuple)):
            return json.dumps(result, indent=2)
        else:
            return str(result)

    @staticmethod
    def format_function_response_error(
        function_call: FunctionCall, error: Exception, context: typing.Any | None = None
    ) -> str:
        """
        Format a function error response.

        Args:
            function_call: The function call that failed
            error: The exception that occurred
            context: Optional context for formatting

        Returns:
            Formatted error response string
        """
        error_data = {
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "function": function_call.name,
                "arguments": function_call.arguments,
            }
        }
        return json.dumps(error_data, indent=2)


def extract_content_from_chunks(
    chunks: list[dict[str, typing.Any]], source_scheme: str
) -> tuple[str, list[dict[str, typing.Any]]]:
    """
    Extract content and function calls from streaming chunks.

    Args:
        chunks: List of streaming chunks
        source_scheme: The provider scheme (openai, anthropic, google)

    Returns:
        Tuple of (full_content, function_calls)
    """
    full_content = ""
    function_calls = []

    for chunk in chunks:
        if source_scheme == "openai":
            if "choices" in chunk and chunk["choices"]:
                delta = chunk["choices"][0].get("delta", {})
                if "content" in delta:
                    full_content += delta["content"]
                if "function_call" in delta:
                    function_calls.append(delta["function_call"])

        elif source_scheme == "anthropic":
            if "delta" in chunk and "text" in chunk["delta"]:
                full_content += chunk["delta"]["text"]

        elif source_scheme == "google":
            if "candidates" in chunk and chunk["candidates"]:
                content = chunk["candidates"][0].get("content", {})
                if "parts" in content and content["parts"]:
                    for part in content["parts"]:
                        if "text" in part:
                            full_content += part["text"]

    return full_content, function_calls


def build_openai_response(
    content: str, function_calls: list[dict[str, typing.Any]], model: str = "unknown"
) -> dict[str, typing.Any]:
    """Build a complete OpenAI-format response."""
    import time

    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "function_call": function_calls[0] if function_calls else None,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def build_anthropic_response(
    content: str, model: str = "unknown"
) -> dict[str, typing.Any]:
    """Build a complete Anthropic-format response."""
    import time

    return {
        "id": f"msg_{int(time.time())}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}],
        "model": model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


def build_google_response(content: str) -> dict[str, typing.Any]:
    """Build a complete Google-format response."""
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": content}], "role": "model"},
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "promptFeedback": {"safetyRatings": []},
    }


def build_generic_response(
    content: str,
    function_calls: list[dict[str, typing.Any]],
    model: str = "unknown",
    provider: str = "unknown",
) -> dict[str, typing.Any]:
    """Build a generic response format."""
    return {
        "content": content,
        "function_calls": function_calls,
        "model": model,
        "provider": provider,
    }


def extract_response_content(response: dict[str, typing.Any]) -> str:
    """
    Extract text content from various response formats.

    Args:
        response: Response dictionary from an LLM provider

    Returns:
        Extracted text content
    """
    # OpenAI format
    if "choices" in response and response["choices"]:
        return response["choices"][0]["message"]["content"]

    # Anthropic format
    elif "content" in response and isinstance(response["content"], list):
        return response["content"][0].get("text", "")

    # Google format
    elif "candidates" in response and response["candidates"]:
        parts = response["candidates"][0]["content"]["parts"]
        return parts[0].get("text", "") if parts else ""

    # Fallback
    else:
        return str(response.get("content", ""))


class FunctionCallCollector:
    """Collects function call data from streaming chunks."""

    def __init__(self):
        self.function_name: str | None = None
        self.function_buffer: str = ""
        self.collecting: bool = False
        self.content_buffer: str = ""

    def process_delta(
        self, delta: dict[str, typing.Any]
    ) -> dict[str, typing.Any] | None:
        """
        Process a delta chunk for function calls.

        Args:
            delta: Delta from streaming chunk

        Returns:
            Content chunk to yield if not collecting function
        """
        # Handle function calls first to set collecting state
        if "function_call" in delta:
            func_call = delta["function_call"]

            if "name" in func_call:
                self.function_name = func_call["name"]
                self.collecting = True
                self.function_buffer = ""

            if "arguments" in func_call:
                self.function_buffer += func_call["arguments"]

        # Handle content
        if "content" in delta and delta["content"]:
            self.content_buffer += delta["content"]
            if not self.collecting:
                return {"delta": {"content": delta["content"]}}

        return None

    def get_function_call(self) -> tuple[str, dict[str, typing.Any], str] | None:
        """
        Get collected function call if complete.

        Returns:
            Tuple of (function_name, arguments, content_buffer) or None
        """
        if self.function_name and self.function_buffer:
            try:
                arguments = json.loads(self.function_buffer)
                return self.function_name, arguments, self.content_buffer
            except json.JSONDecodeError:
                logger.warning(
                    f"Failed to parse function arguments: {self.function_buffer}"
                )
        return None

    def reset(self):
        """Reset the collector for the next function."""
        self.function_name = None
        self.function_buffer = ""
        self.collecting = False
        self.content_buffer = ""


def build_function_messages(
    function_name: str,
    arguments: dict[str, typing.Any],
    result: typing.Any,
    content: str | None = None,
) -> list[dict[str, typing.Any]]:
    """
    Build messages for function call and result.

    Args:
        function_name: Name of the function
        arguments: Function arguments
        result: Function execution result
        content: Optional content before function call

    Returns:
        List of messages for the function interaction
    """
    messages = []

    # Assistant message with function call
    assistant_msg = {
        "role": "assistant",
        "function_call": {"name": function_name, "arguments": json.dumps(arguments)},
    }
    if content:
        assistant_msg["content"] = content
    messages.append(assistant_msg)

    # Function result message
    messages.append(
        {
            "role": "function",
            "name": function_name,
            "content": json.dumps(result) if not isinstance(result, str) else result,
        }
    )

    return messages


def build_error_chunk(function_name: str, error: Exception) -> dict[str, typing.Any]:
    """Build an error chunk for streaming."""
    return {
        "choices": [
            {
                "delta": {
                    "content": f"\n\nError executing {function_name}: {str(error)}"
                },
                "index": 0,
            }
        ]
    }


# Default Language Model Configurations

def get_default_language_models() -> list[dict[str, typing.Any]]:
    """
    Get default language model configurations.

    Returns:
        List of default language model configurations
    """
    return [
        {
            "id": "9d4f2b1e-6c8a-4e7d-95b3-f8a4c7e2d6b9",
            "name": "gpt-4o",
            "model": "gpt-4o",
            "scheme": "openai",
            "completions_uri": "https://api.openai.com/v1/chat/completions",
            "token_env_key": "OPENAI_API_KEY",
        },
        {
            "id": "gpt-4o-mini",
            "name": "gpt-4o-mini",
            "model": "gpt-4o-mini",
            "scheme": "openai",
            "completions_uri": "https://api.openai.com/v1/chat/completions",
            "token_env_key": "OPENAI_API_KEY",
        },
        {
            "id": "7a9c2e4f-5d7f-3b9d-1e3f-5c7e9f1a3b5d",
            "name": "claude-3-5-sonnet-20241022",
            "model": "claude-3-5-sonnet-20241022",
            "scheme": "anthropic",
            "completions_uri": "https://api.anthropic.com/v1/messages",
            "token_env_key": "ANTHROPIC_API_KEY",
            "anthropic-version": "2023-06-01",
        },
        {
            "id": "d4f1c9e7-1f3b-9d5e-7f9c-1e5f3a7b9d1f",
            "name": "gemini-2.0-flash",
            "model": "gemini-2.0-flash",
            "scheme": "google",
            "completions_uri": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            "token_env_key": "GEMINI_API_KEY",
        },
        {
            "id": "legacy-gpt-4",
            "name": "gpt-4",
            "model": "gpt-4",
            "scheme": "openai",
            "completions_uri": "https://api.openai.com/v1/chat/completions",
            "token_env_key": "OPENAI_API_KEY",
        },
    ]


def get_default_model_by_name(model_name: str) -> dict[str, typing.Any]:
    """
    Get default model configuration by name.

    Args:
        model_name: Name of the model to find

    Returns:
        Model configuration dictionary

    Raises:
        ValueError: If model not found
    """
    models = get_default_language_models()

    for model in models:
        if model["name"] == model_name or model["model"] == model_name:
            return model

    raise ValueError(f"Model '{model_name}' not found in default configurations")


def infer_model_scheme(model_name: str) -> str:
    """
    Infer the model scheme from the model name.

    Args:
        model_name: Name of the model

    Returns:
        Inferred scheme (openai, anthropic, google)
    """
    model_lower = model_name.lower()

    if any(
        provider in model_lower
        for provider in ["gpt", "openai", "davinci", "curie", "babbage", "ada"]
    ):
        return "openai"
    elif any(provider in model_lower for provider in ["claude", "anthropic"]):
        return "anthropic"
    elif any(
        provider in model_lower for provider in ["gemini", "palm", "bard", "google"]
    ):
        return "google"
    elif any(
        provider in model_lower for provider in ["llama", "cerebras", "groq"]
    ) or any(provider in model_lower for provider in ["deepseek", "grok", "mercury"]):
        return "openai"  # These use OpenAI-compatible API
    else:
        return "openai"  # Default to OpenAI format


def get_default_completions_uri(scheme: str, model_name: str = None) -> str:
    """
    Get default completions URI for a scheme.

    Args:
        scheme: The model scheme (openai, anthropic, google)
        model_name: Optional model name for Google models

    Returns:
        Default completions URI
    """
    if scheme == "openai":
        return "https://api.openai.com/v1/chat/completions"
    elif scheme == "anthropic":
        return "https://api.anthropic.com/v1/messages"
    elif scheme == "google":
        if model_name:
            return f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        return "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    else:
        return "https://api.openai.com/v1/chat/completions"


def get_default_token_env_key(scheme: str) -> str:
    """
    Get default token environment key for a scheme.

    Args:
        scheme: The model scheme

    Returns:
        Default token environment key
    """
    if scheme == "openai":
        return "OPENAI_API_KEY"
    elif scheme == "anthropic":
        return "ANTHROPIC_API_KEY"
    elif scheme == "google":
        return "GEMINI_API_KEY"
    else:
        return "OPENAI_API_KEY"


def create_default_model_config(
    model_name: str,
    scheme: str = None,
    completions_uri: str = None,
    token_env_key: str = None,
) -> dict[str, typing.Any]:
    """
    Create a default model configuration.

    Args:
        model_name: Name of the model
        scheme: Model scheme (inferred if not provided)
        completions_uri: Completions URI (default if not provided)
        token_env_key: Token environment key (default if not provided)

    Returns:
        Model configuration dictionary
    """
    if scheme is None:
        scheme = infer_model_scheme(model_name)

    if completions_uri is None:
        completions_uri = get_default_completions_uri(scheme, model_name)

    if token_env_key is None:
        token_env_key = get_default_token_env_key(scheme)

    return {
        "id": f"generated-{hash(model_name)}",
        "name": model_name,
        "model": model_name,
        "scheme": scheme,
        "completions_uri": completions_uri,
        "token_env_key": token_env_key,
    }