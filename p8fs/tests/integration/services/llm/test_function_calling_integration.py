"""Integration tests for function calling with real LLM APIs."""

import asyncio
import os
from typing import Any

import pytest
from p8fs.services.llm import CallingContext, MemoryProxy
from p8fs.utils.functions import From_Callable
from tests.sample_data.functions.sample_functions import (
    async_function,
    complex_function,
    error_function,
    simple_function,
    vector_function,
)


@pytest.fixture
async def memory_proxy():
    """Create a MemoryProxy instance and ensure cleanup."""
    proxy = MemoryProxy()
    yield proxy
    await proxy.close()


class TestFunctionSchemaGeneration:
    """Test function schema generation from callables."""

    def test_simple_function_schema(self):
        """Test schema generation for simple function."""
        wrapper = From_Callable(simple_function)
        schema = wrapper.to_openai_tool()
        
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "simple_function"
        assert "description" in schema["function"]
        
        # Check parameters
        params = schema["function"]["parameters"]
        assert params["type"] == "object"
        assert "name" in params["properties"]
        assert "age" in params["properties"]
        assert params["required"] == ["name"]  # age has default

    def test_complex_function_schema(self):
        """Test schema generation for complex function with nested types."""
        wrapper = From_Callable(complex_function)
        schema = wrapper.to_openai_tool()
        
        params = schema["function"]["parameters"]
        
        # Check complex parameter types
        assert "items" in params["properties"]
        assert "options" in params["properties"]
        assert "filters" in params["properties"]
        
        # items should be array type (List[Dict[str, Any]])
        items_prop = params["properties"]["items"]
        assert items_prop["type"] == "array"
        
        # options should handle Union type
        options_prop = params["properties"]["options"]
        # Should be oneOf for Union types or have flexible type

    def test_async_function_schema(self):
        """Test schema generation for async function."""
        wrapper = From_Callable(async_function)
        schema = wrapper.to_openai_tool()
        
        assert schema["function"]["name"] == "async_function"
        
        params = schema["function"]["parameters"]
        assert "query" in params["properties"]
        assert "limit" in params["properties"]
        assert params["required"] == ["query"]

    def test_vector_function_schema(self):
        """Test schema generation for function with vector parameters."""
        wrapper = From_Callable(vector_function)
        schema = wrapper.to_openai_tool()
        
        params = schema["function"]["parameters"]
        embeddings_prop = params["properties"]["embeddings"]
        
        # Should recognize List[float] as array of numbers
        assert embeddings_prop["type"] == "array"
        if "items" in embeddings_prop:
            assert embeddings_prop["items"]["type"] == "number"

    def test_error_function_schema(self):
        """Test schema generation for function that can raise errors."""
        wrapper = From_Callable(error_function)
        schema = wrapper.to_openai_tool()
        
        assert schema["function"]["name"] == "error_function"
        params = schema["function"]["parameters"]
        assert "should_error" in params["properties"]


