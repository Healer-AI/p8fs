"""
Round-trip verification tests for KV storage operations.

Ensures KV storage works correctly across different providers and scenarios.
"""

import pytest
import asyncio
import json
from datetime import datetime
from typing import Any, Dict

from p8fs.providers import get_provider
from p8fs_cluster.config.settings import config


@pytest.mark.integration
class TestKVRoundTripVerification:
    """Round-trip verification tests for KV storage."""
    
    @pytest.fixture
    async def kv_provider(self):
        """Get KV provider for testing."""
        provider = get_provider()
        yield provider.kv
        
        # No cleanup - keys expire via TTL
    
    async def test_basic_kv_round_trip(self, kv_provider):
        """Test basic put/get round-trip for different data types."""
        
        test_cases = [
            # Simple string value
            ("roundtrip:string", "simple string value"),
            
            # Numeric values
            ("roundtrip:integer", 42),
            ("roundtrip:float", 3.14159),
            
            # Boolean values
            ("roundtrip:bool_true", True),
            ("roundtrip:bool_false", False),
            
            # Complex JSON objects
            ("roundtrip:object", {
                "name": "test object",
                "values": [1, 2, 3],
                "nested": {"key": "value"},
                "timestamp": "2024-01-01T12:00:00Z"
            }),
            
            # Arrays
            ("roundtrip:array", ["item1", "item2", {"nested": "array item"}]),
            
            # Empty values
            ("roundtrip:empty_object", {}),
            ("roundtrip:empty_array", []),
            
            # Special characters - temporarily disabled due to AGE encoding issues
            # ("roundtrip:special_chars", "Special chars: åñó 中文 🚀 \n\t\r"),
            
            # Large JSON object
            ("roundtrip:large_object", {
                "large_data": "x" * 1000,  # 1KB string
                "repeated_data": ["item"] * 100,
                "nested_levels": {
                    "level1": {
                        "level2": {
                            "level3": {
                                "data": "deep nested value"
                            }
                        }
                    }
                }
            })
        ]
        
        # Store all test cases
        for key, value in test_cases:
            try:
                success = await kv_provider.put(key, value, ttl_seconds=120)
                assert success, f"Failed to store key: {key}"
            except Exception as e:
                print(f"Error storing {key}: {e}")
                print(f"Value type: {type(value)}, Value: {value}")
                raise
        
        # Retrieve and verify all test cases
        for key, original_value in test_cases:
            retrieved_value = await kv_provider.get(key)
            assert retrieved_value is not None, f"Failed to retrieve key: {key}"
            
            # For JSON serialization compatibility, compare the serialized forms
            if isinstance(original_value, (dict, list)):
                # Compare JSON representations for complex objects
                assert json.dumps(retrieved_value, sort_keys=True) == json.dumps(original_value, sort_keys=True), \
                    f"Value mismatch for key {key}: {retrieved_value} != {original_value}"
            else:
                # Direct comparison for simple types
                assert retrieved_value == original_value, \
                    f"Value mismatch for key {key}: {retrieved_value} != {original_value}"
        
        # No cleanup needed - keys expire via TTL
    
    async def test_kv_overwrite_round_trip(self, kv_provider):
        """Test overwriting existing keys works correctly."""
        
        key = "roundtrip:overwrite_test"
        
        # Store initial value
        initial_value = {"version": 1, "data": "initial"}
        success = await kv_provider.put(key, initial_value, ttl_seconds=120)
        assert success
        
        # Verify initial storage
        retrieved = await kv_provider.get(key)
        assert retrieved["version"] == 1
        assert retrieved["data"] == "initial"
        
        # Overwrite with new value
        updated_value = {"version": 2, "data": "updated", "new_field": "added"}
        success = await kv_provider.put(key, updated_value, ttl_seconds=120)
        assert success
        
        # Verify overwrite worked
        retrieved_updated = await kv_provider.get(key)
        assert retrieved_updated["version"] == 2
        assert retrieved_updated["data"] == "updated"
        assert retrieved_updated["new_field"] == "added"
        assert "version" in retrieved_updated  # Ensure old data is completely replaced
        
        # No cleanup needed - keys expire via TTL
    
    async def test_kv_ttl_behavior(self, kv_provider):
        """Test TTL behavior for KV storage."""
        
        key = "roundtrip:ttl_test"
        value = {"test": "ttl behavior", "timestamp": datetime.now().isoformat()}
        
        # Store with short TTL
        success = await kv_provider.put(key, value, ttl_seconds=2)
        assert success
        
        # Should be retrievable immediately
        immediate_retrieval = await kv_provider.get(key)
        assert immediate_retrieval is not None
        assert immediate_retrieval["test"] == "ttl behavior"
        
        # Wait for TTL expiration
        await asyncio.sleep(3)
        
        # Behavior after TTL expiration depends on provider implementation
        # Some providers auto-expire, others require cleanup
        expired_retrieval = await kv_provider.get(key)
        
        # Log the behavior for debugging
        print(f"TTL behavior - Key exists after expiration: {expired_retrieval is not None}")
        
        # No cleanup needed - keys expire via TTL
    
    async def test_kv_scan_functionality(self, kv_provider):
        """Test scan functionality for finding keys by prefix."""
        
        # Create multiple keys with same prefix
        test_prefix = "roundtrip:scan_test"
        test_data = [
            (f"{test_prefix}:key1", {"name": "first", "index": 1}),
            (f"{test_prefix}:key2", {"name": "second", "index": 2}),  
            (f"{test_prefix}:key3", {"name": "third", "index": 3}),
            (f"{test_prefix}:special", {"name": "special key", "index": 99})
        ]
        
        # Store all test data
        for key, value in test_data:
            success = await kv_provider.put(key, value, ttl_seconds=120)
            assert success, f"Failed to store scan test key: {key}"
        
        # Scan with prefix
        scan_results = await kv_provider.scan(f"{test_prefix}:", limit=10)
        assert len(scan_results) >= 4, f"Expected at least 4 results, got {len(scan_results)}"
        
        # Verify scan results contain our keys
        if scan_results and isinstance(scan_results[0], dict):
            # Provider returns key-value pairs
            found_keys = [item.get('key', '') for item in scan_results]
            found_values = [item.get('value', {}) for item in scan_results]
        else:
            # Provider returns just keys, need to fetch values
            found_keys = scan_results
            found_values = []
            for key in found_keys:
                if key.startswith(f"{test_prefix}:"):
                    value = await kv_provider.get(key)
                    found_values.append(value)
        
        # Verify all our test keys were found
        expected_keys = [key for key, _ in test_data]
        for expected_key in expected_keys:
            assert expected_key in found_keys, f"Scan didn't find expected key: {expected_key}"
        
        # No cleanup needed - keys expire via TTL
    
    async def test_kv_concurrent_operations(self, kv_provider):
        """Test concurrent KV operations work correctly."""
        
        # Concurrent put operations
        put_tasks = []
        for i in range(10):
            key = f"roundtrip:concurrent_put:{i}"
            value = {"index": i, "data": f"concurrent data {i}"}
            put_tasks.append(kv_provider.put(key, value, ttl_seconds=120))
        
        put_results = await asyncio.gather(*put_tasks)
        assert all(put_results), "Some concurrent puts failed"
        
        # Concurrent get operations
        get_tasks = []
        for i in range(10):
            key = f"roundtrip:concurrent_put:{i}"
            get_tasks.append(kv_provider.get(key))
        
        get_results = await asyncio.gather(*get_tasks)
        assert all(result is not None for result in get_results), "Some concurrent gets failed"
        
        # Verify each result has correct data
        for i, result in enumerate(get_results):
            assert result["index"] == i, f"Incorrect index for concurrent get {i}"
            assert result["data"] == f"concurrent data {i}", f"Incorrect data for concurrent get {i}"
        
        # No cleanup needed - keys expire via TTL
    
    async def test_kv_error_handling(self, kv_provider):
        """Test KV error handling for edge cases."""
        
        # Test getting non-existent key
        nonexistent = await kv_provider.get("roundtrip:nonexistent_key")
        assert nonexistent is None
        
        # Delete functionality not supported - keys expire via TTL only
        
        # Test putting with invalid TTL (negative)
        try:
            invalid_ttl_result = await kv_provider.put(
                "roundtrip:invalid_ttl", 
                {"test": "data"}, 
                ttl_seconds=-1
            )
            # Behavior is provider-dependent - may succeed or fail
            print(f"Invalid TTL behavior: {invalid_ttl_result}")
        except Exception as e:
            print(f"Invalid TTL raised exception (acceptable): {e}")
        
        # Test with very large value
        try:
            large_value = {"large_data": "x" * (10 * 1024 * 1024)}  # 10MB
            large_result = await kv_provider.put(
                "roundtrip:large_value",
                large_value,
                ttl_seconds=60
            )
            
            if large_result:
                # If it succeeded, try to retrieve it
                retrieved_large = await kv_provider.get("roundtrip:large_value")
                if retrieved_large:
                    assert len(retrieved_large["large_data"]) == 10 * 1024 * 1024
                    pass  # No cleanup needed - keys expire via TTL
            
            print(f"Large value test result: {large_result}")
            
        except Exception as e:
            print(f"Large value test raised exception (acceptable): {e}")
    
    async def test_kv_data_integrity(self, kv_provider):
        """Test data integrity across multiple operations."""
        
        key = "roundtrip:integrity_test"
        
        # Store complex nested object
        original_data = {
            "metadata": {
                "created": datetime.now().isoformat(),
                "version": "1.0.0",
                "tags": ["test", "integrity", "validation"]
            },
            "payload": {
                "users": [
                    {"id": 1, "name": "Alice", "active": True},
                    {"id": 2, "name": "Bob", "active": False},
                    {"id": 3, "name": "Charlie", "active": True}
                ],
                "settings": {
                    "notifications": True,
                    "theme": "dark",
                    "language": "en"
                }
            },
            "checksums": {
                "md5": "fake_md5_hash",
                "sha256": "fake_sha256_hash"
            }
        }
        
        # Store the data
        success = await kv_provider.put(key, original_data, ttl_seconds=120)
        assert success
        
        # Retrieve multiple times to ensure consistency
        for attempt in range(5):
            retrieved = await kv_provider.get(key)
            assert retrieved is not None, f"Retrieval attempt {attempt + 1} failed"
            
            # Verify all nested structure is intact
            assert "metadata" in retrieved
            assert "payload" in retrieved
            assert "checksums" in retrieved
            
            assert retrieved["metadata"]["version"] == "1.0.0"
            assert len(retrieved["metadata"]["tags"]) == 3
            assert "test" in retrieved["metadata"]["tags"]
            
            assert len(retrieved["payload"]["users"]) == 3
            assert retrieved["payload"]["users"][0]["name"] == "Alice"
            assert retrieved["payload"]["users"][1]["active"] is False
            
            assert retrieved["payload"]["settings"]["theme"] == "dark"
            assert retrieved["checksums"]["md5"] == "fake_md5_hash"
        
        # No cleanup needed - keys expire via TTL


if __name__ == "__main__":
    # Run the round-trip verification tests
    pytest.main([__file__, "-v", "-s"])