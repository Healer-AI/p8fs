"""Pytest configuration for p8fs tests."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Add the src directory to the Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# NOTE: Removed mock config to ensure integration tests use real p8fs-cluster centralized config
# Unit tests should mock config locally as needed, not globally


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test (requires real services)"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test (isolated, mocked)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "llm: mark test as requiring real LLM API calls (use --with-llm to run)"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    # Skip LLM tests unless --with-llm flag is provided
    # Only skip tests explicitly marked with @pytest.mark.llm
    if not config.getoption("--with-llm"):
        skip_llm = pytest.mark.skip(reason="need --with-llm option to run")
        for item in items:
            # Check for explicit @pytest.mark.llm marker, not directory name
            if item.get_closest_marker("llm"):
                item.add_marker(skip_llm)
    
    for item in items:
        # Auto-mark integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        
        # Auto-mark unit tests  
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        
        # Auto-mark async tests as needing event loop
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)


# Removed custom event_loop fixture - pytest-asyncio now handles this automatically
# The custom fixture was causing deprecation warnings in pytest-asyncio >= 0.21

@pytest.fixture
def sample_openai_api_key():
    """Provide a sample API key for testing (not for real use)."""
    return "sk-test1234567890abcdef1234567890abcdef1234567890abcdef"


@pytest.fixture
def sample_anthropic_api_key():
    """Provide a sample Anthropic API key for testing (not for real use)."""
    return "claude-test-1234567890abcdef1234567890abcdef1234567890abcdef"


@pytest.fixture
def sample_google_api_key():
    """Provide a sample Google API key for testing (not for real use)."""
    return "AIzaTest1234567890abcdef1234567890abcdef123"


@pytest.fixture(autouse=True)
def clean_environment():
    """Clean environment variables before each test."""
    # Store original values
    original_env = {}
    test_env_vars = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY", 
        "GOOGLE_API_KEY",
        "TEST_API_KEY"
    ]
    
    for var in test_env_vars:
        if var in os.environ:
            original_env[var] = os.environ[var]
    
    yield
    
    # Restore original values
    for var in test_env_vars:
        if var in original_env:
            os.environ[var] = original_env[var]
        elif var in os.environ:
            del os.environ[var]


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response for testing."""
    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "gpt-4",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "This is a test response."
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 8,
            "total_tokens": 18
        }
    }


@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response for testing."""
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "content": [{
            "type": "text",
            "text": "This is a test response from Claude."
        }],
        "model": "claude-3-5-sonnet-20241022",
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 12
        }
    }


@pytest.fixture
def mock_google_response():
    """Mock Google API response for testing."""
    return {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": "This is a test response from Gemini."
                }],
                "role": "model"
            },
            "finishReason": "STOP",
            "index": 0
        }],
        "usageMetadata": {
            "promptTokenCount": 8,
            "candidatesTokenCount": 12,
            "totalTokenCount": 20
        }
    }


@pytest.fixture
def sample_messages():
    """Sample conversation messages for testing."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing well, thank you!"},
        {"role": "user", "content": "What can you help me with?"}
    ]




@pytest.fixture
def sample_tool_schema():
    """Sample tool schema for testing function calls."""
    return {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name"
                    },
                    "units": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature units"
                    }
                },
                "required": ["location"]
            }
        }
    }


# Skip integration tests by default in CI/local unless explicitly requested
def pytest_runtest_setup(item):
    """Setup hook to skip integration tests unless explicitly requested."""
    if hasattr(item, 'iter_markers'):
        integration_marker = next(item.iter_markers(name="integration"), None)
        if integration_marker:
            # Check if we should run integration tests
            run_integration = (
                item.config.getoption("--integration", False) or
                os.environ.get("RUN_INTEGRATION_TESTS", "").lower() == "true" or
                any(os.environ.get(key) for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"])
            )
            
            if not run_integration:
                pytest.skip("Integration tests skipped (use --integration or set API keys)")


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests"
    )
    parser.addoption(
        "--slow",
        action="store_true", 
        default=False,
        help="Run slow tests"
    )
    parser.addoption(
        "--with-llm",
        action="store_true",
        default=False,
        help="Run tests that make real LLM API calls"
    )