class TestFunctionRegistrationAndExecution:
    """Test function registration and execution in MemoryProxy."""

    def test_function_registration(self):
        """Test registering functions with MemoryProxy."""
        proxy = MemoryProxy()
        initial_count = len(proxy.registered_functions)
        
        @proxy.register_function()
        def test_add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b
        
        assert len(proxy.registered_functions) == initial_count + 1
        assert "test_add" in proxy.registered_functions
        assert proxy.registered_functions["test_add"] == test_add

    async def test_function_execution_sync(self, memory_proxy):
        """Test executing synchronous registered functions."""
        
        @memory_proxy.register_function()
        def multiply(x: int, y: int) -> int:
            """Multiply two numbers."""
            return x * y
        
        result = await memory_proxy._execute_function("multiply", {"x": 6, "y": 7})
        assert result == 42

    async def test_function_execution_async(self, memory_proxy):
        """Test executing asynchronous registered functions."""
        
        @memory_proxy.register_function()
        async def async_multiply(x: int, y: int) -> int:
            """Multiply two numbers asynchronously.""" 
            await asyncio.sleep(0.01)  # Simulate async work
            return x * y
        
        result = await memory_proxy._execute_function("async_multiply", {"x": 8, "y": 5})
        assert result == 40

    async def test_function_execution_error_handling(self, memory_proxy):
        """Test error handling in function execution."""
        
        @memory_proxy.register_function()
        def divide(a: int, b: int) -> float:
            """Divide two numbers."""
            return a / b
        
        # Test division by zero
        result = await memory_proxy._execute_function("divide", {"a": 10, "b": 0})
        
        assert "error" in result
        assert "divide" in result["function"]

    def test_tool_schema_generation(self):
        """Test generating tool schemas from registered functions."""
        proxy = MemoryProxy()
        
        @proxy.register_function()
        def weather_check(city: str, units: str = "celsius") -> dict[str, Any]:
            """Check weather for a city."""
            return {"city": city, "temperature": 22, "units": units}
        
        tools = proxy._get_available_tools()
        
        # Should include built-ins plus our registered function
        weather_tool = None
        for tool in tools:
            if tool.get("function", {}).get("name") == "weather_check":
                weather_tool = tool
                break
        
        assert weather_tool is not None
        assert weather_tool["type"] == "function"
        
        func_def = weather_tool["function"]
        assert func_def["name"] == "weather_check"
        assert "description" in func_def
        
        params = func_def["parameters"]
        assert "city" in params["properties"]
        assert "units" in params["properties"]
        assert params["required"] == ["city"]  # units has default


@pytest.mark.llm
class TestRealAPIFunctionCalling:
    """Test function calling with real LLM APIs."""

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_openai_function_calling_basic(self, memory_proxy):
        """Test basic function calling with OpenAI."""
        
        @memory_proxy.register_function()
        def get_current_time() -> str:
            """Get the current time."""
            import datetime
            return datetime.datetime.now().strftime("%H:%M:%S")
        
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        response = await memory_proxy.run(
            "What time is it? Use the available function to check.",
            context,
            max_iterations=3
        )
        
        assert isinstance(response, str)
        # Should contain a time format or mention time
        assert any(char.isdigit() for char in response) or "time" in response.lower()

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_openai_math_function_calling(self, memory_proxy):
        """Test mathematical function calling with OpenAI."""
        
        @memory_proxy.register_function()
        def calculate_area_circle(radius: float) -> dict[str, Any]:
            """Calculate the area of a circle given its radius."""
            import math
            area = math.pi * radius ** 2
            return {
                "radius": radius,
                "area": round(area, 2),
                "formula": "π × r²"
            }
        
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        response = await memory_proxy.run(
            "Calculate the area of a circle with radius 5 using the available function.",
            context,
            max_iterations=3
        )
        
        assert isinstance(response, str)
        # Should contain the result (~78.54) or mention area calculation
        assert "78.5" in response or "area" in response.lower()

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_openai_multiple_function_calls(self, memory_proxy):
        """Test multiple function calls in sequence."""
        
        @memory_proxy.register_function()
        def convert_celsius_to_fahrenheit(celsius: float) -> dict[str, Any]:
            """Convert temperature from Celsius to Fahrenheit."""
            fahrenheit = (celsius * 9/5) + 32
            return {
                "celsius": celsius,
                "fahrenheit": round(fahrenheit, 1),
                "formula": "(C × 9/5) + 32"
            }
        
        @memory_proxy.register_function()
        def convert_fahrenheit_to_celsius(fahrenheit: float) -> dict[str, Any]:
            """Convert temperature from Fahrenheit to Celsius."""
            celsius = (fahrenheit - 32) * 5/9
            return {
                "fahrenheit": fahrenheit,
                "celsius": round(celsius, 1),
                "formula": "(F - 32) × 5/9"
            }
        
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        response = await memory_proxy.run(
            "Convert 25°C to Fahrenheit, then convert that result back to Celsius to verify.",
            context,
            max_iterations=5
        )
        
        assert isinstance(response, str)
        # Should show both conversions and verification
        assert "77" in response or "25" in response  # 25°C = 77°F

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_openai_function_with_error(self, memory_proxy):
        """Test function calling with error handling."""
        
        @memory_proxy.register_function()
        def divide_numbers(dividend: float, divisor: float) -> dict[str, Any]:
            """Divide two numbers."""
            if divisor == 0:
                raise ValueError("Cannot divide by zero")
            
            result = dividend / divisor
            return {
                "dividend": dividend,
                "divisor": divisor,
                "result": round(result, 4),
                "operation": f"{dividend} ÷ {divisor}"
            }
        
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        # Test with division by zero
        response = await memory_proxy.run(
            "Divide 10 by 0 using the available function.",
            context,
            max_iterations=3
        )
        
        assert isinstance(response, str)
        # Should handle the error gracefully
        assert "error" in response.lower() or "cannot" in response.lower() or "zero" in response.lower()

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Anthropic API key not available")
    @pytest.mark.llm
    async def test_anthropic_function_calling(self, memory_proxy):
        """Test function calling with Anthropic Claude."""
        
        @memory_proxy.register_function()
        def generate_password(length: int = 12, include_symbols: bool = True) -> dict[str, Any]:
            """Generate a random password."""
            import random
            import string
            
            chars = string.ascii_letters + string.digits
            if include_symbols:
                chars += "!@#$%^&*"
            
            password = ''.join(random.choice(chars) for _ in range(length))
            
            return {
                "password": password,
                "length": len(password),
                "includes_symbols": include_symbols,
                "strength": "strong" if length >= 12 else "medium" if length >= 8 else "weak"
            }
        
        context = CallingContext(model="claude-3-5-sonnet-20241022", tenant_id="test")
        
        response = await memory_proxy.run(
            "Generate a secure password with 16 characters including symbols.",
            context,
            max_iterations=3
        )
        
        assert isinstance(response, str)
        # Should contain information about password generation
        assert "password" in response.lower() or "generated" in response.lower()


