#!/usr/bin/env python3
"""Verify IMEI-based deterministic tenant ID generation using DEV endpoint.

This script tests IMEI-based tenant IDs using the development endpoint
which bypasses email verification. Useful for quick testing.

⚠️ WARNING: The dev endpoint does NOT use IMEI-based tenant IDs.
   It uses the default dev tenant (tenant-test) for convenience.
   Use verify_imei_tenant_remote.py for testing the production flow.

Usage:
    # Test against local server
    uv run python scripts/diagnostics/verify_imei_tenant_dev.py \\
        --server http://localhost:8000

    # Test against remote server
    uv run python scripts/diagnostics/verify_imei_tenant_dev.py \\
        --server https://p8fs.eepis.ai

Environment Variables:
    P8FS_DEV_TOKEN: Development token (required)
                    Default: p8fs-dev-dHMZAB_dK8JR6ps-zLBSBTfBeoNdXu2KcpNywjDfD58

    DEV_TOKEN_SECRET: Alternative name for dev token

Notes:
    - Dev endpoint uses default tenant (tenant-test), not IMEI-based
    - For testing IMEI logic, use verify_imei_tenant_remote.py instead
    - Dev token can be found in p8fs-cluster/src/p8fs_cluster/config/settings.py
"""

import argparse
import asyncio
import base64
import hashlib
import os
import sys
from cryptography.hazmat.primitives.asymmetric import ed25519

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Install with: pip install httpx")
    sys.exit(1)


async def test_dev_endpoint(server_url: str, dev_token: str):
    """Test device registration via dev endpoint.

    Args:
        server_url: Server URL to test against
        dev_token: Development authentication token

    Returns:
        True if test succeeds, False otherwise
    """

    test_imei = "999888777666555"
    expected_hash = hashlib.sha256(test_imei.encode()).hexdigest()[:16]
    expected_tenant_id = f"tenant-{expected_hash}"

    print("=" * 70)
    print(f"🌐 Testing Dev Endpoint: {server_url}")
    print("=" * 70)
    print(f"Test IMEI: {test_imei}")
    print(f"Expected if IMEI worked: {expected_tenant_id}")
    print()
    print("⚠️  NOTE: Dev endpoint uses default tenant (tenant-test)")
    print("   It does NOT use IMEI-based tenant IDs")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test with IMEI
        print("📱 Test 1: Register with IMEI via dev endpoint")
        print("-" * 70)

        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key_b64 = base64.b64encode(
            private_key.public_key().public_bytes_raw()
        ).decode('utf-8')

        payload = {
            "email": "dev-test@example.com",
            "public_key": public_key_b64,
            "device_info": {
                "platform": "iOS",
                "model": "iPhone 15",
                "imei": test_imei,
                "device_name": "Dev Test Device"
            }
        }

        headers = {
            "X-Dev-Token": dev_token,
            "X-Dev-Email": "dev-test@example.com",
            "X-Dev-Code": "test123"
        }

        print(f"POST {server_url}/api/v1/auth/dev/register")
        print(f"Headers: X-Dev-Token=<hidden>, X-Dev-Email={headers['X-Dev-Email']}")
        print(f"Payload: imei={test_imei}")

        try:
            response = await client.post(
                f"{server_url}/api/v1/auth/dev/register",
                json=payload,
                headers=headers
            )

            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                tenant_id = result.get("tenant_id")

                print(f"✅ Registration succeeded")
                print(f"   Tenant ID: {tenant_id}")
                print(f"   Expected (IMEI-based): {expected_tenant_id}")
                print(f"   Match: {tenant_id == expected_tenant_id}")
                print()

                if tenant_id == "tenant-test":
                    print("✅ EXPECTED: Dev endpoint returned default tenant (tenant-test)")
                    print("   This is correct behavior for the dev endpoint.")
                    print()
                    print("ℹ️  To test IMEI-based tenant IDs, use:")
                    print("   scripts/diagnostics/verify_imei_tenant_remote.py")
                    return True
                elif tenant_id == expected_tenant_id:
                    print("⚠️  UNEXPECTED: Dev endpoint returned IMEI-based tenant!")
                    print("   Dev endpoint should use tenant-test, not IMEI logic.")
                    return False
                else:
                    print(f"❌ UNEXPECTED: Got tenant {tenant_id}")
                    print("   Expected either tenant-test (dev) or IMEI-based tenant")
                    return False
            else:
                print(f"❌ Request failed: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Request error: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Test dev endpoint (does NOT use IMEI-based tenant IDs)"
    )

    parser.add_argument('--server', default='http://localhost:8000',
                       help='Server URL (default: http://localhost:8000)')

    args = parser.parse_args()

    # Get dev token from environment
    dev_token = os.getenv("P8FS_DEV_TOKEN") or os.getenv("DEV_TOKEN_SECRET")

    if not dev_token:
        # Use default from settings.py
        dev_token = "p8fs-dev-dHMZAB_dK8JR6ps-zLBSBTfBeoNdXu2KcpNywjDfD58"
        print("⚠️  Using default dev token from settings.py")
        print(f"   Token: {dev_token[:20]}...")
        print()

    success = asyncio.run(test_dev_endpoint(args.server, dev_token))

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    if success:
        print("✅ Dev endpoint behaving as expected (returns tenant-test)")
        print()
        print("To test IMEI-based tenant IDs, use the production flow:")
        print("  scripts/diagnostics/verify_imei_tenant_remote.py register --email you@email.com")
    else:
        print("❌ Dev endpoint behavior unexpected")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
