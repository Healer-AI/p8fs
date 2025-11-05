"""Text content provider implementation."""

import logging
from pathlib import Path
from typing import Any

from p8fs_node.models.content import ContentChunk, ContentMetadata, ContentType
from p8fs_node.providers.base import ContentProvider
from p8fs_node.providers.mixins import TextBasedProviderMixin
# Lazy import for embedding service

logger = logging.getLogger(__name__)


class TextContentProvider(TextBasedProviderMixin, ContentProvider):
    """Content provider for text files."""

    @property
    def supported_types(self) -> list[ContentType]:
        """Return list of supported content types."""
        return [ContentType.TEXT, ContentType.MARKDOWN]

    @property
    def provider_name(self) -> str:
        """Return the name of the provider."""
        return "text_provider"
    
    async def extract_text(self, file_path: str) -> str:
        """
        Extract text content from file.
        
        Args:
            file_path: Path to text/markdown file
            
        Returns:
            Raw text content
        """
        return self._extract_text_safely(Path(file_path), encoding="utf-8")

    async def to_markdown_chunks(
        self, content_path: str | Path, extended: bool = False, **options: Any
    ) -> list[ContentChunk]:
        """
        Convert text content to semantic markdown chunks.

        Args:
            content_path: Path to the text file
            extended: Whether to include extended processing
            **options: Additional processing options
                - chunk_size: int - Target chunk size in words (default: 500)

        Returns:
            List of content chunks in markdown format
        """
        path = Path(content_path)
        
        # Extract text using UTF-8 encoding
        text = self._extract_text_safely(path, "utf-8")
        
        # Use TextChunker which now uses semchunk
        from p8fs_node.utils.text import TextChunker
        chunk_texts = TextChunker.chunk_by_characters(text)  # Uses semchunk internally
        
        # Create ContentChunk objects
        chunks = []
        for i, chunk_text in enumerate(chunk_texts):
            if chunk_text.strip():
                chunk = ContentChunk(
                    id=f"{path.stem}-chunk-{i}",
                    content=chunk_text.strip(),
                    chunk_type="text",
                    position=i,
                    metadata={"method": "semchunk_500_words"}
                )
                chunks.append(chunk)
        
        return chunks

    async def to_metadata(
        self,
        content_path: str | Path,
        markdown_chunks: list[ContentChunk] | None = None,
    ) -> ContentMetadata:
        """
        Extract metadata from text file.

        Args:
            content_path: Path to the text file
            markdown_chunks: Pre-processed chunks (optional)

        Returns:
            Extracted metadata
        """
        logger.info(f"Extracting text metadata: {content_path}")
        
        path = Path(content_path)
        
        # Use chunks if provided, otherwise generate them
        if markdown_chunks is None:
            markdown_chunks = await self.to_markdown_chunks(path)
        
        # Use the mixin's base metadata creation
        metadata = self._create_base_metadata(path, markdown_chunks)
        
        # Add text-specific properties
        extension = path.suffix.lower()
        mime_mapping = {
            ".txt": "text/plain",
            ".md": "text/markdown", 
            ".rst": "text/x-rst",
            ".csv": "text/csv",
            ".log": "text/plain",
        }
        metadata.mime_type = mime_mapping.get(extension, "text/plain")
        metadata.properties["encoding"] = "utf-8"
        
        return metadata

    async def to_embeddings(self, markdown_chunk: ContentChunk) -> list[float]:
        """
        Generate embeddings for a text chunk.

        Args:
            markdown_chunk: The chunk to generate embeddings for

        Returns:
            Vector embeddings
        """
        logger.info(f"Generating embeddings for text chunk: {markdown_chunk.id}")

        from p8fs_node.services.embeddings import get_embedding_service
        embedding_service = get_embedding_service()
        return await embedding_service.generate_embedding(markdown_chunk.content)