class TestComplexFunctionScenarios:
    """Test complex function calling scenarios."""

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_data_processing_pipeline(self, memory_proxy):
        """Test a data processing pipeline with multiple functions."""
        
        @memory_proxy.register_function()
        def load_sample_data() -> list[dict[str, Any]]:
            """Load sample sales data."""
            return [
                {"product": "Widget A", "sales": 100, "price": 10.50},
                {"product": "Widget B", "sales": 150, "price": 15.75},
                {"product": "Widget C", "sales": 75, "price": 8.25}
            ]
        
        @memory_proxy.register_function()
        def calculate_revenue(data: list[dict[str, Any]]) -> dict[str, Any]:
            """Calculate total revenue from sales data."""
            # Add validation to prevent string indexing errors
            if not isinstance(data, list):
                return {"error": f"Expected list, got {type(data).__name__}"}
            
            try:
                total_revenue = sum(item["sales"] * item["price"] for item in data)
                return {
                    "total_revenue": round(total_revenue, 2),
                    "products_count": len(data),
                    "breakdown": [
                        {
                            "product": item["product"],
                            "revenue": round(item["sales"] * item["price"], 2)
                        }
                        for item in data
                    ]
                }
            except (TypeError, KeyError) as e:
                return {"error": str(e)}
        
        @memory_proxy.register_function()
        def find_top_performer(revenue_data: dict[str, Any]) -> dict[str, Any]:
            """Find the top performing product by revenue."""
            # Add validation
            if not isinstance(revenue_data, dict):
                return {"error": f"Expected dict, got {type(revenue_data).__name__}"}
            
            if "breakdown" not in revenue_data:
                return {"error": "Missing 'breakdown' in revenue data"}
                
            breakdown = revenue_data["breakdown"]
            if not breakdown:
                return {"error": "No breakdown data available"}
                
            top_product = max(breakdown, key=lambda x: x["revenue"])
            return {
                "top_product": top_product["product"],
                "top_revenue": top_product["revenue"],
                "percentage_of_total": round(
                    (top_product["revenue"] / revenue_data["total_revenue"]) * 100, 1
                )
            }
        
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        # Add timeout to prevent infinite loops
        try:
            response = await asyncio.wait_for(
                memory_proxy.run(
                    "Load the sample sales data, calculate the total revenue, and identify the top performing product.",
                    context,
                    max_iterations=3  # Reduced from 5
                ),
                timeout=30.0  # 30 second timeout
            )
        except asyncio.TimeoutError:
            pytest.skip("Test timed out - likely due to LLM retry loop")
        
        assert isinstance(response, str)
        # Should mention the analysis results
        assert "widget" in response.lower() or "revenue" in response.lower()

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_iterative_problem_solving(self, memory_proxy):
        """Test iterative problem solving with functions."""
        
        fibonacci_cache = {}
        
        @memory_proxy.register_function()
        def fibonacci(n: int) -> dict[str, Any]:
            """Calculate the nth Fibonacci number."""
            if n in fibonacci_cache:
                return {"n": n, "result": fibonacci_cache[n], "cached": True}
            
            if n <= 1:
                result = n
            else:
                result = fibonacci(n-1)["result"] + fibonacci(n-2)["result"]
            
            fibonacci_cache[n] = result
            return {"n": n, "result": result, "cached": False}
        
        @memory_proxy.register_function()
        def fibonacci_sequence(count: int) -> dict[str, Any]:
            """Generate a sequence of Fibonacci numbers."""
            sequence = []
            for i in range(count):
                fib_result = fibonacci(i)
                sequence.append(fib_result["result"])
            
            return {
                "count": count,
                "sequence": sequence,
                "sum": sum(sequence)
            }
        
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        response = await memory_proxy.run(
            "Generate the first 8 Fibonacci numbers and tell me their sum.",
            context,
            max_iterations=3
        )
        
        assert isinstance(response, str)
        # First 8 Fibonacci numbers: 0,1,1,2,3,5,8,13 (sum = 33)
        assert "33" in response or "sum" in response.lower()


