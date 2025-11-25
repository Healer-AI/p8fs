"""Unit tests for structured data content provider."""

from p8fs_node.models.content import ContentType
from p8fs_node.providers.structured import StructuredDataContentProvider


class TestStructuredDataContentProvider:
    """Test structured data content provider implementation."""
    
    def setup_method(self):
        """Set up test provider."""
        self.provider = StructuredDataContentProvider()
    
    def test_supported_types(self):
        """Test supported content types."""
        assert self.provider.supported_types == [ContentType.JSON, ContentType.YAML]
    
    def test_provider_name(self):
        """Test provider name."""
        assert self.provider.provider_name == "structured_data_provider"
    
    def test_basic_functionality(self):
        """Test basic provider functionality."""
        assert hasattr(self.provider, 'to_markdown_chunks')
        assert hasattr(self.provider, 'to_metadata')
        assert callable(self.provider.to_markdown_chunks)
        assert callable(self.provider.to_metadata)