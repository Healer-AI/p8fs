"""Integration test for tenant-based device storage.

This test verifies that:
1. Device information is properly stored in tenant metadata
2. There is one JWT, one tenant, and one row in the database
3. All device authorization info is accessible via the repository
"""

import asyncio
import pytest
from datetime import datetime
import json

from p8fs_api.repositories.auth_repository import P8FSAuthRepository
from p8fs_auth.models.repository import Tenant
from p8fs_auth.models.auth import Device, DeviceTrustLevel
from p8fs_auth.services.jwt_key_manager import JWTKeyManager
from p8fs_cluster.config.settings import config


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tenant_device_storage():
    """Test that device information is properly stored in tenant metadata."""
    print("\n=== Testing Tenant-Based Device Storage ===")
    
    # Initialize repository
    repo = P8FSAuthRepository()
    jwt_manager = JWTKeyManager()
    
    # Test data
    test_email = "test-device@integration.com"
    test_device_id = "test-device-123"
    test_tenant_id = "tenant-test123"
    test_public_key = "test_public_key_base64_encoded"
    
    print("\n=== Step 1: Create Tenant ===")
    
    # Create tenant
    tenant = Tenant(
        tenant_id=test_tenant_id,
        email=test_email,
        public_key=test_public_key,
        created_at=datetime.utcnow(),
        metadata={
            "devices": {},
            "device_authorizations": {}
        }
    )
    
    created_tenant = await repo.create_tenant(tenant)
    assert created_tenant is not None
    assert created_tenant.tenant_id == test_tenant_id
    print(f"✓ Created tenant: {test_tenant_id}")
    
    # Verify tenant in database
    fetched_tenant = await repo.get_tenant_by_id(test_tenant_id)
    assert fetched_tenant is not None
    assert fetched_tenant.email == test_email
    print(f"✓ Verified tenant in database: {fetched_tenant.email}")
    
    print("\n=== Step 2: Store Device in Tenant ===")
    
    # Create device
    device = Device(
        device_id=test_device_id,
        tenant_id=test_tenant_id,
        email=test_email,
        device_name="Test Integration Device",
        public_key=test_public_key,
        trust_level=DeviceTrustLevel.EMAIL_VERIFIED,
        created_at=datetime.utcnow(),
        last_seen=datetime.utcnow()
    )
    
    # Store device
    await repo.create_device(device)
    print(f"✓ Stored device: {test_device_id}")
    
    # Retrieve device
    retrieved_device = await repo.get_device(test_device_id, test_tenant_id)
    assert retrieved_device is not None
    assert retrieved_device.device_id == test_device_id
    assert retrieved_device.email == test_email
    print(f"✓ Retrieved device from tenant metadata")
    
    print("\n=== Step 3: Store Device Authorization in Tenant ===")
    
    # Store device authorization in tenant metadata
    device_auth_data = {
        "device_code": "test_device_code_xyz",
        "user_code": "TEST-1234",
        "client_id": "test_client",
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": datetime.utcnow().isoformat()
    }
    
    # Update tenant with device authorization
    updated_tenant = await repo.get_tenant_by_id(test_tenant_id)
    if "device_authorizations" not in updated_tenant.metadata:
        updated_tenant.metadata["device_authorizations"] = {}
    
    # Store by normalized user code
    normalized_user_code = device_auth_data["user_code"].upper().replace("-", "")
    updated_tenant.metadata["device_authorizations"][normalized_user_code] = device_auth_data
    
    await repo.update_tenant(updated_tenant)
    print(f"✓ Stored device authorization with user code: {device_auth_data['user_code']}")
    
    # Verify device authorization can be retrieved
    final_tenant = await repo.get_tenant_by_id(test_tenant_id)
    assert "device_authorizations" in final_tenant.metadata
    assert normalized_user_code in final_tenant.metadata["device_authorizations"]
    print(f"✓ Retrieved device authorization from tenant metadata")
    
    print("\n=== Step 4: Create JWT with Tenant Info ===")
    
    # Create JWT token with tenant information
    access_token = await jwt_manager.create_access_token(
        user_id=device.device_id,
        client_id="test_client",
        scope=["read", "write"],
        device_id=device.device_id,
        additional_claims={
            "email": test_email,
            "tenant": test_tenant_id,
            "device_name": device.device_name
        }
    )
    
    assert access_token is not None
    print(f"✓ Created JWT token: {access_token[:50]}...")
    
    # Verify token contains tenant info
    payload = await jwt_manager.verify_token(access_token)
    assert payload["tenant"] == test_tenant_id
    assert payload["email"] == test_email
    assert payload["device_id"] == test_device_id
    print(f"✓ JWT contains tenant info: tenant={payload['tenant']}")
    
    print("\n=== Step 5: Verify Single Source of Truth ===")
    
    # Query database directly to verify single tenant row
    from p8fs.repository.SystemRepository import SystemRepository
    from p8fs.models.p8 import Tenant as CoreTenant
    
    tenant_repo = SystemRepository(CoreTenant)
    all_tenants = await tenant_repo.select(filters={"email": test_email})
    
    assert len(all_tenants) == 1, f"Expected 1 tenant, found {len(all_tenants)}"
    db_tenant = all_tenants[0]
    
    print(f"✓ Single tenant row in database")
    print(f"  - Tenant ID: {db_tenant.tenant_id}")
    print(f"  - Email: {db_tenant.email}")
    print(f"  - Devices in metadata: {len(db_tenant.metadata.get('devices', {}))}")
    print(f"  - Device authorizations: {len(db_tenant.metadata.get('device_authorizations', {}))}")
    
    # Verify all data is in one place
    assert db_tenant.tenant_id == test_tenant_id
    assert test_device_id in db_tenant.metadata.get("devices", {})
    assert normalized_user_code in db_tenant.metadata.get("device_authorizations", {})
    
    print("\n=== ✅ Test Complete: Single Source of Truth Verified ===")
    print(f"- One JWT token created")
    print(f"- One tenant in database") 
    print(f"- One row with all device and authorization info")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_device_authorization_repository_methods():
    """Test the repository methods for device authorization storage."""
    print("\n=== Testing Device Authorization Repository Methods ===")
    
    repo = P8FSAuthRepository()
    
    # Test device authorization storage
    user_code = "ABCD-1234"
    device_auth = {
        "device_code": "long_device_code_xyz",
        "user_code": user_code,
        "client_id": "test_client",
        "status": "pending",
        "created_at": datetime.utcnow().isoformat()
    }
    
    print("\n=== Step 1: Store Device Authorization ===")
    
    # Store device authorization
    success = await repo.store_device_authorization(user_code, device_auth)
    assert success
    print(f"✓ Stored device authorization for user code: {user_code}")
    
    print("\n=== Step 2: Retrieve Device Authorization ===")
    
    # Retrieve by user code
    retrieved = await repo.get_device_authorization(user_code)
    assert retrieved is not None
    assert retrieved["device_code"] == device_auth["device_code"]
    assert retrieved["user_code"] == user_code
    print(f"✓ Retrieved device authorization by user code")
    
    # Test with different formats
    test_formats = [
        user_code.lower(),  # lowercase
        user_code.replace("-", ""),  # no dash
        "ABCD1234"  # normalized
    ]
    
    for format_code in test_formats:
        result = await repo.get_device_authorization(format_code)
        assert result is not None, f"Failed to retrieve with format: {format_code}"
        print(f"✓ Retrieved with format: {format_code}")
    
    print("\n=== Step 3: Update Device Authorization ===")
    
    # Update authorization
    updates = {
        "status": "approved",
        "approved_at": datetime.utcnow().isoformat(),
        "access_token": "test_access_token"
    }
    
    update_success = await repo.update_device_authorization(user_code, updates)
    assert update_success
    print(f"✓ Updated device authorization")
    
    # Verify updates
    updated = await repo.get_device_authorization(user_code)
    assert updated["status"] == "approved"
    assert "approved_at" in updated
    assert updated["access_token"] == "test_access_token"
    print(f"✓ Verified updates: status={updated['status']}")
    
    print("\n=== Step 4: Delete Device Authorization ===")
    
    # Delete authorization
    delete_success = await repo.delete_device_authorization(user_code)
    assert delete_success
    print(f"✓ Deleted device authorization")
    
    # Verify deletion
    deleted = await repo.get_device_authorization(user_code)
    assert deleted is None
    print(f"✓ Verified deletion")
    
    print("\n=== ✅ Repository Methods Test Complete ===")


if __name__ == "__main__":
    # Run both tests
    asyncio.run(test_tenant_device_storage())
    asyncio.run(test_device_authorization_repository_methods())