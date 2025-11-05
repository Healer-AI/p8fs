"""Unit tests for LanguageModel class."""

import os
from unittest.mock import patch

import pytest
from p8fs.services.llm import LanguageModel


class TestLanguageModelConfiguration:
    """Test LanguageModel configuration loading and management."""
    
    def test_init_with_registered_model(self):
        """Test initialization with registered model configuration."""
        # Register a test model
        test_config = {
            "scheme": "openai",
            "model": "gpt-4-test",
            "completions_uri": "https://api.openai.com/v1/chat/completions",
            "token_env_key": "OPENAI_API_KEY"
        }
        LanguageModel.register_model("test-model", test_config)
        
        model = LanguageModel("test-model", "test-tenant")
        
        assert model.model_name == "test-model"
        assert model.tenant_id == "test-tenant"
        assert model.params["scheme"] == "openai"
        assert model.params["model"] == "gpt-4-test"

    def test_default_config_loading(self):
        """Test loading default configurations for known models."""
        model = LanguageModel("gpt-4", "default")
        
        assert model.params is not None
        assert model.params["scheme"] == "openai"
        assert model.params["model"] == "gpt-4"
        assert model.params["completions_uri"] == "https://api.openai.com/v1/chat/completions"
        assert model.params["token_env_key"] == "OPENAI_API_KEY"

    def test_anthropic_config_inference(self):
        """Test configuration inference for Anthropic models."""
        model = LanguageModel("claude-3-5-sonnet-20241022")
        
        assert model.params["scheme"] == "anthropic"
        assert model.params["completions_uri"] == "https://api.anthropic.com/v1/messages"
        assert model.params["token_env_key"] == "ANTHROPIC_API_KEY"
        assert model.params["anthropic-version"] == "2023-06-01"

    def test_google_config_inference(self):
        """Test configuration inference for Google models."""
        model = LanguageModel("gemini-1.5-flash")
        
        assert model.params["scheme"] == "google"
        assert model.params["token_env_key"] == "GOOGLE_API_KEY"
        assert "generativelanguage.googleapis.com" in model.params["completions_uri"]

    def test_unknown_model_default_to_openai(self):
        """Test that unknown models default to OpenAI-compatible format."""
        model = LanguageModel("unknown-model-xyz")
        
        assert model.params["scheme"] == "openai"
        assert model.params["model"] == "unknown-model-xyz"
        assert model.params["token_env_key"] == "OPENAI_API_KEY"

    @patch.dict(os.environ, {"TEST_API_KEY": "test-key-12345"})
    def test_api_token_loading(self):
        """Test API token loading from environment variables."""
        test_config = {
            "scheme": "openai",
            "model": "gpt-4",
            "completions_uri": "https://api.test.com/v1/chat/completions",
            "token_env_key": "TEST_API_KEY"
        }
        LanguageModel.register_model("token-test-model", test_config)
        
        model = LanguageModel("token-test-model")
        
        assert model.params["token"] == "test-key-12345"

    def test_model_info(self):
        """Test get_model_info method."""
        model = LanguageModel("gpt-4")
        
        info = asyncio.run(model.get_model_info())
        
        assert info["name"] == "gpt-4"
        assert info["tenant_id"] == "default"
        assert "capabilities" in info
        assert "max_context_length" in info
        assert info["supports_tools"] is True
        assert info["supports_streaming"] is True

    def test_message_validation_valid(self):
        """Test message validation with valid messages."""
        model = LanguageModel("gpt-4")
        
        valid_messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        
        result = asyncio.run(model.validate_messages(valid_messages))
        assert result is True

    def test_message_validation_invalid(self):
        """Test message validation with invalid messages."""
        model = LanguageModel("gpt-4")
        
        # Empty messages
        assert asyncio.run(model.validate_messages([])) is False
        
        # Missing role
        invalid_messages = [{"content": "Hello"}]
        assert asyncio.run(model.validate_messages(invalid_messages)) is False
        
        # Invalid role
        invalid_messages = [{"role": "invalid", "content": "Hello"}]
        assert asyncio.run(model.validate_messages(invalid_messages)) is False
        
        # Missing content and tool_calls
        invalid_messages = [{"role": "user"}]
        assert asyncio.run(model.validate_messages(invalid_messages)) is False


