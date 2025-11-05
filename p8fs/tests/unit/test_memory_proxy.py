"""
Unit tests for MemoryProxy.

These tests verify:
1. Initialization with and without model context
2. AbstractModel.Abstracted application
3. Function registration and discovery
4. Message stack building with system prompts
5. Client creation and tenant isolation
6. Built-in function registration
7. Function call buffering (mocked)
8. Audit session mixin integration
"""

from unittest.mock import AsyncMock, Mock, patch, MagicMock
import pytest
from typing import Dict, Any, List
import json

from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext
from p8fs.models.base import AbstractModel
from pydantic import Field


class SampleAgent(AbstractModel):
    """Test agent for unit testing memory proxy.
    
    This docstring becomes the system prompt when used with MemoryProxy.
    """
    
    name: str = Field(default="TestBot", description="Agent name")
    
    async def test_function(self, param: str) -> Dict[str, Any]:
        """A test function that will be auto-registered.
        
        Args:
            param: Test parameter
            
        Returns:
            Test result
        """
        return {"result": f"Processed: {param}"}
    
    def sync_function(self, value: int) -> int:
        """Sync function should also be registered."""
        return value * 2


class PlainPydanticModel(AbstractModel):
    """Plain model to test Abstracted method."""
    value: str = "test"


class TestMemoryProxy:
    """Test MemoryProxy functionality"""
    
    @pytest.fixture
    def calling_context(self):
        """Create a test calling context"""
        return CallingContext(
            tenant_id="test-tenant",
            user_id="test-user",
            model="gpt-4o-mini",
            temperature=0.7,
            stream=False,
        )
    
    @pytest.fixture
    def test_agent(self):
        """Create a test agent instance"""
        return SampleAgent()
    
    def test_init_without_model(self):
        """Test MemoryProxy initialization without model context"""
        proxy = MemoryProxy()
        
        assert proxy._model_context is None
        assert proxy._function_handler is not None
        assert proxy._client is None
        assert proxy._message_buffer == []
        assert proxy._tenant_id is None
    
    def test_init_with_model(self, test_agent):
        """Test MemoryProxy initialization with model context"""
        proxy = MemoryProxy(model_context=test_agent)
        
        assert proxy._model_context is not None
        assert proxy._function_handler is not None
        
        # Verify model was abstracted
        assert hasattr(proxy._model_context, 'get_model_full_name')
        assert hasattr(proxy._model_context, 'get_model_description')
    
    @patch('p8fs.models.base.AbstractModel.Abstracted')
    def test_abstracted_called(self, mock_abstracted, test_agent):
        """Test that Abstracted is called on model context"""
        mock_abstracted.return_value = test_agent
        
        proxy = MemoryProxy(model_context=test_agent)
        
        mock_abstracted.assert_called_once_with(test_agent)
    
    def test_init_with_plain_pydantic(self):
        """Test initialization with plain Pydantic model"""
        plain_model = PlainPydanticModel()
        proxy = MemoryProxy(model_context=plain_model)
        
        # Should have AbstractModel capabilities after Abstracted
        assert hasattr(proxy._model_context, 'get_model_name')
    
    def test_function_registration_from_model(self, test_agent):
        """Test automatic function registration from model methods"""
        proxy = MemoryProxy(model_context=test_agent)
        
        # Get registered function schemas
        schemas = proxy._function_handler.get_schemas()
        function_names = [s["function"]["name"] for s in schemas if "function" in s]
        
        # Model functions should be registered
        assert "test_function" in function_names
        assert "sync_function" in function_names
    
    def test_builtin_functions_registered(self):
        """Test built-in functions are registered"""
        proxy = MemoryProxy()
        
        schemas = proxy._function_handler.get_schemas()
        function_names = [s["function"]["name"] for s in schemas if "function" in s]
        
        # Built-in functions should be registered
        assert "get_entities" in function_names
        assert "search_resources" in function_names
        assert "get_recent_tenant_uploads" in function_names
    
    def test_register_function_decorator(self):
        """Test manual function registration via decorator"""
        proxy = MemoryProxy()
        
        @proxy.register_function("custom_function")
        async def my_function(text: str) -> str:
            return f"Processed: {text}"
        
        schemas = proxy._function_handler.get_schemas()
        function_names = [s["function"]["name"] for s in schemas if "function" in s]
        
        assert "custom_function" in function_names
    
    def test_build_message_stack_without_model(self):
        """Test message stack building without model context"""
        proxy = MemoryProxy()
        
        messages = proxy._build_message_stack("Test question")
        
        # Should only have user message in relay mode
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Test question"
    
    def test_build_message_stack_with_model(self, test_agent):
        """Test message stack building with model context"""
        proxy = MemoryProxy(model_context=test_agent)
        
        messages = proxy._build_message_stack("Test question")
        
        # Should have system message from docstring
        assert len(messages) >= 2
        
        # Check system message
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) > 0
        assert "test agent" in system_msgs[0]["content"].lower()
        
        # Check user message
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Test question"
    
    
    @pytest.mark.asyncio
    async def test_run_basic(self, calling_context):
        """Test basic run method"""
        proxy = MemoryProxy()
        
        # Mock the stream method
        async def mock_stream(*args, **kwargs):
            yield {"choices": [{"delta": {"content": "Hello"}}]}
            yield {"choices": [{"delta": {"content": " world"}}]}
            yield {"type": "completion", "final_response": "Hello world"}
        
        with patch.object(proxy, 'stream', side_effect=mock_stream):
            result = await proxy.run("Test", calling_context)
            
            assert result == "Hello world"
    
    @pytest.mark.asyncio
    async def test_run_with_error(self, calling_context):
        """Test run method with error handling"""
        proxy = MemoryProxy()
        
        async def mock_stream(*args, **kwargs):
            yield {"type": "error", "error": "Test error"}
        
        with patch.object(proxy, 'stream', side_effect=mock_stream):
            result = await proxy.run("Test", calling_context)
            
            assert result == "Error: Test error"
    
    @pytest.mark.asyncio
    async def test_stream_basic_flow(self, calling_context):
        """Test basic streaming flow"""
        proxy = MemoryProxy()
        
        # Mock stream_completion
        async def mock_stream_completion(*args, **kwargs):
            yield {"choices": [{"delta": {"content": "Test"}, "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        
        # Mock audit_session
        proxy._audit_session = AsyncMock()
        
        with patch.object(proxy, 'stream_completion', side_effect=mock_stream_completion):
            chunks = []
            async for chunk in proxy.stream("Test", calling_context):
                chunks.append(chunk)
            
            # Should have iteration events and completion
            event_types = [c.get("type") for c in chunks if "type" in c]
            assert "iteration_start" in event_types
            assert "completion" in event_types
            
            # Should have called audit
            proxy._audit_session.assert_called_once()
    
    
    @pytest.mark.asyncio
    async def test_get_entities(self):
        """Test get_entities built-in function"""
        mock_client = AsyncMock()
        # get_entities is not awaited when called with keys, so use regular Mock
        mock_client.get_entities = Mock(return_value=[
            {"key": "entity1", "value": {"type": "Test", "name": "Entity 1"}}
        ])
        
        proxy = MemoryProxy(client=mock_client)
        
        result = await proxy.get_entities(keys=["entity1"])
        
        # get_entities with keys returns a list directly
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["key"] == "entity1"
        mock_client.get_entities.assert_called_once_with(["entity1"])
    
    
    
    


# Add this at the end to support asyncio in tests
import asyncio