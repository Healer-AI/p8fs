#!/usr/bin/env python3
"""Verify IMEI-based deterministic tenant ID generation (LOCAL).

This script tests that device registration with the same IMEI
always produces the same tenant ID using local database.

Usage:
    # Run with default PostgreSQL provider
    P8FS_STORAGE_PROVIDER=postgresql uv run python scripts/diagnostics/verify_imei_tenant_local.py

    # Run with TiDB provider
    P8FS_STORAGE_PROVIDER=tidb uv run python scripts/diagnostics/verify_imei_tenant_local.py

Requirements:
    - PostgreSQL or TiDB running locally
    - P8FS_STORAGE_PROVIDER environment variable set
"""

import asyncio
import base64
import hashlib
from cryptography.hazmat.primitives.asymmetric import ed25519


async def test_deterministic_tenant_id():
    """Test that IMEI produces deterministic tenant ID locally."""
    # Import here to ensure proper setup
    from p8fs_api.repositories.auth_repository import P8FSAuthRepository
    from p8fs_auth.services.jwt_key_manager import JWTKeyManager
    from p8fs_auth.services.auth_service import AuthenticationService
    from p8fs_auth.services.mobile_service import MobileAuthenticationService

    # Setup services
    repo = P8FSAuthRepository()
    jwt_mgr = JWTKeyManager()
    auth_svc = AuthenticationService(repository=repo, jwt_manager=jwt_mgr)
    mobile_svc = MobileAuthenticationService(repository=repo, auth_service=auth_svc)

    # Test IMEI
    test_imei = "123456789012345"

    # Calculate expected tenant ID
    expected_hash = hashlib.sha256(test_imei.encode()).hexdigest()[:16]
    expected_tenant_id = f"tenant-{expected_hash}"

    print("=" * 70)
    print("🔍 Testing IMEI-based Deterministic Tenant ID (LOCAL)")
    print("=" * 70)
    print(f"IMEI: {test_imei}")
    print(f"Expected hash: {expected_hash}")
    print(f"Expected tenant_id: {expected_tenant_id}")
    print()

    # Test 1: Register device with IMEI
    print("📱 Test 1: Registering device WITH IMEI")
    print("-" * 70)
    private_key1 = ed25519.Ed25519PrivateKey.generate()
    public_key1_bytes = private_key1.public_key().public_bytes_raw()
    public_key1_b64 = base64.b64encode(public_key1_bytes).decode('utf-8')

    registration1 = await mobile_svc.register_device(
        email="test-imei-1@example.com",
        public_key_base64=public_key1_b64,
        device_name="Test Device 1",
        device_info={"platform": "iOS", "imei": test_imei}
    )

    result1 = await mobile_svc.verify_pending_registration(
        registration_id=registration1["registration_id"],
        verification_code=registration1["verification_code"]
    )

    print(f"✅ Device 1 registered")
    print(f"   Tenant ID: {result1['tenant_id']}")
    print(f"   Matches expected: {result1['tenant_id'] == expected_tenant_id}")
    print()

    # Test 2: Register another device with same IMEI
    print("📱 Test 2: Registering device WITH SAME IMEI (should reuse tenant)")
    print("-" * 70)
    private_key2 = ed25519.Ed25519PrivateKey.generate()
    public_key2_bytes = private_key2.public_key().public_bytes_raw()
    public_key2_b64 = base64.b64encode(public_key2_bytes).decode('utf-8')

    registration2 = await mobile_svc.register_device(
        email="test-imei-2@example.com",
        public_key_base64=public_key2_b64,
        device_name="Test Device 2",
        device_info={"platform": "Android", "imei": test_imei}  # Same IMEI!
    )

    result2 = await mobile_svc.verify_pending_registration(
        registration_id=registration2["registration_id"],
        verification_code=registration2["verification_code"]
    )

    print(f"✅ Device 2 registered")
    print(f"   Tenant ID: {result2['tenant_id']}")
    print(f"   Matches expected: {result2['tenant_id'] == expected_tenant_id}")
    print(f"   Same as Device 1: {result2['tenant_id'] == result1['tenant_id']}")
    print()

    # Test 3: Register device without IMEI (should be random)
    print("📱 Test 3: Registering device WITHOUT IMEI (should be random)")
    print("-" * 70)
    private_key3 = ed25519.Ed25519PrivateKey.generate()
    public_key3_bytes = private_key3.public_key().public_bytes_raw()
    public_key3_b64 = base64.b64encode(public_key3_bytes).decode('utf-8')

    registration3 = await mobile_svc.register_device(
        email="test-no-imei@example.com",
        public_key_base64=public_key3_b64,
        device_name="Test Device 3",
        device_info={"platform": "iOS"}  # No IMEI
    )

    result3 = await mobile_svc.verify_pending_registration(
        registration_id=registration3["registration_id"],
        verification_code=registration3["verification_code"]
    )

    print(f"✅ Device 3 registered")
    print(f"   Tenant ID: {result3['tenant_id']}")
    print(f"   Different from IMEI-based: {result3['tenant_id'] != expected_tenant_id}")
    print()

    # Summary
    print("=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)

    all_tests_passed = (
        result1['tenant_id'] == expected_tenant_id and
        result2['tenant_id'] == expected_tenant_id and
        result1['tenant_id'] == result2['tenant_id'] and
        result3['tenant_id'] != expected_tenant_id
    )

    if all_tests_passed:
        print("✅ ALL TESTS PASSED!")
        print(f"   • Same IMEI produces same tenant ID: {expected_tenant_id}")
        print(f"   • No IMEI produces random tenant ID: {result3['tenant_id']}")
    else:
        print("❌ TESTS FAILED!")
        if result1['tenant_id'] != expected_tenant_id:
            print(f"   • Device 1 tenant ID mismatch")
        if result2['tenant_id'] != expected_tenant_id:
            print(f"   • Device 2 tenant ID mismatch")
        if result1['tenant_id'] != result2['tenant_id']:
            print(f"   • Device 1 and 2 have different tenant IDs (should be same)")
        if result3['tenant_id'] == expected_tenant_id:
            print(f"   • Device 3 without IMEI has IMEI-based tenant ID")

    return all_tests_passed


if __name__ == "__main__":
    success = asyncio.run(test_deterministic_tenant_id())
    exit(0 if success else 1)
