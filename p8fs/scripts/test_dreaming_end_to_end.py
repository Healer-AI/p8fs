#!/usr/bin/env python3
"""End-to-end test for dreaming worker with resource affinity integration.

This script tests:
1. Creating sample resources for multiple tenants
2. Running resource affinity processing (basic + LLM modes)
3. Verifying graph paths were created
4. Testing multi-tenant processing
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config
from p8fs.providers import get_provider
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models.p8 import Resources
from p8fs.workers.dreaming import DreamingWorker

logger = get_logger(__name__)


TENANTS = ["tenant-alice", "tenant-bob", "tenant-carol"]


async def create_sample_resources_for_tenant(tenant_id: str) -> int:
    """Create diverse sample resources for a tenant."""
    logger.info(f"Creating sample resources for {tenant_id}")

    provider = get_provider()
    provider.connect_sync()

    logger.info(f"  Cleaning up old data for {tenant_id}...")
    provider.execute("DELETE FROM embeddings.resources_embeddings WHERE tenant_id = %s", (tenant_id,))
    provider.execute("DELETE FROM resources WHERE tenant_id = %s", (tenant_id,))

    base_time = datetime.now(timezone.utc) - timedelta(hours=12)

    resource_repo = TenantRepository(Resources, tenant_id=tenant_id)

    resources_data = [
        {
            "name": f"{tenant_id}: Python Development Best Practices",
            "category": "technical",
            "content": """Python development requires attention to code quality, testing, and documentation.
            Use type hints for better IDE support, write comprehensive tests with pytest, follow PEP 8
            style guide, and maintain clear documentation. Virtual environments isolate dependencies.""",
        },
        {
            "name": f"{tenant_id}: Machine Learning Project Setup",
            "category": "technical",
            "content": """Setting up ML projects involves data versioning, experiment tracking, and model registry.
            Use tools like MLflow for tracking experiments, DVC for data versioning, and maintain reproducible
            environments. Document data preprocessing steps and model architecture decisions.""",
        },
        {
            "name": f"{tenant_id}: Career Transition Planning",
            "category": "career",
            "content": """Transitioning careers requires strategic planning and skill development. Identify
            transferable skills, build a portfolio demonstrating new capabilities, network in target industry,
            and consider gradual transitions. Update resume to highlight relevant experience.""",
        },
        {
            "name": f"{tenant_id}: Work-Life Balance Strategies",
            "category": "wellness",
            "content": """Maintaining work-life balance requires setting boundaries and prioritizing self-care.
            Establish clear work hours, schedule breaks throughout the day, exercise regularly, and maintain
            social connections. Learn to say no to low-priority commitments.""",
        },
        {
            "name": f"{tenant_id}: Team Leadership Principles",
            "category": "leadership",
            "content": """Effective leadership involves clear communication, empathy, and empowerment. Set clear
            expectations, provide regular feedback, recognize achievements, and support professional growth.
            Foster psychological safety where team members feel comfortable sharing ideas.""",
        },
    ]

    for i, data in enumerate(resources_data):
        resource = Resources(
            id=str(uuid4()),
            tenant_id=tenant_id,
            name=data["name"],
            content=data["content"],
            category=data["category"],
            resource_timestamp=base_time + timedelta(hours=i),
            graph_paths=[],
        )
        await resource_repo.put(resource)

    logger.info(f"  ✓ Created {len(resources_data)} resources for {tenant_id}")
    return len(resources_data)


async def test_single_tenant_affinity():
    """Test resource affinity processing for a single tenant."""
    logger.info("=" * 80)
    logger.info("TEST 1: Single Tenant Affinity Processing")
    logger.info("=" * 80)

    tenant_id = TENANTS[0]

    await create_sample_resources_for_tenant(tenant_id)

    worker = DreamingWorker()

    logger.info(f"\nProcessing affinity for {tenant_id}...")
    stats = await worker.process_resource_affinity(tenant_id, use_llm=True)

    logger.info("\nAffinity Processing Results:")
    logger.info(f"  Tenant: {stats['tenant_id']}")
    logger.info(f"  Basic mode processed: {stats['basic_mode_processed']}")
    logger.info(f"  LLM mode processed: {stats['llm_mode_processed']}")
    logger.info(f"  Total resources updated: {stats['total_updated']}")
    logger.info(f"  Total edges added: {stats['total_edges_added']}")

    if "error" in stats:
        logger.error(f"  Error: {stats['error']}")
        return False

    provider = get_provider()
    provider.connect_sync()

    resources_with_paths = provider.execute(
        """
        SELECT name, category, jsonb_array_length(graph_paths) as edge_count
        FROM resources
        WHERE tenant_id = %s
          AND graph_paths IS NOT NULL
          AND jsonb_array_length(graph_paths) > 0
        ORDER BY edge_count DESC
        """,
        (tenant_id,),
    )

    logger.info(f"\nResources with graph edges: {len(resources_with_paths)}")
    for resource in resources_with_paths:
        logger.info(f"  - {resource['name']}: {resource['edge_count']} edges")

    success = len(resources_with_paths) > 0 and stats['total_edges_added'] > 0
    logger.info(f"\n{'✓ PASS' if success else '✗ FAIL'}: Single tenant affinity processing")
    return success


async def test_multi_tenant_affinity():
    """Test resource affinity processing for multiple tenants."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Multi-Tenant Affinity Processing")
    logger.info("=" * 80)

    total_created = 0
    for tenant_id in TENANTS[1:]:
        count = await create_sample_resources_for_tenant(tenant_id)
        total_created += count

    logger.info(f"\nCreated {total_created} resources across {len(TENANTS[1:])} tenants")

    worker = DreamingWorker()

    logger.info("\nProcessing affinity for all tenants...")

    provider = get_provider()
    provider.connect_sync()

    tenants_with_resources = provider.execute(
        """
        SELECT DISTINCT tenant_id, COUNT(*) as resource_count
        FROM resources
        WHERE tenant_id IN %s
        GROUP BY tenant_id
        """,
        (tuple(TENANTS),),
    )

    logger.info(f"Found {len(tenants_with_resources)} tenants with resources")

    all_stats = []
    for tenant_data in tenants_with_resources:
        tid = tenant_data["tenant_id"]
        logger.info(f"\n  Processing {tid} ({tenant_data['resource_count']} resources)...")

        try:
            stats = await worker.process_resource_affinity(tid, use_llm=False)
            all_stats.append(stats)
            logger.info(f"    ✓ {stats['total_updated']} updated, {stats['total_edges_added']} edges")
        except Exception as e:
            logger.error(f"    ✗ Failed: {e}")
            all_stats.append({"tenant_id": tid, "error": str(e)})

    logger.info("\n" + "=" * 80)
    logger.info("MULTI-TENANT SUMMARY")
    logger.info("=" * 80)

    total_updated = sum(s.get("total_updated", 0) for s in all_stats)
    total_edges = sum(s.get("total_edges_added", 0) for s in all_stats)
    errors = sum(1 for s in all_stats if "error" in s)

    logger.info(f"  Tenants processed: {len(all_stats)}")
    logger.info(f"  Total resources updated: {total_updated}")
    logger.info(f"  Total edges added: {total_edges}")
    logger.info(f"  Errors: {errors}")

    success = total_updated > 0 and total_edges > 0 and errors == 0
    logger.info(f"\n{'✓ PASS' if success else '✗ FAIL'}: Multi-tenant affinity processing")
    return success


