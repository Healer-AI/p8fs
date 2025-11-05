"""Unit tests for content providers."""

import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path

from p8fs_node.models.content import ContentType
from p8fs_node.providers import get_content_provider
from p8fs_node.providers.registry import ContentProviderRegistry
from p8fs_node.providers.text import TextContentProvider


class TestContentProviderRegistry:
    """Test the content provider registry functionality."""
    
    def test_get_provider_returns_default_for_unknown_type(self):
        """Test that get_content_provider returns DefaultContentProvider for unsupported files."""
        from p8fs_node.providers.default import DefaultContentProvider
        
        provider = get_content_provider("/path/to/file.unknown")
        assert isinstance(provider, DefaultContentProvider)
        assert provider.provider_name == "default_provider"
    
    def test_get_provider_returns_text_provider_for_md_files(self):
        """Test that .md files get the TextContentProvider."""
        provider = get_content_provider("/path/to/file.md")
        assert isinstance(provider, TextContentProvider)
    
    def test_get_provider_returns_text_provider_for_txt_files(self):
        """Test that .txt files get the TextContentProvider."""
        provider = get_content_provider("/path/to/file.txt")
        assert isinstance(provider, TextContentProvider)
    
    def test_content_type_detection(self):
        """Test content type detection for various file extensions."""
        registry = ContentProviderRegistry()
        
        test_cases = [
            ("file.md", ContentType.MARKDOWN),
            ("file.txt", ContentType.TEXT),
            ("file.pdf", ContentType.PDF),
            ("file.docx", ContentType.DOCUMENT),
            ("file.mp3", ContentType.AUDIO),
            ("file.mp4", ContentType.VIDEO),
            ("file.jpg", ContentType.IMAGE),
            ("file.py", ContentType.CODE),
            ("file.unknown", ContentType.UNKNOWN),
        ]
        
        for filename, expected_type in test_cases:
            detected_type = registry._detect_content_type(filename)
            assert detected_type == expected_type, f"Failed for {filename}"


class TestMarkdownContentProvider:
    """Test the TextContentProvider for markdown handling."""
    
    @pytest.fixture
    def provider(self):
        """Create a TextContentProvider instance."""
        return TextContentProvider()
    
    def test_supported_types(self, provider):
        """Test that provider supports both TEXT and MARKDOWN types."""
        assert ContentType.MARKDOWN in provider.supported_types
        assert ContentType.TEXT in provider.supported_types
        assert len(provider.supported_types) == 2
    
    def test_provider_name(self, provider):
        """Test provider name."""
        assert provider.provider_name == "text_provider"
    
    @pytest.mark.asyncio
    async def test_extract_text_success(self, provider):
        """Test successful text extraction from markdown file."""
        test_content = "# Test Markdown\n\nThis is a test."
        
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = await provider.extract_text("/path/to/test.md")
            assert result == test_content
    
    @pytest.mark.asyncio
    async def test_extract_text_handles_encoding(self, provider):
        """Test that extract_text handles UTF-8 encoding properly."""
        test_content = "# Test 中文\n\nThis has unicode: 🚀"
        
        with patch("builtins.open", mock_open(read_data=test_content)) as mock_file:
            result = await provider.extract_text("/path/to/test.md")
            mock_file.assert_called_once_with(Path("/path/to/test.md"), encoding='utf-8')
            assert result == test_content
    
    @pytest.mark.asyncio
    async def test_extract_text_file_not_found(self, provider):
        """Test extract_text raises exception for missing file."""
        with patch("builtins.open", side_effect=FileNotFoundError("File not found")):
            with pytest.raises(FileNotFoundError):
                await provider.extract_text("/nonexistent/file.md")
    
    @pytest.mark.asyncio
    async def test_to_markdown_chunks(self, provider):
        """Test markdown chunking functionality."""
        test_content = "# Title\n\nParagraph 1\n\n## Subtitle\n\nParagraph 2"
        
        # Mock the TextChunker
        with patch('p8fs_node.utils.text.TextChunker.chunk_by_characters') as mock_chunker:
            mock_chunker.return_value = [
                "# Title\n\nParagraph 1",
                "## Subtitle\n\nParagraph 2"
            ]
            
            with patch("builtins.open", mock_open(read_data=test_content)):
                result = await provider.to_markdown_chunks("/path/to/test.md")
                
                assert len(result) == 2
                assert result[0].content == "# Title\n\nParagraph 1"
                assert result[1].content == "## Subtitle\n\nParagraph 2"


