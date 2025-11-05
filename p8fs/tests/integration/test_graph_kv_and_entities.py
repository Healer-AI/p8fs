"""Integration test for graph-based KV storage, node operations, and entity indexing.

This test demonstrates:
1. KV storage for temporary device auth requests
2. Direct node operations (add/get) outside the entity system  
3. Entity indexing and retrieval through get_entities
"""

import pytest
import asyncio
from datetime import datetime
import json
from typing import Any

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers.postgresql import PostgreSQLProvider

logger = get_logger(__name__)


class TestGraphKVAndEntities:
    """Test graph operations, KV storage, and entity indexing."""
    
    @pytest.fixture(scope="class")
    def provider(self):
        """Get PostgreSQL provider instance."""
        provider = PostgreSQLProvider()
        # Ensure we have a fresh connection
        provider.connect_sync()
        return provider
    
    def test_01_kv_device_auth_flow(self, provider):
        """Test KV storage for device authorization flow."""
        logger.info("Testing KV storage for device auth...")
        
        # Get KV provider
        kv = provider.kv
        
        # Create a device auth request
        device_code = "test-device-123"
        user_code = "A1B2-C3D4"
        
        device_auth_data = {
            "device_code": device_code,
            "user_code": user_code,
            "client_id": "desktop_app",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Store with TTL (10 minutes)
        success = asyncio.run(kv.put(f"device-auth:{device_code}", device_auth_data, ttl_seconds=600))
        assert success, "Failed to store device auth request"
        
        # Also store by user code for lookup
        success = asyncio.run(kv.put(f"user-code:{user_code}", {"device_code": device_code}, ttl_seconds=600))
        assert success, "Failed to store user code mapping"
        
        # Retrieve by device code
        retrieved = asyncio.run(kv.get(f"device-auth:{device_code}"))
        assert retrieved is not None, "Failed to retrieve device auth"
        assert retrieved["client_id"] == "desktop_app"
        assert retrieved["status"] == "pending"
        
        # Find by user code
        user_code_data = asyncio.run(kv.get(f"user-code:{user_code}"))
        assert user_code_data is not None, "Failed to retrieve by user code"
        assert user_code_data["device_code"] == device_code
        
        # Update status to approved
        device_auth_data["status"] = "approved"
        device_auth_data["approved_by"] = "tenant-abc123"
        device_auth_data["access_token"] = "jwt_token_here"
        
        success = asyncio.run(kv.put(f"device-auth:{device_code}", device_auth_data, ttl_seconds=600))
        assert success, "Failed to update device auth"
        
        # Verify update
        updated = asyncio.run(kv.get(f"device-auth:{device_code}"))
        assert updated["status"] == "approved"
        assert updated["access_token"] == "jwt_token_here"
        
        # Scan for all device auth entries
        all_device_auths = asyncio.run(kv.scan("device-auth:", limit=10))
        assert len(all_device_auths) >= 1, "Should find at least one device auth"
        
        # Clean up
        success = asyncio.run(kv.delete(f"device-auth:{device_code}"))
        assert success, "Failed to delete device auth"
        
        success = asyncio.run(kv.delete(f"user-code:{user_code}"))
        assert success, "Failed to delete user code"
        
        logger.info("KV device auth test completed successfully")
    
    def test_02_direct_node_operations(self, provider):
        """Test direct node add/get operations outside entity system."""
        logger.info("Testing direct node operations...")
        
        # Add a configuration node
        config_node = provider.add_node(
            node_key="config:system-settings",
            node_label="Configuration",
            properties={
                "max_devices_per_user": 5,
                "token_expiry_hours": 24,
                "enable_2fa": True,
                "created_at": datetime.utcnow().isoformat()
            }
        )
        
        # Check if it's an error response
        if isinstance(config_node, dict) and config_node.get("status") == "ERROR":
            logger.warning(f"Failed to add config node: {config_node.get('message')}")
            # This might fail if AGE functions aren't loaded yet
            pytest.skip("AGE functions not available - skipping node operations")
        
        # Add a feature flag node
        feature_node = provider.add_node(
            node_key="feature:new-ui-enabled",
            node_label="FeatureFlag", 
            properties={
                "enabled": True,
                "rollout_percentage": 50,
                "target_groups": ["beta_users", "internal_staff"]
            }
        )
        
        # Get nodes by key
        nodes = provider.get_nodes_by_key([
            "config:system-settings",
            "feature:new-ui-enabled"
        ])
        
        assert len(nodes) == 2, f"Expected 2 nodes, got {len(nodes)}"
        
        # Verify node data
        for node in nodes:
            if node["id"] == "config:system-settings":
                assert node["entity_type"] == "Configuration"
                assert json.loads(node["node_data"])["properties"]["max_devices_per_user"] == 5
            elif node["id"] == "feature:new-ui-enabled":
                assert node["entity_type"] == "FeatureFlag"
                assert json.loads(node["node_data"])["properties"]["enabled"] is True
        
        logger.info("Direct node operations completed successfully")
    
    
    def test_04_kv_stats_and_cleanup(self, provider):
        """Test KV stats and cleanup operations."""
        logger.info("Testing KV stats and cleanup...")
        
        kv = provider.kv
        
        # Add some test data with short TTL
        test_keys = []
        for i in range(5):
            key = f"test-cleanup:{i}"
            test_keys.append(key)
            asyncio.run(kv.put(key, {"index": i}, ttl_seconds=1))  # 1 second TTL
        
        # Check stats (if function exists)
        try:
            conn = provider.connect_sync()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM p8.get_kv_stats()")
            stats = cursor.fetchone()
            
            if stats:
                logger.info(f"KV Stats - Total: {stats[0]}, Expired: {stats[1]}, Active: {stats[2]}")
            
            cursor.close()
        except Exception as e:
            logger.warning(f"Could not get KV stats: {e}")
        
        # Wait for TTL expiration
        import time
        time.sleep(2)
        
        # Try to retrieve expired keys
        for key in test_keys:
            value = asyncio.run(kv.get(key))
            assert value is None, f"Key {key} should have expired"
        
        # Run cleanup (if function exists)
        try:
            conn = provider.connect_sync()
            cursor = conn.cursor()
            cursor.execute("SELECT p8.cleanup_expired_kv()")
            deleted_count = cursor.fetchone()[0]
            conn.commit()
            
            logger.info(f"Cleaned up {deleted_count} expired KV entries")
            cursor.close()
        except Exception as e:
            logger.warning(f"Could not run cleanup: {e}")
        
        logger.info("KV stats and cleanup test completed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])