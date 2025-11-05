"""Centralized markdown and text processing for all content providers."""

import logging
from pathlib import Path
from typing import Any, List

from p8fs_node.models.content import ContentChunk, ContentMetadata, ContentType
from p8fs_node.utils.text import clean_text

logger = logging.getLogger(__name__)


class MarkdownProcessor:
    """
    Centralized processor that converts any text content to semantic markdown chunks.
    
    This eliminates redundant chunking logic across all providers and ensures
    consistent semantic processing of text content.
    """
    
    DEFAULT_CHUNK_SIZE = 512
    DEFAULT_OVERLAP = 0  # Semantic chunking doesn't need overlap
    
    @classmethod
    async def process(
        cls,
        text: str,
        source_file: Path,
        content_type: ContentType,
        extraction_method: str,
        **options: Any
    ) -> tuple[List[ContentChunk], ContentMetadata]:
        """
        Process extracted text into semantic markdown chunks and metadata.
        
        Args:
            text: Raw text content from any provider
            source_file: Original file path
            content_type: Type of content (PDF, DOCUMENT, AUDIO, etc.)
            extraction_method: Method used to extract text (pypdf, python-docx, etc.)
            **options: Additional processing options
                - chunk_size: Target chunk size in characters (default: 512)
                - title: Override title (default: filename stem)
                - preserve_structure: Keep original formatting hints
                - premium_mode: Enable advanced features (default: False)
        
        Returns:
            Tuple of (chunks, metadata)
        """
        logger.info(f"Processing {len(text)} characters from {source_file} via {extraction_method}")
        
        if not text or not text.strip():
            logger.warning(f"Empty text content from {source_file}")
            return [], cls._create_empty_metadata(source_file, content_type, extraction_method)
        
        # Clean the text
        cleaned_text = clean_text(text)
        
        # Determine chunking strategy
        chunk_size = options.get("chunk_size", cls.DEFAULT_CHUNK_SIZE)
        
        # Use semantic splitting for all content - everything becomes markdown
        chunks = await cls._chunk_text_semantically(
            cleaned_text, chunk_size, source_file, **options
        )
        
        # Create ContentChunk objects
        content_chunks = []
        for i, chunk_text in enumerate(chunks):
            if chunk_text.strip():
                metadata = {
                    "source_file": str(source_file),
                    "extraction_method": extraction_method,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "content_type": content_type.value,
                    "processing_method": "semantic_markdown",
                }
                
                # Add provider-specific metadata
                if "provider_metadata" in options:
                    metadata.update(options["provider_metadata"])
                
                chunk = ContentChunk(
                    id=f"{source_file.stem}-{extraction_method}-{i}",
                    content=chunk_text.strip(),
                    chunk_type="text",
                    position=i,
                    metadata=metadata,
                )
                content_chunks.append(chunk)
        
        # Create unified metadata
        metadata = cls._create_metadata(
            source_file, content_type, extraction_method, text, content_chunks, **options
        )
        
        logger.info(f"Created {len(content_chunks)} semantic chunks")
        return content_chunks, metadata
    
    @classmethod  
    def _is_markdown_content(cls, text: str, file_path: Path) -> bool:
        """Determine if content should be treated as markdown."""
        # Check file extension
        if file_path.suffix.lower() in ['.md', '.markdown']:
            return True
            
        # Check for markdown patterns in text
        markdown_indicators = [
            text.count('# ') > 0,  # Headers
            text.count('```') >= 2,  # Code blocks
            text.count('*') > 5,  # Emphasis/lists  
            text.count('[') > 0 and text.count(']') > 0,  # Links
            text.count('|') > 3,  # Tables
        ]
        
        return sum(markdown_indicators) >= 2
    
    @classmethod
    async def _chunk_text_semantically(
        cls, text: str, chunk_size: int, source_file: Path, **options: Any
    ) -> List[str]:
        """
        Use semantic text splitter that respects document structure.
        
        This is the core chunking logic used by ALL providers.
        """
        try:
            # Try semantic-text-splitter first (best option)
            if cls._is_markdown_content(text, source_file):
                return cls._chunk_with_markdown_splitter(text, chunk_size)
            else:
                return cls._chunk_with_text_splitter(text, chunk_size)
        except ImportError:
            logger.warning("semantic-text-splitter not available, falling back to word-boundary chunking")
            return cls._chunk_with_word_boundaries(text, chunk_size)
    
    @classmethod
    def _chunk_with_markdown_splitter(cls, text: str, chunk_size: int) -> List[str]:
        """Use semantic-text-splitter for markdown content."""
        try:
            from semantic_text_splitter import MarkdownSplitter
            # Try different API patterns for semantic-text-splitter
            try:
                # Try newer API first
                splitter = MarkdownSplitter(max_characters=chunk_size)
            except TypeError:
                # Try older API
                splitter = MarkdownSplitter(chunk_size)
            return splitter.chunks(text)
        except (ImportError, Exception) as e:
            logger.debug(f"semantic-text-splitter failed: {e}")
            return cls._chunk_with_word_boundaries(text, chunk_size)
    
    @classmethod 
    def _chunk_with_text_splitter(cls, text: str, chunk_size: int) -> List[str]:
        """Use semantic-text-splitter for plain text."""
        try:
            from semantic_text_splitter import TextSplitter
            # Try different API patterns for semantic-text-splitter
            try:
                # Try newer API first
                splitter = TextSplitter(max_characters=chunk_size)
            except TypeError:
                # Try older API
                splitter = TextSplitter(chunk_size)
            return splitter.chunks(text)
        except (ImportError, Exception) as e:
            logger.debug(f"semantic-text-splitter failed: {e}")
            return cls._chunk_with_word_boundaries(text, chunk_size)
    
    @classmethod
    def _chunk_with_word_boundaries(cls, text: str, max_chars: int = 512) -> List[str]:
        """
        Fallback word-boundary chunking when semantic-text-splitter unavailable.
        
        This ensures we never break words in the middle.
        """
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_length = len(word) + 1  # +1 for space
            if current_length + word_length > max_chars and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_length = len(word)
            else:
                current_chunk.append(word)
                current_length += word_length
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks
    
    @classmethod
    def _create_metadata(
        cls,
        source_file: Path,
        content_type: ContentType,
        extraction_method: str,
        original_text: str,
        chunks: List[ContentChunk],
        **options: Any
    ) -> ContentMetadata:
        """Create unified metadata for processed content."""
        return ContentMetadata(
            title=options.get("title", source_file.stem),
            file_path=str(source_file),
            file_size=source_file.stat().st_size if source_file.exists() else len(original_text.encode()),
            content_type=content_type,
            extraction_method=f"{extraction_method}_semantic",
            word_count=len(original_text.split()),
            confidence_score=options.get("confidence_score", 0.95),
            properties={
                "original_length": len(original_text),
                "chunk_count": len(chunks),
                "processing_method": "semantic_markdown",
                "chunk_size_target": options.get("chunk_size", cls.DEFAULT_CHUNK_SIZE),
                "premium_mode": options.get("premium_mode", False),
                **options.get("extra_properties", {}),
            }
        )
    
    @classmethod
    def _create_empty_metadata(
        cls,
        source_file: Path,
        content_type: ContentType,
        extraction_method: str
    ) -> ContentMetadata:
        """Create metadata for empty content."""
        return ContentMetadata(
            title=source_file.stem,
            file_path=str(source_file),
            file_size=source_file.stat().st_size if source_file.exists() else 0,
            content_type=content_type,
            extraction_method=f"{extraction_method}_empty",
            word_count=0,
            confidence_score=0.0,
            properties={
                "original_length": 0,
                "chunk_count": 0,
                "processing_method": "empty_content",
                "error": "No text content extracted",
            }
        )