"""Pytest configuration for p8fs-node tests."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Add the src directory to the Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


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


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
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


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_pdf_path():
    """Provide path to sample PDF for testing."""
    return Path(__file__).parent / "sample_data" / "sample.pdf"


@pytest.fixture
def sample_wav_path():
    """Provide path to sample WAV file for testing."""
    return Path(__file__).parent / "sample_data" / "sample.wav"


@pytest.fixture
def sample_docx_path():
    """Provide path to sample DOCX file for testing."""
    return Path(__file__).parent / "sample_data" / "sample.docx"


@pytest.fixture
def sample_markdown_path():
    """Provide path to sample Markdown file for testing."""
    return Path(__file__).parent / "sample_data" / "sample.md"


@pytest.fixture
def sample_video_path():
    """Provide path to sample video file for testing."""
    return Path(__file__).parent / "sample_data" / "sample.mp4"


@pytest.fixture(autouse=True)
def clean_environment():
    """Clean environment variables before each test."""
    # Store original values
    original_env = {}
    test_env_vars = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "NATS_URL",
        "S3_ENDPOINT",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "TIDB_URL"
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
def mock_s3_client():
    """Mock S3 client for testing."""
    from unittest.mock import Mock
    client = Mock()
    client.get_object.return_value = {"Body": Mock(read=lambda: b"test content")}
    client.put_object.return_value = {"ETag": "test-etag"}
    return client


@pytest.fixture
def mock_nats_client():
    """Mock NATS client for testing."""
    from unittest.mock import AsyncMock
    client = AsyncMock()
    client.subscribe.return_value = AsyncMock()
    client.publish.return_value = None
    return client


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
                any(os.environ.get(key) for key in ["NATS_URL", "S3_ENDPOINT", "TIDB_URL"])
            )
            
            if not run_integration:
                pytest.skip("Integration tests skipped (use --integration or set service URLs)")


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