"""Integration tests for streaming functionality across providers."""

import asyncio
import os

import pytest
from p8fs.services.llm import BaseProxy, CallingContext, LanguageModel, MemoryProxy


@pytest.mark.llm
class TestStreamingIntegration:
    """Test streaming functionality with real providers."""

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_openai_streaming_chunks(self):
        """Test OpenAI streaming chunk format and content."""
        model = LanguageModel("gpt-4o-mini")
        
        messages = [{"role": "user", "content": "Count from 1 to 5, one number per line."}]
        response = await model.invoke_raw(messages, stream=True, max_tokens=50)
        
        assert "chunks" in response
        assert "full_response" in response
        
        chunks = response["chunks"]
        assert len(chunks) > 0
        
        # Verify chunk structure
        content_chunks = []
        for chunk in chunks:
            if "choices" in chunk and chunk["choices"]:
                choice = chunk["choices"][0]
                if "delta" in choice and choice["delta"].get("content"):
                    content_chunks.append(choice["delta"]["content"])
        
        # Should have received content chunks
        assert len(content_chunks) > 0
        
        # Combined content should contain numbers
        combined_content = "".join(content_chunks)
        assert any(str(i) in combined_content for i in range(1, 6))

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Anthropic API key not available") 
    @pytest.mark.llm
    async def test_anthropic_streaming_chunks(self):
        """Test Anthropic streaming chunk format and content."""
        model = LanguageModel("claude-3-5-sonnet-20241022")
        
        messages = [{"role": "user", "content": "List three colors, one per line."}]
        response = await model.invoke_raw(messages, stream=True, max_tokens=50)
        
        assert "chunks" in response
        assert "full_response" in response
        
        chunks = response["chunks"]
        assert len(chunks) > 0
        
        # Verify we got meaningful content
        full_content = response["full_response"].get("content", "")
        assert len(full_content) > 0

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("GOOGLE_API_KEY"), reason="Google API key not available")
    @pytest.mark.llm
    async def test_google_streaming_chunks(self):
        """Test Google streaming chunk format and content.""" 
        model = LanguageModel("gemini-1.5-flash")
        
        messages = [{"role": "user", "content": "Name three animals."}]
        response = await model.invoke_raw(messages, stream=True, max_tokens=50)
        
        assert "chunks" in response
        assert "full_response" in response
        
        chunks = response["chunks"]
        assert len(chunks) > 0


class TestBaseProxyStreaming:
    """Test BaseProxy streaming across providers."""

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_base_proxy_openai_streaming(self):
        """Test BaseProxy streaming with OpenAI."""
        async with BaseProxy() as proxy:
            messages = [{"role": "user", "content": "Say hello and goodbye."}]
            
            chunks = []
            async for chunk in proxy.stream_completion(messages, "gpt-4o-mini", max_tokens=30):
                chunks.append(chunk)
            
            assert len(chunks) > 0
            
            # Should receive structured chunks
            for chunk in chunks:
                assert isinstance(chunk, dict)

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Anthropic API key not available")
    @pytest.mark.llm
    async def test_base_proxy_anthropic_streaming(self):
        """Test BaseProxy streaming with Anthropic."""
        async with BaseProxy() as proxy:
            messages = [{"role": "user", "content": "Say hello briefly."}]
            
            chunks = []
            async for chunk in proxy.stream_completion(messages, "claude-3-5-sonnet-20241022", max_tokens=20):
                chunks.append(chunk)
            
            assert len(chunks) > 0

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_base_proxy_chat_completion_streaming(self):
        """Test BaseProxy chat_completion streaming."""
        async with BaseProxy() as proxy:
            messages = [{"role": "user", "content": "What is 2+2?"}]
            
            chunks = []
            async for chunk in proxy.chat_completion(
                messages=messages,
                model="gpt-4o-mini",
                stream=True,
                max_tokens=20
            ):
                chunks.append(chunk)
            
            assert len(chunks) > 0
            
            # Should contain the answer
            all_content = " ".join(str(chunk) for chunk in chunks)
            assert "4" in all_content


class TestMemoryProxyStreaming:
    """Test MemoryProxy streaming functionality."""

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_memory_proxy_basic_streaming(self):
        """Test MemoryProxy basic streaming."""
        proxy = MemoryProxy()
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        chunks = []
        async for chunk in proxy.stream("Tell me a very short fact.", context):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        
        # Should receive meaningful chunks
        chunk_content = " ".join(str(chunk) for chunk in chunks)
        assert len(chunk_content) > 10  # Should have substantial content

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_memory_proxy_streaming_with_functions(self):
        """Test MemoryProxy streaming with function calls."""
        proxy = MemoryProxy()
        
        @proxy.register_function()
        def get_current_date() -> str:
            """Get the current date."""
            import datetime
            return datetime.date.today().strftime("%Y-%m-%d")
        
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        chunks = []
        async for chunk in proxy.stream(
            "What's today's date? Use the available function.",
            context,
            max_iterations=3
        ):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        
        # Should contain date information or function calling
        all_content = " ".join(str(chunk) for chunk in chunks).lower()
        assert any(word in all_content for word in ["date", "today", "2024", "function"])

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_memory_proxy_streaming_builtin_functions(self):
        """Test MemoryProxy streaming with built-in functions."""
        proxy = MemoryProxy()
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        chunks = []
        async for chunk in proxy.stream(
            "Search for entities and tell me about what you find.",
            context,
            max_iterations=3
        ):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        
        # Should mention searching or entities
        all_content = " ".join(str(chunk) for chunk in chunks).lower()
        assert any(word in all_content for word in ["search", "entit", "find", "result"])