class TestTextContentProvider:
    """Test the TextContentProvider."""
    
    @pytest.fixture
    def provider(self):
        """Create a TextContentProvider instance."""
        return TextContentProvider()
    
    def test_supported_types(self, provider):
        """Test that provider supports TEXT type."""
        assert ContentType.TEXT in provider.supported_types
    
    @pytest.mark.asyncio
    async def test_extract_text_success(self, provider):
        """Test successful text extraction from text file."""
        test_content = "This is plain text content."
        
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = await provider.extract_text("/path/to/test.txt")
            assert result == test_content
    
    @pytest.mark.asyncio
    async def test_to_markdown_chunks_plain_text(self, provider):
        """Test that plain text is properly converted to markdown."""
        test_content = "Line 1\nLine 2\n\nParagraph 2"
        
        # Mock the TextChunker
        with patch('p8fs_node.utils.text.TextChunker.chunk_by_characters') as mock_chunker:
            mock_chunker.return_value = [
                "Line 1\nLine 2",
                "Paragraph 2"
            ]
            
            with patch("builtins.open", mock_open(read_data=test_content)):
                result = await provider.to_markdown_chunks("/path/to/test.txt")
                
                # Verify it calls the text chunking method
                mock_chunker.assert_called_once()
                assert len(result) == 2


class TestProviderIntegration:
    """Integration tests for provider system."""
    
    @pytest.mark.asyncio
    async def test_provider_chain_for_markdown(self):
        """Test complete chain: get provider -> extract -> chunk."""
        test_content = "# My Document\n\nContent here"
        
        # Get provider
        provider = get_content_provider("test.md")
        assert isinstance(provider, TextContentProvider)
        
        # Mock file reading
        with patch("builtins.open", mock_open(read_data=test_content)):
            # Extract content
            content = await provider.extract_text("test.md")
            assert content == test_content
            
            # Mock chunking
            with patch('p8fs_node.utils.text.TextChunker.chunk_by_characters') as mock_chunker:
                mock_chunker.return_value = [
                    "# My Document",
                    "Content here"
                ]
                
                chunks = await provider.to_markdown_chunks("test.md")
                assert len(chunks) == 2
    
    def test_all_registered_providers_have_implementations(self):
        """Test that all content types in PROVIDER_MAP have actual implementations."""
        from p8fs_node.providers.auto_register import PROVIDER_MAP
        
        for content_type, (module_suffix, class_name) in PROVIDER_MAP.items():
            # Skip heavy providers in unit tests
            if content_type in [ContentType.PDF, ContentType.AUDIO, ContentType.VIDEO]:
                continue
                
            # Try to get a provider for a file of this type
            # This will trigger lazy loading
            extension = {
                ContentType.TEXT: ".txt",
                ContentType.MARKDOWN: ".md",
                ContentType.JSON: ".json",
                ContentType.YAML: ".yaml",
                ContentType.DOCUMENT: ".docx",
                ContentType.CODE: ".py",
                ContentType.UNKNOWN: ".unknown",
                ContentType.SPREADSHEET: ".xlsx",
                ContentType.PRESENTATION: ".pptx",
                ContentType.ARCHIVE: ".zip",
                ContentType.IMAGE: ".jpg"
            }.get(content_type, ".unknown")
            
            try:
                provider = get_content_provider(f"test{extension}")
                assert provider is not None, f"No provider for {content_type}"
                assert hasattr(provider, 'extract_text'), f"Provider for {content_type} missing extract_text"
                assert hasattr(provider, 'to_markdown_chunks'), f"Provider for {content_type} missing to_markdown_chunks"
            except ImportError as e:
                # Heavy providers might have uninstalled dependencies
                if "No module named" in str(e):
                    pytest.skip(f"Skipping {content_type} - missing dependencies: {e}")
                else:
                    raise


class TestErrorHandling:
    """Test error handling in content providers."""
    
    def test_registry_returns_default_provider_for_unknown_types(self):
        """Test that unknown file types get default provider."""
        from p8fs_node.providers.default import DefaultContentProvider
        
        provider = get_content_provider("file.xyz")
        assert isinstance(provider, DefaultContentProvider)
        assert provider.provider_name == "default_provider"
    
    @pytest.mark.asyncio
    async def test_provider_handles_io_errors(self):
        """Test providers handle I/O errors gracefully."""
        provider = get_content_provider("test.md")
        
        with patch("builtins.open", side_effect=IOError("Disk error")):
            with pytest.raises(IOError) as exc_info:
                await provider.extract_text("test.md")
            
            assert "Disk error" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])