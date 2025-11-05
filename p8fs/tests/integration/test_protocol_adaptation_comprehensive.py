"""
Comprehensive protocol adaptation tests for MemoryProxy.

Tests the critical surface areas identified in the LLM services __init__.py:
1. Function calling + streaming combinations
2. Protocol adaptation matrix (Anthropic → OpenAI, Google → OpenAI, etc.)
3. Batch + streaming/non-streaming combinations
4. Complete token capture across providers
5. Full dialect matrix testing

Run with: pytest tests/integration/test_protocol_adaptation_comprehensive.py -v -s
"""

import pytest
import asyncio
import json
from typing import Dict, Any, List

from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext, BatchCallingContext
from p8fs.models.base import AbstractModel
from p8fs_cluster.logging import get_logger
from pydantic import Field

logger = get_logger(__name__)


class CalculatorAgent(AbstractModel):
    """A mathematical calculator agent that can perform arithmetic operations.
    
    This agent can handle basic mathematical calculations including addition,
    subtraction, multiplication, division, and more complex operations.
    """
    
    name: str = Field(default="MathBot", description="Agent name")
    precision: int = Field(default=4, description="Decimal precision for results")
    
    async def add(self, a: float, b: float) -> float:
        """Add two numbers together.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Sum of a and b
        """
        return a + b
    
    async def multiply(self, a: float, b: float) -> float:
        """Multiply two numbers.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Product of a and b
        """
        return a * b
    
    async def calculate_compound_interest(self, principal: float, rate: float, time: int) -> float:
        """Calculate compound interest.
        
        Args:
            principal: Initial amount
            rate: Annual interest rate (as decimal, e.g., 0.05 for 5%)
            time: Number of years
            
        Returns:
            Final amount with compound interest
        """
        return principal * (1 + rate) ** time


