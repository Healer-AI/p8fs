"""Unit tests for TiDB provider."""

from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from p8fs.models import AbstractModel
from p8fs.providers.tidb import TiDBProvider


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


class SampleEmbeddingModel(AbstractModel):
    """Test model with embedding fields."""
    id: str
    name: str
    content: str
    
    @classmethod
    def to_sql_schema(cls):
        return {
            'table_name': 'embedding_models',
            'key_field': 'id',
            'fields': {
                'id': {'type': str, 'is_primary_key': True},
                'name': {'type': str, 'nullable': False},
                'content': {'type': str, 'is_embedding': True}
            },
            'embedding_fields': ['content'],
            'tenant_isolated': True
        }


class TestTiDBProvider:
    """Test TiDB provider implementation."""
    
    def setup_method(self):
        """Set up test provider."""
        self.provider = TiDBProvider()
    
    def test_get_dialect_name(self):
        """Test dialect name."""
        assert self.provider.get_dialect_name() == 'tidb'
    
    def test_get_connection_string(self):
        """Test connection string generation."""
        conn_str = self.provider.get_connection_string(
            host='testhost',
            port=4001,
            user='testuser',
            password='testpass',
            database='testdb'
        )
        assert conn_str == 'mysql://testuser:testpass@testhost:4001/testdb'
    
    def test_get_connection_string_no_password(self):
        """Test connection string without password."""
        conn_str = self.provider.get_connection_string(
            host='localhost',
            user='root',
            database='test'
        )
        assert conn_str == 'mysql://root@localhost:4000/test'
    
    def test_get_vector_type(self):
        """Test vector type."""
        assert self.provider.get_vector_type() == 'VECTOR'
    
    def test_get_json_type(self):
        """Test JSON type."""
        assert self.provider.get_json_type() == 'JSON'
    
    def test_supports_vector_operations(self):
        """Test vector operations support."""
        assert self.provider.supports_vector_operations() is True
    
    def test_get_vector_distance_function(self):
        """Test vector distance function names."""
        assert self.provider.get_vector_distance_function('cosine') == 'VEC_COSINE_DISTANCE'
        assert self.provider.get_vector_distance_function('l2') == 'VEC_L2_DISTANCE'
        assert self.provider.get_vector_distance_function('inner_product') == 'VEC_NEGATIVE_INNER_PRODUCT'
        assert self.provider.get_vector_distance_function('unknown') == 'VEC_COSINE_DISTANCE'  # default
    
    def test_get_vector_operator(self):
        """Test vector operator compatibility method."""
        assert self.provider.get_vector_operator('cosine') == 'VEC_COSINE_DISTANCE'
    
    def test_create_table_sql(self):
        """Test table creation SQL."""
        sql = self.provider.create_table_sql(SampleModel)
        
        assert 'CREATE TABLE IF NOT EXISTS test_models' in sql
        assert 'id VARCHAR(255) PRIMARY KEY' in sql
        assert 'name VARCHAR(255) NOT NULL' in sql
        assert 'description VARCHAR(255)' in sql
        assert 'created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP' in sql
        assert 'updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP' in sql
        assert 'ENGINE=InnoDB' in sql
        assert 'CHARSET=utf8mb4 COLLATE=utf8mb4_bin' in sql
    
    def test_create_embedding_table_sql(self):
        """Test embedding table creation SQL."""
        sql = self.provider.create_embedding_table_sql(SampleEmbeddingModel)

        # NOTE: CREATE SCHEMA statement is now in the migration header, not per-table
        # The embeddings database should be created separately
        assert 'CREATE TABLE IF NOT EXISTS embeddings.embedding_models_embeddings' in sql
        assert 'embedding_vector VECTOR(' in sql
        assert 'tenant_id VARCHAR(36) NOT NULL' in sql  # tenant isolation
        assert 'INDEX idx_entity_field (entity_id, field_name)' in sql
        assert 'ALTER TABLE embeddings.embedding_models_embeddings SET TIFLASH REPLICA 1' in sql
    
    def test_create_embedding_table_sql_no_embeddings(self):
        """Test embedding table creation with no embedding fields."""
        sql = self.provider.create_embedding_table_sql(SampleModel)
        assert sql == ""
    
    def test_map_python_type(self):
        """Test Python type mapping."""
        assert self.provider.map_python_type(str) == 'VARCHAR(255)'
        assert self.provider.map_python_type(int) == 'BIGINT'
        assert self.provider.map_python_type(float) == 'DOUBLE'
        assert self.provider.map_python_type(bool) == 'TINYINT(1)'
        
        from datetime import datetime
        from uuid import UUID
        assert self.provider.map_python_type(UUID) == 'VARCHAR(36)'
        assert self.provider.map_python_type(datetime) == 'TIMESTAMP'
        
        # Test Union types
        import typing
        union_type = typing.Union[UUID, str]
        assert self.provider.map_python_type(union_type) == 'VARCHAR(36)'  # UUID takes precedence
        
        # Test list types
        assert self.provider.map_python_type(list[float]) == 'JSON'
        assert self.provider.map_python_type(list[str]) == 'JSON'
    
    @patch('p8fs_cluster.config.settings.config.db_pool_enabled', False)
    @patch('pymysql.connect')
    def test_connect_sync_new_connection(self, mock_connect):
        """Test synchronous connection creation without connection pooling."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        mock_connect.return_value = mock_conn

        conn = self.provider.connect_sync('mysql://root@localhost:4000/test')

        mock_connect.assert_called_once()
        mock_cursor.execute.assert_called_with("SELECT 1")
        assert conn == mock_conn
    
    @patch('p8fs_cluster.config.settings.config.db_pool_enabled', False)
    @patch('pymysql.connect')
    def test_connect_sync_existing_connection(self, mock_connect):
        """Test synchronous connection reuse without connection pooling."""
        mock_conn = Mock()
        mock_conn.ping.return_value = True
        self.provider._connection = mock_conn

        conn = self.provider.connect_sync('mysql://root@localhost:4000/test')

        # Should not create new connection
        mock_connect.assert_not_called()
        assert conn == mock_conn
    
    def test_apply_user_context(self):
        """Test user context application."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        
        user_id = str(uuid4())
        tenant_id = str(uuid4())
        
        self.provider.apply_user_context(mock_conn, user_id, tenant_id)
        
        # Should set session variables
        calls = mock_cursor.execute.call_args_list
        assert len(calls) == 2
        assert "SET @p8fs_user_id" in calls[0][0][0]
        assert "SET @p8fs_tenant_id" in calls[1][0][0]
    
    def test_execute_select(self):
        """Test SELECT query execution."""
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'id': '1', 'name': 'test1'},
            {'id': '2', 'name': 'test2'}
        ]
        mock_conn.cursor.return_value = mock_cursor
        
        results = self.provider.execute(
            mock_conn,
            "SELECT * FROM test_models",
            None
        )
        
        assert len(results) == 2
        assert results[0]['id'] == '1'
        assert results[1]['name'] == 'test2'
    
    def test_execute_insert(self):
        """Test INSERT query execution."""
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value = mock_cursor
        
        results = self.provider.execute(
            mock_conn,
            "INSERT INTO test_models (id, name) VALUES (%s, %s)",
            ('123', 'test')
        )
        
        assert results == [{'affected_rows': 1}]
        mock_conn.commit.assert_called_once()
    
    def test_execute_batch(self):
        """Test batch query execution."""
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value = mock_cursor
        
        query = "INSERT INTO test VALUES (%s, %s)"
        params_list = [('1', 'test1'), ('2', 'test2')]
        
        result = self.provider.execute_batch(mock_conn, query, params_list)
        
        assert result['affected_rows'] == 2
        assert result['batch_size'] == 2
        mock_conn.commit.assert_called_once()
    
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
        assert '"key"' in serialized['metadata']  # JSON format
    
    def test_upsert_sql(self):
        """Test UPSERT SQL generation."""
        values = {
            'id': '123',
            'name': 'test',
            'description': 'test desc'
        }

        sql, params = self.provider.upsert_sql(SampleModel, values)

        # TiDB uses INSERT ... ON DUPLICATE KEY UPDATE for upserts
        assert 'INSERT INTO test_models' in sql
        assert '(id, name, description)' in sql
        assert 'VALUES (%s, %s, %s)' in sql
        assert 'ON DUPLICATE KEY UPDATE' in sql
        assert len(params) == 3
    
    def test_batch_upsert_sql(self):
        """Test batch UPSERT SQL generation."""
        values_list = [
            {'id': '1', 'name': 'test1', 'description': 'desc1'},
            {'id': '2', 'name': 'test2', 'description': 'desc2'}
        ]

        sql, params_list = self.provider.batch_upsert_sql(SampleModel, values_list)

        # Batch upserts use REPLACE INTO for simplicity
        assert 'REPLACE INTO test_models' in sql
        assert '(id, name, description)' in sql
        assert 'VALUES (%s, %s, %s)' in sql
        assert len(params_list) == 2
        assert len(params_list[0]) == 3  # 3 fields per row
    
    def test_batch_upsert_sql_empty_list(self):
        """Test batch UPSERT with empty list."""
        with pytest.raises(ValueError, match="Empty values list"):
            self.provider.batch_upsert_sql(SampleModel, [])
    
    def test_select_sql_with_filters(self):
        """Test SELECT SQL with filters."""
        filters = {
            'name': 'test',
            'age__gt': 18,
            'status__in': ['active', 'pending'],
            'content__like': '%search%',
            'metadata__contains': '{"key": "value"}'
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
        assert 'content LIKE %s' in sql
        assert 'JSON_CONTAINS(metadata, %s)' in sql
        assert 'ORDER BY created_at DESC, name ASC' in sql
        assert 'LIMIT 10' in sql
        assert len(params) == 6  # name, age, 2 status values, like pattern, json contains
    
    def test_delete_sql(self):
        """Test DELETE SQL generation."""
        sql, params = self.provider.delete_sql(SampleModel, '123')
        
        assert 'DELETE FROM test_models WHERE id = %s' in sql
        assert params == ('123',)
    
    def test_delete_sql_with_tenant(self):
        """Test DELETE SQL with tenant isolation."""
        # Mock tenant isolated model
        schema = SampleEmbeddingModel.to_sql_schema()
        
        with patch.object(SampleEmbeddingModel, 'to_sql_schema', return_value=schema):
            sql, params = self.provider.delete_sql(SampleEmbeddingModel, '123', tenant_id='tenant1')
            
            assert 'DELETE FROM embedding_models WHERE id = %s AND tenant_id = %s' in sql
            assert params == ('123', 'tenant1')
    
    def test_vector_similarity_search_sql(self):
        """Test vector similarity search SQL."""
        query_vector = [0.1, 0.2, 0.3]
        
        sql, params = self.provider.vector_similarity_search_sql(
            SampleEmbeddingModel,
            query_vector,
            'content',
            limit=5,
            threshold=0.8,
            metric='cosine'
        )
        
        assert 'VEC_COSINE_DISTANCE(embedding_vector, VEC_FROM_TEXT(%s))' in sql
        assert 'FROM embeddings.embedding_models_embeddings' in sql
        assert 'WHERE field_name = %s' in sql
        assert 'ORDER BY distance ASC' in sql
        assert 'LIMIT %s' in sql
        
        # Check parameters
        import json
        expected_vector = json.dumps(query_vector)
        assert expected_vector in params
        assert 'content' in params
        assert 5 in params
    
    def test_semantic_search_sql(self):
        """Test semantic search SQL with JOIN."""
        query_vector = [0.1, 0.2, 0.3]
        
        sql, params = self.provider.semantic_search_sql(
            SampleEmbeddingModel,
            query_vector,
            field_name='content',
            limit=10,
            threshold=0.7,
            tenant_id='tenant1'
        )
        
        assert 'FROM embedding_models m' in sql
        assert 'INNER JOIN embeddings.embedding_models_embeddings e ON m.id = e.entity_id' in sql
        assert 'e.field_name = %s' in sql
        assert 'm.tenant_id = %s' in sql
        assert 'e.tenant_id = %s' in sql
        assert 'VEC_COSINE_DISTANCE(e.embedding_vector, VEC_FROM_TEXT(%s))' in sql
        
        # Should include tenant_id twice (main table + embedding table)
        tenant_count = sum(1 for p in params if p == 'tenant1')
        assert tenant_count == 2
    
    def test_create_full_text_index_sql(self):
        """Test full-text index creation."""
        sql = self.provider.create_full_text_index_sql('test_table', 'content')
        assert sql == "CREATE FULLTEXT INDEX idx_test_table_content_fulltext ON test_table (content);"
    
    def test_get_full_text_search_sql(self):
        """Test full-text search SQL generation."""
        sql, params = self.provider.get_full_text_search_sql(
            SampleModel,
            'search query',
            'description',
            limit=20
        )
        
        assert 'MATCH(description) AGAINST(%s IN NATURAL LANGUAGE MODE)' in sql
        assert 'ORDER BY relevance_score DESC' in sql
        assert 'LIMIT %s' in sql
        assert 'search query' in params
        assert 20 in params
    
    def test_get_full_text_search_sql_with_tenant(self):
        """Test full-text search SQL with tenant isolation."""
        with patch.object(SampleModel, 'to_sql_schema') as mock_schema:
            mock_schema.return_value = {
                'table_name': 'test_models',
                'tenant_isolated': True
            }
            
            sql, params = self.provider.get_full_text_search_sql(
                SampleModel,
                'search query',
                'description',
                limit=20,
                tenant_id='tenant1'
            )
            
            assert 'tenant_id = %s' in sql
            assert 'tenant1' in params
    
    def test_get_partition_sql(self):
        """Test table partitioning SQL generation."""
        sql = self.provider.get_partition_sql('test_table')
        
        assert 'ALTER TABLE test_table' in sql
        assert 'PARTITION BY RANGE (created_at)' in sql
        assert 'PARTITION p202501 VALUES LESS THAN' in sql
        assert 'PARTITION pmax VALUES LESS THAN MAXVALUE' in sql
    
    def test_get_partition_sql_custom(self):
        """Test table partitioning with custom parameters."""
        partitions = [
            "PARTITION p1 VALUES LESS THAN ('2025-01-01')",
            "PARTITION p2 VALUES LESS THAN MAXVALUE"
        ]
        
        sql = self.provider.get_partition_sql(
            'custom_table',
            partition_type='HASH',
            partition_column='id',
            partitions=partitions
        )
        
        assert 'ALTER TABLE custom_table' in sql
        assert 'PARTITION BY HASH (id)' in sql
        assert 'PARTITION p1 VALUES LESS THAN' in sql
        assert 'PARTITION p2 VALUES LESS THAN MAXVALUE' in sql
    
    def test_get_vacuum_sql(self):
        """Test table optimization SQL (equivalent to VACUUM)."""
        sql = self.provider.get_vacuum_sql('test_table')
        assert sql == "ANALYZE TABLE test_table;"
    
    def test_get_tiflash_replica_sql(self):
        """Test TiFlash replica SQL generation."""
        sql = self.provider.get_tiflash_replica_sql('test_table', 2)
        assert sql == "ALTER TABLE test_table SET TIFLASH REPLICA 2;"
    
    def test_get_placement_rule_sql(self):
        """Test placement rule SQL generation."""
        sql = self.provider.get_placement_rule_sql('test_table', region='us-west', replicas=5)
        
        assert 'ALTER TABLE test_table' in sql
        assert 'PLACEMENT POLICY' in sql
        assert 'us-west' in sql
        assert 'REPLICAS=5' in sql
    
    def test_optimize_table_sql(self):
        """Test table optimization SQL."""
        sql = self.provider.optimize_table_sql('test_table')
        assert sql == "ANALYZE TABLE test_table;"
    
    def test_get_migration_sql(self):
        """Test migration SQL generation."""
        migrations = self.provider.get_migration_sql('1.0.0', '1.1.0')
        
        assert isinstance(migrations, list)
        assert len(migrations) == 2
        assert 'ALTER TABLE documents ADD COLUMN version' in migrations[0]
        assert 'UPDATE documents SET version' in migrations[1]
    
    def test_get_migration_sql_no_migration(self):
        """Test migration SQL with no defined migration."""
        migrations = self.provider.get_migration_sql('2.0.0', '3.0.0')
        assert migrations == []
    
    def test_connection_error_handling(self):
        """Test connection error handling."""
        with patch('pymysql.connect', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="Connection failed"):
                self.provider.connect_sync()
    
    def test_execute_error_handling(self):
        """Test query execution error handling."""
        import pymysql
        
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.execute.side_effect = pymysql.Error("Query failed")
        mock_conn.cursor.return_value = mock_cursor
        
        with pytest.raises(pymysql.Error, match="Query failed"):
            self.provider.execute(mock_conn, "INVALID SQL", None)
        
        mock_conn.rollback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_async_execute(self):
        """Test async execute (currently calls sync version)."""
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{'id': '1'}]
        mock_conn.cursor.return_value = mock_cursor
        
        # Should work the same as sync execute for now
        result = await self.provider.async_execute(mock_conn, "SELECT * FROM test", None)
        
        assert result == [{'id': '1'}]
    
    def test_vector_dimensions_for_model(self):
        """Test vector dimensions determination."""
        schema = {
            'embedding_providers': {
                'field1': 'openai'
            }
        }
        
        # Should fallback to default since config module might not be available
        dims = self.provider._get_vector_dimensions_for_model(schema)
        assert dims > 0  # Just verify we get valid dimensions, not specific value

        # Test with no embedding providers
        dims = self.provider._get_vector_dimensions_for_model({})
        assert dims > 0  # Just verify we get valid dimensions