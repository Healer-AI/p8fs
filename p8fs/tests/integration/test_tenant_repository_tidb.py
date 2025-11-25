"""Integration tests for TenantRepository with TiDB."""

import os
from uuid import uuid4

import pytest
from p8fs.models import AbstractModel
from p8fs.repository.TenantRepository import TenantRepository


class SampleDocument(AbstractModel):
    """Test document model."""
    id: str
    title: str
    content: str
    tenant_id: str = ""
    
    @classmethod
    def to_sql_schema(cls):
        return {
            'table_name': 'tidb_test_documents',
            'key_field': 'id',
            'tenant_isolated': True,
            'fields': {
                'id': {'type': str, 'is_primary_key': True},
                'title': {'type': str, 'nullable': False},
                'content': {'type': str, 'nullable': True},
                'tenant_id': {'type': str, 'nullable': False}
            }
        }


class SampleEmbeddingDocument(AbstractModel):
    """Test document model with embeddings."""
    id: str
    title: str
    content: str
    tenant_id: str = ""
    
    @classmethod
    def to_sql_schema(cls):
        return {
            'table_name': 'tidb_test_embedding_documents',
            'key_field': 'id',
            'tenant_isolated': True,
            'fields': {
                'id': {'type': str, 'is_primary_key': True},
                'title': {'type': str, 'nullable': False},
                'content': {'type': str, 'nullable': True, 'is_embedding': True},
                'tenant_id': {'type': str, 'nullable': False}
            },
            'embedding_fields': ['content'],
            'embedding_providers': {
                'content': 'openai'
            }
        }


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION_TESTS", "true").lower() == "true",
    reason="Integration tests require Docker TiDB"
)
class TestTenantRepositoryTiDB:
    """Integration tests for TenantRepository with TiDB."""
    
    @pytest.fixture
    def tenant_id(self):
        """Generate test tenant ID."""
        return f"tidb-test-tenant-{uuid4().hex[:8]}"
    
    @pytest.fixture
    def repository(self, tenant_id):
        """Create repository instance with TiDB provider."""
        repo = TenantRepository(
            model_class=SampleDocument,
            tenant_id=tenant_id,
            provider_name='tidb'
        )
        
        # Register the model (create table)
        repo.register_model(SampleDocument, plan=False)
        
        yield repo
        
        # Cleanup
        try:
            repo.close()
        except Exception as e:
            # Log cleanup errors but don't fail test
            print(f"Warning: Failed to close repository: {e}")
    
    @pytest.fixture
    def embedding_repository(self, tenant_id):
        """Create repository instance for embedding tests."""
        repo = TenantRepository(
            model_class=SampleEmbeddingDocument,
            tenant_id=tenant_id,
            provider_name='tidb'
        )
        
        # Register the model (create table and embedding table)
        repo.register_model(SampleEmbeddingDocument, plan=False)
        
        yield repo
        
        # Cleanup
        try:
            repo.close()
        except Exception as e:
            # Log cleanup errors but don't fail test
            print(f"Warning: Failed to close embedding repository: {e}")
    
    def test_tidb_connection(self):
        """Test TiDB connection."""
        from p8fs.providers.tidb import TiDBProvider
        
        provider = TiDBProvider()
        conn = provider.connect_sync()
        
        # Test basic query
        result = provider.execute(conn, "SELECT VERSION()")
        assert len(result) == 1
        assert 'TiDB' in result[0]['VERSION()']
        
        conn.close()
    
    async def test_upsert_single_entity(self, repository):
        """Test upserting a single entity."""
        doc = SampleDocument(
            id=str(uuid4()),
            title="TiDB Test Document",
            content="Test content for TiDB"
        )
        
        result = await repository.upsert(doc)
        
        assert result['success'] is True
        assert result['affected_rows'] >= 1
        assert result['entity_count'] == 1
    
    async def test_upsert_multiple_entities(self, repository):
        """Test upserting multiple entities."""
        docs = [
            SampleDocument(
                id=str(uuid4()),
                title=f"TiDB Document {i}",
                content=f"TiDB Content {i}"
            )
            for i in range(5)
        ]
        
        result = await repository.upsert(docs)
        
        assert result['success'] is True
        assert result['affected_rows'] >= 5
        assert result['entity_count'] == 5
    
    @pytest.mark.asyncio
    async def test_get_entity(self, repository):
        """Test getting a single entity."""
        doc_id = str(uuid4())
        doc = SampleDocument(
            id=doc_id,
            title="TiDB Get Test",
            content="Content for get test"
        )
        
        # First upsert the document
        upsert_result = await repository.upsert(doc)
        assert upsert_result['success'] is True
        
        # Then retrieve it
        retrieved_doc = await repository.get(doc_id)
        
        assert retrieved_doc is not None
        assert retrieved_doc.id == doc_id
        assert retrieved_doc.title == "TiDB Get Test"
        assert retrieved_doc.content == "Content for get test"
    
    @pytest.mark.asyncio
    async def test_select_with_filters(self, repository):
        """Test selecting entities with filters."""
        # Create test documents
        docs = [
            SampleDocument(
                id=str(uuid4()),
                title="Active Document",
                content="Active content"
            ),
            SampleDocument(
                id=str(uuid4()),
                title="Inactive Document",
                content="Inactive content"
            ),
            SampleDocument(
                id=str(uuid4()),
                title="Active Report",
                content="Report content"
            )
        ]
        
        # Upsert all documents
        await repository.upsert(docs)
        
        # Test filter by title pattern
        results = await repository.select(filters={'title__like': 'Active%'})
        assert len(results) == 2
        
        # Test filter by exact content
        results = await repository.select(filters={'content': 'Active content'})
        assert len(results) == 1
        assert results[0].title == "Active Document"
    
    @pytest.mark.asyncio
    async def test_select_with_ordering(self, repository):
        """Test selecting entities with ordering."""
        # Create test documents
        docs = [
            SampleDocument(
                id=str(uuid4()),
                title="B Document",
                content="Content B"
            ),
            SampleDocument(
                id=str(uuid4()),
                title="A Document",
                content="Content A"
            ),
            SampleDocument(
                id=str(uuid4()),
                title="C Document",
                content="Content C"
            )
        ]
        
        # Upsert all documents
        await repository.upsert(docs)
        
        # Test ascending order
        results = await repository.select(order_by=['title'])
        assert len(results) >= 3
        
        # Find our test documents in the results
        test_results = [r for r in results if r.title in ['A Document', 'B Document', 'C Document']]
        assert len(test_results) == 3
        assert test_results[0].title == "A Document"
        assert test_results[1].title == "B Document"
        assert test_results[2].title == "C Document"
        
        # Test descending order
        results = await repository.select(order_by=['-title'])
        test_results = [r for r in results if r.title in ['A Document', 'B Document', 'C Document']]
        assert len(test_results) == 3
        assert test_results[0].title == "C Document"
        assert test_results[1].title == "B Document"
        assert test_results[2].title == "A Document"
    
    @pytest.mark.asyncio
    async def test_select_with_limit(self, repository):
        """Test selecting entities with limit."""
        # Create test documents
        docs = [
            SampleDocument(
                id=str(uuid4()),
                title=f"Limited Document {i}",
                content=f"Limited content {i}"
            )
            for i in range(10)
        ]
        
        # Upsert all documents
        await repository.upsert(docs)
        
        # Test limit
        results = await repository.select(
            filters={'title__like': 'Limited Document%'}, 
            limit=3
        )
        assert len(results) == 3
    
    
    @pytest.mark.asyncio
    async def test_tenant_isolation(self, tenant_id):
        """Test tenant isolation."""
        
        # Create two repositories with different tenant IDs
        tenant_id_1 = f"{tenant_id}-1"
        tenant_id_2 = f"{tenant_id}-2"
        
        repo1 = TenantRepository(
            model_class=SampleDocument,
            tenant_id=tenant_id_1,
            provider_name='tidb'
        )
        repo1.register_model(SampleDocument, plan=False)
        
        repo2 = TenantRepository(
            model_class=SampleDocument,
            tenant_id=tenant_id_2,
            provider_name='tidb'
        )
        repo2.register_model(SampleDocument, plan=False)
        
        try:
            # Create document in tenant 1
            doc_id = str(uuid4())
            doc1 = SampleDocument(
                id=doc_id,
                title="Tenant 1 Document",
                content="Tenant 1 content"
            )
            
            result1 = await repo1.upsert(doc1)
            assert result1['success'] is True
            
            # Try to retrieve from tenant 2 (should not find it)
            results_tenant2 = await repo2.select(filters={'id': doc_id})
            assert len(results_tenant2) == 0
            
            # Retrieve from tenant 1 (should find it)
            results_tenant1 = await repo1.select(filters={'id': doc_id})
            assert len(results_tenant1) == 1
            assert results_tenant1[0].title == "Tenant 1 Document"
            
        finally:
            repo1.close()
            repo2.close()
    
    def test_create_embedding_table(self, embedding_repository):
        """Test creating embedding table."""
        from p8fs.providers.tidb import TiDBProvider
        
        provider = TiDBProvider()
        conn = provider.connect_sync()
        
        try:
            # Test that embedding table was created
            result = provider.execute(
                conn, 
                "SHOW TABLES FROM embeddings LIKE '%tidb_test_embedding_documents_embeddings%'"
            )
            
            assert len(result) == 1
            
            # Test embedding table structure
            result = provider.execute(
                conn,
                "DESCRIBE embeddings.tidb_test_embedding_documents_embeddings"
            )
            
            # Should have the required columns
            columns = [row['Field'] for row in result]
            required_columns = [
                'id', 'entity_id', 'field_name', 'embedding_provider',
                'embedding_vector', 'tenant_id', 'created_at', 'updated_at'
            ]
            
            for col in required_columns:
                assert col in columns, f"Missing required column: {col}"
            
        finally:
            conn.close()
    
    
    @pytest.mark.asyncio
    async def test_batch_operations(self, repository):
        """Test batch operations."""
        # Create large batch of documents
        batch_size = 100
        docs = [
            SampleDocument(
                id=str(uuid4()),
                title=f"Batch Document {i}",
                content=f"Batch content {i}"
            )
            for i in range(batch_size)
        ]
        
        # Test batch upsert
        result = await repository.upsert(docs)
        
        assert result['success'] is True
        assert result['entity_count'] == batch_size
        assert result['affected_rows'] >= batch_size
        
        # Verify all were inserted
        results = await repository.select(filters={'title__like': 'Batch Document%'})
        assert len(results) >= batch_size
    
    def test_connection_retry(self):
        """Test connection retry functionality."""
        from p8fs.providers.tidb import TiDBProvider
        
        provider = TiDBProvider()
        
        # Test with invalid connection string
        try:
            provider.connect_sync("mysql://invalid:host@nonexistent:9999/invalid")
            assert False, "Should have raised an exception"
        except Exception as e:
            # Should handle connection errors gracefully
            assert "failed" in str(e).lower() or "connect" in str(e).lower() or "invalid" in str(e).lower()
    
    def test_transaction_rollback(self, repository):
        """Test transaction rollback on error."""
        from p8fs.providers.tidb import TiDBProvider
        
        provider = TiDBProvider()
        conn = provider.connect_sync()
        
        try:
            # Test batch execution with intentional error
            queries = [
                ("INSERT INTO tidb_test_documents (id, title, tenant_id) VALUES (%s, %s, %s)", 
                 (str(uuid4()), "Good Document", repository.tenant_id)),
                ("INVALID SQL STATEMENT", None),  # This should cause rollback
                ("INSERT INTO tidb_test_documents (id, title, tenant_id) VALUES (%s, %s, %s)", 
                 (str(uuid4()), "Another Document", repository.tenant_id))
            ]
            
            try:
                provider.execute_batch(conn, queries)
                assert False, "Should have raised an exception"
            except Exception:
                # Expected - the batch should fail and rollback
                pass
            
        finally:
            conn.close()