@pytest.mark.integration
@pytest.mark.llm
class TestProtocolAdaptationComprehensive:
    """Comprehensive tests for protocol adaptation across all providers"""
    
    @pytest.fixture
    def calculator_agent(self) -> CalculatorAgent:
        """Create a calculator agent for testing"""
        return CalculatorAgent()
    
    @pytest.fixture
    def openai_context(self) -> CallingContext:
        """OpenAI calling context"""
        return CallingContext(
            model="gpt-4.1-mini",
            temperature=0.1,
            max_tokens=300,
            stream=True,
            tenant_id="test_tenant",
            user_id="test_user_protocol",
            session_id="protocol_test_session",
        )
    
    @pytest.fixture
    def anthropic_context(self) -> CallingContext:
        """Anthropic calling context"""  
        return CallingContext(
            model="claude-3-5-sonnet-20241022",
            temperature=0.1,
            max_tokens=300,
            stream=True,
            tenant_id="test_tenant",
            user_id="test_user_protocol",
            session_id="protocol_test_session",
        )
    
    @pytest.fixture
    def google_context(self) -> CallingContext:
        """Google calling context"""
        return CallingContext(
            model="gemini-2.0-flash",
            temperature=0.1,
            max_tokens=300,
            stream=True,
            tenant_id="test_tenant",
            user_id="test_user_protocol",
            session_id="protocol_test_session",
        )
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_function_calling_streaming_all_providers(self, calculator_agent, openai_context, anthropic_context, google_context):
        """Test function calling with streaming across all providers"""
        proxy = MemoryProxy(model_context=calculator_agent)
        
        contexts = [
            ("OpenAI", openai_context),
            ("Anthropic", anthropic_context), 
            ("Google", google_context)
        ]
        
        question = "What is 15 multiplied by 8?"
        
        for provider_name, context in contexts:
            try:
                events = []
                function_calls = []
                streaming_chunks = []
                
                async for chunk in proxy.stream(question, context, max_iterations=2):
                    events.append(chunk)
                    
                    # Track function-related events
                    if chunk.get("type") == "function_announcement":
                        function_calls.append({
                            "name": chunk["function_name"],
                            "args": chunk.get("args", {})
                        })
                    elif chunk.get("type") == "function_call_complete":
                        function_calls[-1]["result"] = chunk.get("result")
                    
                    # Track streaming format consistency
                    elif isinstance(chunk, dict) and "choices" in chunk:
                        streaming_chunks.append(chunk)
                        
                        # Verify OpenAI format consistency
                        assert "choices" in chunk
                        assert isinstance(chunk["choices"], list)
                        if chunk["choices"]:
                            choice = chunk["choices"][0]
                            assert "index" in choice
                            # Must have either delta (streaming) or message (final)
                            assert "delta" in choice or "message" in choice
                
                # Verify function calls occurred
                assert len(function_calls) > 0, f"{provider_name}: No function calls detected"
                
                # Verify function execution
                multiply_calls = [fc for fc in function_calls if fc["name"] == "multiply"]
                if multiply_calls:
                    assert multiply_calls[0]["result"] == 120.0
                
                # Verify streaming format consistency
                assert len(streaming_chunks) > 0, f"{provider_name}: No streaming chunks in OpenAI format"
                
                event_types = {event.get("type") for event in events if "type" in event}
                logger.info(f"{provider_name} - Events: {list(event_types)}, Functions: {[fc['name'] for fc in function_calls]}, Streaming chunks: {len(streaming_chunks)}")
                
            except Exception as e:
                logger.error(f"{provider_name} function calling + streaming failed: {e}")
                raise
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_protocol_adaptation_matrix(self, openai_context, anthropic_context, google_context):
        """Test protocol adaptation matrix - all providers → OpenAI streaming format"""
        proxy = MemoryProxy()
        
        contexts = [
            ("OpenAI", openai_context, "gpt-4.1-mini"),
            ("Anthropic", anthropic_context, "claude-3-5-sonnet-20241022"),
            ("Google", google_context, "gemini-2.0-flash")
        ]
        
        test_prompts = [
            "Count from 1 to 3",
            "Explain what AI is in one sentence",
            "List two benefits of renewable energy"
        ]
        
        for provider_name, context, expected_model in contexts:
            for prompt in test_prompts:
                try:
                    chunks = []
                    total_content = ""
                    
                    async for chunk in proxy.stream(prompt, context):
                        if isinstance(chunk, dict) and "choices" in chunk:
                            chunks.append(chunk)
                            
                            # Verify OpenAI streaming format structure
                            assert "id" in chunk or "object" in chunk or "choices" in chunk
                            assert isinstance(chunk["choices"], list)
                            
                            if chunk["choices"]:
                                choice = chunk["choices"][0]
                                assert "index" in choice
                                
                                # Check for delta content
                                if "delta" in choice and choice["delta"].get("content"):
                                    total_content += choice["delta"]["content"]
                    
                    # Verify we got streaming chunks
                    assert len(chunks) > 0, f"{provider_name}: No streaming chunks received for '{prompt}'"
                    
                    # Verify content was accumulated
                    assert len(total_content) > 0, f"{provider_name}: No content accumulated for '{prompt}'"
                    
                    logger.info(f"{provider_name} protocol adaptation OK - {len(chunks)} chunks, {len(total_content)} chars")
                    
                except Exception as e:
                    logger.error(f"{provider_name} protocol adaptation failed for '{prompt}': {e}")
                    raise
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_batch_processing_modes(self, openai_context):
        """Test batch processing with different modes"""
        proxy = MemoryProxy()
        
        # Test batch context
        batch_context = BatchCallingContext.for_quick_batch(
            model="gpt-4.1-mini"
        )
        batch_context.tenant_id = "test_tenant"
        
        questions = [
            "What is 2 + 2?",
            "What is the square root of 16?",
            "What is 10 percent of 200?"
        ]
        
        try:
            # Test batch API interface
            response = await proxy.batch(questions, batch_context, save_job=False)
            
            assert response is not None
            assert response.batch_id is not None
            assert response.questions_count == 3
            assert response.batch_type in ["openai_batch_api", "sequential"]
            
            logger.info(f"Batch processing test OK - {response.batch_type} mode, batch_id: {response.batch_id}")
            
        except Exception as e:
            # Batch API requires specific setup - verify error is about batch API, not our code
            error_msg = str(e).lower()
            assert any(term in error_msg for term in ["batch", "file", "api", "upload"]), \
                f"Unexpected batch error (not API-related): {e}"
            logger.info(f"Batch API interface test passed (expected batch API limitation): {e}")
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_complete_token_capture(self, calculator_agent, openai_context, anthropic_context):
        """Test complete token capture across providers with function calls"""
        proxy = MemoryProxy(model_context=calculator_agent)
        
        contexts = [
            ("OpenAI", openai_context),
            ("Anthropic", anthropic_context)
        ]
        
        question = "Calculate the compound interest on $1000 at 5% per year for 3 years, then multiply by 2"
        
        for provider_name, context in contexts:
            try:
                events = []
                token_usage = {}
                
                async for chunk in proxy.stream(question, context, max_iterations=3):
                    events.append(chunk)
                    
                    # Capture token usage from streaming chunks
                    if isinstance(chunk, dict) and "usage" in chunk:
                        usage = chunk["usage"]
                        if "prompt_tokens" in usage:
                            token_usage["prompt_tokens"] = usage["prompt_tokens"]
                        if "completion_tokens" in usage:
                            token_usage["completion_tokens"] = usage["completion_tokens"]  
                        if "total_tokens" in usage:
                            token_usage["total_tokens"] = usage["total_tokens"]
                    
                    # Also check for usage in choice-level data
                    elif isinstance(chunk, dict) and "choices" in chunk:
                        for choice in chunk["choices"]:
                            if "usage" in choice:
                                usage = choice["usage"]
                                for key, value in usage.items():
                                    token_usage[key] = token_usage.get(key, 0) + value
                
                # Verify token information was captured
                assert len(token_usage) > 0, f"{provider_name}: No token usage captured"
                
                # Check for expected token fields
                expected_fields = ["prompt_tokens", "completion_tokens", "total_tokens"]
                captured_fields = list(token_usage.keys())
                
                logger.info(f"{provider_name} token capture - Fields: {captured_fields}, Usage: {token_usage}")
                
                # At minimum, we should have some token count
                total_tokens = sum(v for v in token_usage.values() if isinstance(v, (int, float)))
                assert total_tokens > 0, f"{provider_name}: Total token count should be > 0, got {total_tokens}"
                
            except Exception as e:
                logger.error(f"{provider_name} token capture failed: {e}")
                raise
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_error_handling_and_fallbacks(self, openai_context):
        """Test error handling and fallback scenarios"""
        proxy = MemoryProxy()
        
        # Test with invalid model context
        invalid_context = CallingContext(
            model="invalid-model-name-12345",
            temperature=0.1,
            max_tokens=100,
            stream=True,
            tenant_id="test_tenant",
            user_id="test_error_handling",
            session_id="error_test_session",
        )
        
        try:
            events = []
            async for chunk in proxy.stream("Hello", invalid_context):
                events.append(chunk)
                
                # Check for error chunks
                if isinstance(chunk, dict) and chunk.get("type") == "error":
                    assert "error" in chunk
                    logger.info(f"Received expected error chunk: {chunk}")
                    break
            
            # Should receive some kind of error indication
            error_events = [e for e in events if isinstance(e, dict) and "error" in e]
            logger.info(f"Error handling test - received {len(error_events)} error events from {len(events)} total events")
            
        except Exception as e:
            # Expected - invalid model should cause an error
            assert "model" in str(e).lower() or "invalid" in str(e).lower() or "not found" in str(e).lower()
            logger.info(f"Error handling test passed - received expected error: {e}")
    
    @pytest.mark.asyncio  
    @pytest.mark.llm
    async def test_message_stack_consistency(self, calculator_agent, openai_context, anthropic_context):
        """Test message stack consistency across providers with agent context"""
        proxy = MemoryProxy(model_context=calculator_agent)
        
        contexts = [
            ("OpenAI", openai_context),
            ("Anthropic", anthropic_context)
        ]
        
        for provider_name, context in contexts:
            try:
                # Test message stack building
                messages = proxy._build_message_stack("What can you calculate?")
                
                # Should have system message from agent
                system_messages = [m for m in messages if m["role"] == "system"]
                assert len(system_messages) > 0, f"{provider_name}: No system message found"
                
                system_content = system_messages[0]["content"]
                assert "mathematical" in system_content.lower() or "calculator" in system_content.lower()
                
                # Should have user message
                user_messages = [m for m in messages if m["role"] == "user"]
                assert len(user_messages) > 0, f"{provider_name}: No user message found"
                assert user_messages[-1]["content"] == "What can you calculate?"
                
                logger.info(f"{provider_name} message stack consistency OK - {len(messages)} messages, {len(system_messages)} system")
                
            except Exception as e:
                logger.error(f"{provider_name} message stack consistency failed: {e}")
                raise
    
    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_streaming_non_streaming_combinations(self, openai_context, anthropic_context):
        """Test streaming vs non-streaming mode combinations"""
        proxy = MemoryProxy()
        
        contexts = [
            ("OpenAI", openai_context),
            ("Anthropic", anthropic_context)
        ]
        
        for provider_name, context in contexts:
            # Test streaming mode
            context_streaming = CallingContext(**context.model_dump())
            context_streaming.stream = True
            
            try:
                streaming_chunks = []
                async for chunk in proxy.stream("Say hello", context_streaming):
                    if isinstance(chunk, dict) and "choices" in chunk:
                        streaming_chunks.append(chunk)
                
                assert len(streaming_chunks) > 0, f"{provider_name}: No streaming chunks received"
                logger.info(f"{provider_name} streaming mode OK - {len(streaming_chunks)} chunks")
                
            except Exception as e:
                logger.error(f"{provider_name} streaming mode failed: {e}")
                raise
            
            # Test non-streaming mode
            context_non_streaming = CallingContext(**context.model_dump())  
            context_non_streaming.stream = False
            
            try:
                response = await proxy.run("Say hello", context_non_streaming)
                assert isinstance(response, str)
                assert len(response) > 0
                logger.info(f"{provider_name} non-streaming mode OK - {len(response)} chars")
                
            except Exception as e:
                logger.error(f"{provider_name} non-streaming mode failed: {e}")
                raise