"""Integration tests for Text content provider with real text files.

WHAT GOOD LOOKS LIKE - End-to-End Processing Success Criteria:
============================================================

When the p8fs-node processing system is working correctly, you should see:

✅ **File Processing Success:**
   - Processing /tmp/test.txt with TextContentProvider...
   - ✅ Processed successfully: 1 chunks created, Title: test, Content type: text

✅ **Database Schema Integrity:**
   - tenant_id fields correctly created as TEXT NOT NULL (not UUID)
   - Single embedding field per model (no duplicate embedding fields):
     * Agent: description
     * Project: description  
     * Resources: content
     * Session: query
     * Task: description
     * User: description

✅ **Storage Pipeline Success:**
   - File registration: ✅ Registered file with UUID (e.g., 3e60bec1-80b1-58de-81d9-74c5863dd444)
   - Chunk storage: ✅ Saved 1 chunks to storage with Resource IDs
   - No "column does not exist" errors
   - No "invalid input syntax for type uuid" errors for tenant_id

✅ **Repository Operations:**
   - Successfully upserted Files entities (file metadata stored)
   - Successfully upserted Resources entities (chunks stored with content for embedding)
   - Proper tenant isolation with string-based tenant_id ("test-tenant")

✅ **Provider SQL Generation:**
   - Correct upsert_sql using proper primary key fields (uri for Files, id for Resources)
   - Serialization working correctly (JSON fields properly converted)
   - No duplicate method conflicts in PostgreSQL provider

✅ **End-to-End Data Flow:**
   1. File content extracted by appropriate provider (TextContentProvider, PDFContentProvider, etc.)
   2. Content chunked with proper metadata and IDs
   3. File registered in files table with URI as primary key
   4. Chunks saved as resources with content field for embeddings
   5. Tenant isolation maintained throughout with string tenant_id
   6. Database operations complete without schema errors

This represents a fully functional p8fs-node content processing pipeline ready for
production use with proper tenant isolation, single embedding fields per model, 
and robust error handling.
"""

import logging
import sys
from pathlib import Path

import pytest

# Add src to path
src_dir = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from p8fs_node.models.content import ContentChunk, ContentType
from p8fs_node.providers.text import TextContentProvider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample data path
SAMPLE_DATA_PATH = Path(__file__).parent.parent.parent / "sample_data"
SAMPLE_TEXT_FILE = SAMPLE_DATA_PATH / "text" / "sample.txt"