async def test_config_options():
    """Test configuration options for resource affinity."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Configuration Options")
    logger.info("=" * 80)

    logger.info("\nCurrent configuration:")
    logger.info(f"  dreaming_affinity_enabled: {config.dreaming_affinity_enabled}")
    logger.info(f"  dreaming_affinity_use_llm: {config.dreaming_affinity_use_llm}")
    logger.info(f"  dreaming_lookback_hours: {config.dreaming_lookback_hours}")
    logger.info(f"  dreaming_affinity_basic_batch_size: {config.dreaming_affinity_basic_batch_size}")
    logger.info(f"  dreaming_affinity_llm_batch_size: {config.dreaming_affinity_llm_batch_size}")

    worker = DreamingWorker()

    logger.info("\nTesting with affinity disabled...")
    original_enabled = config.dreaming_affinity_enabled
    config.dreaming_affinity_enabled = False

    stats = await worker.process_resource_affinity(TENANTS[0], use_llm=False)

    config.dreaming_affinity_enabled = original_enabled

    disabled_success = stats.get("enabled") is False

    logger.info(f"  Result: {stats}")
    logger.info(f"  {'✓ PASS' if disabled_success else '✗ FAIL'}: Affinity disabled check")

    return disabled_success


async def display_final_stats():
    """Display final statistics across all tenants."""
    logger.info("\n" + "=" * 80)
    logger.info("FINAL STATISTICS")
    logger.info("=" * 80)

    provider = get_provider()
    provider.connect_sync()

    for tenant_id in TENANTS:
        resources = provider.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN graph_paths IS NOT NULL AND jsonb_array_length(graph_paths) > 0 THEN 1 ELSE 0 END) as with_edges,
                SUM(COALESCE(jsonb_array_length(graph_paths), 0)) as total_edges
            FROM resources
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )

        if resources:
            r = resources[0]
            logger.info(f"\n{tenant_id}:")
            logger.info(f"  Total resources: {r['total']}")
            logger.info(f"  Resources with edges: {r['with_edges']}")
            logger.info(f"  Total edges: {r['total_edges']}")

            if r['with_edges'] and r['with_edges'] > 0:
                avg_edges = r['total_edges'] / r['with_edges']
                logger.info(f"  Average edges per resource: {avg_edges:.1f}")


async def main():
    """Run all end-to-end tests."""
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY required for this test")
        logger.info("Run: export OPENAI_API_KEY=sk-proj-...")
        return

    logger.info("\n" + "=" * 80)
    logger.info("DREAMING END-TO-END TESTS")
    logger.info("=" * 80)

    results = []

    try:
        result1 = await test_single_tenant_affinity()
        results.append(("Single Tenant Affinity", result1))
    except Exception as e:
        logger.error(f"Test 1 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Single Tenant Affinity", False))

    try:
        result2 = await test_multi_tenant_affinity()
        results.append(("Multi-Tenant Affinity", result2))
    except Exception as e:
        logger.error(f"Test 2 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Multi-Tenant Affinity", False))

    try:
        result3 = await test_config_options()
        results.append(("Configuration Options", result3))
    except Exception as e:
        logger.error(f"Test 3 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Configuration Options", False))

    await display_final_stats()

    logger.info("\n" + "=" * 80)
    logger.info("TEST RESULTS SUMMARY")
    logger.info("=" * 80)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"  {status}: {test_name}")

    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)

    logger.info(f"\nTotal: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        logger.info("\n✓ ALL TESTS PASSED")
        logger.info("\nThe dreaming module with resource affinity integration is working correctly!")
    else:
        logger.warning(f"\n✗ {total_tests - total_passed} TESTS FAILED")

    logger.info("")


if __name__ == "__main__":
    asyncio.run(main())
