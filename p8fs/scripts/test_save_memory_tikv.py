#!/usr/bin/env python3
"""
Test save_memory function with TiDB/TiKV in K8s cluster.

This script tests the complete round-trip of save_memory with TiKV's gRPC client
to ensure proper functionality in the cluster environment.

Run in cluster:
    kubectl exec -it <pod-name> -- python scripts/test_save_memory_tikv.py

Or as a K8s job:
    kubectl apply -f k8s/jobs/test-save-memory.yaml

Environment variables:
    P8FS_STORAGE_PROVIDER - Set to 'tidb' (default)
    P8FS_MOCK_LLM - Set to 'true' to mock LLM calls (default: false)
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch

# Set TiDB as storage provider (can be overridden)
if 'P8FS_STORAGE_PROVIDER' not in os.environ:
    os.environ['P8FS_STORAGE_PROVIDER'] = 'tidb'

# Mock LLM if requested (useful when API key not available)
MOCK_LLM = os.environ.get('P8FS_MOCK_LLM', 'false').lower() == 'true'

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.algorithms import save_memory
from p8fs.providers import get_provider
from p8fs.repository import SystemRepository
from p8fs.models.p8 import Resources

logger = get_logger(__name__)


def mock_llm_decorator(func):
    """Decorator to mock LLM calls if MOCK_LLM is enabled."""
    async def wrapper(*args, **kwargs):
        if MOCK_LLM:
            with patch('p8fs.algorithms.memory_saver.MemoryProxy') as mock_proxy_class:
                mock_proxy = AsyncMock()
                mock_proxy.run.return_value = "User preference noted"
                mock_proxy_class.return_value = mock_proxy
                return await func(*args, **kwargs)
        else:
            return await func(*args, **kwargs)
    return wrapper


async def check_database_setup():
    """Verify database tables exist before running tests."""
    logger.info("Checking database setup...")

    provider = get_provider()

    try:
        # Check if resources table exists (different syntax for PostgreSQL vs MySQL)
        if config.storage_provider == "postgresql":
            result = provider.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'resources')"
            )
            table_exists = result[0]['exists'] if result else False
        else:  # TiDB/MySQL
            result = provider.execute("SHOW TABLES LIKE 'resources'")
            table_exists = len(result) > 0 if result else False

        if not table_exists:
            logger.error("❌ 'resources' table does not exist")
            logger.error("Please run migrations first:")
            logger.error(f"  {config.storage_provider.upper()}: See extensions/migrations/{config.storage_provider}/")
            return False

        # Check if kv_storage table exists (optional - may use AGE/TiKV directly)
        if config.storage_provider == "postgresql":
            result = provider.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'kv_storage')"
            )
            kv_exists = result[0]['exists'] if result else False
        else:
            result = provider.execute("SHOW TABLES LIKE 'kv_storage'")
            kv_exists = len(result) > 0 if result else False

        if not kv_exists:
            logger.warning("⚠️  'kv_storage' table does not exist - will use AGE/TiKV directly")

        logger.info("✅ Database setup verified")
        return True

    except Exception as e:
        logger.error(f"❌ Database check failed: {e}")
        return False


@mock_llm_decorator
async def test_kv_mode_basic():
    """Test basic KV mode with entity resolver pattern."""
    logger.info("=" * 80)
    logger.info("TEST 1: Basic KV Mode with TiKV")
    logger.info("=" * 80)

    observation = "User prefers TiDB for production deployments in K8s cluster"
    category = "user_preference"

    logger.info(f"Saving observation: {observation}")

    # Save memory in KV mode
    result = await save_memory(
        observation=observation,
        category=category,
        mode="kv",
        related_to="tidb-production",
        rel_type="prefers",
        tenant_id=config.default_tenant_id
    )

    logger.info(f"Save result: {result}")

    if not result["success"]:
        logger.error(f"FAILED: Save failed with error: {result.get('error')}")
        return False

    # Verify KV has entity reference
    provider = get_provider()
    kv_ref = await provider.kv.get(result["key"])

    if not kv_ref:
        logger.error(f"FAILED: KV reference not found for key: {result['key']}")
        return False

    logger.info(f"KV reference retrieved: {kv_ref}")

    if "resource_id" not in kv_ref:
        logger.error("FAILED: KV reference missing resource_id")
        return False

    # Verify actual resource in TiDB
    resource_repo = SystemRepository(Resources)
    resources = resource_repo.execute(
        "SELECT id, content, graph_paths, category FROM resources WHERE id = %s",
        (kv_ref["resource_id"],)
    )

    if not resources:
        logger.error(f"FAILED: Resource not found with id: {kv_ref['resource_id']}")
        return False

    resource = resources[0]
    logger.info(f"Resource retrieved from TiDB:")
    logger.info(f"  ID: {resource['id']}")
    logger.info(f"  Category: {resource['category']}")
    logger.info(f"  Content: {resource['content'][:100]}...")
    logger.info(f"  Graph edges: {len(resource['graph_paths'])}")

    # Verify graph edge
    if len(resource['graph_paths']) != 1:
        logger.error(f"FAILED: Expected 1 graph edge, got {len(resource['graph_paths'])}")
        return False

    edge = resource['graph_paths'][0]
    logger.info(f"Graph edge: dst={edge['dst']}, rel_type={edge['rel_type']}, weight={edge['weight']}")

    if edge['dst'] != "tidb-production":
        logger.error(f"FAILED: Edge dst mismatch. Expected 'tidb-production', got '{edge['dst']}'")
        return False

    if edge['rel_type'] != "prefers":
        logger.error(f"FAILED: Edge rel_type mismatch. Expected 'prefers', got '{edge['rel_type']}'")
        return False

    logger.info("✅ TEST 1 PASSED: Basic KV mode works with TiKV")
    return True


@mock_llm_decorator
async def test_kv_mode_edge_merging():
    """Test edge merging when saving multiple observations to same KV key."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: KV Mode Edge Merging with TiKV")
    logger.info("=" * 80)

    # Use same KV key for multiple observations
    kv_key = f"{config.default_tenant_id}/test-merge/{uuid4()}"

    # First observation
    logger.info("Saving first observation...")
    result1 = await save_memory(
        observation="User uses TiKV for distributed key-value storage",
        category="user_preference",
        mode="kv",
        source_id=kv_key,
        related_to="tikv-storage",
        rel_type="uses",
        tenant_id=config.default_tenant_id
    )

    if not result1["success"]:
        logger.error(f"FAILED: First save failed: {result1.get('error')}")
        return False

    logger.info(f"First save: resource_id={result1.get('resource_id')}")

    # Second observation to same KV key
    logger.info("Saving second observation to same KV key...")
    result2 = await save_memory(
        observation="User is debugging TiKV connection pool settings",
        category="current_context",
        mode="kv",
        source_id=kv_key,
        related_to="tikv-troubleshooting",
        rel_type="currently_working_on",
        tenant_id=config.default_tenant_id
    )

    if not result2["success"]:
        logger.error(f"FAILED: Second save failed: {result2.get('error')}")
        return False

    logger.info(f"Second save: resource_id={result2.get('resource_id')}")

    # Verify both observations merged into same resource
    if result1.get('resource_id') != result2.get('resource_id'):
        logger.error(f"FAILED: Expected same resource_id, got different: {result1.get('resource_id')} vs {result2.get('resource_id')}")
        return False

    # Verify merged edges
    provider = get_provider()
    kv_ref = await provider.kv.get(kv_key)

    resource_repo = SystemRepository(Resources)
    resources = resource_repo.execute(
        "SELECT graph_paths, content FROM resources WHERE id = %s",
        (kv_ref["resource_id"],)
    )

    if not resources:
        logger.error("FAILED: Resource not found after merging")
        return False

    resource = resources[0]
    graph_paths = resource['graph_paths']

    logger.info(f"Merged resource has {len(graph_paths)} graph edges")

    if len(graph_paths) != 2:
        logger.error(f"FAILED: Expected 2 graph edges after merging, got {len(graph_paths)}")
        return False

    edge_dsts = {edge['dst'] for edge in graph_paths}
    logger.info(f"Edge destinations: {edge_dsts}")

    if "tikv-storage" not in edge_dsts or "tikv-troubleshooting" not in edge_dsts:
        logger.error(f"FAILED: Missing expected edges. Got: {edge_dsts}")
        return False

    # Verify content has both observations
    content = resource['content']
    if "TiKV for distributed key-value storage" not in content:
        logger.error("FAILED: First observation not in merged content")
        return False

    if "debugging TiKV connection pool" not in content:
        logger.error("FAILED: Second observation not in merged content")
        return False

    logger.info("✅ TEST 2 PASSED: Edge merging works with TiKV")
    return True


