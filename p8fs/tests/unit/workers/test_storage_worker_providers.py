"""Unit tests for storage worker content provider integration."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import NAMESPACE_DNS, uuid5
from pathlib import Path

from p8fs.workers.storage import StorageWorker


class TestStorageWorkerProviders:
    """Test storage worker integration with content providers."""
    
    @pytest.fixture
    def storage_worker(self):
        """Create a storage worker instance with mocked repositories."""
        with patch('p8fs.workers.storage.TenantRepository') as mock_repo_class:
            # Create mock instances
            mock_files_repo = Mock()
            mock_files_repo.upsert = AsyncMock()
            mock_files_repo.delete = AsyncMock()
            
            mock_resources_repo = Mock()
            mock_resources_repo.upsert = AsyncMock()
            mock_resources_repo.select = AsyncMock(return_value=[])
            mock_resources_repo.delete = AsyncMock()
            
            # Configure the mock class to return our mock instances
            mock_repo_class.side_effect = lambda model, tenant_id: (
                mock_files_repo if model.__name__ == 'Files' else mock_resources_repo
            )
            
            worker = StorageWorker(tenant_id="test-tenant")
            worker.files_repo = mock_files_repo
            worker.resources_repo = mock_resources_repo
            
            return worker
    
    
    @pytest.mark.asyncio
    async def test_process_file_handles_missing_provider(self, storage_worker, tmp_path):
        """Test that files without providers are handled gracefully."""
        # Create test file with unsupported extension
        test_file = tmp_path / "test.xyz"
        test_file.write_text("unsupported content")
        
        tenant_id = "test-tenant"
        
        with patch("p8fs.workers.storage.get_content_provider") as mock_get_provider:
            mock_get_provider.side_effect = ValueError("No content provider found for file: test.xyz")
            
            # Process should complete without raising exception
            await storage_worker.process_file(str(test_file), tenant_id)
            
            # File entry should still be created
            storage_worker.files_repo.upsert.assert_called_once()
            
            # But no resources should be created
            storage_worker.resources_repo.upsert.assert_not_called()
    
    
    
    @pytest.mark.asyncio
    async def test_process_file_empty_content(self, storage_worker, tmp_path):
        """Test handling of empty content from provider."""
        test_file = tmp_path / "empty.md"
        test_file.write_text("")
        
        tenant_id = "test-tenant"
        
        mock_provider = Mock()
        mock_provider.extract_text = AsyncMock(return_value="")  # Empty content
        mock_provider.to_markdown_chunks = AsyncMock(return_value=[])  # No chunks from empty content
        
        with patch("p8fs.workers.storage.get_content_provider") as mock_get_provider:
            mock_get_provider.return_value = mock_provider
            
            await storage_worker.process_file(str(test_file), tenant_id)
            
            # File entry should be created
            storage_worker.files_repo.upsert.assert_called_once()
            
            # But no resources should be created for empty content
            storage_worker.resources_repo.upsert.assert_not_called()
    


if __name__ == "__main__":
    pytest.main([__file__, "-v"])