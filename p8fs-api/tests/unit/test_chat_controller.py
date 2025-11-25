"""Unit tests for chat controller."""

import os
import sys
from unittest.mock import AsyncMock, Mock, patch

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from p8fs_api.models.responses import ChatMessage, ChatRequest, ChatResponse


class TestChatController:
    """Test the ChatController without external dependencies."""
    
    def test_controller_import(self):
        """Test that the controller can be imported and instantiated."""
        from p8fs_api.controllers import ChatController
        
        controller = ChatController()
        assert controller is not None
    
    async def test_create_chat_completion_basic(self):
        """Test basic chat completion functionality."""
        from p8fs_api.controllers import ChatController
        
        # Setup mocks
        mock_proxy_instance = AsyncMock()
        mock_proxy_instance.run.return_value = "Hello! How can I help you?"
        mock_memory_proxy.return_value = mock_proxy_instance
        
        mock_context.return_value = Mock(model="gpt-4o-mini")
        
        # Create controller and mock user
        controller = ChatController()
        mock_user = Mock()
        mock_user.id = "test-user"
        mock_user.tenant_id = "test-tenant"
        
        # Create test request
        messages = [ChatMessage(role="user", content="Hello")]
        request = ChatRequest(messages=messages, model="gpt-4o-mini", stream=False)
        
        # Test the completion
        response = await controller.create_chat_completion(request, mock_user)
        
        # Verify response structure
        assert isinstance(response, ChatResponse)
        assert response.model == "gpt-4o-mini"
        assert len(response.choices) == 1
        assert response.choices[0]["message"]["role"] == "assistant"
        assert response.choices[0]["message"]["content"] == "Hello! How can I help you?"
        assert response.choices[0]["finish_reason"] == "stop"
        assert "usage" in response.model_dump()
        
        # Verify MemoryProxy was called correctly
        mock_proxy_instance.run.assert_called_once()
    
    def test_extract_question(self):
        """Test question extraction from messages."""
        # This will require importing with mocks
        pass
    
    def test_build_calling_context(self):
        """Test CallingContext building."""
        # This will require importing with mocks
        pass
    
    def test_model_request_validation(self):
        """Test that request models work correctly."""
        # Test ChatMessage model
        message = ChatMessage(role="user", content="Test message")
        assert message.role == "user"
        assert message.content == "Test message"
        assert message.name is None
        
        # Test ChatRequest model
        request = ChatRequest(
            messages=[message],
            model="gpt-4o-mini",
            max_tokens=100,
            temperature=0.8,
            stream=True
        )
        
        assert len(request.messages) == 1
        assert request.messages[0].role == "user"
        assert request.model == "gpt-4o-mini"
        assert request.max_tokens == 100
        assert request.temperature == 0.8
        assert request.stream is True
    
    def test_chat_response_model(self):
        """Test ChatResponse model structure."""
        response = ChatResponse(
            id="test-id",
            created=1234567890,
            model="gpt-4o-mini",
            choices=[{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Test response"
                },
                "finish_reason": "stop"
            }],
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15
            }
        )
        
        assert response.id == "test-id"
        assert response.object == "chat.completion"
        assert response.model == "gpt-4o-mini"
        assert len(response.choices) == 1
        assert response.choices[0]["message"]["content"] == "Test response"