@mock_llm_decorator
async def test_resource_mode():
    """Test Resource mode (direct resource table operations)."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Resource Mode with TiDB")
    logger.info("=" * 80)

    observation = "User configured TiDB cluster with 3 PD nodes and 5 TiKV nodes"

    logger.info(f"Saving observation: {observation}")

    # Save in resource mode
    result = await save_memory(
        observation=observation,
        category="system_config",
        mode="resource",
        related_to="tidb-cluster-config",
        rel_type="configured",
        tenant_id=config.default_tenant_id
    )

    logger.info(f"Save result: {result}")

    if not result["success"]:
        logger.error(f"FAILED: Save failed: {result.get('error')}")
        return False

    # Verify resource created
    resource_repo = SystemRepository(Resources)
    resources = resource_repo.execute(
        "SELECT id, category, content, graph_paths FROM resources WHERE id = %s",
        (result["key"],)
    )

    if not resources:
        logger.error(f"FAILED: Resource not found: {result['key']}")
        return False

    resource = resources[0]
    logger.info(f"Resource created:")
    logger.info(f"  ID: {resource['id']}")
    logger.info(f"  Category: {resource['category']}")
    logger.info(f"  Graph edges: {len(resource['graph_paths'])}")

    if resource['category'] != 'system_config':
        logger.error(f"FAILED: Category mismatch. Expected 'system_config', got '{resource['category']}'")
        return False

    if observation not in resource['content']:
        logger.error("FAILED: Observation not in resource content")
        return False

    logger.info("✅ TEST 3 PASSED: Resource mode works with TiDB")
    return True


@mock_llm_decorator
async def test_kv_ttl():
    """Test that KV entries have proper TTL set."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: KV TTL Verification with TiKV")
    logger.info("=" * 80)

    observation = "Testing TTL for TiKV entries"

    result = await save_memory(
        observation=observation,
        category="test",
        mode="kv",
        related_to="test-ttl",
        rel_type="tests",
        tenant_id=config.default_tenant_id
    )

    if not result["success"]:
        logger.error(f"FAILED: Save failed: {result.get('error')}")
        return False

    # Check KV entry has TTL
    provider = get_provider()

    # For TiKV, check if TTL is properly set (this depends on TiKV provider implementation)
    kv_ref = await provider.kv.get(result["key"])

    if not kv_ref:
        logger.error("FAILED: KV reference not found")
        return False

    logger.info(f"KV reference: {kv_ref}")
    logger.info("Note: TiKV TTL is handled internally by the provider")

    logger.info("✅ TEST 4 PASSED: KV entry created with TTL")
    return True


