"""Unit tests for data serialization."""

import json
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

import pytest
from p8fs.providers.postgresql import PostgreSQLProvider
# from p8fs.providers.rocksdb import RocksDBProvider  # TODO: Enable when RocksDB is implemented
from p8fs.providers.tidb import TiDBProvider


class Status(Enum):
    """Test enum."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


class TestSerialization:
    """Test serialization for different providers."""
    
    @pytest.fixture
    def providers(self):
        """Create provider instances."""
        return {
            'postgresql': PostgreSQLProvider(),
            'tidb': TiDBProvider(),
            # 'rocksdb': RocksDBProvider()  # TODO: Enable when RocksDB is implemented
        }
    
    def test_uuid_serialization(self, providers):
        """Test UUID serialization."""
        test_uuid = uuid4()
        data = {'id': test_uuid, 'name': 'test'}
        
        # PostgreSQL
        pg_serialized = providers['postgresql'].serialize_for_db(data)
        assert isinstance(pg_serialized['id'], str)
        assert pg_serialized['id'] == str(test_uuid)
        
        # TiDB
        tidb_serialized = providers['tidb'].serialize_for_db(data)
        assert isinstance(tidb_serialized['id'], str)
        assert tidb_serialized['id'] == str(test_uuid)
        
        # RocksDB - TODO: Enable when RocksDB is implemented
        # rocks_serialized = providers['rocksdb'].serialize_for_db(data)
        # assert isinstance(rocks_serialized['id'], str)
        # assert rocks_serialized['id'] == str(test_uuid)
    
    def test_enum_serialization(self, providers):
        """Test enum serialization."""
        data = {'status': Status.ACTIVE, 'name': 'test'}
        
        for name, provider in providers.items():
            serialized = provider.serialize_for_db(data)
            assert serialized['status'] == 'active'
            assert isinstance(serialized['status'], str)
    
    def test_datetime_serialization(self, providers):
        """Test datetime serialization."""
        now = datetime.now(timezone.utc)
        data = {'created_at': now, 'name': 'test'}
        
        # PostgreSQL - keeps datetime object
        pg_serialized = providers['postgresql'].serialize_for_db(data)
        assert pg_serialized['created_at'] == now
        assert isinstance(pg_serialized['created_at'], datetime)
        
        # TiDB - keeps datetime object
        tidb_serialized = providers['tidb'].serialize_for_db(data)
        assert tidb_serialized['created_at'] == now
        assert isinstance(tidb_serialized['created_at'], datetime)
        
        # RocksDB - converts to ISO string - TODO: Enable when RocksDB is implemented
        # rocks_serialized = providers['rocksdb'].serialize_for_db(data)
        # assert isinstance(rocks_serialized['created_at'], str)
        # assert rocks_serialized['created_at'] == now.isoformat()
    
    def test_collection_serialization(self, providers):
        """Test dict and list serialization."""
        data = {
            'metadata': {'key': 'value', 'nested': {'deep': True}},
            'tags': ['tag1', 'tag2', 'tag3'],
            'scores': [1.5, 2.7, 3.9]
        }
        
        for name, provider in providers.items():
            serialized = provider.serialize_for_db(data)
            
            # All providers convert collections to JSON strings
            assert isinstance(serialized['metadata'], str)
            assert isinstance(serialized['tags'], str)
            assert isinstance(serialized['scores'], str)
            
            # Verify JSON is valid
            metadata = json.loads(serialized['metadata'])
            assert metadata['key'] == 'value'
            assert metadata['nested']['deep'] is True
            
            tags = json.loads(serialized['tags'])
            assert tags == ['tag1', 'tag2', 'tag3']
            
            scores = json.loads(serialized['scores'])
            assert scores == [1.5, 2.7, 3.9]
    
    def test_none_handling(self, providers):
        """Test None value handling."""
        data = {
            'id': '123',
            'name': None,
            'description': None
        }
        
        for name, provider in providers.items():
            serialized = provider.serialize_for_db(data)
            assert serialized['name'] is None
            assert serialized['description'] is None
    
    def test_complex_nested_serialization(self, providers):
        """Test complex nested data serialization."""
        data = {
            'id': uuid4(),
            'user': {
                'name': 'John Doe',
                'created': datetime.now(),
                'status': Status.ACTIVE,
                'preferences': {
                    'theme': 'dark',
                    'notifications': {
                        'email': True,
                        'push': False
                    }
                }
            },
            'items': [
                {'id': str(uuid4()), 'value': 10.5},
                {'id': str(uuid4()), 'value': 20.7}
            ]
        }
        
        # PostgreSQL and TiDB handle similarly
        for provider_name in ['postgresql', 'tidb']:
            provider = providers[provider_name]
            serialized = provider.serialize_for_db(data)
            
            # UUID converted to string
            assert isinstance(serialized['id'], str)
            
            # Complex nested dict converted to JSON string
            assert isinstance(serialized['user'], str)
            user_data = json.loads(serialized['user'])
            assert user_data['name'] == 'John Doe'
            assert user_data['status'] == 'active'
            
            # List converted to JSON string
            assert isinstance(serialized['items'], str)
            items_data = json.loads(serialized['items'])
            assert len(items_data) == 2
    
    def test_batch_serialization(self, providers):
        """Test batch data serialization."""
        batch_data = []
        for i in range(10):
            batch_data.append({
                'id': str(uuid4()),
                'index': i,
                'data': {'value': i * 10},
                'tags': [f'tag{i}', 'common']
            })
        
        for name, provider in providers.items():
            # Serialize each row
            serialized_batch = []
            for row in batch_data:
                serialized_batch.append(provider.serialize_for_db(row))
            
            # Verify all rows serialized correctly
            assert len(serialized_batch) == 10
            for i, row in enumerate(serialized_batch):
                assert isinstance(row['id'], str)
                assert row['index'] == i
                assert isinstance(row['data'], str)
                assert isinstance(row['tags'], str)