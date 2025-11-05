"""Integration tests for PDF content provider with real PDF files."""

import logging
import sys
from pathlib import Path

import pytest

# Add src to path
src_dir = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from p8fs_node.models.content import ContentChunk, ContentType
from p8fs_node.providers.pdf import HAS_FITZ, HAS_PYPDF, PDFContentProvider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample data path
SAMPLE_DATA_PATH = Path(__file__).parent.parent.parent / "sample_data"


class TestPDFIntegration:
    """Integration tests for PDF content provider."""
    
    def setup_method(self):
        """Setup before each test."""
        self.provider = PDFContentProvider()
        self.sample_pdf = SAMPLE_DATA_PATH / "documents" / "sample.pdf"
        
        # Check if sample file exists
        if not self.sample_pdf.exists():
            pytest.skip(f"Sample PDF not found at {self.sample_pdf}")
    
    def test_pdf_file_exists(self):
        """Test that sample PDF file exists."""
        assert self.sample_pdf.exists()
        assert self.sample_pdf.is_file()
        logger.info(f"Sample PDF found at: {self.sample_pdf}")
    
    def test_provider_initialization(self):
        """Test PDF provider initialization."""
        assert self.provider.supported_types == [ContentType.PDF]
        assert self.provider.provider_name == "pdf_provider"
        logger.info(f"PDF provider initialized, pypdf available: {HAS_PYPDF}, PyMuPDF available: {HAS_FITZ}")
    
    @pytest.mark.skipif(not HAS_PYPDF and not HAS_FITZ, reason="No PDF libraries available")
    @pytest.mark.asyncio
    async def test_pdf_to_markdown_chunks(self):
        """Test converting real PDF to markdown chunks."""
        chunks = await self.provider.to_markdown_chunks(str(self.sample_pdf))
        
        assert isinstance(chunks, list)
        assert len(chunks) > 0
        
        # Check first chunk
        first_chunk = chunks[0]
        assert isinstance(first_chunk, ContentChunk)
        assert first_chunk.chunk_type == "text"
        assert "Sample PDF Document" in first_chunk.content
        
        logger.info(f"Extracted {len(chunks)} chunks from PDF")
        logger.info(f"First chunk content preview: {first_chunk.content[:100]}...")
        
        # Check all chunks have required fields
        for i, chunk in enumerate(chunks):
            assert chunk.id.startswith("pdf-")
            assert chunk.content
            assert chunk.chunk_type in ["text", "heading", "paragraph"]
            assert chunk.metadata
            assert "page" in chunk.metadata
    
    @pytest.mark.skipif(not HAS_PYPDF and not HAS_FITZ, reason="No PDF libraries available")
    @pytest.mark.asyncio
    async def test_pdf_metadata_extraction(self):
        """Test PDF metadata extraction."""
        metadata = await self.provider.to_metadata(str(self.sample_pdf))
        
        assert metadata.extraction_method is not None
        assert metadata.file_size > 0
        assert metadata.mime_type == "application/pdf"
        
        logger.info(f"PDF metadata: {metadata.properties}")
        logger.info(f"File size: {metadata.file_size} bytes")
    
    @pytest.mark.skipif(not HAS_PYPDF and not HAS_FITZ, reason="No PDF libraries available")
    @pytest.mark.asyncio
    async def test_pdf_extended_extraction(self):
        """Test PDF extraction with extended mode."""
        chunks = await self.provider.to_markdown_chunks(
            str(self.sample_pdf), 
            extended=True
        )
        
        assert len(chunks) > 0
        
        # Extended mode should preserve more structure
        for chunk in chunks:
            assert chunk.metadata
            if "page" in chunk.metadata:
                assert isinstance(chunk.metadata["page"], int)
    
    @pytest.mark.asyncio
    async def test_pdf_can_process(self):
        """Test can_process method for PDF files."""
        # Should process PDF file
        can_process = await self.provider.can_process(str(self.sample_pdf))
        assert can_process is True
        
        # Should not process non-PDF file
        text_file = SAMPLE_DATA_PATH / "text" / "sample.txt"
        if text_file.exists():
            can_process = await self.provider.can_process(str(text_file))
            assert can_process is False
    
    @pytest.mark.asyncio
    async def test_pdf_error_handling(self):
        """Test error handling for invalid PDF."""
        non_existent = "non_existent.pdf"
        
        # Should handle non-existent file gracefully
        chunks = await self.provider.to_markdown_chunks(non_existent)
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "error"
        assert "Error" in chunks[0].content or "Failed" in chunks[0].content


def run_tests():
    """Run PDF integration tests."""
    logger.info("=== Running PDF Integration Tests ===")
    
    test_instance = TestPDFIntegration()
    test_methods = [method for method in dir(test_instance) if method.startswith('test_')]
    
    passed = 0
    total = 0
    
    for method_name in test_methods:
        total += 1
        logger.info(f"\nRunning {method_name}...")
        
        try:
            test_instance.setup_method()
            method = getattr(test_instance, method_name)
            
            # Handle async methods
            if method_name.startswith('test_') and callable(method):
                import asyncio
                if asyncio.iscoroutinefunction(method):
                    asyncio.run(method())
                else:
                    method()
            
            logger.info(f"✅ {method_name} PASSED")
            passed += 1
            
        except pytest.skip.Exception as e:
            logger.info(f"⏭️  {method_name} SKIPPED: {e}")
            
        except Exception as e:
            logger.error(f"❌ {method_name} FAILED: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    logger.info("\n=== PDF Integration Test Results ===")
    logger.info(f"Passed: {passed}/{total}")
    
    return passed == total


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)