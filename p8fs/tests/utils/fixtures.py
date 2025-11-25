"""
Common test fixtures and utilities for integration tests.

Provides reusable patterns for database cleanup, environment checks, etc.
"""

import os
import pytest
from typing import Callable
from p8fs.providers import BaseSQLProvider
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


def requires_api_key(key_name: str = "OPENAI_API_KEY"):
    """
    Decorator to skip tests if API key is not set.

    Args:
        key_name: Environment variable name to check

    Example:
        @requires_api_key("OPENAI_API_KEY")
        def test_embedding_generation():
            # This test only runs if OPENAI_API_KEY is set
            pass
    """
    def decorator(func):
        return pytest.mark.skipif(
            not os.getenv(key_name),
            reason=f"{key_name} not set"
        )(func)
    return decorator


class TenantCleanup:
    """Context manager for automatic tenant data cleanup."""

    def __init__(self, provider: BaseSQLProvider, tenant_id: str, tables: list[str] = None):
        """
        Initialize cleanup context.

        Args:
            provider: Database provider
            tenant_id: Tenant ID to clean
            tables: List of tables to clean (default: ['resources', 'sessions'])
        """
        self.provider = provider
        self.tenant_id = tenant_id
        self.tables = tables or ['resources', 'sessions']

    def __enter__(self):
        """Clean before test."""
        self.cleanup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean after test."""
        self.cleanup()

    def cleanup(self):
        """Execute cleanup for all tables."""
        for table in self.tables:
            try:
                self.provider.execute(
                    f"DELETE FROM {table} WHERE tenant_id = %s",
                    (self.tenant_id,)
                )
                logger.debug(f"Cleaned {table} for tenant {self.tenant_id}")
            except Exception as e:
                logger.warning(f"Failed to clean {table}: {e}")


def verify_data_counts(
    provider: BaseSQLProvider,
    tenant_id: str,
    expected: dict[str, int],
    skip_missing_api_key: bool = True
) -> dict[str, int]:
    """
    Verify expected data counts across tables.

    Args:
        provider: Database provider
        tenant_id: Tenant ID to check
        expected: Dict of table_name -> expected_count
        skip_missing_api_key: If True, skip embedding counts when no API key

    Returns:
        Dict of table_name -> actual_count

    Raises:
        AssertionError: If counts don't match expectations

    Example:
        actual = verify_data_counts(
            provider,
            "test-tenant",
            {
                'resources': 3,
                'sessions': 2,
                'embeddings.resources_embeddings': 3
            }
        )
    """
    actual = {}

    for table, expected_count in expected.items():
        # Skip embedding checks if no API key
        if 'embedding' in table and skip_missing_api_key and not os.getenv("OPENAI_API_KEY"):
            logger.info(f"Skipping {table} count check: No API key")
            actual[table] = 0
            continue

        result = provider.execute(
            f"SELECT COUNT(*) as count FROM {table} WHERE tenant_id = %s",
            (tenant_id,)
        )

        count = result[0]['count']
        actual[table] = count

        # Only assert if we're not skipping
        if not ('embedding' in table and skip_missing_api_key and not os.getenv("OPENAI_API_KEY")):
            assert count == expected_count, f"{table}: expected {expected_count}, got {count}"

        logger.info(f"{table}: {count} records")

    return actual
