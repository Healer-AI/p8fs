"""
Base proxy implementation for LLM services.

This module provides the core functionality for proxying requests to various LLM providers.

Key features:
- Unified streaming and non-streaming support
- Provider-agnostic interface
- Request/response format conversion
- Proper error handling and retries
- Full observability integration with token usage tracking

For raw API access without the proxy features, use LanguageModel directly:

    # Raw API invocation examples:
    from p8fs.services.llm.language_model import LanguageModel

    # Basic usage - loads configuration from KV store or defaults
    model = LanguageModel("gpt-4o-mini", tenant_id="my-tenant")

    # Direct API call with streaming
    messages = [{"role": "user", "content": "Hello!"}]
    response = await model.invoke_raw(messages, stream=True, temperature=0.7)
    print(response["full_response"]["content"])

    # Direct API call without streaming
    response = await model.invoke_raw(messages, stream=False, max_tokens=100)
    print(response)

    # Works with any provider - OpenAI, Anthropic, Google
    claude = LanguageModel("claude-3-5-sonnet-20241022", tenant_id="my-tenant")
    response = await claude.invoke_raw(messages, stream=False)

    # Raw access bypasses BaseProxy features like:
    # - Observability/metrics (unless you add them manually)
    # - Response format standardization
    # - Error handling and retries
    # - Function calling utilities
"""

import json
import time
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

from p8fs.models.llm import (
    AnthropicRequest,
    AnthropicResponse,
    AnthropicStreamDelta,
    GoogleRequest,
    GoogleResponse,
    GoogleStreamDelta,
    LLMApiRequest,
    OpenAIRequest,
    OpenAIResponse,
    OpenAIStreamDelta,
)
from p8fs.services.llm.language_model import LanguageModel
from p8fs.services.llm.utils import (
    build_anthropic_response,
    build_generic_response,
    build_google_response,
    build_openai_response,
    extract_content_from_chunks,
    extract_response_content,
)


