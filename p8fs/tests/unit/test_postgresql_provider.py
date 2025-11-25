"""Unit tests for PostgreSQL provider."""

from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from p8fs.models import AbstractModel
from p8fs.providers.postgresql import PostgreSQLProvider


class SampleModel(AbstractModel):
    """Test model for unit tests."""
    id: str
    name: str
    description: str = ""
    
    @classmethod
    def to_sql_schema(cls):
        return {
            'table_name': 'test_models',
            'key_field': 'id',
            'fields': {
                'id': {'type': str, 'is_primary_key': True},
                'name': {'type': str, 'nullable': False},
                'description': {'type': str, 'nullable': True}
            }
        }


class TestPostgreSQLProvider:
    """Test PostgreSQL provider implementation."""
    
    def setup_method(self):
        """Set up test provider."""
        self.provider = PostgreSQLProvider()
    
    def test_get_dialect_name(self):
        """Test dialect name."""
        assert self.provider.get_dialect_name() == 'postgresql'
    
    def test_get_connection_string(self):
        """Test connection string generation."""
        conn_str = self.provider.get_connection_string(
            host='testhost',
            port=5433,
            user='testuser',
            password='testpass',
            database='testdb'
        )
        assert conn_str == 'postgresql://testuser:testpass@testhost:5433/testdb'
    
    def test_get_vector_type(self):
        """Test vector type."""
        assert self.provider.get_vector_type() == 'vector'
    
    def test_get_json_type(self):
        """Test JSON type."""
        assert self.provider.get_json_type() == 'JSONB'
    
    def test_supports_vector_operations(self):
        """Test vector operations support."""
        assert self.provider.supports_vector_operations() is True
    
    
    def test_map_python_type(self):
        """Test Python type mapping."""
        # Basic types
        assert self.provider.map_python_type(str) == 'TEXT'
        assert self.provider.map_python_type(int) == 'BIGINT'
        assert self.provider.map_python_type(float) == 'DOUBLE PRECISION'
        assert self.provider.map_python_type(bool) == 'BOOLEAN'
        
        from uuid import UUID
        from datetime import datetime
        assert self.provider.map_python_type(UUID) == 'UUID'
        assert self.provider.map_python_type(datetime) == 'TIMESTAMPTZ'
        
        # Collection types - CRITICAL for JSONB
        assert self.provider.map_python_type(dict) == 'JSONB'
        assert self.provider.map_python_type(list) == 'JSONB'
        
        # Generic types
        from typing import Dict, List, Optional, Any
        assert self.provider.map_python_type(Dict[str, Any]) == 'JSONB'
        assert self.provider.map_python_type(List[str]) == 'JSONB'
        assert self.provider.map_python_type(List[float]) == 'vector(1536)'  # Special case for vectors
        
        # Optional types (Union with None)
        assert self.provider.map_python_type(Optional[dict]) == 'JSONB'
        assert self.provider.map_python_type(Optional[Dict[str, Any]]) == 'JSONB'
        assert self.provider.map_python_type(Optional[str]) == 'TEXT'
        assert self.provider.map_python_type(Optional[UUID]) == 'UUID'
        
        # Complex Union types  
        from typing import Union
        # dict | None should be JSONB
        dict_or_none = Union[dict, None]
        assert self.provider.map_python_type(dict_or_none) == 'JSONB'
        
        # Dict[str, Any] | None should be JSONB
        dict_str_any_or_none = Union[Dict[str, Any], None]
        assert self.provider.map_python_type(dict_str_any_or_none) == 'JSONB'
    
    @patch('psycopg2.connect')
    def test_connect_sync(self, mock_connect):
        """Test synchronous connection."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        mock_connect.return_value = mock_conn
        
        conn = self.provider.connect_sync('postgresql://localhost/test')
        
        mock_connect.assert_called_once_with('postgresql://localhost/test', connect_timeout=5)
        assert conn.autocommit is False
        mock_cursor.execute.assert_called_with("SELECT 1")
    
    
    def test_serialize_for_db(self):
        """Test database serialization."""
        data = {
            'id': uuid4(),
            'name': 'test',
            'metadata': {'key': 'value'},
            'tags': ['tag1', 'tag2']
        }
        
        serialized = self.provider.serialize_for_db(data)
        
        # UUID should be converted to string
        assert isinstance(serialized['id'], str)
        # Dicts and lists should be JSON strings
        assert isinstance(serialized['metadata'], str)
        assert isinstance(serialized['tags'], str)
    
    def test_upsert_sql(self):
        """Test UPSERT SQL generation."""
        values = {
            'id': '123',
            'name': 'test',
            'description': 'test desc'
        }
        
        sql, params = self.provider.upsert_sql(SampleModel, values)
        
        assert 'INSERT INTO test_models' in sql
        assert 'ON CONFLICT (id)' in sql
        assert 'DO UPDATE SET' in sql
        assert 'updated_at = NOW()' in sql
        assert len(params) == 3
    
    def test_batch_upsert_sql(self):
        """Test batch UPSERT SQL generation."""
        values_list = [
            {'id': '1', 'name': 'test1', 'description': 'desc1'},
            {'id': '2', 'name': 'test2', 'description': 'desc2'}
        ]
        
        sql, params_list = self.provider.batch_upsert_sql(SampleModel, values_list)
        
        assert 'INSERT INTO test_models' in sql
        assert 'VALUES %s' in sql
        assert 'ON CONFLICT (id)' in sql
        assert len(params_list) == 2
        assert len(params_list[0]) == 3  # 3 fields per row
    
    @patch('psycopg2.extras.execute_values')
    def test_execute_batch(self, mock_execute_values):
        """Test batch execution."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.rowcount = 2
        mock_conn.cursor.return_value = mock_cursor
        
        params_list = [('1', 'test1'), ('2', 'test2')]
        result = self.provider.execute_batch(
            mock_conn,
            "INSERT INTO test VALUES %s",
            params_list
        )
        
        assert result['affected_rows'] == 2
        assert result['batch_size'] == 2
        mock_execute_values.assert_called_once()
        mock_conn.commit.assert_called_once()
    
    def test_select_sql_with_filters(self):
        """Test SELECT SQL with filters."""
        filters = {
            'name': 'test',
            'age__gt': 18,
            'status__in': ['active', 'pending']
        }
        
        sql, params = self.provider.select_sql(
            SampleModel,
            filters=filters,
            limit=10,
            order_by=['-created_at', 'name']
        )
        
        assert 'SELECT * FROM test_models' in sql
        assert 'name = %s' in sql
        assert 'age > %s' in sql
        assert 'status IN (%s, %s)' in sql
        assert 'ORDER BY created_at DESC, name ASC' in sql
        assert 'LIMIT 10' in sql
        assert len(params) == 4  # name, age, 2 status values