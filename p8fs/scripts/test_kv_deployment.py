"""Deployment verification script for KV storage with TTL support.

This script tests KV round-trip operations with TTL to ensure the fix for
dual-backend storage is working correctly. Designed to run on cluster pods
where TiKV gRPC endpoints are accessible.

Usage:
    # Run on cluster pod
    kubectl exec -n p8fs <pod-name> -- python scripts/test_kv_deployment.py

    # Or copy to pod and run
    kubectl cp scripts/test_kv_deployment.py p8fs/<pod-name>:/tmp/
    kubectl exec -n p8fs <pod-name> -- python /tmp/test_kv_deployment.py

Expected behavior:
    - PUT with TTL stores in table storage
    - GET retrieves from table storage first, then TiKV
    - Round-trip succeeds for TTL-based keys
"""

import asyncio
import sys
from datetime import datetime, timezone


async def test_kv_with_ttl():
    """Test KV round-trip with TTL to verify dual-backend fix."""
    print("=" * 60)
    print("KV Deployment Verification Test")
    print("=" * 60)

    try:
        from p8fs.providers import get_provider
        from p8fs_cluster.config.settings import config

        print(f"\nEnvironment: {config.environment}")
        print(f"Storage Provider: {config.storage_provider}")
        print(f"TiKV Endpoints: {getattr(config, 'tikv_endpoints', 'Not configured')}")

        provider = get_provider()
        kv = provider.kv

        print(f"\nKV Provider: {kv.__class__.__name__}")

        # Test 1: Basic round-trip with TTL
        print("\n" + "-" * 60)
        print("Test 1: Basic KV round-trip with TTL")
        print("-" * 60)

        test_key = "deployment_test_basic"
        test_value = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "test": "deployment_verification",
            "provider": config.storage_provider
        }

        print(f"Key: {test_key}")
        print(f"Value: {test_value}")
        print(f"TTL: 60 seconds")

        # PUT with TTL
        print("\n1. Executing PUT with TTL...")
        success = await kv.put(test_key, test_value, ttl_seconds=60)
        print(f"   Result: {'SUCCESS' if success else 'FAILED'}")

        if not success:
            print("\n❌ FAILED: PUT operation failed")
            return False

        # GET immediately
        print("\n2. Executing GET...")
        retrieved = await kv.get(test_key)
        print(f"   Retrieved: {retrieved}")
        print(f"   Type: {type(retrieved)}")

        # Verify
        if retrieved is None:
            print("\n❌ FAILED: GET returned None")
            return False

        if not isinstance(retrieved, dict):
            print(f"\n❌ FAILED: Expected dict, got {type(retrieved)}")
            return False

        if retrieved.get("test") != "deployment_verification":
            print(f"\n❌ FAILED: Value mismatch")
            print(f"   Expected: deployment_verification")
            print(f"   Got: {retrieved.get('test')}")
            return False

        print("\n✅ Test 1 PASSED: Basic round-trip works")

        # Test 2: Multiple keys with different TTLs
        print("\n" + "-" * 60)
        print("Test 2: Multiple keys with varying TTLs")
        print("-" * 60)

        test_cases = [
            ("deployment_test_short", {"ttl": "short"}, 30),
            ("deployment_test_medium", {"ttl": "medium"}, 120),
            ("deployment_test_long", {"ttl": "long"}, 300),
        ]

        for key, value, ttl in test_cases:
            print(f"\nKey: {key}, TTL: {ttl}s")
            success = await kv.put(key, value, ttl_seconds=ttl)
            if not success:
                print(f"   ❌ PUT failed")
                return False

            retrieved = await kv.get(key)
            if retrieved is None or retrieved.get("ttl") != value["ttl"]:
                print(f"   ❌ GET failed or value mismatch")
                return False

            print(f"   ✅ Success")

        print("\n✅ Test 2 PASSED: Multiple TTL operations work")

        # Test 3: Overwrite with different TTL
        print("\n" + "-" * 60)
        print("Test 3: Overwrite existing key with new TTL")
        print("-" * 60)

        overwrite_key = "deployment_test_overwrite"

        # Initial value
        initial = {"version": 1}
        await kv.put(overwrite_key, initial, ttl_seconds=60)

        # Overwrite
        updated = {"version": 2, "updated": True}
        await kv.put(overwrite_key, updated, ttl_seconds=120)

        # Verify
        retrieved = await kv.get(overwrite_key)
        if retrieved is None or retrieved.get("version") != 2:
            print(f"   ❌ Overwrite failed")
            return False

        print(f"   ✅ Overwrite successful")
        print("\n✅ Test 3 PASSED: Overwrite operations work")

        # Test 4: Scan functionality
        print("\n" + "-" * 60)
        print("Test 4: Scan for keys with prefix")
        print("-" * 60)

        scan_prefix = "deployment_test_"
        results = await kv.scan(scan_prefix, limit=10)

        print(f"\nScan prefix: {scan_prefix}")
        print(f"Results found: {len(results)}")

        if len(results) < 4:  # We created at least 4 keys with this prefix
            print(f"   ❌ Expected at least 4 results, got {len(results)}")
            return False

        print("   ✅ Scan returned expected results")
        print("\n✅ Test 4 PASSED: Scan functionality works")

        # Summary
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✅")
        print("=" * 60)
        print("\nKV storage with TTL is working correctly!")
        print("The dual-backend fix (table storage + TiKV) is functioning as expected.")
        return True

    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        print("\nTraceback:")
        print(traceback.format_exc())
        return False


def main():
    """Run the deployment verification test."""
    result = asyncio.run(test_kv_with_ttl())

    if result:
        print("\n🎉 Deployment verification SUCCESSFUL")
        sys.exit(0)
    else:
        print("\n💥 Deployment verification FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
