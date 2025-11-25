"""Unit tests for TiKV service and reverse mapping functionality."""

import json
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest
from p8fs.services.storage.tikv_service import TiKVReverseMapping, TiKVService


class TestTiKVService:
    """Test TiKV HTTP proxy service."""
    
    def setup_method(self):
        """Set up test service."""
        self.service = TiKVService("http://test-proxy.example.com")
    
    def test_init(self):
        """Test service initialization."""
        assert self.service.proxy_url == "http://test-proxy.example.com"
        assert isinstance(self.service.client, httpx.Client)
    
    def test_format_key(self):
        """Test key formatting with tenant isolation."""
        formatted = self.service._format_key("mykey", "tenant123")
        assert formatted == "tenant123/mykey"
    
    @patch.object(httpx.Client, 'get')
    def test_get_success(self, mock_get):
        """Test successful key retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": json.dumps({"data": "test"})}
        mock_get.return_value = mock_response
        
        result = self.service.get("testkey", "tenant1")
        
        assert result == {"data": "test"}
        mock_get.assert_called_once_with("http://test-proxy.example.com/kv/tenant1/testkey")
    
    @patch.object(httpx.Client, 'get')
    def test_get_not_found(self, mock_get):
        """Test key not found."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result = self.service.get("nonexistent", "tenant1")
        
        assert result is None
    
    @patch.object(httpx.Client, 'get')
    def test_get_error(self, mock_get):
        """Test get error handling."""
        mock_get.side_effect = Exception("Connection error")
        
        with pytest.raises(Exception):  # RetryError wraps the original exception
            self.service.get("testkey", "tenant1")
    
    @patch.object(httpx.Client, 'put')
    def test_put_success(self, mock_put):
        """Test successful key-value storage."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_put.return_value = mock_response
        
        self.service.put("testkey", {"data": "value"}, "tenant1", ttl_seconds=300)
        
        expected_payload = {
            "key": "tenant1/testkey",
            "value": json.dumps({"data": "value"}),
            "ttl": 300
        }
        mock_put.assert_called_once_with(
            "http://test-proxy.example.com/kv",
            json=expected_payload
        )
    
    @patch.object(httpx.Client, 'put')
    def test_put_without_ttl(self, mock_put):
        """Test put without TTL."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_put.return_value = mock_response
        
        self.service.put("testkey", {"data": "value"}, "tenant1")
        
        expected_payload = {
            "key": "tenant1/testkey",
            "value": json.dumps({"data": "value"})
        }
        mock_put.assert_called_once_with(
            "http://test-proxy.example.com/kv",
            json=expected_payload
        )
    
    @patch.object(httpx.Client, 'put')
    def test_put_error(self, mock_put):
        """Test put error handling."""
        mock_put.side_effect = Exception("Write error")
        
        with pytest.raises(Exception):  # RetryError wraps the original exception
            self.service.put("testkey", {"data": "value"}, "tenant1")
    
    @patch.object(httpx.Client, 'get')
    def test_scan_success(self, mock_get):
        """Test successful prefix scan."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = [
            {"key": "tenant1/prefix/key1", "value": json.dumps({"id": "1"})},
            {"key": "tenant1/prefix/key2", "value": json.dumps({"id": "2"})}
        ]
        mock_get.return_value = mock_response
        
        results = self.service.scan("prefix/", "tenant1", limit=10)
        
        assert len(results) == 2
        assert results[0] == {"key": "prefix/key1", "value": {"id": "1"}}
        assert results[1] == {"key": "prefix/key2", "value": {"id": "2"}}
        
        mock_get.assert_called_once_with(
            "http://test-proxy.example.com/kv/scan",
            params={"prefix": "tenant1/prefix/", "limit": 10}
        )
    
    @patch.object(httpx.Client, 'get')
    def test_scan_empty(self, mock_get):
        """Test scan with no results."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = []
        mock_get.return_value = mock_response
        
        results = self.service.scan("empty/", "tenant1")
        
        assert results == []
    
    @patch.object(httpx.Client, 'delete')
    def test_delete_success(self, mock_delete):
        """Test successful key deletion."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_delete.return_value = mock_response
        
        self.service.delete("testkey", "tenant1")
        
        mock_delete.assert_called_once_with("http://test-proxy.example.com/kv/tenant1/testkey")
    
    @patch.object(httpx.Client, 'post')
    def test_batch_get_success(self, mock_post):
        """Test successful batch get."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = [
            {"key": "tenant1/key1", "value": json.dumps({"id": "1"})},
            {"key": "tenant1/key2", "value": json.dumps({"id": "2"})}
        ]
        mock_post.return_value = mock_response
        
        results = self.service.batch_get(["key1", "key2"], "tenant1")
        
        assert results == {
            "key1": {"id": "1"},
            "key2": {"id": "2"}
        }
        
        expected_payload = {"keys": ["tenant1/key1", "tenant1/key2"]}
        mock_post.assert_called_once_with(
            "http://test-proxy.example.com/kv/batch",
            json=expected_payload
        )
    
    def test_context_manager(self):
        """Test context manager functionality."""
        with TiKVService("http://test.com") as service:
            assert isinstance(service.client, httpx.Client)
        
        # Client should be closed after exiting context
        assert service.client.is_closed  # Use is_closed property instead of _state


