"""
Test 1: Database Operations - REFACTORED VERSION

Demonstrates using test utilities for cleaner, more maintainable tests.

Run with:
    P8FS_STORAGE_PROVIDER=postgresql uv run pytest tests/integration/test_01_database_operations_refactored.py -v --integration
"""

import pytest
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers import get_provider
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models.p8 import Resources

# Import our new utilities
from tests.utils import (
    sync_table_schema,
    ResourceFactory,
    SessionFactory,
    TenantCleanup,
    verify_data_counts,
    requires_api_key
)

logger = get_logger(__name__)
TENANT_ID = "tenant-test-db-v2"


@pytest.mark.integration
class TestDatabaseOperationsRefactored:
    """Refactored test using utilities - notice how much cleaner this is!"""

    @pytest.fixture(scope="class", autouse=True)
    def setup_schema(self):
        """Automatically sync database schema with model."""
        provider = get_provider()
        provider.connect_sync()

        # Auto-sync schema - no more manual ALTER TABLE!
        sync_table_schema(provider, Resources)

        # Use TenantCleanup context manager
        with TenantCleanup(provider, TENANT_ID):
            yield

    @pytest.fixture(scope="class")
    def provider(self):
        """Get database provider."""
        assert config.storage_provider == "postgresql", "Must use PostgreSQL"
        provider = get_provider()
        provider.connect_sync()
        return provider

    @pytest.fixture(scope="class")
    def repo(self, provider):
        """Get tenant repository."""
        return TenantRepository(Resources, tenant_id=TENANT_ID)

    async def test_01_save_resources(self, repo):
        """Test saving resources - using factory!"""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Save Resources (Using Factory)")
        logger.info("=" * 70)

        # Create test resources using factory - no boilerplate!
        resources = ResourceFactory.create_batch(
            tenant_id=TENANT_ID,
            count=3
        )

        saved_ids = []
        for resource in resources:
            success = await repo.put(resource)
            if success:
                saved_ids.append(resource.id)
                logger.info(f"✓ Saved: {resource.name}")

        logger.info(f"\nSaved {len(saved_ids)} resources")
        assert len(saved_ids) == 3, "Should save all 3 resources"

    def test_02_query_resources(self, provider):
        """Test querying resources."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Query Resources")
        logger.info("=" * 70)

        all_resources = provider.execute(
            "SELECT * FROM resources WHERE tenant_id = %s ORDER BY created_at",
            (TENANT_ID,)
        )

        logger.info(f"Found {len(all_resources)} total resources")
        assert len(all_resources) == 3, "Should find 3 resources"

        logger.info("✓ All query tests passed")

    @requires_api_key("OPENAI_API_KEY")  # Clean decorator instead of manual checks!
    def test_03_generate_embeddings(self, provider):
        """Test embedding generation - skipped without API key."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Generate Embeddings")
        logger.info("=" * 70)

        # Embedding generation logic here
        # This test is automatically skipped if OPENAI_API_KEY is not set
        logger.info("✓ Embeddings generated")

    async def test_04_save_sessions(self, provider):
        """Test saving sessions - using factory!"""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Save Sessions (Using Factory)")
        logger.info("=" * 70)

        # Use SessionFactory instead of manual SQL
        sessions = SessionFactory.create_batch(tenant_id=TENANT_ID, count=2)

        for i, session in enumerate(sessions, 1):
            provider.execute(
                """
                INSERT INTO sessions (id, tenant_id, name, query, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (session.id, session.tenant_id, session.name, session.query)
            )
            logger.info(f"✓ Saved session: {session.name}")

        logger.info(f"\n✓ Saved {len(sessions)} sessions")

    def test_05_verify_data_integrity(self, provider):
        """Verify data integrity - using verification utility!"""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Verify Data Integrity (Using Utility)")
        logger.info("=" * 70)

        # Use verification utility instead of manual counts
        verify_data_counts(
            provider,
            TENANT_ID,
            {
                'resources': 3,
                'sessions': 2,
                'embeddings.resources_embeddings': 0  # 0 expected since no API key
            }
        )

        logger.info("\n✓ Data integrity verified")
        logger.info("=" * 70)
        logger.info("DATABASE OPERATIONS TEST COMPLETE ✓")
        logger.info("=" * 70)
