"""Unit tests for protocol adapters and format conversions."""


import pytest
from p8fs.services.llm.models import (
    AnthropicRequest,
    GoogleRequest,
    OpenAIRequest,
)


class TestOpenAIRequestAdapter:
    """Test OpenAI request format and conversions."""

    def test_openai_request_creation(self):
        """Test basic OpenAI request creation."""
        messages = [{"role": "user", "content": "Hello"}]
        
        request = OpenAIRequest(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=100
        )
        
        assert request.model == "gpt-4"
        assert request.messages == messages
        assert request.temperature == 0.7
        assert request.max_tokens == 100

    def test_openai_request_with_tools(self):
        """Test OpenAI request with function tools."""
        messages = [{"role": "user", "content": "Get weather"}]
        tools = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather info"
            }
        }]
        
        request = OpenAIRequest(
            model="gpt-4",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        assert request.tools == tools
        assert request.tool_choice == "auto"

    def test_openai_request_gpt5_params(self):
        """Test OpenAI request with GPT-5 specific parameters."""
        messages = [{"role": "user", "content": "Analyze this"}]
        
        request = OpenAIRequest(
            model="gpt-5",
            messages=messages,
            max_completion_tokens=2000,
            reasoning_effort="high",
            verbosity=2
        )
        
        assert request.max_completion_tokens == 2000
        assert request.reasoning_effort == "high"
        assert request.verbosity == 2

    def test_to_openai_format(self):
        """Test conversion to OpenAI format (should be identity)."""
        messages = [{"role": "user", "content": "Hello"}]
        
        request = OpenAIRequest(
            model="gpt-4",
            messages=messages,
            temperature=0.7
        )
        
        openai_format = request.to_openai_format()
        
        assert openai_format["model"] == "gpt-4"
        assert openai_format["messages"] == messages
        assert openai_format["temperature"] == 0.7

    def test_to_anthropic_format(self):
        """Test conversion from OpenAI to Anthropic format."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
        
        request = OpenAIRequest(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=100
        )
        
        anthropic_format = request.to_anthropic_format()
        
        # System message should be extracted
        assert anthropic_format["system"] == "You are helpful"
        
        # Messages should exclude system message
        assert len(anthropic_format["messages"]) == 2
        assert anthropic_format["messages"][0]["role"] == "user"
        assert anthropic_format["messages"][1]["role"] == "assistant"
        
        # Parameters should be converted
        assert anthropic_format["max_tokens"] == 100
        assert anthropic_format["temperature"] == 0.7

    def test_to_google_format(self):
        """Test conversion from OpenAI to Google format."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
        
        request = OpenAIRequest(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=100
        )
        
        google_format = request.to_google_format()
        
        # Should have system instruction
        assert "system_instruction" in google_format
        assert google_format["system_instruction"]["parts"][0]["text"] == "You are helpful"
        
        # Contents should be converted properly
        assert len(google_format["contents"]) == 2
        assert google_format["contents"][0]["role"] == "user"
        assert google_format["contents"][1]["role"] == "model"  # assistant -> model
        
        # Generation config
        assert "generationConfig" in google_format
        assert google_format["generationConfig"]["temperature"] == 0.7
        assert google_format["generationConfig"]["maxOutputTokens"] == 100


class TestAnthropicRequestAdapter:
    """Test Anthropic request format and conversions."""

    def test_anthropic_request_creation(self):
        """Test basic Anthropic request creation."""
        messages = [{"role": "user", "content": "Hello"}]
        
        request = AnthropicRequest(
            model="claude-3-5-sonnet-20241022",
            messages=messages,
            max_tokens=100,
            system="You are helpful"
        )
        
        assert request.model == "claude-3-5-sonnet-20241022"
        assert request.messages == messages
        assert request.max_tokens == 100
        assert request.system == "You are helpful"

    def test_anthropic_request_with_tools(self):
        """Test Anthropic request with function tools."""
        messages = [{"role": "user", "content": "Search documents"}]
        tools = [{
            "type": "function",
            "function": {
                "name": "search_docs",
                "description": "Search documents"
            }
        }]
        
        request = AnthropicRequest(
            model="claude-3-5-sonnet-20241022",
            messages=messages,
            tools=tools,
            max_tokens=200
        )
        
        assert request.tools == tools

    def test_to_anthropic_format(self):
        """Test conversion to Anthropic format (should be identity)."""
        messages = [{"role": "user", "content": "Hello"}]
        
        request = AnthropicRequest(
            model="claude-3-5-sonnet-20241022",
            messages=messages,
            max_tokens=100,
            system="Be helpful"
        )
        
        anthropic_format = request.to_anthropic_format()
        
        assert anthropic_format["model"] == "claude-3-5-sonnet-20241022"
        assert anthropic_format["messages"] == messages
        assert anthropic_format["max_tokens"] == 100
        assert anthropic_format["system"] == "Be helpful"

    def test_to_openai_format(self):
        """Test conversion from Anthropic to OpenAI format."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
        
        request = AnthropicRequest(
            model="claude-3-5-sonnet-20241022",
            messages=messages,
            max_tokens=100,
            system="You are helpful",
            temperature=0.8
        )
        
        openai_format = request.to_openai_format()
        
        # System message should be prepended to messages
        assert len(openai_format["messages"]) == 3
        assert openai_format["messages"][0]["role"] == "system"
        assert openai_format["messages"][0]["content"] == "You are helpful"
        
        # Other messages should be preserved
        assert openai_format["messages"][1]["role"] == "user"
        assert openai_format["messages"][2]["role"] == "assistant"
        
        # Parameters should be converted
        assert openai_format["temperature"] == 0.8
        assert openai_format["max_tokens"] == 100

    def test_to_google_format(self):
        """Test conversion from Anthropic to Google format."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
        
        request = AnthropicRequest(
            model="claude-3-5-sonnet-20241022",
            messages=messages,
            max_tokens=100,
            system="You are helpful"
        )
        
        google_format = request.to_google_format()
        
        # System instruction should be set
        assert google_format["system_instruction"]["parts"][0]["text"] == "You are helpful"
        
        # Contents should be converted
        assert len(google_format["contents"]) == 2
        assert google_format["contents"][0]["role"] == "user"
        assert google_format["contents"][1]["role"] == "model"


class TestGoogleRequestAdapter:
    """Test Google request format and conversions."""

    def test_google_request_creation(self):
        """Test basic Google request creation."""
        contents = [{
            "role": "user",
            "parts": [{"text": "Hello"}]
        }]
        
        request = GoogleRequest(
            model="gemini-1.5-flash",
            messages=[],  # Required but not used in Google format
            contents=contents,
            generation_config={"temperature": 0.7}
        )
        
        assert request.model == "gemini-1.5-flash"
        assert request.contents == contents

    def test_google_request_with_system_instruction(self):
        """Test Google request with system instruction."""
        contents = [{"role": "user", "parts": [{"text": "Hello"}]}]
        system_instruction = {"parts": [{"text": "You are helpful"}]}
        
        request = GoogleRequest(
            model="gemini-1.5-flash",
            messages=[],
            contents=contents,
            system_instruction=system_instruction
        )
        
        assert request.system_instruction == system_instruction

    def test_google_request_with_tools(self):
        """Test Google request with function declarations."""
        contents = [{"role": "user", "parts": [{"text": "Calculate area"}]}]
        tool_config = {
            "function_calling_config": {
                "mode": "AUTO"
            }
        }
        
        request = GoogleRequest(
            model="gemini-1.5-flash",
            messages=[],
            contents=contents,
            tool_config=tool_config
        )
        
        assert request.tool_config == tool_config

    def test_to_google_format(self):
        """Test conversion to Google format (should be identity)."""
        contents = [{"role": "user", "parts": [{"text": "Hello"}]}]
        gen_config = {"temperature": 0.7, "maxOutputTokens": 100}
        
        request = GoogleRequest(
            model="gemini-1.5-flash",
            messages=[],
            contents=contents,
            generation_config=gen_config
        )
        
        google_format = request.to_google_format()
        
        assert google_format["contents"] == contents
        assert google_format["generation_config"] == gen_config

    def test_to_openai_format(self):
        """Test conversion from Google to OpenAI format."""
        contents = [
            {"role": "user", "parts": [{"text": "Hello"}]},
            {"role": "model", "parts": [{"text": "Hi there"}]}
        ]
        system_instruction = {"parts": [{"text": "You are helpful"}]}
        gen_config = {"temperature": 0.7, "maxOutputTokens": 100}
        
        request = GoogleRequest(
            model="gemini-1.5-flash",
            messages=[],
            contents=contents,
            system_instruction=system_instruction,
            generation_config=gen_config
        )
        
        openai_format = request.to_openai_format()
        
        # Should have system message first
        assert len(openai_format["messages"]) == 3
        assert openai_format["messages"][0]["role"] == "system"
        assert openai_format["messages"][0]["content"] == "You are helpful"
        
        # Content conversion
        assert openai_format["messages"][1]["role"] == "user"
        assert openai_format["messages"][1]["content"] == "Hello"
        assert openai_format["messages"][2]["role"] == "assistant"  # model -> assistant
        assert openai_format["messages"][2]["content"] == "Hi there"
        
        # Parameter conversion
        assert openai_format["temperature"] == 0.7
        assert openai_format["max_tokens"] == 100

    def test_to_anthropic_format(self):
        """Test conversion from Google to Anthropic format."""
        contents = [
            {"role": "user", "parts": [{"text": "Hello"}]},
            {"role": "model", "parts": [{"text": "Hi there"}]}
        ]
        system_instruction = {"parts": [{"text": "You are helpful"}]}
        
        request = GoogleRequest(
            model="gemini-1.5-flash",
            messages=[],
            contents=contents,
            system_instruction=system_instruction
        )
        
        anthropic_format = request.to_anthropic_format()
        
        # System message should be extracted
        assert anthropic_format["system"] == "You are helpful"
        
        # Messages should be converted
        assert len(anthropic_format["messages"]) == 2
        assert anthropic_format["messages"][0]["role"] == "user"
        assert anthropic_format["messages"][1]["role"] == "assistant"


class TestFormatConversions:
    """Test complex format conversions and edge cases."""

    def test_empty_system_message_handling(self):
        """Test handling of empty or None system messages."""
        messages = [{"role": "user", "content": "Hello"}]
        
        # OpenAI with no system message
        openai_request = OpenAIRequest(model="gpt-4", messages=messages)
        anthropic_format = openai_request.to_anthropic_format()
        
        assert "system" not in anthropic_format or anthropic_format.get("system") is None
        assert len(anthropic_format["messages"]) == 1

    def test_multiple_system_messages(self):
        """Test handling of multiple system messages."""
        messages = [
            {"role": "system", "content": "First instruction"},
            {"role": "system", "content": "Second instruction"},
            {"role": "user", "content": "Hello"}
        ]
        
        request = OpenAIRequest(model="gpt-4", messages=messages)
        anthropic_format = request.to_anthropic_format()
        
        # Should take first system message
        assert anthropic_format["system"] == "First instruction"
        
        # Should filter out all system messages
        assert len(anthropic_format["messages"]) == 1
        assert anthropic_format["messages"][0]["role"] == "user"

    def test_tool_calls_preservation(self):
        """Test that tool calls are preserved in conversions."""
        messages = [
            {"role": "user", "content": "Get weather"},
            {
                "role": "assistant", 
                "content": None,
                "tool_calls": [{
                    "id": "call_123",
                    "function": {"name": "get_weather", "arguments": "{}"}
                }]
            }
        ]
        
        request = OpenAIRequest(model="gpt-4", messages=messages)
        converted = request.to_openai_format()
        
        # Tool calls should be preserved
        assert "tool_calls" in converted["messages"][1]
        assert converted["messages"][1]["tool_calls"][0]["id"] == "call_123"

    def test_parameter_edge_cases(self):
        """Test edge cases in parameter conversion."""
        request = OpenAIRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.0,  # Edge case: zero temperature
            max_tokens=1,     # Edge case: minimum tokens
            top_p=1.0         # Edge case: maximum top_p
        )
        
        anthropic_format = request.to_anthropic_format()
        
        assert anthropic_format["temperature"] == 0.0
        assert anthropic_format["max_tokens"] == 1
        assert anthropic_format["top_p"] == 1.0

    def test_nested_content_structures(self):
        """Test handling of complex nested content structures."""
        # Google format with complex parts
        contents = [{
            "role": "user",
            "parts": [
                {"text": "First part"},
                {"text": "Second part"}
            ]
        }]
        
        request = GoogleRequest(
            model="gemini-1.5-flash",
            messages=[],
            contents=contents
        )
        
        openai_format = request.to_openai_format()
        
        # Should combine multiple parts
        assert openai_format["messages"][0]["content"] == "First part"  # Takes first part

    @pytest.mark.parametrize("provider,expected_scheme", [
        ("openai", "openai"),
        ("anthropic", "anthropic"), 
        ("google", "google")
    ])
    def test_provider_scheme_consistency(self, provider, expected_scheme):
        """Test that provider schemes are consistent."""
        if provider == "openai":
            request = OpenAIRequest(model="gpt-4", messages=[])
        elif provider == "anthropic":
            request = AnthropicRequest(model="claude-3-5-sonnet-20241022", messages=[])
        elif provider == "google":
            request = GoogleRequest(model="gemini-1.5-flash", messages=[])
        
        # All requests should have consistent conversion methods
        assert hasattr(request, "to_openai_format")
        assert hasattr(request, "to_anthropic_format")
        assert hasattr(request, "to_google_format")


class TestRequestValidation:
    """Test request validation and error handling."""

    def test_openai_request_validation(self):
        """Test OpenAI request field validation."""
        with pytest.raises(ValueError):
            # Missing required fields
            OpenAIRequest()

    def test_anthropic_request_validation(self):
        """Test Anthropic request field validation.""" 
        # Should require model and messages at minimum
        with pytest.raises(ValueError):
            AnthropicRequest()

    def test_google_request_validation(self):
        """Test Google request field validation."""
        # Should require model and messages at minimum
        with pytest.raises(ValueError):
            GoogleRequest()

    def test_message_role_validation(self):
        """Test message role validation."""
        valid_roles = ["system", "user", "assistant", "tool"]
        
        for role in valid_roles:
            # Should not raise exception
            request = OpenAIRequest(
                model="gpt-4",
                messages=[{"role": role, "content": "test"}]
            )
            assert len(request.messages) == 1

    def test_tool_choice_validation(self):
        """Test tool choice validation."""
        valid_choices = ["none", "auto", "required"]
        
        for choice in valid_choices:
            request = OpenAIRequest(
                model="gpt-4",
                messages=[{"role": "user", "content": "test"}],
                tool_choice=choice
            )
            assert request.tool_choice == choice