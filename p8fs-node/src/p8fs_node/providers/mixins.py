"""Mixin classes for content providers to reduce code duplication."""

import logging
from pathlib import Path
from typing import Any

from p8fs_node.models.content import ContentChunk, ContentMetadata, ContentType

logger = logging.getLogger(__name__)


class BaseProviderMixin:
    """Base mixin providing common functionality for all content providers."""

    def __init__(self):
        """Initialize the provider mixin."""
        self._embedding_service = None

    @property
    def embedding_service(self):
        """Get the embedding service instance."""
        if self._embedding_service is None:
            from p8fs_node.services.embeddings import get_embedding_service
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    async def to_embeddings(self, markdown_chunk: ContentChunk) -> list[float]:
        """
        Generate embeddings for a markdown chunk.

        Args:
            markdown_chunk: The chunk to generate embeddings for

        Returns:
            Vector embeddings
        """
        return await self.embedding_service.generate_embedding(markdown_chunk.content)

    def _create_base_metadata(
        self, content_path: Path, chunks: list[ContentChunk] = None
    ) -> ContentMetadata:
        """Create base metadata using the provider name as extraction method."""
        from p8fs_node.utils import MetadataExtractor
        
        provider_name = getattr(self, "provider_name", "unknown_provider")
        supported_types = getattr(self, "supported_types", [ContentType.UNKNOWN])
        content_type = supported_types[0] if supported_types else ContentType.UNKNOWN

        return MetadataExtractor.create_base_metadata(
            content_path, provider_name, content_type, chunks
        )


