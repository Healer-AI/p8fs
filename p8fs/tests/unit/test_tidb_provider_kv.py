"""Unit tests for TiDB provider with KV and reverse mapping functionality."""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from p8fs.models import AbstractModel
from p8fs.providers.tidb import TiDBProvider


class TestModel(AbstractModel):
    """Test model for unit tests."""
    id: str
    name: str
    description: str = ""
    
    @classmethod
    def to_sql_schema(cls):
        return {
            'table_name': 'test_entities',
            'key_field': 'id',
            'fields': {
                'id': {'type': str, 'is_primary_key': True},
                'name': {'type': str, 'nullable': False},
                'description': {'type': str, 'nullable': True}
            },
            'tenant_isolated': True
        }
    
    @classmethod
    def get_model_key_field(cls):
        return 'name'
    
    @classmethod
    def get_model_table_name(cls):
        return 'test_entities'


class TestTiDBProviderKV:
    """Test TiDB provider KV and reverse mapping functionality."""
    
    def setup_method(self):
        """Set up test provider."""
        self.provider = TiDBProvider()
    
    def test_tikv_service_property(self):
        """Test TiKV service property initialization."""
        from p8fs.services.storage.tikv_service import TiKVService
        
        service = self.provider.tikv_service
        assert isinstance(service, TiKVService)
        # Should reuse same instance
        assert service is self.provider.tikv_service
    
    def test_tikv_reverse_mapping_property(self):
        """Test TiKV reverse mapping property initialization."""
        from p8fs.services.storage.tikv_service import TiKVReverseMapping
        
        mapping = self.provider.tikv_reverse_mapping
        assert isinstance(mapping, TiKVReverseMapping)
        # Should reuse same instance
        assert mapping is self.provider.tikv_reverse_mapping
        # Should use same TiKV service
        assert mapping.tikv is self.provider.tikv_service
    
    @pytest.mark.asyncio
    async def test_kv_put_success(self):
        """Test successful KV put operation."""
        with patch.object(self.provider.tikv_service, 'put') as mock_put:
            result = await self.provider.kv_put("testkey", {"data": "value"}, "tenant1")
            
            assert result is True
            mock_put.assert_called_once_with("testkey", {"data": "value"}, "tenant1")
    
    @pytest.mark.asyncio
    async def test_kv_put_error(self):
        """Test KV put error handling."""
        with patch.object(self.provider.tikv_service, 'put', side_effect=Exception("Put failed")):
            result = await self.provider.kv_put("testkey", {"data": "value"}, "tenant1")
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_compute_tidb_tikv_key(self):
        """Test TiDB TiKV key computation."""
        # Mock the metadata cache and connection
        mock_cache = Mock()
        mock_cache.get_table_id.return_value = 12345
        self.provider._metadata_cache = mock_cache
        
        mock_conn = Mock()
        mock_conn.close = Mock()
        
        with patch.object(self.provider, 'connect_sync', return_value=mock_conn):
            key = await self.provider.compute_tidb_tikv_key("tenant1", "documents", "doc123")
            
            # Should compute binary key
            assert isinstance(key, bytes)
            assert b't' in key  # Table prefix
            assert b'_r' in key  # Record prefix
            
            mock_cache.get_table_id.assert_called_once_with(mock_conn, "documents")
            mock_conn.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_compute_tidb_tikv_key_fallback(self):
        """Test TiDB TiKV key computation fallback."""
        # Mock cache to raise exception
        mock_cache = Mock()
        mock_cache.get_table_id.side_effect = Exception("Table not found")
        self.provider._metadata_cache = mock_cache
        
        mock_conn = Mock()
        with patch.object(self.provider, 'connect_sync', return_value=mock_conn):
            key = await self.provider.compute_tidb_tikv_key("tenant1", "documents", "doc123")
            
            # Should return fallback key
            assert key == b"tidb/tenant1/documents/doc123"
    
    @pytest.mark.asyncio
    async def test_store_entity_reverse_mapping(self):
        """Test async store entity reverse mapping."""
        entity_data = {
            'id': 'entity123',
            'name': 'TestEntity',
            'description': 'Test description'
        }
        
        # Mock the kv_put method
        self.provider.kv_put = AsyncMock(return_value=True)
        
        # Mock compute_tidb_tikv_key
        with patch.object(self.provider, 'compute_tidb_tikv_key', return_value=b'test_tikv_key'):
            result = await self.provider.store_entity_reverse_mapping(
                TestModel,
                entity_data,
                "tenant1"
            )
        
        # Should have called kv_put 3 times (entity, name mapping, reverse mapping)
        assert self.provider.kv_put.call_count == 3
        
        # Check the result
        assert result['entity_id'] == 'TestEntity'
        assert result['entity_key'] == 'testmodel/TestEntity'
        assert result['entity_type'] == 'testmodel'
        assert result['tenant_id'] == 'tenant1'
    
    def test_store_entity_with_reverse_mapping_sync(self):
        """Test synchronous store entity with reverse mapping."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit = Mock()
        
        # Mock primary key info
        with patch.object(self.provider, 'get_primary_key_info', return_value={'column_name': 'id'}):
            # Mock TiKV reverse mapping
            with patch.object(self.provider.tikv_reverse_mapping, 'store_reverse_mapping') as mock_store:
                entity_data = {
                    'id': 'doc123',
                    'name': 'MyDocument',
                    'content': 'Document content'
                }
                
                result = self.provider.store_entity_with_reverse_mapping(
                    mock_conn,
                    'MyDocument',
                    'document',
                    entity_data,
                    'tenant1'
                )
                
                # Should execute SQL insert
                mock_cursor.execute.assert_called_once()
                sql = mock_cursor.execute.call_args[0][0]
                assert 'REPLACE INTO document' in sql
                
                # Should store reverse mapping
                mock_store.assert_called_once_with(
                    name='MyDocument',
                    entity_type='document',
                    entity_key='doc123',
                    table_name='document',
                    tenant_id='tenant1'
                )
                
                # Should return expected format
                assert result == 'tenant1:document:MyDocument'
    
    def test_get_entity_by_name(self):
        """Test retrieving entity by name."""
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': 'doc123',
            'name': 'TestDoc',
            'content': 'Test content',
            'tenant_id': 'tenant1'
        }
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock TiKV lookup
        entity_ref = {
            'entity_key': 'doc123',
            'table_name': 'documents',
            'tenant_id': 'tenant1'
        }
        with patch.object(self.provider.tikv_reverse_mapping, 'lookup_entity_reference', return_value=entity_ref):
            # Mock primary key info
            with patch.object(self.provider, 'get_primary_key_info', return_value={'column_name': 'id'}):
                result = self.provider.get_entity_by_name(
                    mock_conn,
                    'TestDoc',
                    'document',
                    'tenant1'
                )
        
        assert result['id'] == 'doc123'
        assert result['name'] == 'TestDoc'
        
        # Check SQL query
        sql = mock_cursor.execute.call_args[0][0]
        assert 'SELECT * FROM documents' in sql
        assert 'id = %s' in sql
        assert 'tenant_id = %s' in sql
    
    def test_get_entity_by_name_not_found(self):
        """Test retrieving entity by name when not found."""
        mock_conn = Mock()
        
        # Mock TiKV lookup returns None
        with patch.object(self.provider.tikv_reverse_mapping, 'lookup_entity_reference', return_value=None):
            result = self.provider.get_entity_by_name(
                mock_conn,
                'NonExistent',
                'document',
                'tenant1'
            )
        
        assert result is None
    
    def test_get_entities_by_storage_key(self):
        """Test retrieving entity by storage key."""
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': 'doc456',
            'name': 'StoredDoc',
            'content': 'Stored content',
            'tenant_id': 'tenant1'
        }
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock reverse lookup
        reverse_info = {
            'name': 'StoredDoc',
            'entity_type': 'document',
            'table_name': 'documents'
        }
        with patch.object(self.provider.tikv_reverse_mapping, 'reverse_lookup', return_value=reverse_info):
            # Mock primary key info
            with patch.object(self.provider, 'get_primary_key_info', return_value={'column_name': 'id'}):
                result = self.provider.get_entities_by_storage_key(
                    mock_conn,
                    'document/doc456',
                    'tenant1'
                )
        
        assert result['id'] == 'doc456'
        assert result['name'] == 'StoredDoc'
    
    def test_get_entities_by_storage_key_invalid_format(self):
        """Test retrieving entity with invalid storage key format."""
        mock_conn = Mock()
        
        result = self.provider.get_entities_by_storage_key(
            mock_conn,
            'invalid_key_format',
            'tenant1'
        )
        
        assert result is None
    
    def test_compute_tikv_binary_key(self):
        """Test TiKV binary key computation."""
        # Test with string primary key
        key = self.provider.compute_tikv_binary_key(12345, "test_id")
        assert isinstance(key, bytes)
        assert b't12345_r' in key
        assert b'test_id' in key
        
        # Test with integer primary key
        key = self.provider.compute_tikv_binary_key(12345, 67890)
        assert isinstance(key, bytes)
        assert b't12345_r' in key
        
        # Test with other type (converts to string)
        from uuid import uuid4
        test_uuid = uuid4()
        key = self.provider.compute_tikv_binary_key(12345, test_uuid)
        assert isinstance(key, bytes)
        assert str(test_uuid).encode() in key
    
    def test_metadata_cache_methods(self):
        """Test metadata cache wrapper methods."""
        # Test get_metadata_cache
        cache = self.provider.get_metadata_cache()
        assert cache is self.provider._metadata_cache
        
        # Mock cache methods
        mock_conn = Mock()
        self.provider._metadata_cache.table_exists = Mock(return_value=True)
        self.provider._metadata_cache.get_primary_key_info = Mock(return_value={'column_name': 'id'})
        self.provider._metadata_cache.invalidate_table = Mock()
        self.provider._metadata_cache.clear_cache = Mock()
        self.provider._metadata_cache.get_cache_stats = Mock(return_value={'hits': 10, 'misses': 2})
        
        # Test table_exists
        assert self.provider.table_exists(mock_conn, 'test_table') is True
        
        # Test get_primary_key_info
        pk_info = self.provider.get_primary_key_info(mock_conn, 'test_table')
        assert pk_info['column_name'] == 'id'
        
        # Test invalidate_table_cache
        self.provider.invalidate_table_cache('test_table')
        self.provider._metadata_cache.invalidate_table.assert_called_once_with('test_table')
        
        # Test clear_metadata_cache
        self.provider.clear_metadata_cache()
        self.provider._metadata_cache.clear_cache.assert_called_once()
        
        # Test get_cache_stats
        stats = self.provider.get_cache_stats()
        assert stats['hits'] == 10
        assert stats['misses'] == 2