class TestTiKVReverseMapping:
    """Test TiKV reverse mapping functionality."""
    
    def setup_method(self):
        """Set up test reverse mapping."""
        self.tikv_service = Mock()
        self.reverse_mapping = TiKVReverseMapping(self.tikv_service)
    
    def test_store_reverse_mapping(self):
        """Test storing complete reverse mapping."""
        self.reverse_mapping.store_reverse_mapping(
            name="TestEntity",
            entity_type="document",
            entity_key="doc123",
            table_name="documents",
            tenant_id="tenant1"
        )
        
        # Should create 3 entries
        assert self.tikv_service.put.call_count == 3
        
        # Check name-based lookup
        call_args = self.tikv_service.put.call_args_list[0]
        assert call_args[0][0] == "TestEntity/document"
        assert call_args[0][1]["entity_type"] == "document"
        assert call_args[0][1]["entity_name"] == "TestEntity"
        assert call_args[0][1]["entity_key"] == "doc123"
        assert call_args[0][2] == "tenant1"
        
        # Check entity reference
        call_args = self.tikv_service.put.call_args_list[1]
        assert call_args[0][0] == "document/TestEntity"
        assert call_args[0][1]["entity_key"] == "doc123"
        assert call_args[0][1]["table_name"] == "documents"
        assert call_args[0][1]["tenant_id"] == "tenant1"
        
        # Check reverse mapping
        call_args = self.tikv_service.put.call_args_list[2]
        assert call_args[0][0] == "reverse/doc123/document"
        assert call_args[0][1]["name"] == "TestEntity"
        assert call_args[0][1]["entity_type"] == "document"
        assert call_args[0][1]["table_name"] == "documents"
    
    def test_lookup_by_name(self):
        """Test entity lookup by name."""
        expected_result = {
            "entity_type": "document",
            "entity_name": "TestDoc",
            "entity_key": "doc456"
        }
        self.tikv_service.get.return_value = expected_result
        
        result = self.reverse_mapping.lookup_by_name("TestDoc", "document", "tenant1")
        
        assert result == expected_result
        self.tikv_service.get.assert_called_once_with("TestDoc/document", "tenant1")
    
    def test_lookup_entity_reference(self):
        """Test entity reference lookup."""
        expected_result = {
            "entity_key": "doc789",
            "table_name": "documents",
            "tenant_id": "tenant1",
            "entity_type": "document",
            "name": "MyDoc"
        }
        self.tikv_service.get.return_value = expected_result
        
        result = self.reverse_mapping.lookup_entity_reference("document", "MyDoc", "tenant1")
        
        assert result == expected_result
        self.tikv_service.get.assert_called_once_with("document/MyDoc", "tenant1")
    
    def test_reverse_lookup(self):
        """Test reverse lookup from entity key."""
        expected_result = {
            "name": "OriginalName",
            "entity_type": "document",
            "table_name": "documents"
        }
        self.tikv_service.get.return_value = expected_result
        
        result = self.reverse_mapping.reverse_lookup("doc999", "document", "tenant1")
        
        assert result == expected_result
        self.tikv_service.get.assert_called_once_with("reverse/doc999/document", "tenant1")
    
    def test_find_entities_by_type(self):
        """Test finding all entities of a type."""
        expected_results = [
            {"key": "document/Doc1", "value": {"entity_key": "doc1"}},
            {"key": "document/Doc2", "value": {"entity_key": "doc2"}}
        ]
        self.tikv_service.scan.return_value = expected_results
        
        results = self.reverse_mapping.find_entities_by_type("document", "tenant1", limit=50)
        
        assert results == expected_results
        self.tikv_service.scan.assert_called_once_with("document/", "tenant1", 50)
    
    def test_lookup_returns_none_when_not_found(self):
        """Test lookups return None when key not found."""
        self.tikv_service.get.return_value = None
        
        assert self.reverse_mapping.lookup_by_name("NonExistent", "type", "tenant1") is None
        assert self.reverse_mapping.lookup_entity_reference("type", "NonExistent", "tenant1") is None
        assert self.reverse_mapping.reverse_lookup("key123", "type", "tenant1") is None