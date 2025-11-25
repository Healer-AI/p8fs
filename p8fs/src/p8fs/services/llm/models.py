"""LLM service data models and types."""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Literal
import uuid
from pydantic import Field, BaseModel
import typing
from p8fs.models.base import AbstractModel
from p8fs import settings

MAX_AGENT_LOOPS = 5


# LLM Provider Enums
class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    CUSTOM = "custom"


class MessageRole(str, Enum):
    """Message roles in conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ToolChoice(str, Enum):
    """Tool choice options for OpenAI."""

    NONE = "none"
    AUTO = "auto"
    REQUIRED = "required"


# Base Request Models
class LLMApiRequest(AbstractModel, ABC):
    """Base class for LLM API requests with provider-agnostic interface."""

    model: str = Field(..., description="Model identifier")
    messages: list[dict[str, Any]] = Field(..., description="Conversation messages")
    max_tokens: int | None = Field(None, description="Maximum tokens to generate")
    temperature: float | None = Field(None, description="Sampling temperature")
    top_p: float | None = Field(None, description="Top-p sampling")
    stream: bool = Field(False, description="Enable streaming response")
    tools: list[dict[str, Any]] | None = Field(
        None, description="Available tools/functions"
    )

    model_config = {
        "description": "Base LLM API request format"
    }

    @abstractmethod
    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI API format."""
        pass

    @abstractmethod
    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic API format."""
        pass

    @abstractmethod
    def to_google_format(self) -> dict[str, Any]:
        """Convert to Google API format."""
        pass


class OpenAIRequest(LLMApiRequest):
    """OpenAI-specific API request format."""

    tool_choice: ToolChoice | dict[str, Any] | None = Field(
        None, description="Tool selection preference"
    )
    response_format: dict[str, Any] | None = Field(
        None, description="Response format specification"
    )
    user: str | None = Field(None, description="User identifier for tracking")
    max_completion_tokens: int | None = Field(
        None, description="Max completion tokens (GPT-4+)"
    )
    reasoning_effort: str | None = Field(
        None, description="Reasoning effort level (GPT-5)"
    )
    verbosity: int | None = Field(None, description="Response verbosity (GPT-5)")

    model_config = {
        "table_name": "openai_requests",
        "description": "OpenAI API request format with GPT-5 support"
    }

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI API format."""
        return self.model_dump(exclude_none=True)

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic API format."""
        data = self.model_dump(exclude_none=True)

        # Extract system message from messages
        messages = data.get("messages", [])
        system_message = None
        filtered_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                # Take only the first system message
                if system_message is None:
                    system_message = msg.get("content", "")
            else:
                filtered_messages.append(msg)

        anthropic_data = {
            "model": data.get("model"),
            "messages": filtered_messages,
            "max_tokens": data.get("max_tokens", 4000),
            "stream": data.get("stream", False),
        }

        if system_message:
            anthropic_data["system"] = system_message

        if "temperature" in data:
            anthropic_data["temperature"] = data["temperature"]

        if "top_p" in data:
            anthropic_data["top_p"] = data["top_p"]

        return anthropic_data

    def to_google_format(self) -> dict[str, Any]:
        """Convert to Google API format."""
        data = self.model_dump(exclude_none=True)
        messages = data.get("messages", [])

        # Convert messages to Google format
        contents = []
        system_instruction = None

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})

        google_data = {"contents": contents, "generationConfig": {}}

        if system_instruction:
            google_data["system_instruction"] = system_instruction

        if "temperature" in data:
            google_data["generationConfig"]["temperature"] = data["temperature"]

        if "max_tokens" in data:
            google_data["generationConfig"]["maxOutputTokens"] = data["max_tokens"]

        if "top_p" in data:
            google_data["generationConfig"]["topP"] = data["top_p"]

        return google_data


class AnthropicRequest(LLMApiRequest):
    """Anthropic-specific API request format."""

    system: str | None = Field(None, description="System message")
    stop_sequences: list[str] | None = Field(None, description="Stop sequences")
    top_k: int | None = Field(None, description="Top-k sampling")

    model_config = {
        "table_name": "anthropic_requests",
        "description": "Anthropic Claude API request format"
    }

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI API format."""
        data = self.model_dump(exclude_none=True)

        # Convert Anthropic format to OpenAI
        openai_data = {
            "model": data.get("model"),
            "messages": data.get("messages", []),
            "stream": data.get("stream", False),
        }

        # Add system message to messages if present
        if self.system:
            openai_data["messages"].insert(
                0, {"role": "system", "content": self.system}
            )

        if "temperature" in data:
            openai_data["temperature"] = data["temperature"]

        if "max_tokens" in data:
            openai_data["max_tokens"] = data["max_tokens"]

        if "top_p" in data:
            openai_data["top_p"] = data["top_p"]

        return openai_data

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic API format."""
        return self.model_dump(exclude_none=True)

    def to_google_format(self) -> dict[str, Any]:
        """Convert to Google API format."""
        data = self.model_dump(exclude_none=True)
        messages = data.get("messages", [])

        # Convert messages to Google format
        contents = []
        system_instruction = None

        if self.system:
            system_instruction = {"parts": [{"text": self.system}]}

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "user":
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})

        google_data = {"contents": contents, "generationConfig": {}}

        if system_instruction:
            google_data["system_instruction"] = system_instruction

        if "temperature" in data:
            google_data["generationConfig"]["temperature"] = data["temperature"]

        if "max_tokens" in data:
            google_data["generationConfig"]["maxOutputTokens"] = data["max_tokens"]

        if "top_p" in data:
            google_data["generationConfig"]["topP"] = data["top_p"]

        return google_data


class GoogleRequest(LLMApiRequest):
    """Google-specific API request format."""

    contents: list[dict[str, Any]] | None = Field(
        None, description="Google content format"
    )
    generation_config: dict[str, Any] | None = Field(
        None, description="Generation configuration"
    )
    system_instruction: dict[str, Any] | None = Field(
        None, description="System instruction"
    )
    safety_settings: list[dict[str, Any]] | None = Field(
        None, description="Safety settings"
    )
    tool_config: dict[str, Any] | None = Field(None, description="Tool configuration")

    model_config = {
        "table_name": "google_requests",
        "description": "Google Gemini API request format"
    }

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI API format."""
        data = self.model_dump(exclude_none=True)

        # Convert Google contents to OpenAI messages
        contents = data.get("contents", [])
        messages = []

        # Add system instruction as system message
        if self.system_instruction:
            parts = self.system_instruction.get("parts", [])
            if parts:
                system_text = parts[0].get("text", "")
                messages.append({"role": "system", "content": system_text})

        # Convert contents to messages
        for content in contents:
            role = content.get("role", "user")
            parts = content.get("parts", [])

            if parts:
                text = parts[0].get("text", "")
                if role == "model":
                    messages.append({"role": "assistant", "content": text})
                else:
                    messages.append({"role": "user", "content": text})

        openai_data = {
            "model": data.get("model"),
            "messages": messages,
            "stream": data.get("stream", False),
        }

        # Convert generation config
        gen_config = data.get("generation_config", {})
        if gen_config.get("temperature") is not None:
            openai_data["temperature"] = gen_config["temperature"]
        if gen_config.get("maxOutputTokens") is not None:
            openai_data["max_tokens"] = gen_config["maxOutputTokens"]
        if gen_config.get("topP") is not None:
            openai_data["top_p"] = gen_config["topP"]

        return openai_data

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic API format."""
        data = self.model_dump(exclude_none=True)

        # Convert Google contents to Anthropic messages
        contents = data.get("contents", [])
        messages = []
        system_message = None

        # Extract system instruction
        if self.system_instruction:
            parts = self.system_instruction.get("parts", [])
            if parts:
                system_message = parts[0].get("text", "")

        # Convert contents to messages
        for content in contents:
            role = content.get("role", "user")
            parts = content.get("parts", [])

            if parts:
                text = parts[0].get("text", "")
                if role == "model":
                    messages.append({"role": "assistant", "content": text})
                else:
                    messages.append({"role": "user", "content": text})

        anthropic_data = {
            "model": data.get("model"),
            "messages": messages,
            "max_tokens": 4000,
            "stream": data.get("stream", False),
        }

        if system_message:
            anthropic_data["system"] = system_message

        # Convert generation config
        gen_config = data.get("generation_config", {})
        if gen_config.get("temperature") is not None:
            anthropic_data["temperature"] = gen_config["temperature"]
        if gen_config.get("topP") is not None:
            anthropic_data["top_p"] = gen_config["topP"]

        return anthropic_data

    def to_google_format(self) -> dict[str, Any]:
        """Convert to Google API format."""
        return self.model_dump(exclude_none=True)


# Streaming Delta Models
class StreamDelta(AbstractModel):
    """Base streaming delta for incremental responses."""

    delta_type: str = Field(..., description="Type of delta content")
    content: str | None = Field(None, description="Delta content")
    function_call: dict[str, Any] | None = Field(
        None, description="Function call delta"
    )
    tool_calls: list[dict[str, Any]] | None = Field(
        None, description="Tool calls delta"
    )

    model_config = {
        "description": "Base streaming response delta"
    }


class OpenAIStreamDelta(StreamDelta):
    """OpenAI streaming delta format."""

    id: str | None = Field(None, description="Response ID")
    object: str = Field("chat.completion.chunk", description="Object type")
    model: str | None = Field(None, description="Model used")
    choices: list[dict[str, Any]] = Field(
        default_factory=list, description="Choice deltas"
    )
    usage: dict[str, Any] | None = Field(None, description="Token usage")

    model_config = {
        "table_name": "openai_stream_deltas",
        "description": "OpenAI streaming response format"
    }


class AnthropicStreamDelta(StreamDelta):
    """Anthropic streaming delta format."""

    type: str = Field(..., description="Event type")
    index: int | None = Field(None, description="Message index")
    delta: dict[str, Any] | None = Field(None, description="Content delta")

    model_config = {
        "table_name": "anthropic_stream_deltas",
        "description": "Anthropic streaming response format"
    }


class GoogleStreamDelta(StreamDelta):
    """Google streaming delta format."""

    candidates: list[dict[str, Any]] | None = Field(
        None, description="Candidate deltas"
    )
    usage_metadata: dict[str, Any] | None = Field(None, description="Usage metadata")

    model_config = {
        "table_name": "google_stream_deltas",
        "description": "Google streaming response format"
    }


# Response Models
class LLMResponse(AbstractModel):
    """Base LLM response with common fields."""

    id: str = Field(..., description="Response ID")
    model: str = Field(..., description="Model used")
    content: str | None = Field(None, description="Response content")
    finish_reason: str | None = Field(None, description="Completion reason")
    usage: dict[str, Any] | None = Field(None, description="Token usage statistics")
    tool_calls: list[dict[str, Any]] | None = Field(None, description="Tool calls made")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Response timestamp"
    )

    model_config = {
        "description": "Base LLM response format"
    }


class OpenAIResponse(LLMResponse):
    """Complete OpenAI response format."""

    object: str = Field("chat.completion", description="Response object type")
    choices: list[dict[str, Any]] = Field(..., description="Response choices")
    system_fingerprint: str | None = Field(None, description="System fingerprint")

    model_config = {
        "table_name": "openai_responses",
        "description": "Complete OpenAI API response"
    }


class AnthropicResponse(LLMResponse):
    """Complete Anthropic response format."""

    type: str = Field("message", description="Response type")
    role: str = Field("assistant", description="Response role")
    stop_reason: str | None = Field(None, description="Stop reason")
    stop_sequence: str | None = Field(None, description="Stop sequence used")

    model_config = {
        "table_name": "anthropic_responses",
        "description": "Complete Anthropic API response"
    }


class GoogleResponse(LLMResponse):
    """Complete Google response format."""

    candidates: list[dict[str, Any]] = Field(..., description="Response candidates")
    prompt_feedback: dict[str, Any] | None = Field(None, description="Prompt feedback")
    usage_metadata: dict[str, Any] | None = Field(None, description="Usage metadata")

    model_config = {
        "table_name": "google_responses",
        "description": "Complete Google API response"
    }


class ApiCallingContext(BaseModel):
    """calling context object - all have defaults
    an agent session uses these things to control how to communicate with the user or the LLM Api
    """

    # Identity and tenant context
    tenant_id: str | None = Field(
        default=None, description="Tenant identifier for multi-tenant isolation"
    )

    session_id: str | None = Field(
        default=None,
        description="A goal orientated session id actually maps to thread_id in the database and not session.id",
    )

    chat_id: str | None = Field(
        default=None,
        description="The chat_id from OpenWebUI, if provided - usually used as session_id",
    )

    session_context: str | None = Field(
        default=None,
        description="For routing purposes, describe the session's objective",
    )

    session_type: str | None = Field(
        default=None,
        description="Type of session (chat, api, dreaming, analysis, batch) for filtering and context",
    )

    moment_id: str | None = Field(
        default=None,
        description="Optional reference to associated Moment entity ID for contextual linking",
    )

    prefer_json: bool | None = Field(
        default=False, description="If the json format is preferred in response"
    )
    response_model: str | None = Field(
        default=None, description="A Pydantic format model to use to respond"
    )
    username: str | None = Field(default=None, description="The session username")
    user_id: str | uuid.UUID | None = Field(
        default=None,
        description="UUID user id is more accurate if known but we try to resolve",
    )
    channel_context: str | None = Field(
        default=None,
        description="A channel id e.g. slack channel but more broadly any grouping",
    )
    channel_ts: str | None = Field(
        default=None, description="A channel conversation id e.g. slack timestamp (ts)"
    )

    prefers_streaming: bool | None = Field(
        default=False,
        description="Indicate if a streaming response is preferred with or without a callback",
    )

    is_hybrid_streaming: bool | None = Field(
        default=False,
        description="Hybrid Streaming calls functions internally but streams text content",
    )

    temperature: float | None = Field(default=0, description="The LLM temperature")
    max_tokens: int | None = Field(
        default=4000, description="Maximum tokens to generate in the response"
    )
    plan: str | None = Field(
        default=None,
        description="A specific plan/prompt to override default agent plan",
    )
    max_iterations: int | None = Field(
        default=MAX_AGENT_LOOPS,
        description="Agents iterated in a loop to call functions. Set the max number of iterations",
    )
    model: str | None = Field(
        default=settings.default_model, description="The LLM Model to use"
    )

    file_uris: list[str] | None = Field(
        description="files associated with the context", default_factory=list
    )

    headers: dict[str, str] | None = Field(
        default_factory=dict,
        description="Raw X- headers from the request for custom context handling",
    )

    messages: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional pre-built message history (e.g., with session recovery)",
    )

    def get_response_format(self):
        """"""
        if self.prefer_json:
            return {"type": "json_object"}


class CallingContext(ApiCallingContext):
    """add the non serializable callbacks"""

    streaming_callback: typing.Callable | None = Field(
        default=None,
        description="A callback to stream partial results e.g. print progress",
    )
    response_callback: typing.Callable | None = Field(
        default=None,
        description="A callback to send final response e.g a Slack Say method",
    )

    @staticmethod
    def simple_printer(d):
        print(d, end="")

    def in_streaming_mode(self, is_hybrid_streaming: bool = True, model: str = None):
        """convert context as is to streaming"""
        data = self.model_dump()
        data["prefers_streaming"] = True
        data["is_hybrid_streaming"] = is_hybrid_streaming
        if model:
            data["model"] = model
        return CallingContext(**data)

    @property
    def is_streaming(self):
        """the streaming mode is either of these cases"""
        return self.prefers_streaming or self.streaming_callback is not None

    @classmethod
    def with_model(cls, model_name: str):
        """
        construct the default model context but with different model
        """
        defaults = CallingContext().model_dump()
        if model_name:
            defaults["model"] = model_name
        return CallingContext(**defaults)

    @classmethod
    def from_headers(cls, headers: dict, **kwargs):
        """
        Construct CallingContext from HTTP headers.

        Extracts context information from standard P8FS headers and allows
        additional kwargs to override or supplement the context.

        Args:
            headers: Dictionary of HTTP headers (case-insensitive lookup)
            **kwargs: Additional context fields to set or override

        Returns:
            CallingContext instance populated from headers

        Example:
            >>> headers = {
            ...     "X-Username": "alice",
            ...     "X-User-ID": "user-123",
            ...     "X-Thread-ID": "conversation-456",
            ...     "X-Channel-ID": "C1234567890",
            ...     "X-Channel-Type": "slack"
            ... }
            >>> context = CallingContext.from_headers(headers, model="gpt-4")
        """

        # Helper function for case-insensitive header lookup
        def get_header(key: str) -> str | None:
            # Try exact match first
            if key in headers:
                return headers[key]
            # Try case-insensitive lookup
            for header_key, header_value in headers.items():
                if header_key.lower() == key.lower():
                    return header_value
            return None

        # Extract all X- headers for raw access
        x_headers = {}
        for header_key, header_value in headers.items():
            if header_key.lower().startswith("x-"):
                # Store with original casing
                x_headers[header_key] = header_value

        # Map headers to CallingContext fields
        context_data = {
            "username": get_header("X-Username"),
            "user_id": get_header("X-User-ID"),
            "session_id": get_header("X-Session-ID") or get_header("X-Thread-ID"),  # Session ID or Thread ID maps to session ID
            "chat_id": get_header("X-Chat-ID"),
            "channel_context": get_header("X-Channel-ID"),
            "channel_ts": get_header("X-Channel-TS"),
            "moment_id": get_header("X-Moment-Id"),  # Moment ID for contextual linking
            "headers": x_headers,  # Include all X- headers
        }

        # Remove None values (but keep empty headers dict)
        context_data = {k: v for k, v in context_data.items() if v is not None}

        # Override with any additional kwargs
        context_data.update(kwargs)

        return cls(**context_data)


class BatchCallingContext(CallingContext):
    """Batch processing context with GPT-5 optimizations."""

    # Batch settings
    batch_size: int = Field(100, description="Batch processing size")
    batch_timeout: int = Field(3600, description="Batch timeout seconds")
    batch_priority: str = Field("standard", description="Batch processing priority")
    save_job: bool = Field(
        True, description="Whether to save the batch job to database"
    )
    batch_id: str | None = Field(None, description="Batch processing identifier")

    # GPT-5 batch specific
    reasoning_effort_batch: str | None = Field(
        None, description="Batch reasoning effort"
    )
    verbosity_batch: int | None = Field(None, description="Batch verbosity level")
    max_completion_tokens_batch: int | None = Field(
        None, description="Batch max completion tokens"
    )

    model_config = {
        "table_name": "batch_calling_contexts",
        "description": "Batch processing context with GPT-5 support"
    }

    @classmethod
    def for_quick_batch(cls, model: str = "gpt-4") -> "BatchCallingContext":
        """Create context for quick batch processing."""
        return cls(
            model=model,
            batch_size=50,
            batch_timeout=1800,
            batch_priority="high",
            reasoning_effort_batch="quick",
        )

    @classmethod
    def for_comprehensive_batch(cls, model: str = "gpt-5") -> "BatchCallingContext":
        """Create context for comprehensive batch analysis."""
        return cls(
            model=model,
            batch_size=20,
            batch_timeout=7200,
            batch_priority="low",
            reasoning_effort_batch="comprehensive",
            verbosity_batch=3,
        )

    @classmethod
    def for_standard_batch(cls, model: str = "gpt-4") -> "BatchCallingContext":
        """Create context for standard batch processing."""
        return cls(
            model=model,
            batch_size=100,
            batch_timeout=3600,
            batch_priority="standard",
            reasoning_effort_batch="balanced",
        )


# Message Management
class MessageStack(AbstractModel):
    """Conversation message stack with history management."""

    messages: list[dict[str, Any]] = Field(
        default_factory=list, description="Message history"
    )
    max_messages: int = Field(50, description="Maximum messages to keep")
    system_message: str | None = Field(None, description="System message")
    context_window: int = Field(8192, description="Token context window")

    model_config = {
        "table_name": "message_stacks",
        "description": "Conversation message history management"
    }

    def build_message_stack(
        self, user_message: str, tools: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """Build complete message stack for API call."""
        # Implementation stub - should build proper message stack
        return self.messages

    def to_messages(self) -> list[dict[str, Any]]:
        """Convert to API message format."""
        # Implementation stub - should convert to standard message format
        return self.messages

    def get_last_user_message(self) -> dict[str, Any] | None:
        """Get the most recent user message."""
        # Implementation stub - should find last user message
        for message in reversed(self.messages):
            if message.get("role") == "user":
                return message
        return None

    def add_message(
        self,
        role: MessageRole,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ):
        """Add message to stack with automatic truncation."""
        # Implementation stub - should add message and manage stack size
        message = {"role": role.value, "content": content}
        if tool_calls:
            message["tool_calls"] = tool_calls
        self.messages.append(message)

        # Truncate if needed
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages :]


class BatchResponse(AbstractModel):
    """Response from batch processing operations."""

    model_config = {
        "name": "BatchResponse",
        "namespace": "llm",
        "description": "Response from batch processing operations",
    }

    # Batch identification
    batch_id: str = Field(..., description="OpenAI batch identifier")
    job_id: str = Field(..., description="Internal job identifier")

    # Status information
    status: Literal[
        "validating",
        "failed",
        "in_progress",
        "finalizing",
        "completed",
        "expired",
        "cancelled",
    ] = Field(..., description="Batch processing status")

    # Progress tracking
    request_counts: dict[str, int] = Field(
        default_factory=dict, description="Request count by status"
    )
    total_requests: int = Field(0, description="Total number of requests in batch")
    completed_requests: int = Field(0, description="Number of completed requests")

    # File references
    input_file_id: str | None = Field(None, description="OpenAI input file ID")
    output_file_id: str | None = Field(None, description="OpenAI output file ID")
    error_file_id: str | None = Field(None, description="OpenAI error file ID")

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.now, description="Batch creation time"
    )
    in_progress_at: datetime | None = Field(None, description="Processing start time")
    finalizing_at: datetime | None = Field(None, description="Finalizing start time")
    completed_at: datetime | None = Field(None, description="Completion time")
    expired_at: datetime | None = Field(None, description="Expiration time")
    cancelled_at: datetime | None = Field(None, description="Cancellation time")

    # Metadata and errors
    metadata: dict[str, Any] = Field(default_factory=dict, description="Batch metadata")
    errors: list[dict[str, Any]] = Field(
        default_factory=list, description="Processing errors"
    )


class JobStatusResponse(AbstractModel):
    """Unified job status response with OpenAI integration."""

    model_config = {
        "name": "JobStatusResponse",
        "namespace": "llm",
        "description": "Unified job status with OpenAI batch integration",
    }

    # Job identification
    job_id: str = Field(..., description="Internal job identifier")
    tenant_id: str = Field(..., description="Tenant identifier")

    # OpenAI integration
    openai_batch_id: str | None = Field(None, description="Associated OpenAI batch ID")
    openai_status: str | None = Field(None, description="OpenAI batch status")

    # Status and progress
    status: str = Field(..., description="Current job status")
    progress: float = Field(
        0.0, ge=0.0, le=1.0, description="Completion progress (0.0-1.0)"
    )

    # Results and files
    has_results: bool = Field(False, description="Whether results are available")
    results_file_id: str | None = Field(None, description="Results file identifier")
    error_file_id: str | None = Field(None, description="Error file identifier")

    # Timestamps
    created_at: datetime = Field(..., description="Job creation time")
    updated_at: datetime = Field(..., description="Last update time")
    completed_at: datetime | None = Field(None, description="Completion time")

    # Statistics
    total_items: int = Field(0, description="Total items to process")
    completed_items: int = Field(0, description="Completed items")
    failed_items: int = Field(0, description="Failed items")

    # Error information
    error_message: str | None = Field(None, description="Error message if failed")
    error_details: dict[str, Any] = Field(
        default_factory=dict, description="Detailed error information"
    )


class StreamingResponse(AbstractModel):
    """Individual chunk in streaming response."""

    model_config = {
        "name": "StreamingResponse",
        "namespace": "llm",
        "description": "Individual chunk in streaming LLM response",
    }

    # Chunk identification
    chunk_id: str = Field(..., description="Unique chunk identifier")
    sequence: int = Field(..., description="Chunk sequence number")

    # Content
    content: str | None = Field(None, description="Text content of chunk")
    delta: dict[str, Any] | None = Field(None, description="Delta changes in chunk")

    # Tool calls
    tool_calls: list[dict[str, Any]] | None = Field(
        None, description="Tool calls in chunk"
    )
    function_call: dict[str, Any] | None = Field(
        None, description="Legacy function call"
    )

    # Status
    finish_reason: str | None = Field(None, description="Reason for completion")
    is_final: bool = Field(False, description="Whether this is the final chunk")

    # Metadata
    model: str | None = Field(None, description="Model that generated chunk")
    usage: dict[str, Any] | None = Field(None, description="Token usage information")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Chunk timestamp"
    )
