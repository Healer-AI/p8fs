"""Base content provider interface."""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from p8fs_node.models.content import (
    ContentChunk,
    ContentMetadata,
    ContentProcessingResult,
    ContentType,
)


class ContentProvider(ABC):
    """Abstract base class for content providers."""

    @property
    @abstractmethod
    def supported_types(self) -> list[ContentType]:
        """Return list of supported content types."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of the provider."""
        pass

    @abstractmethod
    async def to_markdown_chunks(
        self, content_path: str | Path, extended: bool = False, **options: Any
    ) -> list[ContentChunk]:
        """
        Convert content to markdown chunks.

        Args:
            content_path: Path to the content file
            extended: Whether to include extended processing
            **options: Additional processing options

        Returns:
            List of content chunks in markdown format
        """
        pass

    @abstractmethod
    async def to_metadata(
        self,
        content_path: str | Path,
        markdown_chunks: list[ContentChunk] | None = None,
    ) -> ContentMetadata:
        """
        Extract metadata from content.

        Args:
            content_path: Path to the content file
            markdown_chunks: Pre-processed chunks (optional)

        Returns:
            Extracted metadata
        """
        pass

    @abstractmethod
    async def to_embeddings(self, markdown_chunk: ContentChunk) -> list[float]:
        """
        Generate embeddings for a markdown chunk.

        Args:
            markdown_chunk: The chunk to generate embeddings for

        Returns:
            Vector embeddings
        """
        pass

    async def process_content(
        self,
        content_path: str | Path,
        extended: bool = False,
        generate_embeddings: bool = True,
        **options: Any,
    ) -> ContentProcessingResult:
        """
        Process content through the full pipeline.

        Args:
            content_path: Path to the content file
            extended: Whether to include extended processing
            generate_embeddings: Whether to generate embeddings
            **options: Additional processing options

        Returns:
            Complete processing result
        """
        try:
            start_time = datetime.utcnow()

            # Convert to markdown chunks
            chunks = await self.to_markdown_chunks(content_path, extended, **options)

            # Extract metadata
            metadata = await self.to_metadata(content_path, chunks)

            # Generate embeddings if requested
            embeddings = None
            if generate_embeddings and chunks:
                embeddings = []
                for chunk in chunks:
                    chunk_embeddings = await self.to_embeddings(chunk)
                    embeddings.append(chunk_embeddings)

            processing_time = (datetime.utcnow() - start_time).total_seconds()

            return ContentProcessingResult(
                success=True,
                content_type=self._detect_content_type(content_path),
                chunks=chunks,
                metadata=metadata,
                embeddings=embeddings,
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            return ContentProcessingResult(
                success=False,
                content_type=self._detect_content_type(content_path),
                chunks=[],
                metadata=ContentMetadata(
                    extraction_method=self.provider_name,
                    content_type=self._detect_content_type(content_path)
                ),
                error=str(e),
                processing_time=processing_time,
            )

    def _detect_content_type(self, content_path: str | Path) -> ContentType:
        """Detect content type from file extension."""
        path = Path(content_path)
        extension = path.suffix.lower()

        type_mapping = {
            ".pdf": ContentType.PDF,
            ".wav": ContentType.AUDIO,
            ".mp3": ContentType.AUDIO,
            ".m4a": ContentType.AUDIO,
            ".flac": ContentType.AUDIO,
            ".mp4": ContentType.VIDEO,
            ".avi": ContentType.VIDEO,
            ".mov": ContentType.VIDEO,
            ".mkv": ContentType.VIDEO,
            ".jpg": ContentType.IMAGE,
            ".jpeg": ContentType.IMAGE,
            ".png": ContentType.IMAGE,
            ".gif": ContentType.IMAGE,
            ".bmp": ContentType.IMAGE,
            ".txt": ContentType.TEXT,
            ".md": ContentType.TEXT,
            ".rst": ContentType.TEXT,
            ".docx": ContentType.DOCUMENT,
            ".doc": ContentType.DOCUMENT,
            ".odt": ContentType.DOCUMENT,
            ".xlsx": ContentType.SPREADSHEET,
            ".xls": ContentType.SPREADSHEET,
            ".ods": ContentType.SPREADSHEET,
            ".csv": ContentType.SPREADSHEET,
            ".pptx": ContentType.PRESENTATION,
            ".ppt": ContentType.PRESENTATION,
            ".odp": ContentType.PRESENTATION,
            ".zip": ContentType.ARCHIVE,
            ".tar": ContentType.ARCHIVE,
            ".gz": ContentType.ARCHIVE,
            ".7z": ContentType.ARCHIVE,
            ".py": ContentType.CODE,
            ".js": ContentType.CODE,
            ".ts": ContentType.CODE,
            ".java": ContentType.CODE,
            ".cpp": ContentType.CODE,
            ".c": ContentType.CODE,
            ".h": ContentType.CODE,
            ".hpp": ContentType.CODE,
            ".rs": ContentType.CODE,
            ".go": ContentType.CODE,
        }

        return type_mapping.get(extension, ContentType.UNKNOWN)

    def can_process(self, content_path: str | Path) -> bool:
        """Check if this provider can process the given content."""
        content_type = self._detect_content_type(content_path)
        return content_type in self.supported_types

    def __str__(self) -> str:
        return f"{self.provider_name} ({', '.join(self.supported_types)})"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.provider_name}>"