class PlaceholderProviderMixin(BaseProviderMixin):
    """Mixin for providers that generate placeholder content."""

    async def to_markdown_chunks(
        self, content_path: str | Path, extended: bool = False, **options: Any
    ) -> list[ContentChunk]:
        """
        Generate placeholder content chunks.

        Args:
            content_path: Path to the content file
            extended: Whether to include extended processing (ignored for placeholders)
            **options: Additional processing options (ignored for placeholders)

        Returns:
            List containing a single placeholder chunk
        """
        content_path = Path(content_path)
        supported_types = getattr(self, "supported_types", [ContentType.UNKNOWN])
        content_type = supported_types[0] if supported_types else ContentType.UNKNOWN

        logger.info(
            f"Generating placeholder content for {content_type.value}: {content_path}"
        )

        # Create placeholder content
        placeholder_content = f"""# {content_path.name}

This is a placeholder for {content_type.value} content.

**File**: {content_path.name}
**Type**: {content_type.value}
**Provider**: {getattr(self, "provider_name", "unknown")}

## Processing Details

- Extended mode: {extended}
- Options: {options}

*Note: This is placeholder content. Actual content processing is not yet implemented.*"""

        chunk = ContentChunk(
            id=f"{content_path.stem}-chunk-1",
            content=placeholder_content,
            chunk_type="placeholder",
            position=0,
            metadata={
                "is_placeholder": True,
                "content_type": content_type.value,
                "provider": getattr(self, "provider_name", "unknown"),
            }
        )

        return [chunk]

    async def to_metadata(
        self,
        content_path: str | Path,
        markdown_chunks: list[ContentChunk] | None = None,
    ) -> ContentMetadata:
        """
        Generate placeholder metadata.

        Args:
            content_path: Path to the content file
            markdown_chunks: Pre-processed chunks (ignored for placeholders)

        Returns:
            Basic metadata with placeholder indicators
        """
        content_path = Path(content_path)
        chunks = markdown_chunks or await self.to_markdown_chunks(content_path)

        metadata = self._create_base_metadata(content_path, chunks)
        metadata.properties["is_placeholder"] = True
        metadata.properties["implementation_status"] = "placeholder"

        # Set mime_type based on file extension
        metadata.mime_type = self._get_mime_type(str(content_path))

        # Add content-type specific metadata for images
        supported_types = getattr(self, "supported_types", [ContentType.UNKNOWN])
        content_type = supported_types[0] if supported_types else ContentType.UNKNOWN
        
        if content_type == ContentType.IMAGE:
            # Try to extract real image metadata
            try:
                from PIL import Image
                with Image.open(content_path) as img:
                    metadata.properties.update({
                        "dimensions": f"{img.width}x{img.height}",
                        "format": img.format.lower() if img.format else content_path.suffix.lower().replace(".", ""),
                        "color_mode": img.mode,
                        "width": img.width,
                        "height": img.height,
                    })
            except Exception:
                # Fallback to basic metadata for placeholder
                metadata.properties.update({
                    "dimensions": "100x100",  # Mock dimensions
                    "format": content_path.suffix.lower().replace(".", ""),
                    "color_mode": "RGB",
                    "width": 100,
                    "height": 100,
                })
        elif content_type == ContentType.DOCUMENT:
            # Add document-specific metadata
            metadata.properties.update({
                "document_format": content_path.suffix.lower().replace(".", ""),
                "document_type": content_path.suffix.lower().replace(".", ""),
                "has_images": False,  # Placeholder assumes no images
                "has_tables": False,  # Placeholder assumes no tables
                "revision_count": 1,  # Placeholder assumes single revision
            })
            # Set author to "Unknown" if not already set
            if metadata.author is None:
                metadata.author = "Unknown"

        return metadata

    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type from file extension."""
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"


class TextBasedProviderMixin(BaseProviderMixin):
    """Mixin for providers that work with text-based content."""

    def _extract_text_safely(self, file_path: Path, encoding: str = None) -> str:
        """
        Extract text from a file with proper encoding.

        Args:
            file_path: Path to the text file
            encoding: Optional encoding to use (defaults to UTF-8)

        Returns:
            Extracted text content
        """
        # Default to UTF-8 instead of unreliable encoding detection
        encoding = encoding or "utf-8"
        
        with open(file_path, encoding=encoding) as f:
            return f.read()

    def _create_text_chunks(
        self, text: str, file_path: Path, chunk_type: str = "text", **options: Any
    ) -> list[ContentChunk]:
        """
        Create content chunks from text using smart chunking.

        Args:
            text: Text content to chunk
            file_path: Original file path
            chunk_type: Type of chunks to create
            **options: Chunking options

        Returns:
            List of content chunks
        """
        from p8fs_node.utils import TextChunker

        # Get chunking parameters
        chunk_size = options.get("chunk_size", 500)
        chunk_overlap = options.get("chunk_overlap", 50)

        # Use the existing TextChunker
        text_chunks = TextChunker.chunk_by_characters(text, chunk_size, chunk_overlap)

        # Create content chunks
        chunks = []
        for i, chunk_text in enumerate(text_chunks):
            # Base metadata
            metadata = {
                "source_file": str(file_path),
                "chunk_index": i,
                "total_chunks": len(text_chunks),
            }
            
            # Add any additional metadata from options
            for key, value in options.items():
                if key not in ["chunk_size", "chunk_overlap"] and value is not None:
                    metadata[key] = value
            
            chunk = ContentChunk(
                id=f"{file_path.stem}-chunk-{i + 1}",
                content=chunk_text,
                chunk_type=chunk_type,
                position=i,
                metadata=metadata,
            )
            chunks.append(chunk)

        return chunks


class MediaProviderMixin(BaseProviderMixin):
    """Mixin for providers that work with media files (audio, video, images)."""

    def _get_media_metadata(self, file_path: Path) -> dict[str, Any]:
        """
        Extract basic media metadata using available libraries.

        Args:
            file_path: Path to the media file

        Returns:
            Dictionary containing media metadata
        """
        metadata = {
            "duration": None,
            "format": file_path.suffix.lower(),
            "size": file_path.stat().st_size,
        }

        # Try to get additional metadata based on file type
        try:
            if file_path.suffix.lower() in [".mp3", ".wav", ".m4a", ".ogg"]:
                # Audio metadata
                try:
                    from pydub import AudioSegment

                    audio = AudioSegment.from_file(str(file_path))
                    metadata.update(
                        {
                            "duration": len(audio) / 1000.0,  # Convert to seconds
                            "channels": audio.channels,
                            "sample_rate": audio.frame_rate,
                            "frame_width": audio.frame_width,
                        }
                    )
                except ImportError:
                    logger.debug("PyDub not available for audio metadata extraction")

            elif file_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif", ".bmp"]:
                # Image metadata
                try:
                    from PIL import Image

                    with Image.open(file_path) as img:
                        metadata.update(
                            {
                                "width": img.width,
                                "height": img.height,
                                "mode": img.mode,
                                "format": img.format,
                            }
                        )

                        # Try to get EXIF data
                        if hasattr(img, "_getexif") and img._getexif():
                            metadata["has_exif"] = True
                except ImportError:
                    logger.debug("PIL not available for image metadata extraction")

        except Exception as e:
            logger.debug(f"Could not extract media metadata from {file_path}: {e}")

        return metadata