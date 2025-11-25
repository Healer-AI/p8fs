"""Content data models and types."""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    """Supported content types."""

    PDF = "pdf"
    AUDIO = "audio"
    WAV = "wav"
    MP3 = "mp3"
    VIDEO = "video"
    IMAGE = "image"
    TEXT = "text"
    MARKDOWN = "markdown"
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    ARCHIVE = "archive"
    CODE = "code"
    JSON = "json"
    YAML = "yaml"
    UNKNOWN = "unknown"


class ContentChunk(BaseModel):
    """A chunk of processed content."""

    id: str = Field(..., description="Unique identifier for the chunk")
    content: str = Field(..., description="Markdown content of the chunk")
    chunk_type: str = Field(
        default="text", description="Type of chunk (text, header, table, etc.)"
    )
    page_number: int | None = Field(None, description="Page number if applicable")
    position: int | None = Field(None, description="Position within the document")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional chunk metadata"
    )


class ContentMetadata(BaseModel):
    """Metadata extracted from content."""

    title: str | None = Field(None, description="Document title")
    author: str | None = Field(None, description="Document author")
    file_path: str | None = Field(None, description="Source file path")
    subject: str | None = Field(None, description="Document subject")
    keywords: list[str] = Field(default_factory=list, description="Document keywords")
    language: str | None = Field(None, description="Document language")
    page_count: int | None = Field(None, description="Number of pages")
    word_count: int | None = Field(None, description="Number of words")
    file_size: int | None = Field(None, description="File size in bytes")
    mime_type: str | None = Field(None, description="MIME type")
    created_date: datetime | None = Field(None, description="Creation date")
    modified_date: datetime | None = Field(None, description="Last modified date")
    processing_date: datetime = Field(
        default_factory=datetime.utcnow, description="Processing timestamp"
    )
    extraction_method: str = Field(..., description="Method used for extraction")
    content_type: ContentType = Field(..., description="Content type")
    confidence_score: float | None = Field(None, description="Confidence score (0-1)")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Additional properties"
    )


class ContentProcessingResult(BaseModel):
    """Result of content processing."""

    success: bool = Field(..., description="Whether processing was successful")
    content_type: ContentType = Field(..., description="Type of content processed")
    chunks: list[ContentChunk] = Field(
        default_factory=list, description="Processed content chunks"
    )
    metadata: ContentMetadata = Field(..., description="Extracted metadata")
    embeddings: list[list[float]] | None = Field(
        None, description="Generated embeddings"
    )
    error: str | None = Field(None, description="Error message if processing failed")
    processing_time: float | None = Field(
        None, description="Processing time in seconds"
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
    async def extract_text(self, content_path: str | Path) -> str:
        """
        Extract raw text content from file.

        Args:
            content_path: Path to the content file

        Returns:
            Raw text content extracted from the file
        """
        pass

    @abstractmethod
    async def to_metadata(
        self, content_path: str | Path, **options: Any
    ) -> ContentMetadata:
        """
        Extract metadata from content.

        Args:
            content_path: Path to the content file
            **options: Additional processing options

        Returns:
            Content metadata
        """
        pass

    async def can_process(self, content_path: str | Path) -> bool:
        """
        Check if this provider can process the given content.

        Args:
            content_path: Path to the content file

        Returns:
            True if provider can handle this content type
        """
        path = Path(content_path)
        
        # Basic file extension check
        suffix = path.suffix.lower()
        
        for content_type in self.supported_types:
            if suffix == f".{content_type.value}":
                return True
        
        return False