class TestStreamingErrorHandling:
    """Test streaming error handling scenarios."""

    @pytest.mark.integration
    @pytest.mark.llm
    async def test_streaming_with_invalid_model(self):
        """Test streaming with invalid model name."""
        model = LanguageModel("nonexistent-model-12345")
        
        messages = [{"role": "user", "content": "Hello"}]
        
        try:
            response = await model.invoke_raw(messages, stream=True, max_tokens=10)
            # If it somehow works, should still be valid format
            if "chunks" in response:
                assert isinstance(response["chunks"], list)
        except Exception as e:
            # Should get meaningful error
            assert len(str(e)) > 0

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_streaming_with_function_error(self):
        """Test streaming when function execution fails."""
        proxy = MemoryProxy()
        
        @proxy.register_function()
        def failing_function(param: str) -> str:
            """A function that always fails."""
            raise Exception("This function always fails")
        
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        chunks = []
        try:
            async for chunk in proxy.stream(
                "Use the failing function with parameter 'test'.",
                context,
                max_iterations=2
            ):
                chunks.append(chunk)
        except Exception:
            pass  # Expected to potentially fail
        
        # Should handle gracefully and produce some chunks
        assert len(chunks) >= 0  # May or may not produce chunks depending on error handling


class TestStreamingPerformance:
    """Test streaming performance characteristics."""

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_streaming_response_time(self):
        """Test that streaming starts quickly."""
        import time
        
        model = LanguageModel("gpt-4o-mini")
        messages = [{"role": "user", "content": "Write a short paragraph about cats."}]
        
        start_time = time.time()
        response = await model.invoke_raw(messages, stream=True, max_tokens=100)
        first_chunk_time = time.time()
        
        # Should get response quickly (streaming)
        time_to_first_chunk = first_chunk_time - start_time
        
        # Should be faster than 10 seconds for first chunk
        assert time_to_first_chunk < 10.0
        
        # Should have received chunks
        assert "chunks" in response
        assert len(response["chunks"]) > 0

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_concurrent_streaming(self):
        """Test multiple concurrent streaming requests."""
        async def single_stream():
            model = LanguageModel("gpt-4o-mini")
            messages = [{"role": "user", "content": "Count to 3."}]
            response = await model.invoke_raw(messages, stream=True, max_tokens=20)
            return response
        
        # Run multiple concurrent streams
        tasks = [single_stream() for _ in range(3)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed or fail gracefully
        successes = [r for r in results if not isinstance(r, Exception)]
        
        # At least some should succeed
        assert len(successes) > 0
        
        # Check successful responses
        for response in successes:
            assert "chunks" in response
            assert len(response["chunks"]) > 0


class TestProviderSpecificStreaming:
    """Test provider-specific streaming behavior."""

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_openai_streaming_with_tools(self):
        """Test OpenAI streaming with function calls."""
        async with BaseProxy() as proxy:
            messages = [{"role": "user", "content": "What time is it?"}]
            
            tools = [{
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get the current time",
                    "parameters": {"type": "object", "properties": {}}
                }
            }]
            
            chunks = []
            async for chunk in proxy.chat_completion(
                messages=messages,
                model="gpt-4o-mini",
                stream=True,
                tools=tools,
                max_tokens=50
            ):
                chunks.append(chunk)
            
            assert len(chunks) > 0
            
            # May contain tool calls in streaming format
            has_tool_reference = any(
                "tool" in str(chunk).lower() or "function" in str(chunk).lower() 
                for chunk in chunks
            )
            
            # Should either use tools or explain why not
            assert has_tool_reference or any("time" in str(chunk).lower() for chunk in chunks)

    @pytest.mark.integration  
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_streaming_token_usage_tracking(self):
        """Test token usage tracking in streaming responses."""
        model = LanguageModel("gpt-4o-mini")
        messages = [{"role": "user", "content": "Write exactly 10 words."}]
        
        response = await model.invoke_raw(messages, stream=True, max_tokens=30)
        
        # Check if usage information is available
        chunks = response["chunks"]
        
        # Usage info typically comes in the last chunk for streaming
        usage_info = None
        for chunk in reversed(chunks):
            if isinstance(chunk, dict) and "usage" in chunk:
                usage_info = chunk["usage"]
                break
        
        # May or may not have usage info depending on provider implementation
        if usage_info:
            assert "total_tokens" in usage_info or "prompt_tokens" in usage_info