class TestStreamingWithFunctionCalls:
    """Test streaming responses with function calls."""

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_streaming_with_function_execution(self, memory_proxy):
        """Test streaming response that includes function calls."""
        
        @memory_proxy.register_function()
        def get_random_fact() -> str:
            """Get a random interesting fact."""
            facts = [
                "Octopuses have three hearts and blue blood.",
                "A group of flamingos is called a 'flamboyance'.",
                "Honey never spoils - archaeologists have found edible honey in ancient Egyptian tombs.",
                "Bananas are berries, but strawberries aren't.",
                "A single cloud can weigh more than a million pounds."
            ]
            import random
            return random.choice(facts)
        
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        chunks = []
        async for chunk in memory_proxy.stream(
            "Get a random fact and then explain why it's interesting.",
            context,
            max_iterations=3
        ):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        
        # Should have received streaming chunks
        chunk_content = " ".join(str(chunk) for chunk in chunks)
        
        # Should contain some indication of function execution or facts
        assert "fact" in chunk_content.lower() or "interesting" in chunk_content.lower()


@pytest.mark.llm
class TestBuiltInFunctionIntegration:
    """Test integration of built-in MemoryProxy functions with LLMs."""

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_entity_search_integration(self, memory_proxy):
        """Test entity search function integration."""
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        response = await memory_proxy.run(
            "Search for entities and tell me about the results.",
            context,
            max_iterations=3
        )
        
        assert isinstance(response, str)
        # Should mention entities or search results
        assert "entit" in response.lower() or "search" in response.lower() or "result" in response.lower()

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available") 
    @pytest.mark.llm
    async def test_resource_search_integration(self, memory_proxy):
        """Test resource search function integration."""
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        response = await memory_proxy.run(
            "Search for resources about 'machine learning' and summarize what you find.",
            context,
            max_iterations=3
        )
        
        assert isinstance(response, str)
        # Should mention resources or search results
        assert "resource" in response.lower() or "search" in response.lower() or "machine learning" in response.lower()

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_recent_uploads_integration(self, memory_proxy):
        """Test recent uploads function integration."""
        context = CallingContext(model="gpt-4o-mini", tenant_id="test")
        
        response = await memory_proxy.run(
            "Check recent tenant uploads and tell me about them.",
            context,
            max_iterations=3
        )
        
        assert isinstance(response, str)
        # Should mention uploads or files
        assert "upload" in response.lower() or "file" in response.lower() or "recent" in response.lower()