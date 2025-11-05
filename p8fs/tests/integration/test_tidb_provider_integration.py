"""Integration tests for TiDB provider connection and operations.

This test suite verifies:
- Connection to TiDB (overriding default PostgreSQL)
- Table creation capabilities
- Semantic search functionality
- Vector operations
- Full-text search
- Other TiDB-specific features
"""

import json
import os
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from p8fs.models import AbstractModel
from p8fs.providers import get_provider
from p8fs.providers.tidb import TiDBProvider
from p8fs_cluster.config.settings import config


class TestDocument(AbstractModel):
    """Test document model with various field types."""
    id: str
    title: str
    content: str
    summary: str = ""
    tags: list[str] = []
    metadata: dict = {}
    score: float = 0.0
    published: bool = False
    created_at: datetime = None
    
    @classmethod
    def to_sql_schema(cls):
        return {
            'table_name': 'test_documents',
            'key_field': 'id',
            'fields': {
                'id': {'type': str, 'is_primary_key': True},
                'title': {'type': str, 'nullable': False, 'unique': True},
                'content': {'type': str, 'is_embedding': True},
                'summary': {'type': str, 'is_embedding': True, 'nullable': True},
                'tags': {'type': list[str]},
                'metadata': {'type': dict},
                'score': {'type': float},
                'published': {'type': bool},
                'created_at': {'type': datetime}
            },
            'embedding_fields': ['content', 'summary'],
            'tenant_isolated': True,
            'embedding_providers': {
                'content': 'openai',
                'summary': 'openai'
            }
        }


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv('P8FS_SKIP_TIDB_TESTS', 'true').lower() == 'true',
    reason="TiDB integration tests skipped (set P8FS_SKIP_TIDB_TESTS=false to run)"
)
class TestTiDBProviderIntegration:
    """Integration tests for TiDB provider."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment with TiDB provider."""
        # Force TiDB provider instead of default PostgreSQL
        with patch.object(config, 'storage_provider', 'tidb'):
            self.provider = get_provider()
            assert isinstance(self.provider, TiDBProvider), f"Expected TiDBProvider, got {type(self.provider)}"
        
        # Alternative direct instantiation if patching doesn't work
        if not isinstance(self.provider, TiDBProvider):
            self.provider = TiDBProvider()
        
        self.tenant_id = f"test_{uuid4().hex[:8]}"
        self.user_id = str(uuid4())
        
        # Create connection
        self.connection = self.provider.connect_sync()
        assert self.connection is not None
        
        # Apply user context
        self.provider.apply_user_context(self.connection, self.user_id, self.tenant_id)
        
        # Clean up any existing test tables
        self._cleanup_tables()
        
        yield
        
        # Cleanup after tests
        self._cleanup_tables()
        if self.connection:
            self.connection.close()
    
    def _cleanup_tables(self):
        """Clean up test tables."""
        cursor = self.connection.cursor()
        try:
            # Drop tables if they exist
            cursor.execute("DROP TABLE IF EXISTS test_documents")
            cursor.execute("DROP TABLE IF EXISTS embeddings.test_documents_embeddings")
            cursor.execute("DROP TABLE IF EXISTS p8fs_kv_mappings")
            self.connection.commit()
        except Exception as e:
            print(f"Cleanup warning: {e}")
        finally:
            cursor.close()
    
    def test_provider_type(self):
        """Test that we're using TiDB provider, not PostgreSQL."""
        assert isinstance(self.provider, TiDBProvider)
        assert self.provider.get_dialect_name() == 'tidb'
        assert 'mysql://' in self.provider.get_connection_string()
    
    def test_connection_and_basic_query(self):
        """Test basic connection and query execution."""
        # Test connection
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        assert result['test'] == 1
        
        # Test TiDB version
        cursor.execute("SELECT VERSION() as version")
        result = cursor.fetchone()
        assert 'TiDB' in result['version'] or 'MySQL' in result['version']
        cursor.close()
    
    def test_table_creation(self):
        """Test creating tables with TiDB-specific features."""
        # Create main table
        create_sql = self.provider.create_table_sql(TestDocument)
        assert 'CREATE TABLE IF NOT EXISTS test_documents' in create_sql
        assert 'ENGINE=InnoDB' in create_sql
        assert 'CHARSET=utf8mb4' in create_sql
        
        cursor = self.connection.cursor()
        cursor.execute(create_sql)
        
        # Create embedding table
        embedding_sql = self.provider.create_embedding_table_sql(TestDocument)
        assert 'CREATE SCHEMA IF NOT EXISTS embeddings' in embedding_sql
        assert 'VECTOR(' in embedding_sql
        assert 'SET TIFLASH REPLICA' in embedding_sql
        
        # Execute embedding table creation
        for statement in embedding_sql.split(';'):
            if statement.strip():
                cursor.execute(statement)
        
        # Create KV mapping table
        kv_sql = self.provider.create_kv_mapping_table_sql()
        cursor.execute(kv_sql)
        
        self.connection.commit()
        
        # Verify tables exist
        assert self.provider.table_exists(self.connection, 'test_documents')
        
        # Test table metadata caching
        pk_info = self.provider.get_primary_key_info(self.connection, 'test_documents')
        assert pk_info is not None
        assert pk_info['column_name'] == 'id'
    
    def test_crud_operations(self):
        """Test Create, Read, Update, Delete operations."""
        # Ensure tables exist
        self.test_table_creation()
        
        # Create document
        doc_id = str(uuid4())
        doc_data = {
            'id': doc_id,
            'title': 'Integration Test Document',
            'content': 'This is a test document for TiDB integration testing',
            'summary': 'Test summary',
            'tags': ['test', 'tidb', 'integration'],
            'metadata': {'category': 'testing', 'priority': 'high'},
            'score': 0.95,
            'published': True,
            'created_at': datetime.utcnow(),
            'tenant_id': self.tenant_id
        }
        
        # Test REPLACE INTO (TiDB upsert)
        sql, params = self.provider.upsert_sql(TestDocument, doc_data)
        assert 'REPLACE INTO test_documents' in sql
        
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        self.connection.commit()
        
        # Read document
        sql, params = self.provider.select_sql(
            TestDocument,
            filters={'id': doc_id, 'tenant_id': self.tenant_id}
        )
        results = self.provider.execute(self.connection, sql, params)
        
        assert len(results) == 1
        result = results[0]
        assert result['title'] == 'Integration Test Document'
        assert result['score'] == 0.95
        assert result['published'] == 1  # MySQL returns tinyint for bool
        
        # Update document
        doc_data['score'] = 0.99
        doc_data['summary'] = 'Updated summary'
        sql, params = self.provider.upsert_sql(TestDocument, doc_data)
        cursor.execute(sql, params)
        self.connection.commit()
        
        # Verify update
        sql, params = self.provider.select_sql(
            TestDocument,
            filters={'id': doc_id, 'tenant_id': self.tenant_id}
        )
        results = self.provider.execute(self.connection, sql, params)
        assert results[0]['score'] == 0.99
        assert results[0]['summary'] == 'Updated summary'
        
        # Delete document
        sql, params = self.provider.delete_sql(TestDocument, doc_id, self.tenant_id)
        cursor.execute(sql, params)
        self.connection.commit()
        
        # Verify deletion
        sql, params = self.provider.select_sql(
            TestDocument,
            filters={'id': doc_id, 'tenant_id': self.tenant_id}
        )
        results = self.provider.execute(self.connection, sql, params)
        assert len(results) == 0
    
    def test_batch_operations(self):
        """Test batch insert and query operations."""
        # Ensure tables exist
        self.test_table_creation()
        
        # Create multiple documents
        docs = []
        for i in range(10):
            docs.append({
                'id': str(uuid4()),
                'title': f'Batch Document {i}',
                'content': f'Content for batch document number {i}',
                'summary': f'Summary {i}',
                'tags': ['batch', f'doc{i}'],
                'metadata': {'batch_id': i, 'type': 'test'},
                'score': i * 0.1,
                'published': i % 2 == 0,
                'created_at': datetime.utcnow(),
                'tenant_id': self.tenant_id
            })
        
        # Batch insert
        sql, params_list = self.provider.batch_upsert_sql(TestDocument, docs)
        result = self.provider.execute_batch(self.connection, sql, params_list)
        assert result['batch_size'] == 10
        assert result['affected_rows'] >= 10  # REPLACE might affect more rows
        
        # Query with filters
        sql, params = self.provider.select_sql(
            TestDocument,
            filters={
                'tenant_id': self.tenant_id,
                'published': True,
                'score__gte': 0.5
            },
            order_by=['-score'],
            limit=5
        )
        results = self.provider.execute(self.connection, sql, params)
        
        assert len(results) <= 5
        if results:
            # Verify descending order
            scores = [r['score'] for r in results]
            assert scores == sorted(scores, reverse=True)
    
    def test_vector_operations_if_available(self):
        """Test vector operations if TiDB supports them."""
        # Check if vector functions are available
        if not self.provider.check_vector_functions_available(self.connection):
            pytest.skip("TiDB vector functions not available in this instance")
        
        # Ensure tables exist
        self.test_table_creation()
        
        # Create document with mock embedding
        doc_id = str(uuid4())
        doc_data = {
            'id': doc_id,
            'title': 'Vector Search Test',
            'content': 'Document for testing vector search capabilities',
            'summary': 'Vector test summary',
            'tenant_id': self.tenant_id
        }
        
        sql, params = self.provider.upsert_sql(TestDocument, doc_data)
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        
        # Insert mock embedding (768-dimensional)
        test_embedding = [0.1 + i * 0.001 for i in range(768)]
        embedding_sql = """
            INSERT INTO embeddings.test_documents_embeddings 
            (entity_id, field_name, embedding_vector, tenant_id, created_at)
            VALUES (%s, %s, VEC_FROM_TEXT(%s), %s, NOW())
        """
        cursor.execute(embedding_sql, (
            doc_id,
            'content',
            json.dumps(test_embedding),
            self.tenant_id
        ))
        self.connection.commit()
        
        # Test vector similarity search
        query_vector = [0.1 + i * 0.001 for i in range(768)]  # Similar vector
        sql, params = self.provider.vector_similarity_search_sql(
            TestDocument,
            query_vector,
            'content',
            limit=5,
            metric='cosine'
        )
        
        assert 'VEC_COSINE_DISTANCE' in sql
        assert 'VEC_FROM_TEXT' in sql
        
        results = self.provider.execute(self.connection, sql, params)
        assert isinstance(results, list)
        if results:
            assert 'distance' in results[0]
    
    def test_semantic_search(self):
        """Test semantic search with vector embeddings."""
        # Skip if vectors not available
        if not self.provider.check_vector_functions_available(self.connection):
            pytest.skip("TiDB vector functions not available")
        
        # Ensure tables exist
        self.test_table_creation()
        
        # Create test documents with embeddings
        cursor = self.connection.cursor()
        
        # Document 1: About machine learning
        doc1_id = str(uuid4())
        doc1_embedding = [0.8 if i % 10 == 0 else 0.1 for i in range(768)]  # Spike pattern
        
        cursor.execute(*self.provider.upsert_sql(TestDocument, {
            'id': doc1_id,
            'title': 'Introduction to Machine Learning',
            'content': 'Machine learning is a subset of artificial intelligence',
            'tenant_id': self.tenant_id
        }))
        
        cursor.execute("""
            INSERT INTO embeddings.test_documents_embeddings 
            (entity_id, field_name, embedding_vector, tenant_id, created_at)
            VALUES (%s, %s, VEC_FROM_TEXT(%s), %s, NOW())
        """, (doc1_id, 'content', json.dumps(doc1_embedding), self.tenant_id))
        
        # Document 2: About databases
        doc2_id = str(uuid4())
        doc2_embedding = [0.1 if i % 10 == 0 else 0.8 for i in range(768)]  # Opposite pattern
        
        cursor.execute(*self.provider.upsert_sql(TestDocument, {
            'id': doc2_id,
            'title': 'Database Management Systems',
            'content': 'Relational databases store data in tables',
            'tenant_id': self.tenant_id
        }))
        
        cursor.execute("""
            INSERT INTO embeddings.test_documents_embeddings 
            (entity_id, field_name, embedding_vector, tenant_id, created_at)
            VALUES (%s, %s, VEC_FROM_TEXT(%s), %s, NOW())
        """, (doc2_id, 'content', json.dumps(doc2_embedding), self.tenant_id))
        
        self.connection.commit()
        
        # Search with query similar to doc1
        query_vector = [0.7 if i % 10 == 0 else 0.2 for i in range(768)]  # Similar to doc1
        
        sql, params = self.provider.semantic_search_sql(
            TestDocument,
            query_vector,
            field_name='content',
            limit=2,
            tenant_id=self.tenant_id
        )
        
        # Verify SQL structure
        assert 'INNER JOIN embeddings.test_documents_embeddings' in sql
        assert 'VEC_COSINE_DISTANCE' in sql
        assert 'ORDER BY distance ASC' in sql
        
        results = self.provider.execute(self.connection, sql, params)
        
        # Should return both documents ordered by similarity
        assert len(results) <= 2
        if len(results) == 2:
            # Doc1 should be more similar (lower distance)
            assert 'Machine Learning' in results[0]['title']
            assert 'Database' in results[1]['title']
    
    def test_advanced_queries(self):
        """Test advanced query features."""
        # Ensure tables exist
        self.test_table_creation()
        
        # Insert test data
        cursor = self.connection.cursor()
        test_docs = [
            {
                'id': str(uuid4()),
                'title': 'Advanced Query Test 1',
                'content': 'Testing advanced query features in TiDB',
                'tags': ['advanced', 'query', 'test'],
                'metadata': {'level': 1, 'type': 'advanced'},
                'score': 0.8,
                'tenant_id': self.tenant_id
            },
            {
                'id': str(uuid4()),
                'title': 'Advanced Query Test 2',
                'content': 'Another test for complex queries',
                'tags': ['advanced', 'complex'],
                'metadata': {'level': 2, 'type': 'complex'},
                'score': 0.6,
                'tenant_id': self.tenant_id
            },
            {
                'id': str(uuid4()),
                'title': 'Simple Test',
                'content': 'A simple test document',
                'tags': ['simple'],
                'metadata': {'level': 0, 'type': 'simple'},
                'score': 0.3,
                'tenant_id': self.tenant_id
            }
        ]
        
        for doc in test_docs:
            sql, params = self.provider.upsert_sql(TestDocument, doc)
            cursor.execute(sql, params)
        self.connection.commit()
        
        # Test complex filters
        sql, params = self.provider.select_sql(
            TestDocument,
            filters={
                'tenant_id': self.tenant_id,
                'title__like': '%Advanced%',
                'score__gt': 0.5,
                'tags__contains': json.dumps('advanced')
            },
            order_by=['-score', 'title']
        )
        
        results = self.provider.execute(self.connection, sql, params)
        assert len(results) == 2
        assert all('Advanced' in r['title'] for r in results)
        assert all(r['score'] > 0.5 for r in results)
        
        # Test JSON operations
        sql, params = self.provider.select_sql(
            TestDocument,
            filters={
                'tenant_id': self.tenant_id,
                'metadata__contains': json.dumps({'type': 'advanced'})
            }
        )
        
        assert 'JSON_CONTAINS' in sql
        results = self.provider.execute(self.connection, sql, params)
        assert len(results) == 1
        assert json.loads(results[0]['metadata'])['type'] == 'advanced'
    
    def test_full_text_search(self):
        """Test full-text search capabilities."""
        # Ensure tables exist
        self.test_table_creation()
        
        # Create full-text index
        cursor = self.connection.cursor()
        try:
            index_sql = self.provider.create_full_text_index_sql('test_documents', 'content')
            cursor.execute(index_sql)
            self.connection.commit()
        except Exception as e:
            # Index might already exist
            print(f"Full-text index creation: {e}")
        
        # Insert searchable documents
        docs = [
            {
                'id': str(uuid4()),
                'title': 'TiDB Features',
                'content': 'TiDB is a distributed SQL database with horizontal scalability',
                'tenant_id': self.tenant_id
            },
            {
                'id': str(uuid4()),
                'title': 'MySQL Compatibility',
                'content': 'TiDB maintains compatibility with MySQL protocol and syntax',
                'tenant_id': self.tenant_id
            },
            {
                'id': str(uuid4()),
                'title': 'Vector Search',
                'content': 'Modern databases support vector similarity search for AI applications',
                'tenant_id': self.tenant_id
            }
        ]
        
        for doc in docs:
            sql, params = self.provider.upsert_sql(TestDocument, doc)
            cursor.execute(sql, params)
        self.connection.commit()
        
        # Test full-text search
        sql, params = self.provider.get_full_text_search_sql(
            TestDocument,
            'distributed database',
            'content',
            limit=5,
            tenant_id=self.tenant_id
        )
        
        assert 'MATCH(content) AGAINST' in sql
        assert 'IN NATURAL LANGUAGE MODE' in sql
        
        results = self.provider.execute(self.connection, sql, params)
        assert isinstance(results, list)
        if results:
            assert 'relevance_score' in results[0]
    
    def test_tidb_specific_features(self):
        """Test TiDB-specific features like TiFlash and partitioning."""
        # Test TiFlash replica SQL generation
        tiflash_sql = self.provider.get_tiflash_replica_sql('test_documents', 2)
        assert tiflash_sql == "ALTER TABLE test_documents SET TIFLASH REPLICA 2;"
        
        # Test partition SQL generation
        partition_sql = self.provider.get_partition_sql(
            'test_documents',
            partition_type='RANGE',
            partition_column='created_at'
        )
        assert 'PARTITION BY RANGE' in partition_sql
        assert 'created_at' in partition_sql
        
        # Test placement rule SQL
        placement_sql = self.provider.get_placement_rule_sql(
            'test_documents',
            region='us-east',
            replicas=3
        )
        assert 'PLACEMENT POLICY' in placement_sql
        assert 'us-east' in placement_sql
        assert 'REPLICAS=3' in placement_sql
        
        # Test optimization SQL (ANALYZE TABLE)
        optimize_sql = self.provider.optimize_table_sql('test_documents')
        assert optimize_sql == "ANALYZE TABLE test_documents;"
    
    def test_error_handling_and_recovery(self):
        """Test error handling and connection recovery."""
        # Test invalid query
        with pytest.raises(Exception):
            self.provider.execute(self.connection, "INVALID SQL SYNTAX", None)
        
        # Connection should still work
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1
        
        # Test connection recovery after close
        self.connection.close()
        
        # Should reconnect automatically
        new_conn = self.provider.connect_sync()
        cursor = new_conn.cursor()
        cursor.execute("SELECT 2")
        assert cursor.fetchone()[0] == 2
        new_conn.close()
    
    def test_performance_features(self):
        """Test performance-related features."""
        # Ensure tables exist
        self.test_table_creation()
        
        # Test connection pooling by creating multiple connections
        connections = []
        for i in range(3):
            conn = self.provider.connect_sync()
            connections.append(conn)
        
        # All connections should work
        for i, conn in enumerate(connections):
            cursor = conn.cursor()
            cursor.execute(f"SELECT {i} as num")
            assert cursor.fetchone()['num'] == i
            cursor.close()
            conn.close()
        
        # Test metadata caching
        cache_stats_before = self.provider.get_cache_stats()
        
        # Access table metadata multiple times
        for _ in range(5):
            self.provider.table_exists(self.connection, 'test_documents')
            self.provider.get_primary_key_info(self.connection, 'test_documents')
        
        cache_stats_after = self.provider.get_cache_stats()
        # Cache should have entries
        assert cache_stats_after['size'] > 0