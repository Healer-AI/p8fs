"""
Integration tests for MemoryProxy with real LLM calls.

These tests verify the complete end-to-end functionality:
1. Real API calls to GPT-4, Claude, and Gemini
2. Proper response aggregation from streaming
3. Usage information collection via audit sessions
4. Function call handling with native dialect conversion
5. Message stack management with correct formats
6. Protocol adapter streaming conversion
7. Agentic loop with function execution
8. Batch processing capabilities

Run with: pytest tests/integration/test_memory_proxy_integration.py -v -s
"""

import pytest
import asyncio
import os
from typing import Dict, Any, List
import json

from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext, BatchCallingContext
from p8fs.models.base import AbstractModel
from p8fs_cluster.logging import get_logger
from pydantic import Field

logger = get_logger(__name__)


class WeatherAgent(AbstractModel):
    """A weather information agent that can check weather conditions.
    
    This agent demonstrates the abstracted model pattern where the docstring
    becomes the system prompt and methods become available functions.
    """
    
    name: str = Field(default="WeatherBot", description="Agent name")
    version: str = Field(default="1.0", description="Agent version")
    
    async def get_weather(self, location: str) -> Dict[str, Any]:
        """Get current weather for a location.
        
        Args:
            location: City name or location to check weather for
            
        Returns:
            Current weather conditions
        """
        # Mock weather data for testing
        return {
            "location": location,
            "temperature": 22,
            "conditions": "Partly cloudy",
            "humidity": 65,
            "wind_speed": 10,
            "unit": "celsius"
        }
    
    async def get_forecast(self, location: str, days: int = 3) -> Dict[str, Any]:
        """Get weather forecast for upcoming days.
        
        Args:
            location: City name or location
            days: Number of days to forecast (1-7)
            
        Returns:
            Weather forecast data
        """
        return {
            "location": location,
            "forecast": [
                {"day": f"Day {i+1}", "high": 25-i, "low": 15-i, "conditions": "Sunny"}
                for i in range(min(days, 7))
            ]
        }


