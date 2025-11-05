"""
Simple integration test for device authorization KV storage.

Verifies that device auth KV operations work correctly with the current provider.
"""

import pytest
import asyncio
from p8fs.models.device_auth import (
    PendingDeviceRequest,
    store_pending_request,
    get_pending_request_by_device_code,
    get_pending_request_by_user_code,
    delete_pending_request
)
from p8fs.providers import get_provider


def test_device_auth_kv_round_trip():
    """Test device auth KV storage round-trip using sync wrapper."""
    
    async def async_test():
        # Get KV provider
        provider = get_provider()
        kv = provider.kv
        
        # Create a device request
        request = PendingDeviceRequest.create_pending_request(
            device_code="test-device-123",
            user_code="T1S2-T3T4",
            client_id="test-client",
            ttl_seconds=300
        )
        
        try:
            # Store the request
            store_result = await store_pending_request(kv, request, ttl_seconds=300)
            assert store_result, "Failed to store device request"
            
            # Retrieve by device code
            retrieved_device = await get_pending_request_by_device_code(kv, "test-device-123")
            assert retrieved_device is not None, "Failed to retrieve by device code"
            assert retrieved_device.device_code == "test-device-123"
            assert retrieved_device.user_code == "T1S2-T3T4"
            assert retrieved_device.client_id == "test-client"
            assert retrieved_device.status == "pending"
            
            # Retrieve by user code
            retrieved_user = await get_pending_request_by_user_code(kv, "T1S2-T3T4")
            assert retrieved_user is not None, "Failed to retrieve by user code"
            assert retrieved_user.device_code == "test-device-123"
            
            # Verify both retrievals return same data
            assert retrieved_device.model_dump() == retrieved_user.model_dump()
            
            print("✅ Device auth KV round-trip test passed!")
            
        finally:
            # Cleanup
            await delete_pending_request(kv, "test-device-123", "T1S2-T3T4")
    
    # Run the async test
    asyncio.run(async_test())


def test_device_approval_workflow():
    """Test the complete device approval workflow."""
    
    async def async_workflow():
        provider = get_provider()
        kv = provider.kv
        
        # Step 1: Create pending request
        request = PendingDeviceRequest.create_pending_request(
            device_code="workflow-device-456",
            user_code="W1R2-K3F4",
            client_id="workflow-client"
        )
        
        try:
            # Store initial request
            await store_pending_request(kv, request, ttl_seconds=300)
            
            # Step 2: Mobile retrieves for approval
            mobile_request = await get_pending_request_by_user_code(kv, "W1R2-K3F4")
            assert mobile_request is not None
            assert mobile_request.status == "pending"
            
            # Step 3: User approves
            mobile_request.approve(tenant_id="tenant-789", access_token="jwt.token.here")
            
            # Step 4: Update approval in storage  
            from p8fs.models.device_auth import update_pending_request
            await update_pending_request(kv, mobile_request)
            
            # Step 5: Desktop polls for result
            polling_request = await get_pending_request_by_device_code(kv, "workflow-device-456")
            assert polling_request is not None
            assert polling_request.status == "approved"
            assert polling_request.approved_by_tenant == "tenant-789"
            assert polling_request.access_token == "jwt.token.here"
            
            # Step 6: Consume token
            consumed_token = polling_request.consume()
            assert consumed_token == "jwt.token.here"
            assert polling_request.status == "consumed"
            
            print("✅ Device approval workflow test passed!")
            
        finally:
            # Cleanup
            await delete_pending_request(kv, "workflow-device-456", "W1R2-K3F4")
    
    asyncio.run(async_workflow())


def test_kv_basic_operations():
    """Test basic KV operations work correctly."""
    
    async def test_kv():
        provider = get_provider()
        kv = provider.kv
        
        # Test put/get
        test_data = {"test": "data", "number": 42}
        put_result = await kv.put("test-key-basic", test_data, ttl_seconds=60)
        assert put_result, "Failed to put test data"
        
        get_result = await kv.get("test-key-basic")
        assert get_result is not None, "Failed to get test data"
        assert get_result["test"] == "data"
        assert get_result["number"] == 42
        
        # Test scan
        scan_results = await kv.scan("test-key", limit=10)
        assert len(scan_results) >= 1, "Scan should find at least one key"
        
        # Test delete
        await kv.delete("test-key-basic")
        deleted_result = await kv.get("test-key-basic")
        assert deleted_result is None, "Key should be deleted"
        
        print("✅ Basic KV operations test passed!")
    
    asyncio.run(test_kv())


if __name__ == "__main__":
    print("Running device auth KV integration tests...")
    
    try:
        test_kv_basic_operations()
        test_device_auth_kv_round_trip()
        test_device_approval_workflow()
        print("\n🎉 All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise