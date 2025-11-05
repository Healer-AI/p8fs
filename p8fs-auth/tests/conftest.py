"""Pytest configuration and shared fixtures.

Provides common test fixtures and configuration for both
unit and integration tests.
"""

import asyncio

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Marker definitions
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests with mocked dependencies"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests with real services"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take longer to run"
    )