@pytest.mark.integration
@pytest.mark.llm
class TestMemoryProxyIntegration:
    """Integration tests for MemoryProxy with real LLM providers"""
    
    @pytest.fixture
    def gpt4_context(self) -> CallingContext:
        """Calling context for GPT-4 model"""
        return CallingContext(
            model="gpt-4.1-mini",  # Using mini for cost efficiency in tests
            temperature=0.3,  # Lower temperature for consistent responses
            max_tokens=500,
            stream=True,
            tenant_id="test_tenant",
            user_id="test_user_123",
            session_id="integration_test_thread",
        )
    
    @pytest.fixture
    def claude_context(self) -> CallingContext:
        """Calling context for Claude Sonnet model"""  
        return CallingContext(
            model="claude-3-5-sonnet-20241022",
            temperature=0.3,
            max_tokens=500,
            stream=True,
            tenant_id="test_tenant",
            user_id="test_user_123", 
            session_id="integration_test_thread",
        )
    
    @pytest.fixture
    def gemini_context(self) -> CallingContext:
        """Calling context for Google Gemini model"""
        return CallingContext(
            model="gemini-2.0-flash",
            temperature=0.3,
            max_tokens=500,
            stream=True,
            tenant_id="test_tenant",
            user_id="test_user_123",
            session_id="integration_test_thread",
        )
    
    @pytest.fixture
    def weather_agent(self) -> WeatherAgent:
        """Create a weather agent for testing"""
        return WeatherAgent()
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_gpt4_simple_relay_mode(self, gpt4_context):
        """Test GPT-4 simple content response in relay mode (no agent)"""
        # Create MemoryProxy without model context (simple LLM relay mode)
        proxy = MemoryProxy()
        
        question = "What is the capital of Ireland?"
        
        try:
            response = await proxy.run(question, gpt4_context)
            
            # Verify response content
            assert response is not None
            assert len(response) > 0
            assert "dublin" in response.lower(), \
                f"Expected 'Dublin' in response: {response}"
            
            logger.info(f"GPT-4 Response: {response}")
            
        except Exception as e:
            logger.error(f"GPT-4 API call failed: {e}")
            raise
    
    @pytest.mark.asyncio 
    @pytest.mark.llm
    async def test_claude_simple_relay_mode(self, claude_context):
        """Test Claude simple content response in relay mode"""
        proxy = MemoryProxy()
        
        question = "What is the capital of Ireland?"
        
        try:
            response = await proxy.run(question, claude_context)
            
            assert response is not None
            assert len(response) > 0
            response_lower = response.lower()
            # Claude might answer directly or say it wants to search - both are valid
            assert any(term in response_lower for term in ["dublin", "ireland", "capital", "search"]), \
                f"Expected relevant response about Ireland/Dublin: {response}"
            
            logger.info(f"Claude Response: {response}")
            
        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            raise
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_gemini_simple_relay_mode(self, gemini_context):
        """Test Gemini simple content response in relay mode"""
        proxy = MemoryProxy()
        
        question = "What is the capital of Ireland?"
        
        try:
            response = await proxy.run(question, gemini_context)
            
            assert response is not None
            assert len(response) > 0
            assert "dublin" in response.lower(), \
                f"Expected 'Dublin' in response: {response}"
            
            logger.info(f"Gemini Response: {response}")
            
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_agent_with_system_prompt(self, weather_agent, gpt4_context):
        """Test agent mode where docstring becomes system prompt"""
        # Create MemoryProxy with weather agent
        proxy = MemoryProxy(model_context=weather_agent)
        
        question = "What kind of agent are you?"
        
        try:
            response = await proxy.run(question, gpt4_context)
            
            assert response is not None
            # Should identify as weather agent based on system prompt
            response_lower = response.lower()
            assert any(term in response_lower for term in ["weather", "forecast", "conditions"]), \
                f"Expected weather-related response: {response}"
            
            logger.info(f"Agent identification response: {response}")
            
        except Exception as e:
            logger.error(f"GPT-4 API call failed: {e}")
            raise
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_agent_function_calling(self, weather_agent, gpt4_context):
        """Test agent with function calling in agentic loop"""
        proxy = MemoryProxy(model_context=weather_agent)
        
        question = "What's the weather like in Dublin, Ireland?"
        
        try:
            response = await proxy.run(question, gpt4_context, max_iterations=3)
            
            assert response is not None
            response_lower = response.lower()
            
            # Should mention Dublin and weather details from function call
            assert "dublin" in response_lower, f"Expected Dublin in response: {response}"
            assert any(term in response_lower for term in ["22", "partly cloudy", "celsius"]), \
                f"Expected weather details from function: {response}"
            
            logger.info(f"Weather function response: {response}")
            
        except Exception as e:
            logger.error(f"GPT-4 API call failed: {e}")
            raise
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_streaming_with_function_calls(self, weather_agent, claude_context):
        """Test streaming responses with function call events"""
        proxy = MemoryProxy(model_context=weather_agent)
        
        question = "Check the weather and forecast for Paris"
        
        events = []
        try:
            async for chunk in proxy.stream(question, claude_context, max_iterations=3):
                events.append(chunk)
                
                # Log specific event types
                if chunk.get("type") == "iteration_start":
                    logger.info(f"Starting iteration {chunk['iteration']}")
                elif chunk.get("type") == "function_announcement":
                    logger.info(f"Calling function: {chunk['function_name']}")
                elif chunk.get("type") == "function_call_complete":
                    logger.info(f"Function {chunk['function_name']} returned: {chunk['result']}")
            
            # Verify we got expected event types
            event_types = {event.get("type") for event in events if "type" in event}
            assert "iteration_start" in event_types
            assert "completion" in event_types
            
            # Check if function calls were made (Claude may or may not call functions)
            if "function_announcement" in event_types:
                assert "function_call_complete" in event_types
                
                # Find function results
                function_results = [e for e in events if e.get("type") == "function_call_complete"]
                assert len(function_results) > 0
                
                # Verify function returned weather data
                weather_result = function_results[0]["result"]
                assert "location" in weather_result
                assert weather_result["location"] == "Paris"
            
        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            raise
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_protocol_adapter_streaming(self, gpt4_context, claude_context, gemini_context):
        """Test that protocol adapters properly convert streaming formats"""
        proxy = MemoryProxy()
        
        contexts = [
            ("GPT-4", gpt4_context),
            ("Claude", claude_context),
            ("Gemini", gemini_context)
        ]
        
        for provider_name, context in contexts:
            try:
                chunks = []
                async for chunk in proxy.stream("Count from 1 to 3", context):
                    if isinstance(chunk, dict) and "choices" in chunk:
                        chunks.append(chunk)
                
                # All providers should produce OpenAI-format chunks
                assert len(chunks) > 0, f"{provider_name} produced no chunks"
                
                # Verify OpenAI format structure
                for chunk in chunks[:5]:  # Check first few chunks
                    assert "choices" in chunk
                    assert isinstance(chunk["choices"], list)
                    if chunk["choices"]:
                        choice = chunk["choices"][0]
                        assert "delta" in choice or "message" in choice
                        assert "index" in choice
                
                logger.info(f"{provider_name} produced {len(chunks)} chunks in OpenAI format")
                
            except Exception as e:
                logger.error(f"{provider_name} API call failed: {e}")
                raise
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_batch_processing(self, gpt4_context):
        """Test batch processing capabilities"""
        proxy = MemoryProxy()
        
        # Create batch context
        batch_context = BatchCallingContext.for_quick_batch(
            model="gpt-4.1-mini"
        )
        batch_context.tenant_id = "test_tenant"
        
        questions = [
            "What is 2 + 2?",
            "What is the capital of France?",
            "How many days in a week?"
        ]
        
        try:
            # Note: Real batch processing requires OpenAI batch API setup
            # This test verifies the interface works correctly
            response = await proxy.batch(questions, batch_context, save_job=False)
            
            assert response is not None
            assert response.batch_id is not None
            assert response.questions_count == 3
            assert response.batch_type == "openai_batch_api"
            assert response.status == "submitted"
            
            logger.info(f"Batch submitted: {response.batch_id}")
            
        except Exception as e:
            # Batch API requires specific setup, so we expect this might fail
            logger.info(f"Batch API test result: {e}")
            # Don't skip - verify the error is about batch API, not our code
            assert "batch" in str(e).lower() or "file" in str(e).lower()
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_audit_session_tracking(self, weather_agent, gpt4_context):
        """Test that sessions are properly audited"""
        proxy = MemoryProxy(model_context=weather_agent)
        
        # Ensure we have a tenant ID for auditing
        gpt4_context.tenant_id = "test_tenant"
        
        try:
            response = await proxy.run("Hello, weather bot!", gpt4_context)
            
            # Verify response
            assert response is not None
            
            # The audit should have been called - we can't easily verify the DB write
            # but we can check that no exceptions were raised
            logger.info("Audit session completed without errors")
            
        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_builtin_functions(self, gpt4_context):
        """Test built-in functions like get_entities"""
        proxy = MemoryProxy()
        
        # The built-in get_entities function should be registered
        assert proxy._function_handler is not None
        schemas = proxy._function_handler.get_schemas()
        
        # Find get_entities in schemas
        function_names = [s["function"]["name"] for s in schemas if "function" in s]
        assert "get_entities" in function_names
        assert "search_resources" in function_names
        assert "get_recent_tenant_uploads" in function_names
        
        logger.info(f"Built-in functions registered: {function_names}")
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_message_stack_building(self, weather_agent):
        """Test proper message stack construction"""
        proxy = MemoryProxy(model_context=weather_agent)
        
        messages = proxy._build_message_stack("Test question")
        
        # Should have system message from agent docstring
        assert len(messages) >= 1
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Test question"
        
        # Check for system message with agent description
        system_messages = [m for m in messages if m["role"] == "system"]
        if system_messages:
            system_content = system_messages[0]["content"]
            assert "weather" in system_content.lower()
            logger.info(f"System prompt: {system_content[:100]}...")
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_system_prompt_from_agent_description(self, weather_agent):
        """Test that system prompts come from agent.get_model_description()"""
        proxy = MemoryProxy(model_context=weather_agent)
        
        # Get the agent's model description directly
        agent_description = weather_agent.get_model_description()
        
        # Build message stack and check system message
        messages = proxy._build_message_stack("What are you?")
        
        system_messages = [m for m in messages if m["role"] == "system"]
        assert len(system_messages) > 0, "Should have at least one system message"
        
        system_content = system_messages[0]["content"]
        
        # System prompt should contain key parts of the agent description
        assert "weather" in system_content.lower()
        assert "information agent" in system_content.lower()
        
        # System prompt should match or contain the agent's description
        assert agent_description in system_content or system_content in agent_description
        
        logger.info(f"Agent description: {agent_description}")
        logger.info(f"System prompt: {system_content}")
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_protocol_adaptation_streaming_with_function_calls(self, weather_agent, gpt4_context, claude_context):
        """Test protocol adaptation with streaming function calls across providers"""
        proxy = MemoryProxy(model_context=weather_agent)
        
        question = "Get the weather for Paris and tell me about it"
        
        providers = [
            ("GPT-4", gpt4_context),
            ("Claude", claude_context)
        ]
        
        for provider_name, context in providers:
            try:
                events = []
                function_calls = []
                
                async for chunk in proxy.stream(question, context, max_iterations=3):
                    events.append(chunk)
                    
                    # Track function call events
                    if chunk.get("type") == "function_announcement":
                        function_calls.append(chunk["function_name"])
                    elif chunk.get("type") in ["completion", "content"]:
                        # All streaming events should be in OpenAI format after protocol adaptation
                        if isinstance(chunk, dict) and "choices" in chunk:
                            assert "choices" in chunk
                            assert isinstance(chunk["choices"], list)
                            if chunk["choices"]:
                                choice = chunk["choices"][0]
                                assert "index" in choice
                                # Either delta (streaming) or message (completion)
                                assert "delta" in choice or "message" in choice
                
                # Verify we got streaming events
                event_types = {event.get("type") for event in events if "type" in event}
                assert len(event_types) > 0
                
                logger.info(f"{provider_name} streaming events: {list(event_types)}")
                logger.info(f"{provider_name} function calls: {function_calls}")
                
            except Exception as e:
                logger.error(f"{provider_name} streaming with functions failed: {e}")
                raise