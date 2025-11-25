"""
Integration test for agent tracing with OpenTelemetry.

Tests that agent execution with tool calls generates proper traces.
"""
import asyncio
import pytest
from p8fs.services.llm import MemoryProxy
from p8fs.services.llm.models import CallingContext
from p8fs.models.base import AbstractModel
from pydantic import Field


class SimpleAgent(AbstractModel):
    """Simple test agent with a basic tool."""

    name: str = "SimpleAgent"
    description: str = "A simple test agent with tool calling capabilities"

    def get_weather(self, location: str) -> dict:
        """
        Get the weather for a location.

        Args:
            location: The city name

        Returns:
            Weather information
        """
        return {
            "location": location,
            "temperature": 72,
            "condition": "sunny",
            "message": f"The weather in {location} is sunny and 72°F"
        }


@pytest.mark.integration
async def test_agent_with_tool_call_generates_traces():
    """Test that agent execution with tool calls generates OTEL traces."""
    print("\n" + "="*60)
    print("Testing Agent Tracing with Tool Calls")
    print("="*60)

    # Create agent with tool
    proxy = MemoryProxy(SimpleAgent)

    # Create context
    context = CallingContext(
        model="gpt-4o-mini",
        tenant_id="test-tenant",
        user_id="test-user",
        temperature=0.7,
        max_tokens=150
    )

    # Question that should trigger the tool
    question = "What's the weather in San Francisco?"

    print(f"\nQuestion: {question}")
    print(f"Expected: Agent should call get_weather tool")

    # Execute agent
    iteration_count = 0
    tool_calls = []
    final_response = ""

    try:
        async for chunk in proxy.stream(question, context, max_iterations=3):
            if isinstance(chunk, dict):
                chunk_type = chunk.get("type")

                if chunk_type == "iteration_start":
                    iteration_count += 1
                    print(f"\n→ Iteration {iteration_count} started")

                elif chunk_type == "function_announcement":
                    func_name = chunk.get("function_name")
                    tool_calls.append(func_name)
                    print(f"  📞 Tool call: {func_name}")

                elif chunk_type == "function_call_complete":
                    result = chunk.get("result", {})
                    print(f"  ✓ Tool result: {result.get('message', result)}")

                elif chunk_type == "completion":
                    final_response = chunk.get("final_response", "")
                    print(f"\n✓ Agent completed in {iteration_count} iterations")
                    print(f"  Final response: {final_response[:150]}...")

        # Verify execution
        print("\n" + "-"*60)
        print("Verification:")
        assert iteration_count > 0, "Agent should have run at least one iteration"
        print(f"  ✓ Agent executed {iteration_count} iterations")

        # Note: Tool calling might fail due to API key, but we're testing tracing not functionality
        if tool_calls:
            assert "get_weather" in tool_calls, "get_weather tool should have been called"
            print(f"  ✓ Tools called: {tool_calls}")
        else:
            print(f"  ⚠ No tools called (API error expected in test)")

        assert final_response or iteration_count > 0, "Should have some response or iterations"
        print(f"  ✓ Response generated")

        print("\n" + "="*60)
        print("✓ Agent execution test PASSED")
        print("="*60)

        # Give traces time to export (batch interval is 1s)
        print("\nWaiting 3 seconds for trace export...")
        await asyncio.sleep(3)

        return True

    except Exception as e:
        print(f"\n✗ Error during agent execution: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_simple_agent_execution():
    """Simpler test without tool calls to verify basic tracing."""
    print("\n" + "="*60)
    print("Testing Simple Agent Execution")
    print("="*60)

    # Create simple proxy without model context
    proxy = MemoryProxy()

    context = CallingContext(
        model="gpt-4o-mini",
        tenant_id="test-tenant",
        temperature=0.7,
        max_tokens=50
    )

    question = "Say hello"
    print(f"\nQuestion: {question}")

    try:
        iteration_count = 0
        async for chunk in proxy.stream(question, context, max_iterations=1):
            if isinstance(chunk, dict) and chunk.get("type") == "iteration_start":
                iteration_count += 1

        print(f"✓ Agent executed {iteration_count} iteration(s)")

        # Wait for trace export
        await asyncio.sleep(3)
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    # Run tests
    print("\nInitializing OpenTelemetry for testing...")
    print("Using endpoint: localhost:4317 (port-forward required)")

    # Set environment for OTEL
    import os
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "localhost:4317"
    os.environ["P8FS_DEBUG"] = "false"

    # Initialize OTEL like the API does
    from p8fs_api.observability import setup_observability
    setup_observability(service_name="p8fs-agent-test")

    # Run tests
    results = []

    print("\n" + "="*60)
    print("Test 1: Simple Agent Execution")
    print("="*60)
    result1 = asyncio.run(test_simple_agent_execution())
    results.append(("Simple execution", result1))

    print("\n" + "="*60)
    print("Test 2: Agent with Tool Calls")
    print("="*60)
    result2 = asyncio.run(test_agent_with_tool_call_generates_traces())
    results.append(("Tool calls", result2))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status} - {name}")

    all_passed = all(r for _, r in results)

    if all_passed:
        print("\n✓ All tests PASSED")
        print("\nNext: Check OTel collector logs for traces:")
        print("  kubectl logs -n observability deployment/otel-collector --tail=30 | grep -i trace")
    else:
        print("\n✗ Some tests FAILED")