class TestRequestPayloadCreation:
    """Test request payload creation for different model types."""

    def test_basic_payload_creation(self):
        """Test basic request payload creation."""
        model = LanguageModel("gpt-4")
        messages = [{"role": "user", "content": "Hello"}]
        
        payload = model.create_request_payload(messages, temperature=0.7, max_tokens=100)
        
        assert payload["model"] == "gpt-4"
        assert payload["messages"] == messages
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 100

    def test_gpt5_payload_creation(self):
        """Test GPT-5 specific payload creation."""
        model = LanguageModel("gpt-5")
        messages = [{"role": "user", "content": "Analyze this"}]
        
        payload = model.create_request_payload(
            messages,
            max_completion_tokens=2000,
            reasoning_effort="high",
            verbosity="detailed"
        )
        
        assert payload["model"] == "gpt-5"
        assert payload["max_completion_tokens"] == 2000
        assert payload["reasoning_effort"] == "high"
        assert payload["verbosity"] == "detailed"
        assert "temperature" not in payload  # GPT-5 doesn't support custom temperature

    def test_tools_payload_creation(self):
        """Test payload creation with tools."""
        model = LanguageModel("gpt-4")
        messages = [{"role": "user", "content": "Get weather"}]
        tools = [{"type": "function", "function": {"name": "get_weather"}}]
        
        payload = model.create_request_payload(messages, tools=tools)
        
        assert payload["tools"] == tools
        assert payload["tool_choice"] == "auto"

    def test_max_tokens_fallback(self):
        """Test max_tokens fallback for GPT-5."""
        model = LanguageModel("gpt-5")
        messages = [{"role": "user", "content": "Hello"}]
        
        # Test max_tokens conversion to max_completion_tokens
        payload = model.create_request_payload(messages, max_tokens=1500)
        
        assert payload["max_completion_tokens"] == 1500
        assert "max_tokens" not in payload


class TestModelCapabilities:
    """Test model capability detection."""

    def test_openai_capabilities(self):
        """Test OpenAI model capabilities."""
        model = LanguageModel("gpt-4")
        capabilities = model._get_model_capabilities()
        
        expected_capabilities = ["chat", "completion", "tools", "streaming"]
        for capability in expected_capabilities:
            assert capability in capabilities

    def test_whisper_capabilities(self):
        """Test Whisper model capabilities."""
        model = LanguageModel("whisper-1")
        capabilities = model._get_model_capabilities()
        
        assert "transcription" in capabilities

    def test_context_length_detection(self):
        """Test context length detection for different models."""
        # Test GPT-4
        gpt4_model = LanguageModel("gpt-4")
        assert gpt4_model._get_context_length() == 128000
        
        # Test GPT-5
        gpt5_model = LanguageModel("gpt-5")
        assert gpt5_model._get_context_length() == 200000
        
        # Test Claude
        claude_model = LanguageModel("claude-3-5-sonnet-20241022")
        assert claude_model._get_context_length() == 200000
        
        # Test unknown model
        unknown_model = LanguageModel("unknown-model")
        assert unknown_model._get_context_length() == 8192

    def test_tools_support_detection(self):
        """Test tools support detection."""
        # Models that support tools
        gpt4_model = LanguageModel("gpt-4")
        assert gpt4_model._supports_tools() is True
        
        claude_model = LanguageModel("claude-3-5-sonnet-20241022")
        assert claude_model._supports_tools() is True
        
        gemini_model = LanguageModel("gemini-1.5-flash")
        assert gemini_model._supports_tools() is True


class TestAsyncContextManager:
    """Test async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager_entry_exit(self):
        """Test async context manager entry and exit."""
        async with LanguageModel("gpt-4") as model:
            assert isinstance(model, LanguageModel)
            assert model.model_name == "gpt-4"
        
        # After exit, client should be closed if it was created
        # This is tested indirectly as the client is only created when needed


# Import asyncio for async test support
import asyncio