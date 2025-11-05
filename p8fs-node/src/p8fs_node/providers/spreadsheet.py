"""Spreadsheet content provider implementation."""

import logging

from p8fs_node.models.content import (
    ContentProvider,
    ContentType,
)
from p8fs_node.providers.mixins import PlaceholderProviderMixin

logger = logging.getLogger(__name__)


class SpreadsheetContentProvider(PlaceholderProviderMixin, ContentProvider):
    """Content provider for spreadsheet files."""

    @property
    def supported_types(self) -> list[ContentType]:
        """Return list of supported content types."""
        return [ContentType.SPREADSHEET]

    @property
    def provider_name(self) -> str:
        """Return the name of the provider."""
        return "spreadsheet_provider"

    async def extract_text(self, content_path: str) -> str:
        """Extract text from spreadsheet (placeholder)."""
        from pathlib import Path
        path = Path(content_path)
        if not path.exists():
            return f"[File not found: {content_path}]"
        size = path.stat().st_size
        return f"[Spreadsheet file: {path.name}, Size: {size} bytes. Data extraction not implemented.]"

    # TODO: Future implementation notes:
    # - Use openpyxl for Excel file processing (XLSX, XLSM)
    # - Use pandas for data analysis and CSV/TSV processing
    # - Use xlrd for legacy Excel format support (XLS)
    # - Use odfpy for OpenDocument spreadsheet (ODS) support
    # - Convert tables to markdown format
    # - Extract formulas and cell relationships
    # - Detect and summarize data patterns
    # - Process multiple sheets within workbooks
    # - Extract charts and pivot table summaries
    # - Support formats: XLSX, XLS, CSV, TSV, ODS