#!/usr/bin/env python3
"""Test resource affinity with TiDB provider.

This script verifies that the ResourceAffinityBuilder works correctly with TiDB,
including vector search operations and JSON field updates.
"""

import asyncio
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config
from p8fs.providers import get_provider
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models.p8 import Resources
from p8fs.algorithms.resource_affinity import ResourceAffinityBuilder

logger = get_logger(__name__)


async def test_tidb_vector_operations():
    """Test TiDB vector search and JSON operations."""

    logger.info("=" * 80)
    logger.info("TIDB RESOURCE AFFINITY TEST")
    logger.info("=" * 80)

    # Verify we're using TiDB
    logger.info(f"Storage provider: {config.storage_provider}")
    if config.storage_provider != "tidb":
        logger.error("This test requires P8FS_STORAGE_PROVIDER=tidb")
        logger.info("Set: export P8FS_STORAGE_PROVIDER=tidb")
        return False

    # Get provider and verify it's TiDB
    provider = get_provider()
    provider.connect_sync()

    dialect = getattr(provider, 'dialect', 'unknown')
    logger.info(f"Provider dialect: {dialect}")

    if dialect != 'tidb':
        logger.error(f"Expected TiDB dialect, got: {dialect}")
        return False

    tenant_id = "tenant-tidb-test"

    # Clean up old test data
    logger.info(f"\nCleaning up old data for {tenant_id}...")
    try:
        provider.execute("DELETE FROM embeddings.resources_embeddings WHERE tenant_id = %s", (tenant_id,))
        provider.execute("DELETE FROM resources WHERE tenant_id = %s", (tenant_id,))
    except Exception as e:
        logger.warning(f"Cleanup warning (table may not exist): {e}")

    # Create test resources
    logger.info(f"\nCreating test resources for {tenant_id}...")
    resource_repo = TenantRepository(Resources, tenant_id=tenant_id)

    base_time = datetime.now(timezone.utc) - timedelta(hours=1)

    test_resources = [
        {
            "name": "TiDB Vector Search Overview",
            "category": "technical",
            "content": """TiDB provides native vector search capabilities using VEC_COSINE_DISTANCE function.
            Vector indexes can be created on columns of type VECTOR. The system supports cosine similarity,
            L2 distance, and inner product metrics for efficient similarity search operations."""
        },
        {
            "name": "TiDB JSON Operations",
            "category": "technical",
            "content": """TiDB supports JSON data types and provides functions for JSON manipulation.
            JSON columns can store arbitrary JSON documents and support indexing on extracted fields.
            Use JSON_EXTRACT, JSON_SET, and other functions for efficient JSON operations."""
        },
        {
            "name": "Database Performance Tuning",
            "category": "technical",
            "content": """Performance tuning involves analyzing query execution plans, optimizing indexes,
            and configuring system parameters. Monitor slow queries, optimize table statistics, and
            use appropriate index strategies for your workload patterns."""
        },
        {
            "name": "Cloud Native Databases",
            "category": "infrastructure",
            "content": """Cloud-native databases are designed for distributed environments with automatic
            scaling, high availability, and geo-replication. They separate storage and compute layers
            for elastic scaling and provide ACID guarantees across distributed transactions."""
        },
    ]

    created_ids = []
    for i, data in enumerate(test_resources):
        resource = Resources(
            id=str(uuid4()),
            tenant_id=tenant_id,
            name=data["name"],
            content=data["content"],
            category=data["category"],
            resource_timestamp=base_time + timedelta(minutes=i * 10),
            graph_paths=[],
        )
        await resource_repo.put(resource)
        created_ids.append(resource.id)
        logger.info(f"  Created: {resource.name}")

    logger.info(f"\n✓ Created {len(test_resources)} resources")

    # Verify embeddings were created
    embeddings_check = provider.execute(
        "SELECT COUNT(*) as count FROM embeddings.resources_embeddings WHERE tenant_id = %s",
        (tenant_id,)
    )
    embedding_count = embeddings_check[0]['count'] if embeddings_check else 0
    logger.info(f"✓ Verified {embedding_count} embeddings created")

    if embedding_count == 0:
        logger.error("No embeddings created - cannot proceed with vector search test")
        return False

    # Test ResourceAffinityBuilder with TiDB
    logger.info(f"\nTesting ResourceAffinityBuilder with TiDB...")
    builder = ResourceAffinityBuilder(provider, tenant_id)

    logger.info(f"  Dialect detected: {builder.dialect}")

    # Process resource affinity (basic mode)
    logger.info(f"\nRunning resource affinity processing (basic mode)...")
    stats = await builder.process_resource_batch(
        lookback_hours=24,
        batch_size=10,
        mode="basic"
    )

    logger.info(f"\nResource Affinity Results:")
    logger.info(f"  Processed: {stats['processed']}")
    logger.info(f"  Updated: {stats['updated']}")
    logger.info(f"  Total edges added: {stats['total_edges_added']}")

    # Verify graph paths were created
    resources_with_paths = provider.execute(
        """
        SELECT name, category, JSON_LENGTH(graph_paths) as edge_count
        FROM resources
        WHERE tenant_id = %s
          AND graph_paths IS NOT NULL
          AND JSON_LENGTH(graph_paths) > 0
        ORDER BY edge_count DESC
        """,
        (tenant_id,)
    )

    logger.info(f"\nResources with graph edges: {len(resources_with_paths)}")
    for resource in resources_with_paths:
        logger.info(f"  - {resource['name']}: {resource['edge_count']} edges ({resource['category']})")

    # Verify JSON operations worked
    if resources_with_paths:
        sample_resource = resources_with_paths[0]
        paths_query = provider.execute(
            """
            SELECT graph_paths
            FROM resources
            WHERE name = %s AND tenant_id = %s
            """,
            (sample_resource['name'], tenant_id)
        )
        if paths_query:
            sample_paths = paths_query[0]['graph_paths']
            logger.info(f"\nSample graph paths from '{sample_resource['name']}':")
            import json
            if isinstance(sample_paths, str):
                sample_paths = json.loads(sample_paths)
            for path in sample_paths[:3]:
                logger.info(f"  - {path}")

    # Success criteria
    success = (
        stats['processed'] > 0 and
        stats['total_edges_added'] > 0 and
        len(resources_with_paths) > 0
    )

    logger.info(f"\n{'=' * 80}")
    if success:
        logger.info("✓ TIDB RESOURCE AFFINITY TEST PASSED")
        logger.info(f"{'=' * 80}")
        logger.info(f"Successfully tested:")
        logger.info(f"  - TiDB vector search with VEC_COSINE_DISTANCE")
        logger.info(f"  - JSON field updates for graph_paths")
        logger.info(f"  - ResourceAffinityBuilder with TiDB dialect")
        logger.info(f"  - Multi-resource semantic similarity")
    else:
        logger.error("✗ TIDB RESOURCE AFFINITY TEST FAILED")
        logger.error(f"{'=' * 80}")

    return success


