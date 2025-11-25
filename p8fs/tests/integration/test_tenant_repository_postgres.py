"""Integration tests for TenantRepository with PostgreSQL."""

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
            'table_name': 'test_documents',
            'key_field': 'id',
            'tenant_isolated': True,
            'fields': {
                'id': {'type': str, 'is_primary_key': True},
                'title': {'type': str, 'nullable': False},
                'content': {'type': str, 'nullable': True},
                'tenant_id': {'type': str, 'nullable': False}
            }
        }


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION_TESTS", "true").lower() == "true",
    reason="Integration tests require Docker PostgreSQL"
)
class TestTenantRepositoryPostgres:
    """Integration tests for TenantRepository with PostgreSQL."""
    
    @pytest.fixture
    def tenant_id(self):
        """Generate test tenant ID."""
        return f"test-tenant-{uuid4().hex[:8]}"
    
    @pytest.fixture
    def repository(self, tenant_id):
        """Create repository instance."""
        repo = TenantRepository(
            model_class=SampleDocument,
            tenant_id=tenant_id
            # Uses default provider from config (postgresql)
        )
        
        # Register the model (create table)
        repo.register_model(SampleDocument, plan=False)
        
        yield repo
        
        # Cleanup
        repo.close()
    
    def test_upsert_single_entity(self, repository):
        """Test upserting a single entity."""
        doc = SampleDocument(
            id=str(uuid4()),
            title="Test Document",
            content="Test content"
        )
        
        result = repository.upsert(doc)
        
        assert result['success'] is True
        assert result['affected_rows'] >= 1
        assert result['entity_count'] == 1
    
    def test_upsert_multiple_entities(self, repository):
        """Test upserting multiple entities."""
        docs = [
            SampleDocument(
                id=str(uuid4()),
                title=f"Document {i}",
                content=f"Content {i}"
            )
            for i in range(5)
        ]
        
        result = repository.upsert(docs)
        
        assert result['success'] is True
        assert result['affected_rows'] >= 5
        assert result['entity_count'] == 5
    
    @pytest.mark.asyncio
    async def test_get_entity(self, repository):
        """Test getting a single entity."""
        doc_id = str(uuid4())
        doc = SampleDocument(
            id=doc_id,
            title="Get Test",
            content="Test content"
        )
        
        # Insert the document
        repository.upsert(doc)
        
        # Retrieve it
        retrieved = await repository.get(doc_id)
        
        assert retrieved is not None
        assert retrieved.id == doc_id
        assert retrieved.title == "Get Test"
        assert retrieved.tenant_id == repository.tenant_id
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_entity(self, repository):
        """Test getting a non-existent entity."""
        result = await repository.get("nonexistent-id")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_select_with_filters(self, repository):
        """Test selecting entities with filters."""
        # Insert test data
        docs = [
            SampleDocument(id=str(uuid4()), title="Python Guide", content="Python content"),
            SampleDocument(id=str(uuid4()), title="JavaScript Guide", content="JS content"),
            SampleDocument(id=str(uuid4()), title="Python Tutorial", content="Tutorial content"),
        ]
        repository.upsert(docs)
        
        # Select Python-related documents
        results = await repository.select(
            filters={'title__like': '%Python%'},
            order_by=['title']
        )
        
        assert len(results) == 2
        assert all('Python' in doc.title for doc in results)
    
    @pytest.mark.asyncio
    async def test_get_entities_batch(self, repository):
        """Test batch getting entities."""
        # Insert test data
        doc_ids = [str(uuid4()) for _ in range(3)]
        docs = [
            SampleDocument(id=doc_id, title=f"Doc {i}", content=f"Content {i}")
            for i, doc_id in enumerate(doc_ids)
        ]
        repository.upsert(docs)
        
        # Get entities
        results = await repository.get_entities(doc_ids)
        
        assert len(results) == 3
        assert all(doc_id in results for doc_id in doc_ids)
        assert all(results[doc_id] is not None for doc_id in doc_ids)
    
    @pytest.mark.asyncio
    async def test_tenant_isolation(self, repository):
        """Test that tenant isolation works."""
        # Create another repository with different tenant
        other_tenant_repo = TenantRepository(
            model_class=SampleDocument,
            tenant_id=f"other-tenant-{uuid4().hex[:8]}",
            provider_name='postgresql'
        )
        
        try:
            # Insert document in first tenant
            doc_id = str(uuid4())
            doc = SampleDocument(id=doc_id, title="Tenant Test", content="Test")
            repository.upsert(doc)
            
            # Try to get it from other tenant
            result = await other_tenant_repo.get(doc_id)
            assert result is None  # Should not find it
            
            # Verify we can get it from correct tenant
            result = await repository.get(doc_id)
            assert result is not None
            assert result.id == doc_id
            
        finally:
            other_tenant_repo.close()
    
    @pytest.mark.asyncio
    async def test_execute_raw_sql(self, repository):
        """Test executing raw SQL with tenant isolation."""
        # Insert test data
        doc = SampleDocument(
            id=str(uuid4()),
            title="SQL Test",
            content="Test content"
        )
        repository.upsert(doc)
        
        # Execute raw SQL
        results = await repository.execute(
            "SELECT COUNT(*) as count FROM test_documents WHERE tenant_id = {tenant_id}"
        )
        
        assert len(results) > 0
        assert results[0]['count'] >= 1
    
    def test_connection_management(self, repository):
        """Test connection management."""
        # Get connection
        conn = repository.get_connection_sync()
        assert conn is not None
        
        # Should reuse same connection
        conn2 = repository.get_connection_sync()
        assert conn2 is conn
        
        # Close and verify
        repository.close()
        assert repository.connection is None