"""Integration tests for Audio content provider with real audio files."""

import logging
import os
import sys
from pathlib import Path

import pytest

# Add src to path
src_dir = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from p8fs_node.models.content import ContentChunk, ContentType
from p8fs_node.providers.audio import AudioContentProvider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample data path
SAMPLE_DATA_PATH = Path(__file__).parent.parent.parent / "sample_data"


class TestAudioIntegration:
    """Integration tests for Audio content provider."""
    
    def setup_method(self):
        """Setup before each test."""
        self.provider = AudioContentProvider()
        self.sample_wav = SAMPLE_DATA_PATH / "audio" / "sample.wav"
        
        # Check if sample file exists
        if not self.sample_wav.exists():
            pytest.skip(f"Sample WAV not found at {self.sample_wav}")
    
    def test_audio_file_exists(self):
        """Test that sample audio file exists."""
        assert self.sample_wav.exists()
        assert self.sample_wav.is_file()
        logger.info(f"Sample WAV found at: {self.sample_wav}")
    
    def test_provider_initialization(self):
        """Test audio provider initialization."""
        assert ContentType.WAV in self.provider.supported_types
        assert ContentType.MP3 in self.provider.supported_types
        assert self.provider.provider_name == "audio_provider"
        logger.info("Audio provider initialized")
    
    @pytest.mark.asyncio
    async def test_audio_metadata_extraction(self):
        """Test audio metadata extraction."""
        metadata = await self.provider.to_metadata(str(self.sample_wav))
        
        assert metadata.extraction_method is not None
        assert metadata.file_size > 0
        assert metadata.mime_type == "audio/wav"
        
        # Check audio-specific metadata
        audio_meta = metadata.properties
        if "duration" in audio_meta:
            assert audio_meta["duration"] > 0
            logger.info(f"Audio duration: {audio_meta['duration']} seconds")
        
        if "sample_rate" in audio_meta:
            assert audio_meta["sample_rate"] > 0
            logger.info(f"Sample rate: {audio_meta['sample_rate']} Hz")
        
        logger.info(f"Audio metadata: {metadata.properties}")
        logger.info(f"File size: {metadata.file_size} bytes")
    
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") and not os.getenv("ASSEMBLYAI_API_KEY"),
        reason="No transcription API keys available"
    )
    @pytest.mark.asyncio
    async def test_audio_transcription(self):
        """Test audio transcription with available services."""
        # This will attempt transcription if API keys are available
        chunks = await self.provider.to_markdown_chunks(str(self.sample_wav))
        
        assert isinstance(chunks, list)
        assert len(chunks) > 0
        
        # Check chunk structure
        for chunk in chunks:
            assert isinstance(chunk, ContentChunk)
            assert chunk.chunk_type in ["text", "transcript", "error", "metadata"]
            assert chunk.content
            assert chunk.metadata
        
        logger.info(f"Extracted {len(chunks)} chunks from audio")
        if chunks:
            logger.info(f"First chunk type: {chunks[0].chunk_type}")
            logger.info(f"First chunk content preview: {chunks[0].content[:100]}...")
    
    @pytest.mark.asyncio
    async def test_audio_to_markdown_chunks_no_api(self):
        """Test audio processing without transcription API."""
        # Temporarily remove API keys
        old_openai = os.environ.pop("OPENAI_API_KEY", None)
        old_assembly = os.environ.pop("ASSEMBLYAI_API_KEY", None)
        
        try:
            chunks = await self.provider.to_markdown_chunks(str(self.sample_wav))
            
            assert isinstance(chunks, list)
            assert len(chunks) > 0
            
            # Without API, should return metadata chunk
            metadata_chunks = [c for c in chunks if c.chunk_type == "metadata"]
            assert len(metadata_chunks) > 0
            
            logger.info(f"Without API: extracted {len(chunks)} chunks")
            logger.info(f"Chunk types: {[c.chunk_type for c in chunks]}")
            
        finally:
            # Restore API keys
            if old_openai:
                os.environ["OPENAI_API_KEY"] = old_openai
            if old_assembly:
                os.environ["ASSEMBLYAI_API_KEY"] = old_assembly
    
    @pytest.mark.asyncio
    async def test_audio_can_process(self):
        """Test can_process method for audio files."""
        # Should process WAV file
        can_process = await self.provider.can_process(str(self.sample_wav))
        assert can_process is True
        
        # Should not process non-audio file
        text_file = SAMPLE_DATA_PATH / "text" / "sample.txt"
        if text_file.exists():
            can_process = await self.provider.can_process(str(text_file))
            assert can_process is False
    
    @pytest.mark.asyncio
    async def test_audio_extended_mode(self):
        """Test audio extraction with extended mode."""
        chunks = await self.provider.to_markdown_chunks(
            str(self.sample_wav),
            extended=True
        )
        
        assert len(chunks) > 0
        
        # Extended mode should include more metadata
        for chunk in chunks:
            assert chunk.metadata
            if chunk.chunk_type == "metadata":
                # Should have audio-specific metadata
                meta = chunk.metadata
                logger.info(f"Extended metadata: {meta}")
    
    @pytest.mark.asyncio
    async def test_audio_error_handling(self):
        """Test error handling for invalid audio."""
        non_existent = "non_existent.wav"
        
        # Should handle non-existent file gracefully
        chunks = await self.provider.to_markdown_chunks(non_existent)
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "error"
        assert "Error" in chunks[0].content or "Failed" in chunks[0].content


def run_tests():
    """Run audio integration tests."""
    logger.info("=== Running Audio Integration Tests ===")
    
    test_instance = TestAudioIntegration()
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
    
    logger.info("\n=== Audio Integration Test Results ===")
    logger.info(f"Passed: {passed}/{total}")
    
    return passed == total


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)