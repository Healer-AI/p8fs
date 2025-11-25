"""Unit tests for audio content provider."""

from p8fs_node.models.content import ContentType
from p8fs_node.providers.audio import AudioContentProvider


class TestAudioContentProvider:
    """Test audio content provider implementation."""
    
    def setup_method(self):
        """Set up test provider."""
        self.provider = AudioContentProvider()
    
    def test_supported_types(self):
        """Test supported content types."""
        assert self.provider.supported_types == [ContentType.AUDIO]
    
    def test_provider_name(self):
        """Test provider name."""
        assert self.provider.provider_name == "audio_provider"
    
    def test_basic_functionality(self):
        """Test basic provider functionality."""
        assert hasattr(self.provider, 'to_markdown_chunks')
        assert hasattr(self.provider, 'to_metadata')
        assert callable(self.provider.to_markdown_chunks)
        assert callable(self.provider.to_metadata)
    
    def test_can_process(self):
        """Test file type detection."""
        assert self.provider.can_process("audio.wav") == True
        assert self.provider.can_process("audio.mp3") == True
        assert self.provider.can_process("audio.txt") == False