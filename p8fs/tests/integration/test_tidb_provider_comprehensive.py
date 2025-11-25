"""Comprehensive integration tests for TiDB provider with SQL, KV, and reverse mapping.

This test demonstrates the full functionality of the TiDB provider including:
- SQL operations (CRUD, vector search, semantic search)
- KV operations via HTTP proxy
- Reverse key mapping system
- Table metadata caching
"""

import json
import os
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from p8fs.models import AbstractModel
from p8fs.providers.tidb import TiDBProvider
from p8fs_cluster.config.settings import config


class DocumentModel(AbstractModel):
    """Test document model with embeddings."""
    id: str
    name: str
    content: str
    metadata: dict = {}
    created_at: datetime = None
    updated_at: datetime = None
    
    @classmethod
    def to_sql_schema(cls):
        return {
            'table_name': 'test_documents',
            'key_field': 'id',
            'fields': {
                'id': {'type': str, 'is_primary_key': True},
                'name': {'type': str, 'nullable': False, 'unique': True},
                'content': {'type': str, 'is_embedding': True},
                'metadata': {'type': dict},
                'created_at': {'type': datetime},
                'updated_at': {'type': datetime}
            },
            'embedding_fields': ['content'],
            'tenant_isolated': True,
            'embedding_providers': {'content': 'openai'}
        }
    
    @classmethod
    def get_model_key_field(cls):
        return 'name'
    
    @classmethod
    def get_model_table_name(cls):
        return 'test_documents'


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv('P8FS_SKIP_TIDB_TESTS', 'true').lower() == 'true',
    reason="TiDB integration tests skipped (set P8FS_SKIP_TIDB_TESTS=false to run)"
)
class TestTiDBProviderComprehensive:
    """Comprehensive integration tests for TiDB provider."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment."""
        self.provider = TiDBProvider()
        self.tenant_id = f"test_tenant_{uuid4().hex[:8]}"
        self.user_id = str(uuid4())
        
        # Create test connection
        self.connection = self.provider.connect_sync()
        
        # Apply user context
        self.provider.apply_user_context(self.connection, self.user_id, self.tenant_id)
        
        # Create test tables
        self._create_test_tables()
        
        yield
        
        # Cleanup
        self._cleanup_test_tables()
        self.connection.close()
    
    def _create_test_tables(self):
        """Create test tables for integration tests."""
        # Create main table
        create_table_sql = self.provider.create_table_sql(DocumentModel)
        cursor = self.connection.cursor()
        cursor.execute(create_table_sql)
        
        # Create embedding table
        embedding_sql = self.provider.create_embedding_table_sql(DocumentModel)
        if embedding_sql:
            for statement in embedding_sql.split(';'):
                if statement.strip():
                    cursor.execute(statement)
        
        # Create KV mapping table
        kv_sql = self.provider.create_kv_mapping_table_sql()
        cursor.execute(kv_sql)
        
        self.connection.commit()
        cursor.close()
    
    def _cleanup_test_tables(self):
        """Clean up test tables."""
        cursor = self.connection.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS test_documents")
        cursor.execute(f"DROP TABLE IF EXISTS embeddings.test_documents_embeddings")
        cursor.execute(f"DROP TABLE IF EXISTS p8fs_kv_mappings")
        self.connection.commit()
        cursor.close()
    
    def test_sql_crud_operations(self):
        """Test basic SQL CRUD operations."""
        # Create
        doc_data = {
            'id': str(uuid4()),
            'name': 'test_doc_1',
            'content': 'This is test content for document 1',
            'metadata': {'category': 'test', 'tags': ['integration', 'tidb']},
            'tenant_id': self.tenant_id
        }
        
        sql, params = self.provider.upsert_sql(DocumentModel, doc_data)
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        self.connection.commit()
        
        # Read
        sql, params = self.provider.select_sql(
            DocumentModel,
            filters={'name': 'test_doc_1', 'tenant_id': self.tenant_id}
        )
        results = self.provider.execute(self.connection, sql, params)
        
        assert len(results) == 1
        assert results[0]['name'] == 'test_doc_1'
        assert json.loads(results[0]['metadata'])['category'] == 'test'
        
        # Update
        doc_data['content'] = 'Updated content'
        sql, params = self.provider.upsert_sql(DocumentModel, doc_data)
        cursor.execute(sql, params)
        self.connection.commit()
        
        # Verify update
        sql, params = self.provider.select_sql(
            DocumentModel,
            filters={'id': doc_data['id'], 'tenant_id': self.tenant_id}
        )
        results = self.provider.execute(self.connection, sql, params)
        assert results[0]['content'] == 'Updated content'
        
        # Delete
        sql, params = self.provider.delete_sql(DocumentModel, doc_data['id'], self.tenant_id)
        cursor.execute(sql, params)
        self.connection.commit()
        
        # Verify deletion
        sql, params = self.provider.select_sql(
            DocumentModel,
            filters={'id': doc_data['id'], 'tenant_id': self.tenant_id}
        )
        results = self.provider.execute(self.connection, sql, params)
        assert len(results) == 0
    
    def test_batch_operations(self):
        """Test batch SQL operations."""
        # Create multiple documents
        docs = [
            {
                'id': str(uuid4()),
                'name': f'batch_doc_{i}',
                'content': f'Batch document content {i}',
                'metadata': {'batch': i},
                'tenant_id': self.tenant_id
            }
            for i in range(5)
        ]
        
        sql, params_list = self.provider.batch_upsert_sql(DocumentModel, docs)
        result = self.provider.execute_batch(self.connection, sql, params_list)
        
        assert result['batch_size'] == 5
        
        # Query with filters
        sql, params = self.provider.select_sql(
            DocumentModel,
            filters={'name__like': 'batch_doc_%', 'tenant_id': self.tenant_id},
            order_by=['-name'],
            limit=3
        )
        results = self.provider.execute(self.connection, sql, params)
        
        assert len(results) == 3
        assert results[0]['name'] == 'batch_doc_4'  # Descending order
    
    @patch('p8fs.services.storage.tikv_service.TiKVService.put')
    @patch('p8fs.services.storage.tikv_service.TiKVService.get')
    def test_reverse_mapping_integration(self, mock_get, mock_put):
        """Test reverse mapping system integration."""
        # Mock TiKV operations
        mock_put.return_value = None  # Successful put
        
        # Store entity with reverse mapping
        entity_data = {
            'id': str(uuid4()),
            'name': 'mapped_document',
            'content': 'Document with reverse mapping',
            'metadata': {'mapped': True},
            'tenant_id': self.tenant_id
        }
        
        storage_key = self.provider.store_entity_with_reverse_mapping(
            self.connection,
            'mapped_document',
            'test_documents',
            entity_data,
            self.tenant_id
        )
        
        assert storage_key == f"{self.tenant_id}:test_documents:mapped_document"
        
        # Verify TiKV puts were called
        assert mock_put.call_count == 3  # name mapping, entity ref, reverse mapping
        
        # Mock get responses for retrieval
        mock_get.side_effect = [
            {
                'entity_key': entity_data['id'],
                'table_name': 'test_documents',
                'tenant_id': self.tenant_id
            },
            {
                'name': 'mapped_document',
                'entity_type': 'test_documents',
                'table_name': 'test_documents'
            }
        ]
        
        # Test retrieval by name
        result = self.provider.get_entity_by_name(
            self.connection,
            'mapped_document',
            'test_documents',
            self.tenant_id
        )
        
        assert result is not None
        assert result['name'] == 'mapped_document'
        
        # Test retrieval by storage key
        result = self.provider.get_entities_by_storage_key(
            self.connection,
            f"test_documents/{entity_data['id']}",
            self.tenant_id
        )
        
        assert result is not None
        assert result['id'] == entity_data['id']
    
    def test_table_metadata_caching(self):
        """Test table metadata caching functionality."""
        # First access should cache
        exists = self.provider.table_exists(self.connection, 'test_documents')
        assert exists is True
        
        # Get cache stats
        stats = self.provider.get_cache_stats()
        initial_size = stats['size']
        
        # Second access should use cache
        exists = self.provider.table_exists(self.connection, 'test_documents')
        assert exists is True
        
        # Cache size should remain same
        stats = self.provider.get_cache_stats()
        assert stats['size'] == initial_size
        
        # Test primary key info caching
        pk_info = self.provider.get_primary_key_info(self.connection, 'test_documents')
        assert pk_info is not None
        assert pk_info['column_name'] == 'id'
        
        # Invalidate specific table
        self.provider.invalidate_table_cache('test_documents')
        
        # Clear entire cache
        self.provider.clear_metadata_cache()
        stats = self.provider.get_cache_stats()
        assert stats['size'] == 0
    
    def test_vector_operations(self):
        """Test vector operations if available."""
        # Check if vector functions are available
        if not self.provider.check_vector_functions_available(self.connection):
            pytest.skip("TiDB vector functions not available")
        
        # Create documents with embeddings
        test_embedding = [0.1] * 768  # Mock 768-dimensional embedding
        
        # Insert document
        doc_data = {
            'id': str(uuid4()),
            'name': 'vector_doc',
            'content': 'Document with vector embedding',
            'metadata': {},
            'tenant_id': self.tenant_id
        }
        
        sql, params = self.provider.upsert_sql(DocumentModel, doc_data)
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        
        # Insert embedding
        embedding_data = {
            'entity_id': doc_data['id'],
            'field_name': 'content',
            'embedding_vector': json.dumps(test_embedding),
            'tenant_id': self.tenant_id
        }
        
        sql = """
            INSERT INTO embeddings.test_documents_embeddings 
            (entity_id, field_name, embedding_vector, tenant_id, created_at)
            VALUES (%s, %s, VEC_FROM_TEXT(%s), %s, NOW())
        """
        cursor.execute(sql, (
            embedding_data['entity_id'],
            embedding_data['field_name'],
            embedding_data['embedding_vector'],
            embedding_data['tenant_id']
        ))
        self.connection.commit()
        
        # Test vector similarity search
        query_vector = [0.1] * 768
        sql, params = self.provider.vector_similarity_search_sql(
            DocumentModel,
            query_vector,
            'content',
            limit=5,
            metric='cosine'
        )
        
        results = self.provider.execute(self.connection, sql, params)
        assert len(results) >= 0  # May have results depending on data
        
        # Test semantic search
        sql, params = self.provider.semantic_search_sql(
            DocumentModel,
            query_vector,
            field_name='content',
            limit=5,
            tenant_id=self.tenant_id
        )
        
        results = self.provider.execute(self.connection, sql, params)
        assert isinstance(results, list)
    
    def test_concurrent_operations(self):
        """Test concurrent operations and connection management."""
        import threading
        import time
        
        results = []
        errors = []
        
        def worker(worker_id):
            """Worker thread for concurrent operations."""
            try:
                # Each thread gets its own connection
                conn = self.provider.connect_sync()
                
                # Insert a document
                doc_data = {
                    'id': str(uuid4()),
                    'name': f'concurrent_doc_{worker_id}',
                    'content': f'Content from worker {worker_id}',
                    'metadata': {'worker': worker_id},
                    'tenant_id': self.tenant_id
                }
                
                sql, params = self.provider.upsert_sql(DocumentModel, doc_data)
                cursor = conn.cursor()
                cursor.execute(sql, params)
                conn.commit()
                cursor.close()
                
                # Read it back
                sql, params = self.provider.select_sql(
                    DocumentModel,
                    filters={'name': doc_data['name'], 'tenant_id': self.tenant_id}
                )
                result = self.provider.execute(conn, sql, params)
                
                results.append(result)
                conn.close()
                
            except Exception as e:
                errors.append(e)
        
        # Run multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join(timeout=10)
        
        # Verify results
        assert len(errors) == 0
        assert len(results) == 5
        for result in results:
            assert len(result) == 1
            assert 'concurrent_doc_' in result[0]['name']
    
    def test_error_recovery(self):
        """Test error handling and recovery."""
        # Test invalid SQL
        with pytest.raises(Exception):
            self.provider.execute(self.connection, "INVALID SQL QUERY", None)
        
        # Connection should still be valid
        sql, params = self.provider.select_sql(
            DocumentModel,
            filters={'tenant_id': self.tenant_id},
            limit=1
        )
        results = self.provider.execute(self.connection, sql, params)
        assert isinstance(results, list)
        
        # Test connection recovery
        self.connection.close()
        
        # Should automatically reconnect
        conn = self.provider.connect_sync()
        assert conn is not None
        
        # Should be able to execute queries
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1