"""Integration tests for query functionality in TenantRepository."""

import asyncio
from uuid import uuid4

import pytest
from p8fs_cluster.config.settings import config
from p8fs.models.p8 import Resources
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.utils import make_uuid


@pytest.mark.integration
class TestQueryFunctionality:
    """Test the query method functionality without relying on embeddings."""
    
    @pytest.fixture
    def tenant_id(self):
        """Use test tenant from config."""
        return config.default_tenant_id
    
    @pytest.fixture
    def resources_repo(self, tenant_id):
        """Create resources repository."""
        repo = TenantRepository(
            model_class=Resources,
            tenant_id=tenant_id
        )
        
        # Clean up any existing test data
        repo.execute(
            "DELETE FROM public.resources WHERE name LIKE %s AND tenant_id = %s",
            ["Query Test%", tenant_id]
        )
        
        yield repo
        
        # Cleanup after test
        repo.execute(
            "DELETE FROM public.resources WHERE name LIKE %s AND tenant_id = %s",
            ["Query Test%", tenant_id]
        )
        repo.close()
    
    async def test_sql_hint_query(self, resources_repo):
        """Test SQL hint executes raw SQL queries."""
        # Create test data
        resources = [
            Resources(
                id=make_uuid("query-sql-1"),
                name="Query Test Alpha",
                category="document",
                content="Test content for SQL query",
                summary="Test summary",
                tenant_id=resources_repo.tenant_id
            ),
            Resources(
                id=make_uuid("query-sql-2"),
                name="Query Test Beta",
                category="project",
                content="Another test content",
                summary="Another summary",
                tenant_id=resources_repo.tenant_id
            )
        ]
        resources_repo.upsert_sync(resources)
        
        # Test SQL query with parameters
        sql = f"SELECT * FROM public.resources WHERE category = 'document' AND tenant_id = '{resources_repo.tenant_id}' AND name LIKE 'Query Test%'"
        results = await resources_repo.query(
            query_text=sql,
            hint="sql",
            limit=10  # Ignored for SQL queries
        )
        
        # Should find only the document
        assert len(results) == 1
        assert results[0]['name'] == "Query Test Alpha"
        assert results[0]['category'] == "document"
    
    async def test_query_method_exists(self, resources_repo):
        """Test that query method is available and handles different hints."""
        # Test that query method exists
        assert hasattr(resources_repo, 'query')
        
        # Test unimplemented hints raise appropriate errors
        with pytest.raises(NotImplementedError, match="Hybrid search not yet implemented"):
            await resources_repo.query(
                query_text="test query",
                hint="hybrid"
            )
        
        with pytest.raises(NotImplementedError, match="Graph search not yet implemented"):
            await resources_repo.query(
                query_text="test query", 
                hint="graph"
            )
    
    async def test_query_with_limit(self, resources_repo):
        """Test that limit parameter is respected for SQL queries."""
        # Create multiple test records
        resources = [
            Resources(
                id=make_uuid(f"query-limit-{i}"),
                name=f"Query Test {i}",
                category="test",
                content=f"Content {i}",
                summary=f"Summary {i}",
                tenant_id=resources_repo.tenant_id
            )
            for i in range(5)
        ]
        resources_repo.upsert_sync(resources)
        
        # Query with LIMIT in SQL
        sql = f"SELECT * FROM public.resources WHERE tenant_id = '{resources_repo.tenant_id}' AND name LIKE 'Query Test%' ORDER BY name LIMIT 2"
        results = await resources_repo.query(
            query_text=sql,
            hint="sql"
        )
        
        # Should respect the SQL LIMIT
        assert len(results) == 2
        assert results[0]['name'] == "Query Test 0"
        assert results[1]['name'] == "Query Test 1"
    
    def test_semantic_search_method_exists(self, resources_repo):
        """Test that semantic_search method exists on BaseRepository."""
        assert hasattr(resources_repo, 'semantic_search')
        
        # The method should be callable
        assert callable(getattr(resources_repo, 'semantic_search'))
    
    async def test_invalid_hint_error(self, resources_repo):
        """Test that invalid hint raises appropriate error."""
        with pytest.raises(ValueError, match="Unsupported query hint"):
            await resources_repo.query(
                query_text="test",
                hint="invalid_hint"
            )