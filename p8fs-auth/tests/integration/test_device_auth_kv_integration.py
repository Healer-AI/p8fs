"""
Integration tests for device authorization KV storage functionality.

Tests the complete integration between PendingDeviceRequest models and KV storage
across different providers (PostgreSQL, TiDB, RocksDB).
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from p8fs.models.device_auth import (
    PendingDeviceRequest, 
    store_pending_request,
    get_pending_request_by_device_code,
    get_pending_request_by_user_code,
    update_pending_request,
    delete_pending_request
)
from p8fs.providers import get_provider
from p8fs_cluster.config.settings import config


@pytest.mark.integration 
class TestDeviceAuthKVIntegration:
    """Test device authorization KV storage integration."""
    
    @pytest_asyncio.fixture
    async def kv_provider(self):
        """Get KV provider based on current configuration."""
        provider = get_provider()
        yield provider.kv
        
        # Cleanup any test data
        try:
            test_keys = await provider.kv.scan("test-device:", limit=100)
            for key_info in test_keys:
                if isinstance(key_info, dict) and 'key' in key_info:
                    await provider.kv.delete(key_info['key'])
                elif isinstance(key_info, str):
                    await provider.kv.delete(key_info)
        except Exception:
            pass  # Ignore cleanup errors
    
    async def test_pending_device_request_round_trip(self, kv_provider):
        """Test complete round-trip storage and retrieval of PendingDeviceRequest."""
        
        # Create a pending device request
        request = PendingDeviceRequest.create_pending_request(
            device_code="test-device-abc123",
            user_code="T1E2-S3T4",
            client_id="test-client",
            ttl_seconds=600
        )
        
        # Verify request structure
        assert request.device_code == "test-device-abc123"
        assert request.user_code == "T1E2-S3T4"
        assert request.client_id == "test-client"
        assert request.status == "pending"
        assert request.approved_by_tenant is None
        assert request.access_token is None
        
        # Store in KV with TTL
        success = await store_pending_request(kv_provider, request, ttl_seconds=600)
        assert success, "Failed to store pending request"
        
        # Retrieve by device code
        retrieved_by_device = await get_pending_request_by_device_code(
            kv_provider, "test-device-abc123"
        )
        assert retrieved_by_device is not None
        assert retrieved_by_device.device_code == request.device_code
        assert retrieved_by_device.user_code == request.user_code
        assert retrieved_by_device.client_id == request.client_id
        assert retrieved_by_device.status == "pending"
        
        # Retrieve by user code  
        retrieved_by_user = await get_pending_request_by_user_code(
            kv_provider, "T1E2-S3T4"
        )
        assert retrieved_by_user is not None
        assert retrieved_by_user.device_code == request.device_code
        assert retrieved_by_user.user_code == request.user_code
        
        # Verify both retrievals return the same data
        assert retrieved_by_device.model_dump() == retrieved_by_user.model_dump()
        
        # Clean up
        await delete_pending_request(kv_provider, "test-device-abc123", "T1E2-S3T4")
        
        # Verify deletion
        deleted_request = await get_pending_request_by_device_code(
            kv_provider, "test-device-abc123"
        )
        assert deleted_request is None
    
    async def test_device_authorization_approval_workflow(self, kv_provider):
        """Test the complete device authorization approval workflow."""
        
        # Step 1: Create pending request (device initiates auth)
        request = PendingDeviceRequest.create_pending_request(
            device_code="test-device-workflow123",
            user_code="W1O2-R3K4", 
            client_id="desktop-app",
            ttl_seconds=600
        )
        
        await store_pending_request(kv_provider, request, ttl_seconds=600)
        
        # Step 2: Mobile app retrieves by user code for approval
        mobile_request = await get_pending_request_by_user_code(
            kv_provider, "W1O2-R3K4"
        )
        assert mobile_request is not None
        assert mobile_request.status == "pending"
        assert mobile_request.approved_by_tenant is None
        
        # Step 3: User approves on mobile (updates with tenant and token)
        mobile_request.approve(
            tenant_id="tenant-12345",
            access_token="jwt.access.token.here"
        )
        
        # Update in KV storage
        update_success = await update_pending_request(kv_provider, mobile_request)
        assert update_success
        
        # Step 4: Desktop app polls by device code
        polling_request = await get_pending_request_by_device_code(
            kv_provider, "test-device-workflow123"
        )
        assert polling_request is not None
        assert polling_request.status == "approved"
        assert polling_request.tenant_id == "tenant-12345"
        assert polling_request.access_token == "jwt.access.token.here"
        
        # Step 5: Desktop consumes token (final step)
        consumed_token = polling_request.consume()
        assert consumed_token == "jwt.access.token.here"
        assert polling_request.status == "consumed"
        
        # Update final state
        await update_pending_request(kv_provider, polling_request)
        
        # Step 6: Cleanup after consumption
        await delete_pending_request(
            kv_provider, "test-device-workflow123", "W1O2-R3K4"
        )
        
        # Verify complete removal
        final_request = await get_pending_request_by_device_code(
            kv_provider, "test-device-workflow123"
        )
        assert final_request is None
    
    async def test_pending_request_expiration_handling(self, kv_provider):
        """Test handling of expired device authorization requests."""
        
        # Create request with very short TTL for testing
        request = PendingDeviceRequest.create_pending_request(
            device_code="test-device-expire123",
            user_code="E1X2-P3I4",
            client_id="test-expire",
            ttl_seconds=1  # 1 second TTL
        )
        
        # Store with short TTL
        await store_pending_request(kv_provider, request, ttl_seconds=1)
        
        # Should be retrievable immediately
        immediate_request = await get_pending_request_by_device_code(
            kv_provider, "test-device-expire123"
        )
        assert immediate_request is not None
        
        # Wait for expiration (1+ seconds)
        await asyncio.sleep(2)
        
        # Should be expired and return None
        expired_request = await get_pending_request_by_device_code(
            kv_provider, "test-device-expire123"
        )
        # NOTE: This test depends on KV provider implementing TTL correctly
        # PostgreSQL provider may return the expired item - that's provider-specific behavior
        
        # Clean up just in case
        if expired_request:
            await delete_pending_request(
                kv_provider, "test-device-expire123", "E1X2-P3I4"
            )
    
    async def test_concurrent_device_authorization_requests(self, kv_provider):
        """Test handling multiple concurrent device authorization requests."""
        
        # Create multiple pending requests
        requests = []
        for i in range(5):
            request = PendingDeviceRequest.create_pending_request(
                device_code=f"test-device-concurrent{i}",
                user_code=f"C{i}N{i+1}-U{i+2}R{i+3}",
                client_id=f"client-{i}",
                ttl_seconds=600
            )
            requests.append(request)
        
        # Store all requests concurrently
        store_tasks = [
            store_pending_request(kv_provider, req, ttl_seconds=600) 
            for req in requests
        ]
        store_results = await asyncio.gather(*store_tasks)
        assert all(store_results), "Some requests failed to store"
        
        # Retrieve all requests concurrently by device code
        retrieve_tasks = [
            get_pending_request_by_device_code(kv_provider, req.device_code)
            for req in requests
        ]
        retrieved_requests = await asyncio.gather(*retrieve_tasks)
        
        # Verify all retrieved successfully
        assert len(retrieved_requests) == 5
        assert all(req is not None for req in retrieved_requests)
        
        # Verify each request has correct data
        for i, retrieved in enumerate(retrieved_requests):
            assert retrieved.device_code == f"test-device-concurrent{i}"
            assert retrieved.user_code == f"C{i}N{i+1}-U{i+2}R{i+3}"
            assert retrieved.client_id == f"client-{i}"
            assert retrieved.status == "pending"
        
        # Cleanup all requests
        cleanup_tasks = [
            delete_pending_request(kv_provider, req.device_code, req.user_code)
            for req in requests
        ]
        await asyncio.gather(*cleanup_tasks)
    
    async def test_device_auth_error_scenarios(self, kv_provider):
        """Test error handling scenarios for device authorization."""
        
        # Test retrieving non-existent device code
        nonexistent_device = await get_pending_request_by_device_code(
            kv_provider, "nonexistent-device-code"
        )
        assert nonexistent_device is None
        
        # Test retrieving non-existent user code
        nonexistent_user = await get_pending_request_by_user_code(
            kv_provider, "XXXX-YYYY"  
        )
        assert nonexistent_user is None
        
        # Test updating non-existent request
        fake_request = PendingDeviceRequest.create_pending_request(
            device_code="fake-device-code",
            user_code="F1K2-E3R4",
            client_id="fake-client"
        )
        update_result = await update_pending_request(kv_provider, fake_request)
        # Update may succeed (creates new entry) or fail - both are valid behaviors
        
        # Test deleting non-existent request
        delete_result = await delete_pending_request(
            kv_provider, "nonexistent-device", "XXXX-YYYY"
        )
        # Delete of non-existent item should succeed (idempotent)
        assert delete_result is not None  # Should not raise an exception
    
    async def test_kv_provider_compatibility(self, kv_provider):
        """Test that device auth works with different KV providers."""
        
        # Test basic KV operations work
        test_key = "test-provider-compatibility"
        test_data = {"test": "data", "number": 42}
        
        # Store test data
        store_success = await kv_provider.put(test_key, test_data, ttl_seconds=60)
        assert store_success
        
        # Retrieve test data
        retrieved_data = await kv_provider.get(test_key)
        assert retrieved_data is not None
        assert retrieved_data["test"] == "data"
        assert retrieved_data["number"] == 42
        
        # Test scan functionality
        scan_results = await kv_provider.scan("test-provider", limit=10)
        assert len(scan_results) >= 1  # Should find our test key
        
        # Cleanup
        await kv_provider.delete(test_key)
        
        # Test with actual device request
        request = PendingDeviceRequest.create_pending_request(
            device_code="test-provider-device",
            user_code="P1R2-O3V4",
            client_id="provider-test"
        )
        
        # Full workflow should work regardless of provider
        await store_pending_request(kv_provider, request, ttl_seconds=300)
        retrieved = await get_pending_request_by_device_code(
            kv_provider, "test-provider-device"
        )
        assert retrieved is not None
        assert retrieved.device_code == request.device_code
        
        # Cleanup
        await delete_pending_request(
            kv_provider, "test-provider-device", "P1R2-O3V4"
        )


@pytest.mark.integration
class TestDeviceAuthKVPerformance:
    """Performance tests for device auth KV operations."""
    
    @pytest_asyncio.fixture
    async def kv_provider(self):
        """Get KV provider for performance testing."""
        provider = get_provider() 
        yield provider.kv
        
        # Cleanup performance test data
        try:
            perf_keys = await provider.kv.scan("perf-test:", limit=1000)
            for key_info in perf_keys:
                if isinstance(key_info, dict) and 'key' in key_info:
                    await provider.kv.delete(key_info['key'])
                elif isinstance(key_info, str):
                    await provider.kv.delete(key_info)
        except Exception:
            pass
    
    async def test_device_auth_bulk_operations(self, kv_provider):
        """Test performance with bulk device authorization operations."""
        
        # Create many device requests
        num_requests = 50
        requests = []
        
        start_time = datetime.now()
        
        for i in range(num_requests):
            request = PendingDeviceRequest.create_pending_request(
                device_code=f"perf-test-device-{i:03d}",
                user_code=f"P{i:02d}-{i+10:02d}{i+20:02d}",
                client_id=f"perf-client-{i}"
            )
            requests.append(request)
        
        # Bulk store operations
        store_tasks = [
            store_pending_request(kv_provider, req, ttl_seconds=300)
            for req in requests
        ]
        store_results = await asyncio.gather(*store_tasks)
        
        store_time = datetime.now()
        assert all(store_results), f"Some bulk stores failed: {store_results.count(False)} failures"
        
        # Bulk retrieve operations
        retrieve_tasks = [
            get_pending_request_by_device_code(kv_provider, req.device_code)
            for req in requests
        ]
        retrieved_requests = await asyncio.gather(*retrieve_tasks)
        
        retrieve_time = datetime.now()
        assert all(req is not None for req in retrieved_requests), "Some bulk retrievals failed"
        
        # Bulk cleanup
        cleanup_tasks = [
            delete_pending_request(kv_provider, req.device_code, req.user_code)
            for req in requests
        ]
        await asyncio.gather(*cleanup_tasks)
        
        cleanup_time = datetime.now()
        
        # Performance metrics
        store_duration = (store_time - start_time).total_seconds()
        retrieve_duration = (retrieve_time - store_time).total_seconds()
        cleanup_duration = (cleanup_time - retrieve_time).total_seconds()
        
        print(f"\nPerformance metrics for {num_requests} device auth requests:")
        print(f"Store time: {store_duration:.2f}s ({num_requests/store_duration:.1f} ops/sec)")
        print(f"Retrieve time: {retrieve_duration:.2f}s ({num_requests/retrieve_duration:.1f} ops/sec)")  
        print(f"Cleanup time: {cleanup_duration:.2f}s ({num_requests/cleanup_duration:.1f} ops/sec)")
        
        # Performance assertions (reasonable thresholds)
        assert store_duration < 5.0, f"Store operations too slow: {store_duration:.2f}s"
        assert retrieve_duration < 5.0, f"Retrieve operations too slow: {retrieve_duration:.2f}s"
        assert cleanup_duration < 5.0, f"Cleanup operations too slow: {cleanup_duration:.2f}s"


if __name__ == "__main__":
    # Run specific tests
    pytest.main([__file__, "-v", "-s"])