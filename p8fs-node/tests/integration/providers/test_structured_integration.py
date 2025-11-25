"""Integration tests for Structured content provider with real JSON/YAML files."""

import json
import logging
import sys
from pathlib import Path

import pytest
import yaml

# Add src to path
src_dir = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from p8fs_node.models.content import ContentChunk, ContentType
from p8fs_node.providers.structured import StructuredDataContentProvider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample data path
SAMPLE_DATA_PATH = Path(__file__).parent.parent.parent / "sample_data"


class TestStructuredIntegration:
    """Integration tests for Structured content provider."""
    
    def setup_method(self):
        """Setup before each test."""
        self.provider = StructuredDataContentProvider()
        self.sample_json = SAMPLE_DATA_PATH / "structured" / "sample.json"
        self.sample_yaml = SAMPLE_DATA_PATH / "structured" / "sample.yaml"
        
        # Check if sample files exist
        if not self.sample_json.exists() and not self.sample_yaml.exists():
            pytest.skip("No structured sample files found")
    
    def test_structured_files_exist(self):
        """Test that sample structured files exist."""
        assert self.sample_json.exists() or self.sample_yaml.exists()
        
        if self.sample_json.exists():
            assert self.sample_json.is_file()
            logger.info(f"Sample JSON found at: {self.sample_json}")
            
            # Validate JSON structure
            with open(self.sample_json) as f:
                data = json.load(f)
                logger.info(f"JSON keys: {list(data.keys())}")
        
        if self.sample_yaml.exists():
            assert self.sample_yaml.is_file()
            logger.info(f"Sample YAML found at: {self.sample_yaml}")
            
            # Validate YAML structure
            with open(self.sample_yaml) as f:
                data = yaml.safe_load(f)
                logger.info(f"YAML keys: {list(data.keys())}")
    
    def test_provider_initialization(self):
        """Test structured provider initialization."""
        assert ContentType.JSON in self.provider.supported_types
        assert ContentType.YAML in self.provider.supported_types
        assert self.provider.provider_name == "structured_data_provider"
        logger.info(f"Structured provider supports: {[t.value for t in self.provider.supported_types]}")
    
    @pytest.mark.asyncio
    async def test_json_to_markdown_chunks(self):
        """Test converting real JSON file to markdown chunks."""
        if not self.sample_json.exists():
            pytest.skip("Sample JSON not found")
        
        chunks = await self.provider.to_markdown_chunks(str(self.sample_json))
        
        assert isinstance(chunks, list)
        assert len(chunks) > 0
        
        # Check chunk structure
        for i, chunk in enumerate(chunks):
            assert isinstance(chunk, ContentChunk)
            assert chunk.id.startswith("json-")
            assert chunk.content
            assert chunk.chunk_type in ["text", "metadata", "section", "data"]
            assert chunk.metadata
            
            logger.info(f"Chunk {i}: type={chunk.chunk_type}, length={len(chunk.content)}")
        
        # Verify content preservation
        full_content = "\n".join(chunk.content for chunk in chunks)
        assert "Sample JSON Document" in full_content
        assert "Introduction" in full_content
        assert "Main Content" in full_content
        
        logger.info(f"Extracted {len(chunks)} chunks from JSON file")
    
    @pytest.mark.asyncio
    async def test_yaml_to_markdown_chunks(self):
        """Test converting real YAML file to markdown chunks."""
        if not self.sample_yaml.exists():
            pytest.skip("Sample YAML not found")
        
        chunks = await self.provider.to_markdown_chunks(str(self.sample_yaml))
        
        assert isinstance(chunks, list)
        assert len(chunks) > 0
        
        # Check chunk structure
        for i, chunk in enumerate(chunks):
            assert isinstance(chunk, ContentChunk)
            assert chunk.id.startswith("yaml-")
            assert chunk.content
            assert chunk.chunk_type in ["text", "metadata", "section", "data"]
            assert chunk.metadata
            
            logger.info(f"Chunk {i}: type={chunk.chunk_type}, length={len(chunk.content)}")
        
        # Verify content preservation
        full_content = "\n".join(chunk.content for chunk in chunks)
        assert "Sample YAML Document" in full_content
        assert "Introduction" in full_content
        assert "Main Content" in full_content
        
        logger.info(f"Extracted {len(chunks)} chunks from YAML file")
    
    @pytest.mark.asyncio
    async def test_structured_metadata_extraction(self):
        """Test structured file metadata extraction."""
        # Test JSON metadata
        if self.sample_json.exists():
            json_metadata = await self.provider.to_metadata(str(self.sample_json))
            
            assert json_metadata.extraction_method is not None
            assert json_metadata.file_size > 0
            assert json_metadata.mime_type == "application/json"
            
            # Check structure-specific metadata
            if "structure" in json_metadata.properties:
                assert isinstance(json_metadata.properties["structure"], dict)
                logger.info(f"JSON structure: {json_metadata.properties['structure']}")
            
            logger.info(f"JSON metadata: {json_metadata.properties}")
        
        # Test YAML metadata
        if self.sample_yaml.exists():
            yaml_metadata = await self.provider.to_metadata(str(self.sample_yaml))
            
            assert yaml_metadata.extraction_method is not None
            assert yaml_metadata.file_size > 0
            assert yaml_metadata.mime_type in ["application/yaml", "text/yaml"]
            
            logger.info(f"YAML metadata: {yaml_metadata.properties}")
    
    @pytest.mark.asyncio
    async def test_structured_extended_mode(self):
        """Test structured extraction with extended mode."""
        if not self.sample_json.exists():
            pytest.skip("Sample JSON not found")
        
        chunks = await self.provider.to_markdown_chunks(
            str(self.sample_json),
            extended=True
        )
        
        assert len(chunks) > 0
        
        # Extended mode should preserve more structure
        has_sections = any(c.chunk_type == "section" for c in chunks)
        has_metadata = any(c.chunk_type == "metadata" for c in chunks)
        
        logger.info(f"Extended mode: {len(chunks)} chunks")
        logger.info(f"Has sections: {has_sections}")
        logger.info(f"Has metadata chunks: {has_metadata}")
        
        # Check for path information in metadata
        for chunk in chunks:
            if "path" in chunk.metadata:
                logger.info(f"Chunk path: {chunk.metadata['path']}")
    
    @pytest.mark.asyncio
    async def test_structured_nested_data_handling(self):
        """Test handling of nested structured data."""
        if not self.sample_json.exists():
            pytest.skip("Sample JSON not found")
        
        chunks = await self.provider.to_markdown_chunks(str(self.sample_json))
        
        # Check that nested sections are handled
        section_chunks = [c for c in chunks if "sections" in c.content.lower() or "section" in str(c.metadata)]
        assert len(section_chunks) > 0
        
        # Check that arrays are handled
        array_content = any("test" in c.content and "sample" in c.content for c in chunks)
        assert array_content
        
        logger.info(f"Found {len(section_chunks)} section-related chunks")
    
    @pytest.mark.asyncio
    async def test_structured_can_process(self):
        """Test can_process method for structured files."""
        # Should process JSON file
        if self.sample_json.exists():
            can_process = await self.provider.can_process(str(self.sample_json))
            assert can_process is True
        
        # Should process YAML file
        if self.sample_yaml.exists():
            can_process = await self.provider.can_process(str(self.sample_yaml))
            assert can_process is True
        
        # Should not process non-structured files
        text_file = SAMPLE_DATA_PATH / "text" / "sample.txt"
        if text_file.exists():
            can_process = await self.provider.can_process(str(text_file))
            assert can_process is False
    
    @pytest.mark.asyncio
    async def test_structured_flattening_options(self):
        """Test different flattening options for structured data."""
        if not self.sample_json.exists():
            pytest.skip("Sample JSON not found")
        
        # Test with flattening enabled
        chunks_flat = await self.provider.to_markdown_chunks(
            str(self.sample_json),
            flatten=True
        )
        
        # Test without flattening
        chunks_nested = await self.provider.to_markdown_chunks(
            str(self.sample_json),
            flatten=False
        )
        
        # Both should produce chunks
        assert len(chunks_flat) > 0
        assert len(chunks_nested) > 0
        
        logger.info(f"Flattened: {len(chunks_flat)} chunks")
        logger.info(f"Nested: {len(chunks_nested)} chunks")
        
        # Check content differences
        flat_content = "\n".join(c.content for c in chunks_flat)
        nested_content = "\n".join(c.content for c in chunks_nested)
        
        logger.info(f"Flattened content length: {len(flat_content)}")
        logger.info(f"Nested content length: {len(nested_content)}")
    
    @pytest.mark.asyncio
    async def test_structured_error_handling(self):
        """Test error handling for invalid structured files."""
        # Test non-existent file
        non_existent = "non_existent.json"
        chunks = await self.provider.to_markdown_chunks(non_existent)
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "error"
        assert "Error" in chunks[0].content or "Failed" in chunks[0].content
        
        # Test invalid JSON (create temporary file)
        invalid_json = SAMPLE_DATA_PATH / "structured" / "invalid.json"
        try:
            with open(invalid_json, 'w') as f:
                f.write('{"invalid": json without closing}')
            
            chunks = await self.provider.to_markdown_chunks(str(invalid_json))
            assert len(chunks) == 1
            assert chunks[0].chunk_type == "error"
            
        finally:
            # Clean up
            if invalid_json.exists():
                invalid_json.unlink()


def run_tests():
    """Run structured integration tests."""
    logger.info("=== Running Structured Integration Tests ===")
    
    test_instance = TestStructuredIntegration()
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
    
    logger.info("\n=== Structured Integration Test Results ===")
    logger.info(f"Passed: {passed}/{total}")
    
    return passed == total


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)