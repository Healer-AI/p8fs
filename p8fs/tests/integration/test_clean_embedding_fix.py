"""Clean integration test for resource embedding fix."""

import pytest
import uuid
from datetime import datetime, timezone

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from p8fs.models.p8 import Resources
from p8fs.repository import TenantRepository

logger = get_logger(__name__)


@pytest.mark.integration 
class TestCleanEmbeddingFix:
    """Clean test for resource embedding fix without data pollution."""
    
    def setup_method(self):
        """Set up test with unique identifiers."""
        self.tenant_id = config.default_tenant_id
        # Use unique test ID to avoid conflicts
        self.test_id = str(uuid.uuid4())[:8]
        self.repo = TenantRepository(Resources, tenant_id=self.tenant_id)
        
    def teardown_method(self):
        """Clean up test data."""
        try:
            conn = self.repo.get_connection_sync()
            cursor = conn.cursor()
            
            # Clean up by test ID
            cursor.execute(
                "DELETE FROM resources WHERE tenant_id = %s AND name LIKE %s",
                (self.tenant_id, f"%{self.test_id}%")
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
    
    @pytest.mark.asyncio
    async def test_async_upsert_creates_embeddings(self):
        """Test that async upsert now creates embeddings with the fix."""
        # Create unique resource
        resource_data = {
            "tenant_id": self.tenant_id,
            "name": f"test_{self.test_id}_async",
            "category": "test",
            "content": f"Test content for {self.test_id} that should be embedded",
            "summary": f"Test summary for {self.test_id} that should be embedded",
            "uri": f"test://async/{self.test_id}/{datetime.now().timestamp()}",
            "resource_timestamp": datetime.now(timezone.utc),
        }
        
        # Use async upsert
        result = await self.repo.upsert(resource_data)
        assert result["success"] is True
        
        # Get the created resource
        resources = self.repo.execute(
            "SELECT id FROM resources WHERE tenant_id = %s AND name = %s",
            (self.tenant_id, f"test_{self.test_id}_async")
        )
        assert len(resources) == 1
        resource_id = resources[0]["id"]
        
        # Check embeddings - should have 2 (content and summary)
        embeddings = self.repo.execute(
            """
            SELECT field_name, vector_dimension 
            FROM embeddings.resources_embeddings 
            WHERE tenant_id = %s AND entity_id = %s
            ORDER BY field_name
            """,
            (self.tenant_id, resource_id)
        )
        
        # Should only have 1 embedding for 'content' field (not summary)
        assert len(embeddings) == 1
        assert embeddings[0]["field_name"] == "content"
        
        # Verify dimensions
        for e in embeddings:
            assert e["vector_dimension"] > 0
            
    @pytest.mark.asyncio
    async def test_async_upsert_without_embeddings(self):
        """Test that embeddings can be disabled."""
        resource_data = {
            "tenant_id": self.tenant_id,
            "name": f"test_{self.test_id}_no_embed",
            "category": "test", 
            "content": f"Content for {self.test_id} without embeddings",
            "summary": f"Summary for {self.test_id} without embeddings",
            "uri": f"test://no_embed/{self.test_id}/{datetime.now().timestamp()}",
            "resource_timestamp": datetime.now(timezone.utc),
        }
        
        # Use async upsert with embeddings disabled
        result = await self.repo.upsert(resource_data, create_embeddings=False)
        assert result["success"] is True
        
        # Get resource
        resources = self.repo.execute(
            "SELECT id FROM resources WHERE tenant_id = %s AND name = %s",
            (self.tenant_id, f"test_{self.test_id}_no_embed")
        )
        assert len(resources) == 1
        resource_id = resources[0]["id"]
        
        # Check no embeddings were created
        embeddings = self.repo.execute(
            """
            SELECT COUNT(*) as count
            FROM embeddings.resources_embeddings 
            WHERE tenant_id = %s AND entity_id = %s
            """,
            (self.tenant_id, resource_id)
        )
        
        assert embeddings[0]["count"] == 0
        
    def test_sync_upsert_still_works(self):
        """Test that sync upsert continues to work with embeddings."""
        resource_data = {
            "tenant_id": self.tenant_id,
            "name": f"test_{self.test_id}_sync",
            "category": "test",
            "content": f"Sync content for {self.test_id} with embeddings",
            "summary": f"Sync summary for {self.test_id} with embeddings", 
            "uri": f"test://sync/{self.test_id}/{datetime.now().timestamp()}",
            "resource_timestamp": datetime.now(timezone.utc),
        }
        
        # Use sync upsert
        result = self.repo.upsert_sync(resource_data)
        assert result["success"] is True
        
        # Get resource
        resources = self.repo.execute(
            "SELECT id FROM resources WHERE tenant_id = %s AND name = %s",
            (self.tenant_id, f"test_{self.test_id}_sync")
        )
        assert len(resources) == 1
        resource_id = resources[0]["id"]
        
        # Check embeddings
        embeddings = self.repo.execute(
            """
            SELECT field_name 
            FROM embeddings.resources_embeddings 
            WHERE tenant_id = %s AND entity_id = %s
            ORDER BY field_name
            """,
            (self.tenant_id, resource_id)
        )
        
        # Should only have 1 embedding for 'content' field
        assert len(embeddings) == 1
        assert embeddings[0]["field_name"] == "content"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])