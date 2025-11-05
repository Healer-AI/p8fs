"""Unit tests for text content provider."""

from p8fs_node.models.content import ContentType
from p8fs_node.providers.text import TextContentProvider


class TestTextContentProvider:
    """Test text content provider implementation."""
    
    def setup_method(self):
        """Set up test provider."""
        self.provider = TextContentProvider()
    
    def test_supported_types(self):
        """Test supported content types."""
        assert self.provider.supported_types == [ContentType.TEXT]
    
    def test_provider_name(self):
        """Test provider name."""
        assert self.provider.provider_name == "text_provider"
    
    def test_basic_functionality(self):
        """Test basic provider functionality."""
        assert hasattr(self.provider, 'to_markdown_chunks')
        assert hasattr(self.provider, 'to_metadata')
        assert callable(self.provider.to_markdown_chunks)
        assert callable(self.provider.to_metadata)