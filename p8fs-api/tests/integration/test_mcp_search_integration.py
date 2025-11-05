"""Integration test for MCP search_content tool with real database."""

import pytest
import asyncio
from p8fs_api.routers.mcp_server import create_secure_mcp_server
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models.p8 import Resources
from p8fs_cluster.config.settings import config
import uuid


@pytest.mark.integration
class TestMCPSearchIntegration:
    """Integration tests for MCP search tool with real database."""
    
    @pytest.fixture
    async def setup_test_data(self):
        """Create test data in the database."""
        # Create test tenant and resources
        test_tenant = f"test-mcp-search-{uuid.uuid4().hex[:8]}"
        repo = TenantRepository(Resources, tenant_id=test_tenant)
        
        # Insert test resources
        test_resources = [
            {
                "id": str(uuid.uuid4()),
                "tenant_id": test_tenant,
                "name": "Machine Learning Introduction",
                "content": "This document provides a comprehensive introduction to machine learning concepts including supervised and unsupervised learning.",
                "category": "education",
                "uri": "/docs/ml-intro.pdf",
                "metadata": {"type": "document", "format": "pdf"}
            },
            {
                "id": str(uuid.uuid4()),
                "tenant_id": test_tenant,
                "name": "Deep Learning Tutorial",
                "content": "Advanced tutorial on deep neural networks, covering convolutional networks and transformers.",
                "category": "education",
                "uri": "/docs/deep-learning.pdf",
                "metadata": {"type": "tutorial", "format": "pdf"}
            },
            {
                "id": str(uuid.uuid4()),
                "tenant_id": test_tenant,
                "name": "Python Programming Guide",
                "content": "Complete guide to Python programming for beginners and intermediate developers.",
                "category": "programming",
                "uri": "/docs/python-guide.md",
                "metadata": {"type": "guide", "format": "markdown"}
            }
        ]
        
        # Insert resources
        for resource in test_resources:
            await repo.upsert(resource)
        
        yield test_tenant, test_resources
        
        # Cleanup
        for resource in test_resources:
            try:
                await repo.delete(resource["id"])
            except:
                pass
    
    @pytest.fixture
    def mock_auth_provider(self):
        """Mock auth provider that bypasses authentication."""
        from unittest.mock import MagicMock, AsyncMock
        provider = MagicMock()
        provider.verify_token = AsyncMock(return_value=None)
        return provider
    
    @pytest.fixture
    def mcp_server(self, mock_auth_provider):
        """Create MCP server with mocked auth."""
        from unittest.mock import patch
        with patch('p8fs_api.routers.mcp_server.P8FSAuthProvider', return_value=mock_auth_provider):
            return create_secure_mcp_server()
    
    @pytest.mark.asyncio
    async def test_search_real_data(self, setup_test_data, mcp_server):
        """Test searching with real database data."""
        test_tenant, test_resources = setup_test_data
        
        # Patch config to use test tenant
        original_tenant = config.default_tenant_id
        config.default_tenant_id = test_tenant
        
        try:
            # Get search tool
            search_tool = await mcp_server.get_tool("search_content")
            
            # Search for machine learning content
            result = await search_tool.fn(
                query="machine learning",
                model="resources",
                limit=5
            )
            
            # Verify results
            assert result["status"] == "success"
            assert result["total_results"] >= 1  # Should find at least ML intro
            
            # Check if ML content was found
            ml_found = any("machine learning" in r["content"].lower() 
                          for r in result["results"])
            assert ml_found, "Machine learning content not found in results"
            
            # Search for Python content
            result = await search_tool.fn(
                query="Python programming",
                model="resources",
                limit=5
            )
            
            assert result["status"] == "success"
            assert result["total_results"] >= 1  # Should find Python guide
            
        finally:
            # Restore original tenant
            config.default_tenant_id = original_tenant
    
    @pytest.mark.asyncio
    async def test_search_with_threshold(self, setup_test_data, mcp_server):
        """Test search with custom threshold."""
        test_tenant, test_resources = setup_test_data
        
        # Patch config to use test tenant
        original_tenant = config.default_tenant_id
        config.default_tenant_id = test_tenant
        
        try:
            # Get search tool
            search_tool = await mcp_server.get_tool("search_content")
            
            # Search with high threshold
            result = await search_tool.fn(
                query="quantum computing",  # Unrelated query
                model="resources",
                limit=10,
                threshold=0.9  # High threshold
            )
            
            # Should have few or no results due to high threshold
            assert result["status"] == "success"
            assert result["total_results"] == 0 or all(
                r["score"] >= 0.9 for r in result["results"]
            )
            
        finally:
            config.default_tenant_id = original_tenant


if __name__ == "__main__":
    # Run the integration test
    pytest.main([__file__, "-v", "-k", "integration"])