"""Language model service for LLM API interactions."""

import json
import os
import uuid
from typing import Any, ClassVar

import aiohttp

from .models import BatchCallingContext
from .openai_client import OpenAIRequestsClient


class LanguageModel:
    """Core language model service for LLM API interactions."""

    # Class-level model registry
    _registered_models: ClassVar[dict[str, dict[str, Any]]] = {}

    def __init__(self, model_name: str, tenant_id: str = "default"):
        """Initialize language model instance.

        Args:
            model_name: Name/identifier of the model to use
            tenant_id: Tenant identifier for multi-tenancy
        """
        self.model_name = model_name
        self.tenant_id = tenant_id
        self._params: dict[str, Any] | None = None
        self._client: OpenAIRequestsClient | None = None

        # Load model configuration
        self._load_model_config()

    @property
    def params(self) -> dict[str, Any]:
        """Get current model parameters."""
        return self._params.copy()

    def update_params(self, **kwargs):
        """Update model parameters.

        Args:
            **kwargs: Parameter updates to apply
        """
        self._params.update(kwargs)

    @classmethod
    def register_model(cls, name: str, config: dict[str, Any]):
        """Register a model configuration.

        Args:
            name: Model name/identifier
            config: Model configuration dictionary
        """
        cls._registered_models[name] = config

    async def invoke_raw(
        self, messages: list[dict[str, Any]], stream: bool = False, **kwargs
    ) -> dict[str, Any]:
        """Invoke model with raw messages.

        Args:
            messages: List of message dictionaries in OpenAI format
            stream: Whether to stream the response
            **kwargs: Additional parameters for the API call

        Returns:
            Raw API response dictionary
        """
        from p8fs.models.llm import OpenAIRequest

        if not self._params:
            raise ValueError(f"No configuration available for model: {self.model_name}")

        # Get the model configuration
        scheme = self._params.get("scheme", "openai")
        model_name = self._params.get("model", self.model_name)

        # Handle GPT-5 specific parameter conversion
        processed_kwargs = kwargs.copy()
        is_gpt5 = model_name.startswith("gpt-5") or model_name == "gpt-5"

        if is_gpt5:
            if (
                "max_tokens" in processed_kwargs
                and "max_completion_tokens" not in processed_kwargs
            ):
                processed_kwargs["max_completion_tokens"] = processed_kwargs.pop(
                    "max_tokens"
                )
            if "temperature" in processed_kwargs:
                processed_kwargs.pop("temperature")

        # Build request using OpenAI format as canonical internal format
        # Messages are assumed to be in OpenAI format (role/content)
        request = OpenAIRequest(
            model=model_name,
            messages=messages,
            stream=stream,
            **processed_kwargs,
        )

        # Use the request model's prepare_request_data method
        # This handles format conversion internally based on the target scheme
        prepared = request.prepare_request_data(self._params, scheme)

        api_url = prepared["api_url"]
        headers = prepared["headers"]
        api_data = prepared["api_data"]

        # Make the API call
        async with aiohttp.ClientSession() as session:
            if stream:
                return await self._stream_raw_response(
                    session, api_url, headers, api_data, scheme
                )
            else:
                return await self._complete_raw_response(
                    session, api_url, headers, api_data, scheme
                )


    async def process_batch(
        self,
        message_stacks: list[list[dict[str, Any]]],
        context: BatchCallingContext,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Process multiple message stacks in batch.

        Args:
            message_stacks: List of message stack lists
            context: Batch calling context
            tools: Optional tools/functions for batch processing

        Returns:
            Batch processing results

        """
        import json
        import tempfile


        if not self._params or not self._params.get("token"):
            raise ValueError(f"No API key configured for model {self.model_name}")

        # Extract parameters from context
        batch_id = (
            getattr(context, "custom_id_prefix", "p8fs") + f"_{uuid.uuid4().hex[:8]}"
        )
        temperature = context.temperature

        # Get GPT-5 parameters from context
        is_gpt5 = self.model_name.startswith("gpt-5") or self.model_name == "gpt-5"
        max_tokens_field = "max_completion_tokens" if is_gpt5 else "max_tokens"
        max_tokens_value = getattr(context, "max_completion_tokens", None) or getattr(
            context, "max_tokens", 4000
        )

        # Prepare batch requests
        batch_requests = []
        for i, messages in enumerate(message_stacks):
            request_body = self.create_request_payload(
                messages=messages,
                temperature=temperature,
                max_tokens=(
                    max_tokens_value if max_tokens_field == "max_tokens" else None
                ),
                max_completion_tokens=(
                    max_tokens_value
                    if max_tokens_field == "max_completion_tokens"
                    else None
                ),
                reasoning_effort=getattr(context, "reasoning_effort", None),
                verbosity=getattr(context, "verbosity", None),
                tools=tools,
            )

            batch_request = {
                "custom_id": f"{batch_id}_{i}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": request_body,
            }
            batch_requests.append(batch_request)

        # Create temporary JSONL file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for request in batch_requests:
                f.write(json.dumps(request) + "\n")
            temp_file_path = f.name

        try:
            # Get client
            client = self._get_client()

            # Upload batch file
            batch_file = await client.upload_file(temp_file_path, purpose="batch")

            # Submit batch job
            batch_job = await client.create_batch(
                input_file_id=batch_file.get("id"),
                endpoint="/v1/chat/completions",
                completion_window="24h",
                metadata={
                    "tenant_id": self.tenant_id,
                    "batch_id": batch_id,
                    "model": self.model_name,
                    "questions_count": str(len(message_stacks)),
                },
            )

            return {
                "openai_batch_id": batch_job.get("id"),
                "openai_file_id": batch_file.get("id"),
                "status": batch_job.get("status"),
                "created_at": batch_job.get("created_at"),
                "requests_count": len(message_stacks),
                "model": self.model_name,
                "batch_id": batch_id,
            }

        finally:
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def create_request_payload(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        max_completion_tokens: int | None = None,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Create request payload for LLM API.

        Args:
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate (legacy)
            max_completion_tokens: Maximum completion tokens (GPT-5 style)
            reasoning_effort: Reasoning effort level for advanced models
            verbosity: Response verbosity level
            tools: Available tools/functions
            **kwargs: Additional parameters

        Returns:
            Request payload dictionary
        """
        payload = {"model": self.model_name, "messages": messages}

        # Add temperature (ignored for some models like GPT-5)
        if reasoning_effort is None:  # Only add temperature if not using reasoning
            payload["temperature"] = temperature

        # Handle token limits (prefer max_completion_tokens for newer models)
        is_gpt5 = self.model_name.startswith("gpt-5") or self.model_name == "gpt-5"

        if max_completion_tokens is not None:
            payload["max_completion_tokens"] = max_completion_tokens
        elif max_tokens is not None:
            if is_gpt5:
                # Convert max_tokens to max_completion_tokens for GPT-5
                payload["max_completion_tokens"] = max_tokens
            else:
                payload["max_tokens"] = max_tokens

        # GPT-5 specific parameters
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        if verbosity is not None:
            payload["verbosity"] = verbosity

        # Add tools if provided
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Add any additional parameters
        payload.update(kwargs)

        return payload

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.close()

    def _get_client(self) -> OpenAIRequestsClient:
        """Get or create OpenAI client instance.

        Returns:
            OpenAI requests client
        """
        if self._client is None:
            if not self._params or not self._params.get("token"):
                raise ValueError(f"No API key configured for model {self.model_name}")

            api_key = self._params["token"]
            base_url = self._params.get(
                "completions_uri", "https://api.openai.com/v1/chat/completions"
            )
            # Convert completions URL to base URL
            base_url = base_url.replace("/chat/completions", "")

            self._client = OpenAIRequestsClient(api_key=api_key, base_url=base_url)
        return self._client

    async def get_model_info(self) -> dict[str, Any]:
        """Get information about the current model.

        Returns:
            Model information dictionary

        """
        return {
            "name": self.model_name,
            "tenant_id": self.tenant_id,
            "parameters": self.params,
            "capabilities": self._get_model_capabilities(),
            "max_context_length": self._get_context_length(),
            "supports_tools": self._supports_tools(),
            "supports_streaming": True,
        }

    async def validate_messages(self, messages: list[dict[str, Any]]) -> bool:
        """Validate message format and content.

        Args:
            messages: List of message dictionaries to validate

        Returns:
            True if messages are valid

        """
        return self._validate_message_format(messages)

    def _load_model_config(self):
        """Load model configuration from multiple sources."""
        # Try defaults first, then registered models, then inference
        try:
            self._params = self._get_default_config()
            if self._params:
                self._add_api_token()
                return
        except Exception:
            pass

        # Try registered models
        if self.model_name in self._registered_models:
            self._params = self._registered_models[self.model_name].copy()
            self._add_api_token()
            return

        # Try inference from model name
        try:
            self._params = self._infer_config_from_name()
            self._add_api_token()
        except Exception as e:
            raise ValueError(
                f"Could not load configuration for model: {self.model_name}"
            ) from e

    # TODO: register these in the database but also the codebase sohuld have SAMPLE_MODELS that we use by default and merge in
    def _get_default_config(self) -> dict[str, Any] | None:
        """Get default configuration for known models."""
        default_configs = {
            "gpt-4": {
                "scheme": "openai",
                "model": "gpt-4",
                "completions_uri": "https://api.openai.com/v1/chat/completions",
                "token_env_key": "OPENAI_API_KEY",
            },
            "gpt-4.1": {
                "scheme": "openai",
                "model": "gpt-4.1",
                "completions_uri": "https://api.openai.com/v1/chat/completions",
                "token_env_key": "OPENAI_API_KEY",
            },
            "gpt-4o": {
                "scheme": "openai",
                "model": "gpt-4o",
                "completions_uri": "https://api.openai.com/v1/chat/completions",
                "token_env_key": "OPENAI_API_KEY",
            },
            "gpt-4o-mini": {
                "scheme": "openai",
                "model": "gpt-4o-mini",
                "completions_uri": "https://api.openai.com/v1/chat/completions",
                "token_env_key": "OPENAI_API_KEY",
            },
            "gpt-5": {
                "scheme": "openai",
                "model": "gpt-5",
                "completions_uri": "https://api.openai.com/v1/chat/completions",
                "token_env_key": "OPENAI_API_KEY",
            },
            "claude-3-5-sonnet-20241022": {
                "scheme": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "completions_uri": "https://api.anthropic.com/v1/messages",
                "token_env_key": "ANTHROPIC_API_KEY",
                "anthropic-version": "2023-06-01",
            },
            "claude-sonnet-4-5": {
                "scheme": "anthropic",
                "model": "claude-sonnet-4-5",
                "completions_uri": "https://api.anthropic.com/v1/messages",
                "token_env_key": "ANTHROPIC_API_KEY",
                "anthropic-version": "2023-06-01",
            },
            "claude-opus-4-1": {
                "scheme": "anthropic",
                "model": "claude-opus-4-1",
                "completions_uri": "https://api.anthropic.com/v1/messages",
                "token_env_key": "ANTHROPIC_API_KEY",
                "anthropic-version": "2023-06-01",
            },
            "gemini-1.5-flash": {
                "scheme": "google",
                "model": "gemini-1.5-flash",
                "completions_uri": "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
                "token_env_key": "GOOGLE_API_KEY",
            },
        }
        return default_configs.get(self.model_name)

    def _infer_config_from_name(self) -> dict[str, Any]:
        """Infer configuration from model name.

        Takes configuration from an existing configured model and applies
        the requested model name. This allows any claude-* or gpt-* model
        to work without explicit configuration.
        """
        model_name = self.model_name.lower()

        if "gpt" in model_name or "chatgpt" in model_name:
            # Use OpenAI configuration template
            return {
                "scheme": "openai",
                "model": self.model_name,
                "completions_uri": "https://api.openai.com/v1/chat/completions",
                "token_env_key": "OPENAI_API_KEY",
            }
        elif "claude" in model_name:
            # Use Claude/Anthropic configuration template
            return {
                "scheme": "anthropic",
                "model": self.model_name,
                "completions_uri": "https://api.anthropic.com/v1/messages",
                "token_env_key": "ANTHROPIC_API_KEY",
                "anthropic-version": "2023-06-01",
            }
        elif "gemini" in model_name:
            # Use Google/Gemini configuration template
            return {
                "scheme": "google",
                "model": self.model_name,
                "completions_uri": f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent",
                "token_env_key": "GOOGLE_API_KEY",
            }
        else:
            # Default to OpenAI-compatible
            return {
                "scheme": "openai",
                "model": self.model_name,
                "completions_uri": "https://api.openai.com/v1/chat/completions",
                "token_env_key": "OPENAI_API_KEY",
            }

    def _add_api_token(self):
        """Add API token from central configuration."""
        if not self._params:
            return

        token_env_key = self._params.get("token_env_key")
        if token_env_key:
            try:
                from p8fs_cluster.config import config
                # Map environment variable names to config attributes
                api_key_map = {
                    "OPENAI_API_KEY": config.openai_api_key,
                    "ANTHROPIC_API_KEY": config.anthropic_api_key,
                    "GOOGLE_API_KEY": config.google_api_key
                }
                token = api_key_map.get(token_env_key, "")
                if token:
                    self._params["token"] = token
                else:
                    # Fallback to direct environment variable lookup
                    token = os.getenv(token_env_key)
                    if token:
                        self._params["token"] = token
            except ImportError:
                # Fallback to direct environment variable lookup
                token = os.getenv(token_env_key)
                if token:
                    self._params["token"] = token

    async def _complete_raw_response(
        self,
        session: aiohttp.ClientSession,
        api_url: str,
        headers: dict[str, str],
        api_data: dict[str, Any],
        scheme: str,
    ) -> dict[str, Any]:
        """Make a complete (non-streaming) raw API call."""
        async with session.post(
            api_url,
            headers=headers,
            json=api_data,
            timeout=aiohttp.ClientTimeout(total=300),
        ) as response:
            if response.status >= 400:
                error_text = await response.text()
                from p8fs_cluster.logging import get_logger
                logger = get_logger(__name__)
                logger.error(f"API error from {scheme}: {response.status} - {error_text}")

            response.raise_for_status()
            return await response.json()

    async def _stream_raw_response(
        self,
        session: aiohttp.ClientSession,
        api_url: str,
        headers: dict[str, str],
        api_data: dict[str, Any],
        scheme: str,
    ) -> dict[str, Any]:
        """Make a streaming raw API call and collect all chunks."""
        chunks = []

        async with session.post(
            api_url,
            headers=headers,
            json=api_data,
            timeout=aiohttp.ClientTimeout(total=300),
        ) as response:
            response.raise_for_status()

            async for line in response.content:
                if not line:
                    continue

                line = line.decode("utf-8").strip()
                if not line or line == "data: [DONE]":
                    continue

                if line.startswith("data: "):
                    line = line[6:]  # Remove "data: " prefix

                try:
                    chunk_data = json.loads(line)
                    chunks.append(chunk_data)
                except json.JSONDecodeError:
                    continue

        return {"chunks": chunks, "full_response": self._combine_chunks(chunks, scheme)}

    def _combine_chunks(
        self, chunks: list[dict[str, Any]], scheme: str
    ) -> dict[str, Any]:
        """Combine streaming chunks into a complete response."""
        if not chunks:
            return {}

        combined_content = ""
        for chunk in chunks:
            if scheme == "openai":
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        combined_content += content
            elif scheme == "anthropic":
                delta = chunk.get("delta", {})
                text = delta.get("text", "")
                if text:
                    combined_content += text
            elif scheme == "google":
                candidates = chunk.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        text = parts[0].get("text", "")
                        if text:
                            combined_content += text

        return {
            "content": combined_content,
            "chunks_count": len(chunks),
            "model": self.model_name,
        }

    def _get_model_capabilities(self) -> list[str]:
        """Get model capabilities based on configuration."""
        capabilities = ["chat", "completion"]

        scheme = self._params.get("scheme", "openai") if self._params else "openai"

        if scheme == "openai":
            capabilities.extend(["tools", "streaming"])
            if "whisper" in self.model_name.lower():
                capabilities.append("transcription")
        elif scheme == "anthropic" or scheme == "google":
            capabilities.extend(["tools", "streaming"])

        return capabilities

    # TODO push this into the LanguageModelApi type
    def _get_context_length(self) -> int:
        """Get model context length."""
        model_name = self.model_name.lower()

        if "gpt-4" in model_name:
            return 128000
        elif "gpt-5" in model_name or "claude" in model_name:
            return 200000
        elif "gemini" in model_name:
            return 1000000
        else:
            return 8192  # Default

    def _supports_tools(self) -> bool:
        """Check if model supports function calling."""
        scheme = self._params.get("scheme", "openai") if self._params else "openai"
        model_name = self.model_name.lower()

        if scheme == "openai" and ("gpt-4" in model_name or "gpt-3.5" in model_name) or scheme == "anthropic" and "claude-3" in model_name or scheme == "google" and "gemini" in model_name:
            return True

        return False

    def _validate_message_format(self, messages: list[dict[str, Any]]) -> bool:
        """Validate message format and content."""
        if not messages:
            return False

        valid_roles = {"system", "user", "assistant", "tool"}

        for message in messages:
            if not isinstance(message, dict):
                return False

            if "role" not in message:
                return False

            if message["role"] not in valid_roles:
                return False

            # Check for content or tool_calls
            if "content" not in message and "tool_calls" not in message:
                return False

        return True



    async def batch_process(
        self, batch_requests: list[dict[str, Any]], **kwargs
    ) -> list[dict[str, Any]]:
        """Process multiple requests using batch API if available."""
        if not self._supports_batch_processing():
            # Fall back to individual requests
            results = []
            for request in batch_requests:
                try:
                    result = await self.invoke_raw(
                        request.get("messages", []), **kwargs
                    )
                    results.append(result)
                except Exception as e:
                    results.append({"error": str(e)})
            return results

        # OpenAI batch processing
        if self._params.get("scheme") == "openai":
            return await self._process_openai_batch(batch_requests, **kwargs)

        # For other providers, fall back to individual requests
        results = []
        for request in batch_requests:
            try:
                result = await self.invoke_raw(request.get("messages", []), **kwargs)
                results.append(result)
            except Exception as e:
                results.append({"error": str(e)})
        return results

    def _supports_batch_processing(self) -> bool:
        """Check if model supports batch processing."""
        return self._params.get("scheme") == "openai"

    async def _process_openai_batch(
        self, batch_requests: list[dict[str, Any]], **kwargs
    ) -> list[dict[str, Any]]:
        """Process batch requests using OpenAI batch API."""
        try:
            # TODO - remove this, we always use REST only
            # import openai

            client = openai.AsyncOpenAI(api_key=self._get_api_key())

            # Create batch file content
            batch_data = []
            for i, request in enumerate(batch_requests):
                batch_item = {
                    "custom_id": f"request-{i}",
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": self.model_name,
                        "messages": request.get("messages", []),
                        **kwargs,
                    },
                }
                batch_data.append(batch_item)

            jsonl_content = "\n".join(json.dumps(item) for item in batch_data)

            # Create batch file
            batch_file = await client.files.create(
                file=jsonl_content.encode(), purpose="batch"
            )

            # Create batch job
            batch_job = await client.batches.create(
                input_file_id=batch_file.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
            )

            # For now, return the batch job info
            # In practice, you'd want to poll for completion
            return [{"batch_id": batch_job.id, "status": "submitted"}]

        except Exception:
            # Fall back to individual requests
            results = []
            for request in batch_requests:
                try:
                    result = await self.invoke_raw(
                        request.get("messages", []), **kwargs
                    )
                    results.append(result)
                except Exception as e:
                    results.append({"error": str(e)})
            return results
