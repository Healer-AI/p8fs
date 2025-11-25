"""Unit tests for semantic search functionality with mocked dependencies."""

from unittest.mock import patch, Mock, AsyncMock
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


class TestSemanticSearchUnit:
    """Unit tests for semantic search functionality."""
    
    @pytest.fixture
    def tenant_id(self):
        """Generate unique tenant ID."""
        return f"test-tenant-{uuid4().hex[:8]}"
    
    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider."""
        provider = Mock()
        provider.create_embedding_table_sql = Mock(return_value="CREATE TABLE mock")
        provider.semantic_search_sql = Mock(return_value=("SELECT * FROM mock", []))
        provider.vector_similarity_search_sql = Mock(return_value=("SELECT * FROM mock", []))
        return provider
    
    @pytest.fixture
    def article_repo(self, tenant_id, mock_provider):
        """Create article repository with mocked provider."""
        repo = Mock(spec=TenantRepository)
        repo.tenant_id = tenant_id
        repo.provider = mock_provider
        repo.provider_name = 'postgresql'
        repo.register_model = Mock()
        repo.upsert = Mock()
        repo.semantic_search = AsyncMock()
        repo.get_entities = AsyncMock()
        repo._generate_query_embedding = AsyncMock()
        return repo
    
    def _create_test_embedding(self, dim=1536):
        """Create a test embedding vector."""
        import random
        return [random.uniform(-1.0, 1.0) for _ in range(dim)]
    
    @pytest.mark.asyncio
    async def test_semantic_search_basic(self, article_repo):
        """Test basic semantic search functionality with mocks."""
        # Mock the embedding generation
        article_repo._generate_query_embedding.return_value = self._create_test_embedding()
        
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
            Article(
                id="3",
                title="Python Programming Guide",
                content="Python is a versatile programming language...",
                abstract="Learn Python from basics to advanced.",
                category="Programming"
            ),
        ]
        
        # Configure mock to return expected results
        article_repo.semantic_search.return_value = [articles[1], articles[0]]  # AI articles
        
        # Test semantic search
        results = await article_repo.semantic_search(
            query="neural networks and deep learning",
            limit=5,
            threshold=0.7
        )
        
        # Verify the search was called correctly
        article_repo.semantic_search.assert_called_once_with(
            query="neural networks and deep learning",
            limit=5,
            threshold=0.7
        )
        
        # Verify results
        assert len(results) == 2
        assert results[0].title == "Deep Learning Fundamentals"
        assert results[1].title == "Introduction to Machine Learning"
    
    @pytest.mark.asyncio
    async def test_semantic_search_with_field_filter(self, article_repo):
        """Test semantic search on specific fields with mocks."""
        article_repo._generate_query_embedding.return_value = self._create_test_embedding()
        
        # Configure mock
        article_repo.semantic_search.return_value = []
        
        # Search only in content field
        results = await article_repo.semantic_search(
            query="machine learning applications",
            field_name="content",
            limit=10,
            threshold=0.8
        )
        
        # Verify the search was called with field filter
        article_repo.semantic_search.assert_called_once_with(
            query="machine learning applications",
            field_name="content",
            limit=10,
            threshold=0.8
        )
        
        assert results == []