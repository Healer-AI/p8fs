"""Auto-registration of content providers with lazy imports."""

import logging
from p8fs_node.models.content import ContentType

logger = logging.getLogger(__name__)

# Provider mapping - no imports until needed
PROVIDER_MAP = {
    # Fast providers
    ContentType.TEXT: ('.text', 'TextContentProvider'),
    ContentType.MARKDOWN: ('.text', 'TextContentProvider'),  # Markdown is just text
    ContentType.JSON: ('.structured', 'StructuredDataContentProvider'),
    ContentType.YAML: ('.structured', 'StructuredDataContentProvider'),
    ContentType.DOCUMENT: ('.document', 'DocumentContentProvider'),
    ContentType.CODE: ('.code', 'CodeContentProvider'),
    ContentType.UNKNOWN: ('.default', 'DefaultContentProvider'),
    
    # Heavy providers (only load when actually needed)
    ContentType.PDF: ('.pdf', 'PDFContentProvider'),
    ContentType.AUDIO: ('.audio', 'AudioContentProvider'),
    ContentType.WAV: ('.audio', 'AudioContentProvider'),
    ContentType.MP3: ('.audio', 'AudioContentProvider'),
    ContentType.VIDEO: ('.video', 'VideoContentProvider'),
    ContentType.IMAGE: ('.image', 'ImageContentProvider'),
    ContentType.SPREADSHEET: ('.spreadsheet', 'SpreadsheetContentProvider'),
    ContentType.PRESENTATION: ('.presentation', 'PresentationContentProvider'),
    ContentType.ARCHIVE: ('.archive', 'ArchiveContentProvider'),
}


def register_all_providers():
    """Register provider map with lazy loading registry."""
    from .registry import register_provider_map
    register_provider_map(PROVIDER_MAP)
    logger.debug("Registered provider map for lazy loading")


def auto_register():
    """Automatically register all providers when called."""
    register_all_providers()