"""Unit tests for base content provider and registry."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from p8fs_node.models.content import (
    ContentChunk,
    ContentMetadata,
    ContentType,
)
from p8fs_node.providers.base import ContentProvider
from p8fs_node.providers.registry import (
    ContentProviderRegistry,
    get_content_provider,
    register_content_provider,
)


class MockContentProvider(ContentProvider):
    """Mock content provider for testing."""
    
    @property
    def supported_types(self) -> list[ContentType]:
        return [ContentType.TEXT]
    
    @property
    def provider_name(self) -> str:
        return "mock_provider"
    
    async def to_markdown_chunks(self, content_path: str | Path, extended: bool = False, **options) -> list[ContentChunk]:
        return [
            ContentChunk(
                id="chunk-1",
                content="Test content",
                chunk_type="text",
                position=0
            )
        ]
    
    async def to_metadata(self, content_path: str | Path, markdown_chunks: list[ContentChunk] | None = None) -> ContentMetadata:
        return ContentMetadata(
            title="Test file",
            extraction_method=self.provider_name,
            content_type=ContentType.TEXT
        )
    
    async def to_embeddings(self, markdown_chunk: ContentChunk) -> list[float]:
        return [0.1] * 384


class TestContentProvider:
    """Test base ContentProvider class."""
    
    def test_detect_content_type(self):
        """Test content type detection from file extension."""
        provider = MockContentProvider()
        
        # Test various file types
        assert provider._detect_content_type("test.pdf") == ContentType.PDF
        assert provider._detect_content_type("audio.mp3") == ContentType.AUDIO
        assert provider._detect_content_type("video.mp4") == ContentType.VIDEO
        assert provider._detect_content_type("image.jpg") == ContentType.IMAGE
        assert provider._detect_content_type("doc.txt") == ContentType.TEXT
        assert provider._detect_content_type("data.csv") == ContentType.SPREADSHEET
        assert provider._detect_content_type("code.py") == ContentType.CODE
        assert provider._detect_content_type("unknown.xyz") == ContentType.UNKNOWN
    
    def test_can_process(self):
        """Test can_process method."""
        provider = MockContentProvider()
        
        # Provider supports TEXT type
        assert provider.can_process("test.txt") is True
        assert provider.can_process("test.md") is True
        assert provider.can_process("test.pdf") is False
        assert provider.can_process("test.mp3") is False
    
    @pytest.mark.asyncio
    async def test_process_content_success(self):
        """Test successful content processing."""
        provider = MockContentProvider()
        
        result = await provider.process_content("test.txt", extended=False, generate_embeddings=True)
        
        assert result.success is True
        assert result.content_type == ContentType.TEXT
        assert len(result.chunks) == 1
        assert result.chunks[0].content == "Test content"
        assert result.metadata.title == "Test file"
        assert result.embeddings is not None
        assert len(result.embeddings) == 1
        assert len(result.embeddings[0]) == 384
        assert result.processing_time > 0
    
    @pytest.mark.asyncio
    async def test_process_content_without_embeddings(self):
        """Test content processing without embeddings."""
        provider = MockContentProvider()
        
        result = await provider.process_content("test.txt", extended=False, generate_embeddings=False)
        
        assert result.success is True
        assert result.embeddings is None
    
    @pytest.mark.asyncio
    async def test_process_content_error(self):
        """Test content processing with error."""
        provider = MockContentProvider()
        
        # Mock to_markdown_chunks to raise an error
        with patch.object(provider, 'to_markdown_chunks', side_effect=Exception("Processing error")):
            result = await provider.process_content("test.txt")
        
        assert result.success is False
        assert result.error == "Processing error"
        assert len(result.chunks) == 0
        assert result.processing_time > 0
    
    def test_str_representation(self):
        """Test string representations."""
        provider = MockContentProvider()
        
        # Just verify the str method works and contains key info
        str_repr = str(provider)
        assert "mock_provider" in str_repr
        assert "text" in str_repr.lower()
        assert repr(provider) == "<MockContentProvider: mock_provider>"


class TestContentProviderRegistry:
    """Test ContentProviderRegistry class."""
    
    def setup_method(self):
        """Set up test registry."""
        self.registry = ContentProviderRegistry()
    
    def test_register_provider(self):
        """Test provider registration."""
        self.registry.register(MockContentProvider)
        
        assert ContentType.TEXT in self.registry._providers
        assert self.registry._providers[ContentType.TEXT] == MockContentProvider
    
    def test_register_default_provider(self):
        """Test default provider registration."""
        self.registry.register(MockContentProvider, is_default=True)
        
        assert self.registry._default_provider == MockContentProvider
    
    def test_register_provider_override_warning(self, caplog):
        """Test warning when overriding existing provider."""
        # Register first provider
        self.registry.register(MockContentProvider)
        
        # Create another provider for same type
        class AnotherMockProvider(MockContentProvider):
            pass
        
        # Register second provider (should warn)
        self.registry.register(AnotherMockProvider)
        
        assert "Overriding existing provider" in caplog.text
        assert self.registry._providers[ContentType.TEXT] == AnotherMockProvider
    
    def test_get_provider_by_file(self):
        """Test getting provider by file path."""
        self.registry.register(MockContentProvider)
        
        provider = self.registry.get_provider("test.txt")
        assert provider is not None
        assert provider.provider_name == "mock_provider"
        
        # Test non-supported file
        provider = self.registry.get_provider("test.pdf")
        assert provider is None
    
    def test_basic_registry_functionality(self):
        """Test basic registry functionality without complex file matching."""
        # Simple test that registry works
        assert hasattr(self.registry, 'register')
        assert hasattr(self.registry, 'get_provider')
        assert callable(self.registry.register)
        assert callable(self.registry.get_provider)
    
    def test_get_provider_with_default(self):
        """Test getting provider with default fallback."""
        # Register default provider
        class DefaultProvider(ContentProvider):
            @property
            def supported_types(self):
                return [ContentType.UNKNOWN]
            
            @property
            def provider_name(self):
                return "default_provider"
            
            async def to_markdown_chunks(self, content_path, extended=False, **options):
                return []
            
            async def to_metadata(self, content_path, markdown_chunks=None):
                return ContentMetadata(extraction_method=self.provider_name, content_type=ContentType.UNKNOWN)
            
            async def to_embeddings(self, markdown_chunk):
                return []
        
        self.registry.register(DefaultProvider, is_default=True)
        
        # Unknown file should use default provider
        provider = self.registry.get_provider("unknown.xyz")
        assert provider is not None
        assert provider.provider_name == "default_provider"
    
    def test_get_provider_by_type(self):
        """Test getting provider by content type."""
        self.registry.register(MockContentProvider)
        
        provider = self.registry.get_provider_by_type(ContentType.TEXT)
        assert provider is not None
        assert provider.provider_name == "mock_provider"
        
        # Test non-registered type
        provider = self.registry.get_provider_by_type(ContentType.PDF)
        assert provider is None
    
    def test_list_providers(self):
        """Test listing registered providers."""
        self.registry.register(MockContentProvider)
        
        providers = self.registry.list_providers()
        assert ContentType.TEXT in providers
        assert providers[ContentType.TEXT] == "MockContentProvider"
    
    def test_list_supported_types(self):
        """Test listing supported content types."""
        self.registry.register(MockContentProvider)
        
        types = self.registry.list_supported_types()
        assert ContentType.TEXT in types
    
    def test_instance_caching(self):
        """Test that provider instances are cached."""
        self.registry.register(MockContentProvider)
        
        provider1 = self.registry.get_provider("test.txt")
        provider2 = self.registry.get_provider("another.txt")
        
        assert provider1 is provider2  # Same instance
    
    def test_detect_content_type(self):
        """Test registry's content type detection."""
        registry = ContentProviderRegistry()
        
        assert registry._detect_content_type("test.json") == ContentType.TEXT
        assert registry._detect_content_type("data.yaml") == ContentType.TEXT
        assert registry._detect_content_type("sheet.xlsx") == ContentType.SPREADSHEET


class TestModuleFunctions:
    """Test module-level registry functions."""
    
    @patch('p8fs_node.providers.registry._registry')
    def test_get_content_provider(self, mock_registry):
        """Test get_content_provider function."""
        mock_provider = Mock()
        mock_registry.get_provider.return_value = mock_provider
        
        result = get_content_provider("test.txt")
        
        mock_registry.get_provider.assert_called_once_with("test.txt")
        assert result == mock_provider
    
    @patch('p8fs_node.providers.registry._registry')
    def test_register_content_provider(self, mock_registry):
        """Test register_content_provider function."""
        register_content_provider(MockContentProvider, is_default=True)
        
        mock_registry.register.assert_called_once_with(MockContentProvider, True)