async def compare_postgresql_tidb():
    """Compare behavior between PostgreSQL and TiDB implementations."""

    logger.info("\n" + "=" * 80)
    logger.info("POSTGRESQL vs TIDB COMPARISON")
    logger.info("=" * 80)

    logger.info("\nVector Search Syntax:")
    logger.info("  PostgreSQL: e.embedding_vector <-> %s::vector")
    logger.info("  TiDB:       VEC_COSINE_DISTANCE(e.embedding_vector, VEC_FROM_TEXT(%s))")

    logger.info("\nJSON Field Updates:")
    logger.info("  PostgreSQL: SET graph_paths = %s::jsonb")
    logger.info("  TiDB:       SET graph_paths = %s  (JSON type, no cast needed)")

    logger.info("\nQuery Array Length:")
    logger.info("  PostgreSQL: jsonb_array_length(graph_paths)")
    logger.info("  TiDB:       JSON_LENGTH(graph_paths)")

    logger.info("\n" + "=" * 80)


async def main():
    """Run TiDB resource affinity tests."""

    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY required for embeddings generation")
        logger.info("Set: export OPENAI_API_KEY=sk-...")
        return

    # Check provider setting
    if config.storage_provider != "tidb":
        logger.warning(f"Current provider: {config.storage_provider}")
        logger.info("To test TiDB, set: export P8FS_STORAGE_PROVIDER=tidb")
        logger.info("\nAlso ensure TiDB is running:")
        logger.info("  docker-compose up tidb -d")
        return

    try:
        # Run TiDB test
        tidb_passed = await test_tidb_vector_operations()

        # Show comparison
        await compare_postgresql_tidb()

        if tidb_passed:
            logger.info("\n✓ All TiDB tests passed!")
            logger.info("\nTiDB provider is ready for production deployment.")
        else:
            logger.error("\n✗ TiDB tests failed")
            logger.info("Review errors above and verify:")
            logger.info("  1. TiDB is running (docker-compose up tidb -d)")
            logger.info("  2. Migrations have been applied")
            logger.info("  3. Vector extension is enabled")

    except Exception as e:
        logger.error(f"Test failed with exception: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
