#!/usr/bin/env python3
"""
Quick smoke test to verify REM environment is ready.

This minimal script verifies:
- TiDB connection works
- KV storage is accessible
- Basic table structure exists
- Embedding provider is configured

Run this first to ensure the environment is ready for comprehensive tests.
"""

import sys
import asyncio
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


async def smoke_test():
    """Run quick smoke test of REM environment."""
    logger.info("=" * 80)
    logger.info("REM SMOKE TEST")
    logger.info("=" * 80)

    passed = 0
    failed = 0

    # Test 1: Check configuration
    logger.info("\n1. Checking configuration...")
    try:
        logger.info(f"   Provider: {config.storage_provider}")
        logger.info(f"   Environment: {config.environment}")
        logger.info(f"   Default model: {config.default_model}")

        if config.storage_provider == "tidb":
            logger.info(f"   TiDB host: {config.tidb_host}:{config.tidb_port}")
        elif config.storage_provider == "postgresql":
            logger.info(f"   PostgreSQL host: {config.pg_host}:{config.pg_port}")

        logger.info("   ✓ Configuration loaded")
        passed += 1
    except Exception as e:
        logger.error(f"   ✗ Configuration error: {e}")
        failed += 1

    # Test 2: Provider connection
    logger.info("\n2. Testing database connection...")
    try:
        from p8fs.providers import get_provider

        provider = get_provider()
        provider.connect_sync()

        logger.info(f"   ✓ Connected to {config.storage_provider}")
        passed += 1
    except Exception as e:
        logger.error(f"   ✗ Connection failed: {e}")
        failed += 1
        return 1

    # Test 3: KV storage
    logger.info("\n3. Testing KV storage...")
    try:
        kv = provider.kv
        test_key = "test-tenant/smoke-test/verify"
        test_value = {"test": "smoke-test-value"}

        await kv.put(test_key, test_value)
        retrieved = await kv.get(test_key)

        if retrieved and retrieved.get("test") == "smoke-test-value":
            logger.info("   ✓ KV storage working")
            passed += 1

            # Cleanup
            await kv.delete(test_key)
        else:
            logger.error(f"   ✗ KV storage read/write mismatch: {retrieved}")
            failed += 1
    except Exception as e:
        logger.error(f"   ✗ KV storage error: {e}")
        failed += 1

    # Test 4: Resources table
    logger.info("\n4. Checking resources table...")
    try:
        conn = provider.connect_sync()
        result = provider.execute(conn, "SELECT COUNT(*) as count FROM resources WHERE tenant_id = 'test-tenant'")
        count = result[0]["count"] if result else 0

        logger.info(f"   ✓ Resources table accessible (found {count} test resources)")
        passed += 1
    except Exception as e:
        logger.error(f"   ✗ Resources table error: {e}")
        failed += 1

    # Test 5: Moments table
    logger.info("\n5. Checking moments table...")
    try:
        conn = provider.connect_sync()
        result = provider.execute(conn, "SELECT COUNT(*) as count FROM moments WHERE tenant_id = 'test-tenant'")
        count = result[0]["count"] if result else 0

        logger.info(f"   ✓ Moments table accessible (found {count} test moments)")
        passed += 1
    except Exception as e:
        logger.error(f"   ✗ Moments table error: {e}")
        failed += 1

    # Test 6: Embeddings table
    logger.info("\n6. Checking embeddings table...")
    try:
        conn = provider.connect_sync()
        result = provider.execute(
            conn,
            "SELECT COUNT(*) as count FROM embeddings.resources_embeddings WHERE tenant_id = 'test-tenant'"
        )
        count = result[0]["count"] if result else 0

        logger.info(f"   ✓ Embeddings table accessible (found {count} test embeddings)")
        passed += 1
    except Exception as e:
        logger.error(f"   ✗ Embeddings table error: {e}")
        failed += 1

    # Test 7: Embedding service (optional)
    logger.info("\n7. Testing embedding service...")
    try:
        if config.openai_api_key:
            # Quick test with minimal text
            embeddings = provider.generate_embeddings_batch(["test"])

            if embeddings and len(embeddings) > 0 and len(embeddings[0]) > 0:
                logger.info(f"   ✓ Embedding service working (dimension: {len(embeddings[0])})")
                passed += 1
            else:
                logger.error("   ✗ Embedding service returned empty result")
                failed += 1
        else:
            logger.warning("   ⚠ No OpenAI API key configured (semantic search will not work)")
            logger.info("   ○ Skipping embedding service test")
    except Exception as e:
        logger.error(f"   ✗ Embedding service error: {e}")
        failed += 1

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SMOKE TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")

    if failed == 0:
        logger.info("\n✓ Environment is ready for REM testing")
        logger.info("\nRun comprehensive tests with:")
        logger.info("  python scripts/rem/test_tidb_rem_comprehensive.py")
        return 0
    else:
        logger.error("\n✗ Environment has issues - fix errors above before running tests")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(smoke_test())
    sys.exit(exit_code)
