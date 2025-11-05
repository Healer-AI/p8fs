"""Default content provider implementation."""

import logging

from p8fs_node.models.content import (
    ContentProvider,
    ContentType,
)
from p8fs_node.providers.mixins import PlaceholderProviderMixin

logger = logging.getLogger(__name__)


class DefaultContentProvider(PlaceholderProviderMixin, ContentProvider):
    """Default content provider for unknown or binary files."""

    @property
    def supported_types(self) -> list[ContentType]:
        """Return list of supported content types."""
        return [ContentType.UNKNOWN]

    @property
    def provider_name(self) -> str:
        """Return the name of the provider."""
        return "default_provider"

    async def extract_text(self, content_path: str) -> str:
        """
        Extract raw text content from unknown file type.
        
        Args:
            content_path: Path to the file
            
        Returns:
            Basic file information as text
        """
        from pathlib import Path
        
        file_path = Path(content_path)
        if not file_path.exists():
            return f"[File not found: {content_path}]"
        
        # Return basic file information for unknown types
        size = file_path.stat().st_size
        return f"[Unknown file type: {file_path.name}, Size: {size} bytes]"

    # TODO: Future implementation notes:
    # - Use python-magic or libmagic for file type detection
    # - Extract basic file metadata (size, timestamps, permissions)
    # - Perform entropy analysis for file classification
    # - Generate file hexdump preview for binary files
    # - Attempt to detect embedded text in binary formats
    # - Use file extension and magic bytes for type inference
    # - Provide safe fallback processing for any file type
    # - Support streaming for large files
    # - Extract any available metadata headers
    # - Handle all unrecognized file formats gracefully