class BaseProxy:
    """
    Base proxy for LLM API calls.

    This class provides the core functionality for making requests to LLM providers
    and handling responses. It serves as the foundation for both simple model proxying
    and more complex scenarios like memory-enhanced conversations.

    Use BaseProxy for:
    - Full-featured LLM interactions with observability
    - Standardized response formats across providers
    - Function calling and tool integration
    - Error handling and retry logic
    - Token usage tracking and cost estimation

    For raw API access, use LanguageModel.invoke_raw() instead:

    Example comparison:

    # BaseProxy - Full featured with observability
    proxy = BaseProxy()
    async for chunk in proxy.stream_completion(messages, "gpt-4o-mini"):
        print(chunk)  # Standardized format with metrics

    # LanguageModel - Raw API access
    model = LanguageModel("gpt-4o-mini")
    response = await model.invoke_raw(messages, stream=True)
    print(response["chunks"])  # Raw provider format
    """

    def __init__(self, *args, **kwargs):
        """Initialize the base proxy."""
        super().__init__(*args, **kwargs)
        self._session: aiohttp.ClientSession | None = None
        logger.debug("Initialized BaseProxy")

    async def _ensure_session(self):
        """Ensure aiohttp session is initialized."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    def _create_request(
        self, messages: list[dict[str, Any]], model_config: dict[str, Any], **kwargs
    ) -> LLMApiRequest:
        """
        Create an appropriate request object based on the provider scheme.
        
        Note: We always start with OpenAI format as the canonical internal format,
        then convert to the target provider format during request preparation.

        Args:
            messages: List of message dictionaries (should be in OpenAI format)
            model_config: Model configuration including scheme
            **kwargs: Additional parameters for the request

        Returns:
            An OpenAI format request object (conversion happens during preparation)
        """
        scheme = model_config.get("scheme", "openai")
        model_name = model_config.get("model", "gpt-4")

        # Handle GPT-5 specific parameters
        is_gpt5_model = model_name.startswith(("gpt-5", "o1-"))
        
        # Merge kwargs with defaults
        request_params = {
            "model": model_name,
            "messages": messages,  # Always OpenAI format messages
            "temperature": kwargs.get("temperature", 0.7),
            "top_p": kwargs.get("top_p", 1.0),
            "stream": kwargs.get("stream", True),
            "tools": kwargs.get("tools"),
        }
        
        # GPT-5 models require max_completion_tokens instead of max_tokens
        if is_gpt5_model:
            if "max_completion_tokens" in kwargs:
                request_params["max_completion_tokens"] = kwargs["max_completion_tokens"]
            elif "max_tokens" in kwargs:
                request_params["max_completion_tokens"] = kwargs["max_tokens"]
            else:
                request_params["max_completion_tokens"] = 1024
            
            # Add GPT-5 specific parameters if provided
            if "reasoning_effort" in kwargs:
                request_params["reasoning_effort"] = kwargs["reasoning_effort"]
            if "verbosity" in kwargs:
                request_params["verbosity"] = kwargs["verbosity"]
        else:
            # Standard models use max_tokens
            request_params["max_tokens"] = kwargs.get("max_tokens", 1024)

        # Always create OpenAI request as canonical format
        # Conversion to target format happens in prepare_request_data()
        return OpenAIRequest(**request_params)

    async def stream_completion(
        self, messages: list[dict[str, Any]], model_name: str, **kwargs
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream a completion from the specified model.

        Args:
            messages: List of message dictionaries
            model_name: Name of the model to use
            **kwargs: Additional parameters for the request

        Yields:
            Streaming response chunks
        """
        # Load model configuration
        tenant_id = kwargs.get("tenant_id", "default")
        language_model = LanguageModel(model_name, tenant_id)
        model_config = language_model.params

        if not model_config:
            raise ValueError(f"No configuration found for model: {model_name}")

        # Create the request
        request = self._create_request(messages, model_config, **kwargs)

        # Get the source scheme
        source_scheme = model_config.get("scheme", "openai")

        # Stream the response
        async for chunk in self._stream_from_provider(
            request, model_config, source_scheme
        ):
            yield chunk

    async def _stream_from_provider(
        self, request: LLMApiRequest, model_config: dict[str, Any], source_scheme: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream response from the LLM provider.

        Args:
            request: The request object
            model_config: Model configuration
            source_scheme: The provider scheme

        Yields:
            Streaming response chunks
        """
        await self._ensure_session()

        # Prepare the request (validation happens in prepare_*_request methods)
        prepared = request.prepare_request_data(model_config, source_scheme)
        api_url = prepared["api_url"]
        headers = prepared["headers"]
        api_data = prepared["api_data"]

        # Make the streaming request
        try:
            async with self._session.post(
                api_url,
                headers=headers,
                json=api_data,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as response:
                # Get error details before raising
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"API error from {source_scheme}: {response.status} - {error_text}")
                    response.raise_for_status()

                # Parse streaming response based on provider
                async for chunk in self._parse_stream(response, source_scheme):
                    yield chunk

        except aiohttp.ClientError as e:
            logger.error(f"Error streaming from {source_scheme}: {e}")
            raise

    async def _parse_stream(
        self, response: aiohttp.ClientResponse, source_scheme: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Parse streaming response based on provider format.

        Args:
            response: The aiohttp response object
            source_scheme: The provider scheme

        Yields:
            Parsed streaming chunks
        """
        async for line in response.content:
            if not line:
                continue

            line = line.decode("utf-8").strip()
            if not line or line == "data: [DONE]":
                continue

            # Handle different SSE formats
            data_line = None
            if line.startswith("data: "):
                data_line = line[6:]  # Remove "data: " prefix
            elif source_scheme == "anthropic" and not line.startswith("event: "):
                # Anthropic sometimes sends raw JSON without "data: " prefix
                data_line = line
            elif line.startswith("event: "):
                # Skip event type lines for Anthropic SSE format
                continue
            else:
                # Skip other SSE metadata lines
                continue

            if not data_line:
                continue

            try:
                chunk_data = json.loads(data_line)

                # Parse based on provider format and convert to OpenAI format
                if source_scheme == "openai":
                    delta = OpenAIStreamDelta(**chunk_data)
                    yield delta.model_dump()
                elif source_scheme == "anthropic":
                    # Convert Anthropic to OpenAI format for unified processing downstream
                    openai_chunk = self._convert_anthropic_chunk_to_openai(chunk_data)
                    if openai_chunk:
                        yield openai_chunk
                elif source_scheme == "google":
                    delta = GoogleStreamDelta(**chunk_data)
                    yield delta.model_dump()
                else:
                    # Return raw chunk for unknown formats
                    yield chunk_data

            except json.JSONDecodeError:
                logger.warning(f"Failed to parse streaming chunk: {data_line}")
                continue
            except Exception as e:
                logger.error(f"Error parsing {source_scheme} stream: {e}")
                continue

    def _convert_anthropic_chunk_to_openai(self, anthropic_chunk: dict) -> dict | None:
        """
        Convert Anthropic streaming chunk to OpenAI format.

        Handles:
        - text content deltas
        - tool use blocks
        - stop signals
        """
        chunk_type = anthropic_chunk.get("type")

        # Convert text content
        if chunk_type == "content_block_delta":
            delta = anthropic_chunk.get("delta", {})
            if delta.get("type") == "text_delta":
                return {
                    "choices": [{
                        "index": 0,
                        "delta": {"content": delta.get("text", "")},
                        "finish_reason": None
                    }]
                }

        # Convert tool use start
        elif chunk_type == "content_block_start":
            content_block = anthropic_chunk.get("content_block", {})
            if content_block.get("type") == "tool_use":
                tool_id = content_block.get("id")
                tool_name = content_block.get("name")
                # Return tool call initialization
                return {
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "tool_calls": [{
                                "index": 0,
                                "id": tool_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": ""
                                }
                            }]
                        },
                        "finish_reason": None
                    }]
                }

        # Convert tool input streaming
        elif chunk_type == "content_block_delta":
            delta = anthropic_chunk.get("delta", {})
            if delta.get("type") == "input_json_delta":
                partial_json = delta.get("partial_json", "")
                return {
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "tool_calls": [{
                                "index": 0,
                                "function": {
                                    "arguments": partial_json
                                }
                            }]
                        },
                        "finish_reason": None
                    }]
                }

        # Convert stop signals
        elif chunk_type == "message_delta":
            delta = anthropic_chunk.get("delta", {})
            stop_reason = delta.get("stop_reason")
            if stop_reason:
                # Map Anthropic stop reasons to OpenAI
                finish_reason = {
                    "end_turn": "stop",
                    "tool_use": "tool_calls",
                    "max_tokens": "length"
                }.get(stop_reason, stop_reason)

                return {
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": finish_reason
                    }]
                }

        # Skip other chunk types (message_start, content_block_stop, etc.)
        return None

    async def complete(
        self, messages: list[dict[str, Any]], model_name: str, **kwargs
    ) -> dict[str, Any]:
        """
        Get a non-streaming completion from the specified model.

        Args:
            messages: List of message dictionaries
            model_name: Name of the model to use
            **kwargs: Additional parameters for the request

        Returns:
            Complete response dictionary
        """
        # Force non-streaming
        kwargs["stream"] = False

        # Load model configuration
        tenant_id = kwargs.get("tenant_id", "default")
        language_model = LanguageModel(model_name, tenant_id)
        model_config = language_model.params

        if not model_config:
            raise ValueError(f"No configuration found for model: {model_name}")

        # Create the request
        request = self._create_request(messages, model_config, **kwargs)

        # Get the source scheme
        source_scheme = model_config.get("scheme", "openai")

        # Make the request
        return await self._request_from_provider(request, model_config, source_scheme)

    async def _request_from_provider(
        self, request: LLMApiRequest, model_config: dict[str, Any], source_scheme: str
    ) -> dict[str, Any]:
        """
        Make a non-streaming request to the LLM provider.

        Args:
            request: The request object
            model_config: Model configuration
            source_scheme: The provider scheme

        Returns:
            Complete response dictionary
        """
        await self._ensure_session()

        # Prepare the request (validation happens in prepare_*_request methods)
        prepared = request.prepare_request_data(model_config, source_scheme)
        api_url = prepared["api_url"]
        headers = prepared["headers"]
        api_data = prepared["api_data"]

        start_time = time.time()

        # Make the request
        try:
            async with self._session.post(
                api_url,
                headers=headers,
                json=api_data,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as response:
                response.raise_for_status()
                response_data = await response.json()

                # Parse response based on provider
                parsed_response = None
                if source_scheme == "openai":
                    parsed_response = OpenAIResponse(**response_data).model_dump()
                elif source_scheme == "anthropic":
                    parsed_response = AnthropicResponse(**response_data).model_dump()
                elif source_scheme == "google":
                    parsed_response = GoogleResponse(**response_data).model_dump()
                else:
                    # Return raw response for unknown formats
                    parsed_response = response_data

                return parsed_response

        except aiohttp.ClientError as e:
            logger.error(f"Error requesting from {source_scheme}: {e}")
            raise

    def _collect_streaming_response(
        self, chunks: list[dict[str, Any]], source_scheme: str
    ) -> dict[str, Any]:
        """
        Collect streaming chunks into a complete response.

        Args:
            chunks: List of streaming chunks
            source_scheme: The provider scheme

        Returns:
            Complete response dictionary
        """
        if not chunks:
            return {}

        # Extract content from chunks
        full_content, function_calls = extract_content_from_chunks(
            chunks, source_scheme
        )

        # Get model name from first chunk
        model = chunks[0].get("model", "unknown") if chunks else "unknown"

        # Build response based on provider format
        if source_scheme == "openai":
            return build_openai_response(full_content, function_calls, model)
        elif source_scheme == "anthropic":
            return build_anthropic_response(full_content, model)
        elif source_scheme == "google":
            return build_google_response(full_content)
        else:
            return build_generic_response(
                full_content, function_calls, model, source_scheme
            )

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = True,
        **kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream a chat completion from the specified model.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Name of the model to use
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            **kwargs: Additional model-specific parameters

        Yields:
            Streaming response chunks if stream=True

        Returns:
            Complete response if stream=False
        """
        params = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs,
        }

        if stream:
            async for chunk in self.stream_completion(messages, model, **params):
                yield chunk
        else:
            response = await self.complete(messages, model, **params)
            yield response

    async def function_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str = "gpt-4",
        temperature: float = 0.0,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Make a function call using the specified model.

        Args:
            messages: List of message dictionaries
            tools: List of tool/function definitions
            model: Name of the model to use
            temperature: Sampling temperature (usually 0 for function calls)
            **kwargs: Additional parameters

        Returns:
            Complete response with function call
        """
        params = {
            "temperature": temperature,
            "tools": tools,
            "stream": False,  # Function calls typically don't stream
            **kwargs,
        }

        return await self.complete(messages, model, **params)

    async def quick_prompt(
        self,
        prompt: str,
        model: str = "gpt-4",
        system_prompt: str | None = None,
        **kwargs,
    ) -> str:
        """
        Convenience method for simple prompt-response interactions.

        Args:
            prompt: The user prompt
            model: Name of the model to use
            system_prompt: Optional system message
            **kwargs: Additional parameters

        Returns:
            The model's response as a string
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.complete(messages, model, stream=False, **kwargs)
        return extract_response_content(response)

    @classmethod
    async def create(cls) -> "BaseProxy":
        """
        Factory method to create a BaseProxy instance.

        Returns:
            Initialized BaseProxy instance
        """
        return cls()