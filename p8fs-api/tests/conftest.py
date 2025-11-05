"""Test configuration for p8fs-api tests."""

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def enable_debug_mode():
    """Enable debug mode for all tests to avoid TrustedHostMiddleware issues."""
    with patch('p8fs_cluster.config.settings.config.debug', True):
        yield