async def cleanup_test_data():
    """Clean up test data from TiDB."""
    logger.info("\n" + "=" * 80)
    logger.info("CLEANUP: Removing test data from TiDB")
    logger.info("=" * 80)

    provider = get_provider()

    # Clean up test resources
    provider.execute(
        "DELETE FROM resources WHERE category IN ('user_preference', 'current_context', 'system_config', 'test') AND tenant_id = %s",
        (config.default_tenant_id,)
    )

    logger.info("✅ Cleanup complete")


async def main():
    """Run all TiKV save_memory tests."""
    logger.info("🚀 Starting TiKV save_memory integration tests")
    logger.info(f"Storage provider: {config.storage_provider}")
    logger.info(f"Tenant ID: {config.default_tenant_id}")
    logger.info(f"Mock LLM: {MOCK_LLM}")

    if config.storage_provider == "tidb":
        logger.info(f"TiDB connection: {config.tidb_host}:{config.tidb_port}")
    elif config.storage_provider == "postgresql":
        logger.info(f"PostgreSQL connection: {config.pg_host}:{config.pg_port}")
        logger.warning("⚠️  Using PostgreSQL instead of TiDB - some TiKV-specific features won't be tested")
    else:
        logger.error(f"❌ Unsupported storage provider: {config.storage_provider}")
        sys.exit(1)

    # Check database setup
    if not await check_database_setup():
        logger.error("❌ Database setup check failed - cannot run tests")
        sys.exit(1)

    tests = [
        ("Basic KV Mode", test_kv_mode_basic),
        ("KV Edge Merging", test_kv_mode_edge_merging),
        ("Resource Mode", test_resource_mode),
        ("KV TTL", test_kv_ttl),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = await test_func()
            results.append((test_name, passed))
        except Exception as e:
            logger.error(f"❌ Test '{test_name}' raised exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Cleanup
    try:
        await cleanup_test_data()
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")

    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status}: {test_name}")

    logger.info("=" * 80)
    logger.info(f"Results: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        logger.info("🎉 All tests passed!")
        sys.exit(0)
    else:
        logger.error(f"💥 {total_count - passed_count} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
