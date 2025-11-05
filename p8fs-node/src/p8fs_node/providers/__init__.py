"""Content providers for various file formats (PDF, WAV, video, DOCX, Markdown)."""

# Import placeholder providers
from .archive import ArchiveContentProvider

# Heavy providers - imported lazily via registry to avoid startup delays
# from .audio import AudioContentProvider  # Lazy loaded
# from .pdf import PDFContentProvider  # Lazy loaded

# Import auto-registration
from .auto_register import auto_register
from .base import ContentProvider
from .code import CodeContentProvider
from .default import DefaultContentProvider
from .document import DocumentContentProvider
from .image import ImageContentProvider
from .mixins import (
    BaseProviderMixin,
    MediaProviderMixin,
    PlaceholderProviderMixin,
    TextBasedProviderMixin,
)
from .presentation import PresentationContentProvider
from .registry import (
    get_content_provider,
    list_content_providers,
    list_supported_content_types,
    register_content_provider,
)
from .spreadsheet import SpreadsheetContentProvider
from .structured import StructuredDataContentProvider
from .text import TextContentProvider
from .video import VideoContentProvider

__all__ = [
    # Base classes
    "ContentProvider",
    # Mixins
    "BaseProviderMixin",
    "TextBasedProviderMixin",
    "MediaProviderMixin",
    "PlaceholderProviderMixin",
    # Registry functions
    "register_content_provider",
    "get_content_provider",
    "list_content_providers",
    "list_supported_content_types",
    # Light providers only - heavy ones loaded on demand
    # "PDFContentProvider",  # Lazy loaded
    # "AudioContentProvider",  # Lazy loaded
    "TextContentProvider",
    "StructuredDataContentProvider",
    # Placeholder providers
    "VideoContentProvider",
    "DocumentContentProvider",
    "ImageContentProvider",
    "SpreadsheetContentProvider",
    "PresentationContentProvider",
    "CodeContentProvider",
    "ArchiveContentProvider",
    "DefaultContentProvider",
    # Auto-registration
    "auto_register",
]