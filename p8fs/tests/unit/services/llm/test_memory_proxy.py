"""Unit tests for MemoryProxy class - focused on deterministic protocol testing."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from p8fs.services.llm import BatchCallingContext, CallingContext, MemoryProxy
from tests.sample_data.functions.sample_functions import (
    async_function,
    error_function,
    simple_function,
)


class TestMemoryProxyInitialization:
    """Test MemoryProxy initialization and configuration."""

    def test_init_without_model_context(self):
        """Test initialization without model context (relay mode)."""
        proxy = MemoryProxy()
        
        assert proxy.model_context is None
        assert proxy.client is None
        assert isinstance(proxy.registered_functions, dict)

    def test_builtin_functions_registered(self):
        """Test that built-in functions are registered correctly."""
        proxy = MemoryProxy()
        
        expected_functions = [
            "get_entities",
            "search_resources", 
            "get_recent_tenant_uploads"
        ]
        
        for func_name in expected_functions:
            assert func_name in proxy.registered_functions
            assert callable(proxy.registered_functions[func_name])


class TestFunctionRegistration:
    """Test function registration and schema generation."""

    def test_register_function_decorator(self):
        """Test function registration via decorator."""
        proxy = MemoryProxy()
        
        @proxy.register_function()
        def test_function(param: str) -> str:
            return f"Result: {param}"
        
        assert "test_function" in proxy.registered_functions
        assert proxy.registered_functions["test_function"] == test_function

    def test_register_function_with_custom_name(self):
        """Test function registration with custom name."""
        proxy = MemoryProxy()
        
        @proxy.register_function(name="custom_name")
        def original_function(param: str) -> str:
            return param
        
        assert "custom_name" in proxy.registered_functions
        assert "original_function" not in proxy.registered_functions

    def test_register_function_with_schema(self):
        """Test function registration with custom schema."""
        proxy = MemoryProxy()
        
        custom_schema = {
            "type": "function",
            "function": {
                "name": "test_func",
                "description": "Test function",
                "parameters": {"type": "object"}
            }
        }
        
        @proxy.register_function(schema=custom_schema)
        def test_func(param: str) -> str:
            return param
        
        assert hasattr(proxy.registered_functions["test_func"], "_llm_schema")
        assert proxy.registered_functions["test_func"]._llm_schema == custom_schema

    def test_get_available_tools_with_schema(self):
        """Test getting available tools with custom schemas - deterministic test."""
        proxy = MemoryProxy()
        
        custom_schema = {
            "type": "function",
            "function": {
                "name": "weather_tool",
                "description": "Get weather information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"}
                    }
                }
            }
        }
        
        @proxy.register_function(schema=custom_schema)
        def weather_tool(city: str) -> dict:
            return {"city": city, "temp": 20}
        
        tools = proxy._get_available_tools()
        
        # Should include custom schema exactly as provided
        weather_spec = next(
            (tool for tool in tools if tool.get("function", {}).get("name") == "weather_tool"),
            None
        )
        assert weather_spec == custom_schema


class TestFunctionExecution:
    """Test function execution mechanics - deterministic tests only."""

    @pytest.mark.asyncio
    async def test_execute_nonexistent_function(self):
        """Test execution of non-existent function - deterministic error."""
        proxy = MemoryProxy()
        
        result = await proxy._execute_function("nonexistent", {})
        
        # Should return error in structured format
        assert isinstance(result, dict)
        assert "error" in result
        assert "nonexistent" in result["error"]
        assert result["function"] == "nonexistent"


class TestBuiltinFunctionProtocol:
    """Test built-in function protocol/format conversions."""

    @pytest.mark.asyncio
    async def test_get_entities_response_format(self):
        """Test get_entities returns correct response format."""
        proxy = MemoryProxy()
        
        # Mock the client with known data
        mock_results = [
            {"key": "entity1", "value": {"name": "Test Entity"}},
            {"key": "entity2", "value": {"name": "Another Entity"}}
        ]
        
        mock_client = AsyncMock()
        # Mock find_by_type for entity_type queries
        mock_client.find_by_type = AsyncMock(return_value=mock_results)
        
        proxy._client = mock_client
        
        result = await proxy.get_entities(entity_type="Agent", limit=5)
        
        # Test deterministic response structure
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["key"] == "entity1"
        assert result[0]["value"]["name"] == "Test Entity"


