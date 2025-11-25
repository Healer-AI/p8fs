"""Integration tests for semantic search functionality."""

import os
from uuid import uuid4

import pytest
from p8fs.models import AbstractModel
from p8fs.repository.TenantRepository import TenantRepository


class Article(AbstractModel):
    """Article model with embeddings."""
    id: str
    title: str
    content: str
    abstract: str
    category: str = "general"
    tenant_id: str = ""
    
    @classmethod
    def to_sql_schema(cls):
        return {
            'table_name': 'articles',
            'key_field': 'id',
            'tenant_isolated': True,
            'embedding_fields': ['content', 'abstract'],
            'embedding_providers': {
                'content': 'openai',
                'abstract': 'sentence-transformers'
            },
            'fields': {
                'id': {'type': str, 'is_primary_key': True},
                'title': {'type': str, 'nullable': False},
                'content': {'type': str, 'nullable': False, 'is_embedding': True},
                'abstract': {'type': str, 'nullable': False, 'is_embedding': True},
                'category': {'type': str, 'nullable': True},
                'tenant_id': {'type': str, 'nullable': False}
            }
        }


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION_TESTS", "true").lower() == "true",
    reason="Integration tests require Docker PostgreSQL"
)
class TestSemanticSearch:
    """Test semantic search functionality."""
    
    @pytest.fixture
    def tenant_id(self):
        """Generate unique tenant ID."""
        return f"test-tenant-{uuid4().hex[:8]}"
    
    @pytest.fixture
    def article_repo(self, tenant_id):
        """Create article repository with embedding support."""
        repo = TenantRepository(
            model_class=Article,
            tenant_id=tenant_id
        )
        
        # Register model (creates embedding tables)
        repo.register_model(Article, plan=False)
        
        yield repo
        repo.close()
    
    def _create_test_embedding(self, dim=1536):
        """Create a test embedding vector for SQL generation tests."""
        import random
        return [random.uniform(-1.0, 1.0) for _ in range(dim)]
    
    @pytest.mark.asyncio
    @pytest.mark.skip("Requires real embedding service - use test_semantic_search_structure instead")
    async def test_semantic_search_basic(self, article_repo):
        """Test basic semantic search functionality with real embeddings."""
        # This test requires a real embedding service to be configured
        pass
    
    def test_embedding_table_creation(self, article_repo):
        """Test that embedding tables are created properly."""
        # Get the SQL for creating embedding tables
        sql = article_repo.provider.create_embedding_table_sql(Article)
        
        # Verify SQL contains expected elements
        assert "CREATE SCHEMA IF NOT EXISTS embeddings" in sql
        assert "CREATE TABLE IF NOT EXISTS embeddings.articles_embeddings" in sql
        assert "entity_id" in sql
        assert "field_name" in sql
        assert "embedding_vector" in sql
        assert "tenant_id" in sql  # Should include tenant isolation
        
        # Verify indexes
        assert "idx_articles_embeddings_entity_field" in sql
        assert "idx_articles_embeddings_vector_cosine" in sql
    
    @pytest.mark.asyncio
    @pytest.mark.skip("Requires real embedding service")
    async def test_semantic_search_with_field_filter(self, article_repo):
        """Test semantic search on specific fields with real embeddings."""
        # This test requires a real embedding service to be configured
        pass
    
    @pytest.mark.asyncio
    async def test_semantic_search_sql_generation(self, article_repo):
        """Test SQL generation for semantic search."""
        # Create a mock vector
        query_vector = self._create_test_embedding(384)  # Smaller dimension for test
        
        # Get the SQL that would be generated
        sql, params = article_repo.provider.semantic_search_sql(
            Article,
            query_vector=query_vector,
            field_name="content",
            limit=10,
            threshold=0.75,
            metric="cosine",
            tenant_id=article_repo.tenant_id
        )
        
        # Verify SQL structure
        assert "SELECT m.*" in sql
        assert "similarity_score" in sql or "distance_score" in sql
        assert "FROM public.articles m" in sql
        assert "INNER JOIN embeddings.articles_embeddings e" in sql
        assert "WHERE" in sql
        assert "e.field_name = %s" in sql
        assert "m.tenant_id = %s" in sql
        assert "ORDER BY" in sql
        assert "LIMIT %s" in sql
        
        # Verify parameters
        assert len(params) > 0
        assert "content" in params  # field_name
        assert article_repo.tenant_id in params  # tenant_id
        assert 10 in params  # limit
    
    def test_semantic_search_structure(self, article_repo):
        """Test semantic search API structure and table creation without real embeddings."""
        # Create test articles
        articles = [
            Article(
                id="1",
                title="Introduction to Machine Learning",
                content="Machine learning is a subset of artificial intelligence...",
                abstract="This article introduces basic ML concepts.",
                category="AI"
            ),
            Article(
                id="2",
                title="Deep Learning Fundamentals",
                content="Deep learning uses neural networks with multiple layers...",
                abstract="An overview of deep learning architectures.",
                category="AI"
            ),
        ]
        
        # Test that we can insert articles
        article_repo.upsert(articles)
        
        # Verify the articles were inserted
        stored_articles = article_repo.get_all()
        assert len(stored_articles) >= 2
    
    def test_vector_similarity_search_sql(self, article_repo):
        """Test vector similarity search SQL generation."""
        query_vector = self._create_test_embedding(1536)
        
        # Test PostgreSQL provider
        if article_repo.provider_name == 'postgresql':
            sql, params = article_repo.provider.vector_similarity_search_sql(
                Article,
                query_vector=query_vector,
                field_name="content",
                limit=5,
                threshold=0.8,
                metric="cosine"
            )
            
            # Check PostgreSQL-specific syntax
            assert "<=>" in sql  # Cosine operator
            assert "::vector" in sql  # Type casting
            assert "1 - (embedding_vector <=> %s::vector)" in sql  # Similarity calculation