class TestTextIntegration:
    """Integration tests for Text content provider."""
    
    def setup_method(self):
        """Setup before each test."""
        self.provider = TextContentProvider()
        self.sample_txt = SAMPLE_TEXT_FILE
    
    def test_text_file_exists(self):
        """Test that sample text file exists."""
        if not self.sample_txt.exists():
            pytest.skip(f"Sample text file not found at {self.sample_txt}")
        
        assert self.sample_txt.exists()
        assert self.sample_txt.is_file()
        logger.info(f"Sample text found at: {self.sample_txt}")
        
        # Log file content preview
        with open(self.sample_txt) as f:
            content = f.read()
            logger.info(f"File size: {len(content)} characters")
            logger.info(f"Content preview: {content[:100]}...")
    
    def test_provider_initialization(self):
        """Test text provider initialization."""
        assert ContentType.TEXT in self.provider.supported_types
        assert ContentType.MARKDOWN in self.provider.supported_types
        assert self.provider.provider_name == "text_provider"
        logger.info(f"Text provider supports: {[t.value for t in self.provider.supported_types]}")
    
    @pytest.mark.asyncio
    async def test_text_to_markdown_chunks(self):
        """Test converting real text file to markdown chunks."""
        if not self.sample_txt.exists():
            pytest.skip(f"Sample text file not found at {self.sample_txt}")
        
        chunks = await self.provider.to_markdown_chunks(str(self.sample_txt))
        
        assert isinstance(chunks, list)
        assert len(chunks) > 0
        
        # Check chunk structure
        for i, chunk in enumerate(chunks):
            assert isinstance(chunk, ContentChunk)
            assert chunk.id.startswith("text-")
            assert chunk.content
            assert chunk.chunk_type in ["text", "heading", "paragraph", "code"]
            assert chunk.metadata
            
            logger.info(f"Chunk {i}: type={chunk.chunk_type}, length={len(chunk.content)}")
        
        # Verify content is preserved
        full_content = "\n".join(chunk.content for chunk in chunks)
        assert "sample text file" in full_content
        assert "Section Header" in full_content
        assert "code block" in full_content
        
        logger.info(f"Extracted {len(chunks)} chunks from text file")
    
    @pytest.mark.asyncio
    async def test_text_metadata_extraction(self):
        """Test text file metadata extraction."""
        
        if not self.sample_txt.exists():
            pytest.skip(f"Sample text file not found at {self.sample_txt}")
        
        metadata = await self.provider.to_metadata(str(self.sample_txt))
        
        assert metadata.extraction_method is not None
        assert metadata.file_size > 0
        assert metadata.mime_type == "text/plain"
        
        # Check text-specific metadata
        text_meta = metadata.properties
        if "encoding" in text_meta:
            assert text_meta["encoding"] in ["utf-8", "ascii"]
            logger.info(f"Text encoding: {text_meta['encoding']}")
        
        if "line_count" in text_meta:
            assert text_meta["line_count"] > 0
            logger.info(f"Line count: {text_meta['line_count']}")
        
        logger.info(f"Text metadata: {metadata.properties}")
        logger.info(f"File size: {metadata.file_size} bytes")
    
    @pytest.mark.asyncio
    async def test_text_chunking_options(self):
        """Test different chunking options."""
        # Test with different chunk sizes
        chunks_small = await self.provider.to_markdown_chunks(
            str(self.sample_txt),
            chunk_size=100
        )
        
        chunks_large = await self.provider.to_markdown_chunks(
            str(self.sample_txt),
            chunk_size=500
        )
        
        # Smaller chunks should result in more pieces
        assert len(chunks_small) >= len(chunks_large)
        
        logger.info(f"Small chunks (100 chars): {len(chunks_small)} chunks")
        logger.info(f"Large chunks (500 chars): {len(chunks_large)} chunks")
    
    @pytest.mark.asyncio
    async def test_text_extended_mode(self):
        """Test text extraction with extended mode."""
        chunks = await self.provider.to_markdown_chunks(
            str(self.sample_txt),
            extended=True
        )
        
        assert len(chunks) > 0
        
        # Extended mode should preserve more structure
        has_code_block = any(c.chunk_type == "code" for c in chunks)
        has_heading = any(c.chunk_type == "heading" for c in chunks)
        
        logger.info(f"Extended mode: {len(chunks)} chunks")
        logger.info(f"Has code blocks: {has_code_block}")
        logger.info(f"Has headings: {has_heading}")
        
        # Check metadata in extended mode
        for chunk in chunks:
            assert chunk.metadata
            if chunk.chunk_type == "code":
                logger.info(f"Code chunk metadata: {chunk.metadata}")
    
    @pytest.mark.asyncio
    async def test_text_can_process(self):
        """Test can_process method for text files."""
        # Should process text file
        can_process = await self.provider.can_process(str(self.sample_txt))
        assert can_process is True
        
        # Should process markdown as text
        md_file = self.sample_txt.with_suffix('.md')
        if md_file.exists():
            can_process = await self.provider.can_process(str(md_file))
            assert can_process is True
        
        # Should not process binary files
        pdf_file = SAMPLE_DATA_PATH / "documents" / "sample.pdf"
        if pdf_file.exists():
            can_process = await self.provider.can_process(str(pdf_file))
            assert can_process is False
    
    @pytest.mark.asyncio
    async def test_text_encoding_handling(self):
        """Test handling of different text encodings."""
        chunks = await self.provider.to_markdown_chunks(str(self.sample_txt))
        
        # Should handle UTF-8 properly
        assert all(isinstance(chunk.content, str) for chunk in chunks)
        
        # Check for special characters if present
        full_content = "".join(chunk.content for chunk in chunks)
        
        # Verify no encoding errors
        try:
            full_content.encode('utf-8')
            logger.info("Text properly encoded as UTF-8")
        except UnicodeEncodeError:
            pytest.fail("Text contains invalid UTF-8 characters")
    
    @pytest.mark.asyncio
    async def test_text_error_handling(self):
        """Test error handling for invalid text files."""
        non_existent = "non_existent.txt"
        
        # Should handle non-existent file gracefully
        chunks = await self.provider.to_markdown_chunks(non_existent)
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "error"
        assert "Error" in chunks[0].content or "Failed" in chunks[0].content


def run_tests():
    """Run text integration tests."""
    logger.info("=== Running Text Integration Tests ===")
    
    test_instance = TestTextIntegration()
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
    
    logger.info("\n=== Text Integration Test Results ===")
    logger.info(f"Passed: {passed}/{total}")
    
    return passed == total


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)