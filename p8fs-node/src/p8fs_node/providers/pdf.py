"""PDF content provider implementation."""

import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from p8fs_node.models.content import ContentChunk, ContentMetadata, ContentType
from p8fs_node.providers.base import ContentProvider
from p8fs_node.providers.mixins import BaseProviderMixin

logger = logging.getLogger(__name__)

# Check for PDF libraries availability without importing
HAS_KREUZBERG = None
HAS_PYPDF = None
HAS_FITZ = None

def _check_kreuzberg_available():
    """Check if Kreuzberg is available without importing."""
    try:
        import kreuzberg
        return True
    except ImportError:
        return False

def _check_pypdf_available():
    """Check if pypdf is available without importing."""
    try:
        import pypdf
        return True
    except ImportError:
        return False

def _check_fitz_available():
    """Check if PyMuPDF is available without importing."""
    try:
        import fitz
        return True
    except ImportError:
        return False


class PDFContentProvider(BaseProviderMixin, ContentProvider):
    """Content provider for PDF files."""

    @property
    def supported_types(self) -> list[ContentType]:
        """Return list of supported content types."""
        return [ContentType.PDF]

    @property
    def provider_name(self) -> str:
        """Return the name of the provider."""
        return "pdf_provider"

    async def extract_text(self, content_path: str | Path) -> str:
        """
        Extract raw text content from PDF file.

        Args:
            content_path: Path to the PDF file

        Returns:
            Raw text content extracted from all pages
        """
        # Check PDF library availability
        global HAS_KREUZBERG, HAS_PYPDF, HAS_FITZ
        if HAS_KREUZBERG is None:
            HAS_KREUZBERG = _check_kreuzberg_available()
        if HAS_PYPDF is None:
            HAS_PYPDF = _check_pypdf_available()
        if HAS_FITZ is None:
            HAS_FITZ = _check_fitz_available()

        if not HAS_KREUZBERG and not HAS_PYPDF and not HAS_FITZ:
            raise ImportError("PDF support requires kreuzberg, pypdf, or PyMuPDF")

        content_path = Path(content_path)

        # Try Kreuzberg first (default)
        if HAS_KREUZBERG:
            try:
                from kreuzberg import extract_file
                result = await extract_file(str(content_path))
                return result.content
            except Exception as e:
                logger.warning(f"Kreuzberg extraction failed, falling back: {e}")

        # Fallback to pypdf/fitz
        with open(content_path, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()

        text_pages = await self._extract_text_pages(pdf_bytes)
        all_text = "\n\n".join(page_text for page_text in text_pages if page_text and page_text.strip())

        return all_text

    async def to_markdown_chunks(
        self, content_path: str | Path, extended: bool = False, **options: Any
    ) -> list[ContentChunk]:
        """
        Convert PDF content to markdown chunks.

        Args:
            content_path: Path to the PDF file
            extended: Whether to include extended processing (OCR, table extraction)
            **options: Additional processing options
                - extract_tables: bool - Extract tables as markdown
                - extract_images: bool - Extract and describe images
                - ocr_enabled: bool - Enable OCR for scanned PDFs
                - chunk_size: int - Target chunk size in characters
                - chunk_overlap: int - Number of characters to overlap

        Returns:
            List of content chunks in markdown format
        """
        logger.info(f"Processing PDF: {content_path} (extended={extended})")

        # Check PDF library availability
        global HAS_KREUZBERG, HAS_PYPDF, HAS_FITZ
        if HAS_KREUZBERG is None:
            HAS_KREUZBERG = _check_kreuzberg_available()
        if HAS_PYPDF is None:
            HAS_PYPDF = _check_pypdf_available()
        if HAS_FITZ is None:
            HAS_FITZ = _check_fitz_available()

        if not HAS_KREUZBERG and not HAS_PYPDF and not HAS_FITZ:
            raise ImportError("PDF support requires kreuzberg, pypdf, or PyMuPDF")

        content_path = Path(content_path)
        all_text = ""
        page_metadata = []
        extraction_method = "unknown"

        # Try Kreuzberg first (default)
        if HAS_KREUZBERG:
            try:
                from kreuzberg import extract_file
                result = await extract_file(str(content_path))
                all_text = result.content
                extraction_method = "kreuzberg"

                # Kreuzberg returns text without page markers, estimate page count from metadata
                if hasattr(result, 'metadata') and hasattr(result.metadata, 'page_count'):
                    page_count = result.metadata.page_count
                    page_metadata = [{"page_number": i+1} for i in range(page_count)]

                logger.info(f"Extracted text using Kreuzberg: {len(all_text)} characters")
            except Exception as e:
                logger.warning(f"Kreuzberg extraction failed, falling back: {e}")
                HAS_KREUZBERG = False

        # Fallback to pypdf/fitz
        if not all_text and (HAS_PYPDF or HAS_FITZ):
            with open(content_path, "rb") as pdf_file:
                pdf_bytes = pdf_file.read()

            text_pages = await self._extract_text_pages(pdf_bytes)
            extraction_method = "pypdf" if HAS_PYPDF else "fitz"

            for page_num, page_text in enumerate(text_pages, 1):
                if page_text and page_text.strip():
                    all_text += f"\n\n## Page {page_num}\n\n{page_text}"
                    page_metadata.append({
                        "page_number": page_num,
                        "text_length": len(page_text),
                        "word_count": len(page_text.split())
                    })

        if not all_text.strip():
            logger.warning(f"No text extracted from PDF: {content_path}")
            return []

        # Use centralized MarkdownProcessor
        from p8fs_node.processors import MarkdownProcessor

        chunks, _ = await MarkdownProcessor.process(
            text=all_text,
            source_file=content_path,
            content_type=ContentType.PDF,
            extraction_method=extraction_method,
            provider_metadata={
                "page_count": len(page_metadata),
                "pages_with_text": len(page_metadata),
                "page_details": page_metadata
            },
            **options
        )

        logger.info(f"Extracted {len(chunks)} semantic chunks using {extraction_method}")
        return chunks

    async def to_metadata(
        self,
        content_path: str | Path,
        markdown_chunks: list[ContentChunk] | None = None,
    ) -> ContentMetadata:
        """Extract metadata from PDF using MarkdownProcessor."""
        from p8fs_node.processors import MarkdownProcessor

        logger.info(f"Extracting PDF metadata: {content_path}")

        content_path = Path(content_path)

        # Check PDF library availability
        global HAS_KREUZBERG, HAS_PYPDF, HAS_FITZ
        if HAS_KREUZBERG is None:
            HAS_KREUZBERG = _check_kreuzberg_available()
        if HAS_PYPDF is None:
            HAS_PYPDF = _check_pypdf_available()
        if HAS_FITZ is None:
            HAS_FITZ = _check_fitz_available()

        if not HAS_KREUZBERG and not HAS_PYPDF and not HAS_FITZ:
            # Basic metadata without PDF libraries
            return ContentMetadata(
                title=content_path.stem,
                file_path=str(content_path),
                file_size=content_path.stat().st_size,
                content_type=ContentType.PDF,
                extraction_method="no_pdf_library",
                properties={"error": "No PDF processing library available"}
            )

        try:
            all_text = ""
            page_metadata = []
            pdf_metadata = {}
            extraction_method = "unknown"

            # Try Kreuzberg first (default)
            if HAS_KREUZBERG:
                try:
                    from kreuzberg import extract_file
                    result = await extract_file(str(content_path))
                    all_text = result.content
                    extraction_method = "kreuzberg"

                    # Extract metadata from Kreuzberg result
                    if hasattr(result, 'metadata'):
                        metadata_obj = result.metadata
                        if hasattr(metadata_obj, 'page_count'):
                            pdf_metadata['page_count'] = metadata_obj.page_count
                            page_metadata = [{"page_number": i+1} for i in range(metadata_obj.page_count)]
                        if hasattr(metadata_obj, 'title') and metadata_obj.title:
                            pdf_metadata['title'] = metadata_obj.title
                        if hasattr(metadata_obj, 'author') and metadata_obj.author:
                            pdf_metadata['author'] = metadata_obj.author
                        if hasattr(metadata_obj, 'creation_date') and metadata_obj.creation_date:
                            pdf_metadata['creation_date'] = str(metadata_obj.creation_date)
                        if hasattr(metadata_obj, 'language') and metadata_obj.language:
                            pdf_metadata['language'] = metadata_obj.language

                        pdf_metadata['extraction_library'] = 'kreuzberg'

                    logger.info(f"Extracted metadata using Kreuzberg")
                except Exception as e:
                    logger.warning(f"Kreuzberg metadata extraction failed, falling back: {e}")
                    HAS_KREUZBERG = False

            # Fallback to pypdf/fitz
            if not all_text and (HAS_PYPDF or HAS_FITZ):
                with open(content_path, "rb") as pdf_file:
                    pdf_bytes = pdf_file.read()

                text_pages = await self._extract_text_pages(pdf_bytes)
                extraction_method = "pypdf" if HAS_PYPDF else "fitz"

                for page_num, page_text in enumerate(text_pages, 1):
                    if page_text and page_text.strip():
                        all_text += f"\n\n## Page {page_num}\n\n{page_text}"
                        page_metadata.append({
                            "page_number": page_num,
                            "text_length": len(page_text),
                            "word_count": len(page_text.split())
                        })

                # Get PDF-specific metadata
                pdf_metadata = self._extract_pdf_metadata(pdf_bytes)
            
            if not all_text.strip():
                # Return basic metadata for empty PDFs
                return ContentMetadata(
                    title=pdf_metadata.get("title", content_path.stem),
                    file_path=str(content_path),
                    file_size=content_path.stat().st_size,
                    content_type=ContentType.PDF,
                    extraction_method="pdf_empty",
                    word_count=0,
                    properties={
                        **pdf_metadata,
                        "error": "No text content extracted"
                    }
                )

            # Use MarkdownProcessor to get unified metadata
            _, metadata = await MarkdownProcessor.process(
                text=all_text,
                source_file=content_path,
                content_type=ContentType.PDF,
                extraction_method=extraction_method,
                provider_metadata={
                    "page_count": len(page_metadata),
                    "pages_with_text": len(page_metadata),
                    "page_details": page_metadata,
                    **pdf_metadata
                },
                title=pdf_metadata.get("title", content_path.stem)
            )

            # Add PDF-specific properties
            metadata.mime_type = "application/pdf"
            metadata.properties.update(pdf_metadata)

            return metadata

        except Exception as e:
            logger.error(f"Failed to extract PDF metadata: {e}")
            # Return basic metadata on error
            return ContentMetadata(
                title=content_path.stem,
                file_path=str(content_path),
                file_size=content_path.stat().st_size,
                content_type=ContentType.PDF,
                extraction_method="pdf_error",
                properties={"error": str(e)}
            )


    async def _extract_text_pages(self, pdf_bytes: bytes) -> list[str]:
        """Extract text from each page of the PDF."""
        text_pages = []

        if HAS_PYPDF:
            try:
                import pypdf
                pdf_file = io.BytesIO(pdf_bytes)
                pdf_reader = pypdf.PdfReader(pdf_file)

                for page in pdf_reader.pages:
                    text = page.extract_text()
                    # Clean up text
                    text = text.replace("\n \n", "\n").strip()
                    text_pages.append(text)

                return text_pages
            except Exception as e:
                logger.error(f"Error extracting text with pypdf: {e}")

        if HAS_FITZ:
            try:
                import fitz  # PyMuPDF
                pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

                for page_num in range(pdf_document.page_count):
                    page = pdf_document.load_page(page_num)
                    text = page.get_text()
                    text_pages.append(text.strip())

                pdf_document.close()
                return text_pages
            except Exception as e:
                logger.error(f"Error extracting text with PyMuPDF: {e}")

        return text_pages
    
    def _extract_pdf_metadata(self, pdf_bytes: bytes) -> dict:
        """Extract PDF-specific metadata."""
        metadata = {}
        
        try:
            if HAS_PYPDF:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
                metadata.update({
                    "page_count": len(reader.pages),
                    "pdf_version": reader.pdf_header,
                    "is_encrypted": reader.is_encrypted,
                    "extraction_library": "pypdf"
                })
                
                # Extract document metadata if available
                if reader.metadata:
                    if reader.metadata.title:
                        metadata["title"] = reader.metadata.title
                    if reader.metadata.author:
                        metadata["author"] = reader.metadata.author
                    if reader.metadata.subject:
                        metadata["subject"] = reader.metadata.subject
                    if reader.metadata.creator:
                        metadata["creator"] = reader.metadata.creator
            
            elif HAS_FITZ:
                import fitz
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                metadata.update({
                    "page_count": doc.page_count,
                    "is_pdf": doc.is_pdf,
                    "pdf_version": f"1.{doc.pdf_version()}" if hasattr(doc, 'pdf_version') else "unknown",
                    "extraction_library": "fitz"
                })
                
                # Extract document metadata
                doc_metadata = doc.metadata
                for key in ["title", "author", "subject", "creator"]:
                    if doc_metadata.get(key):
                        metadata[key] = doc_metadata[key]
                
                doc.close()
                
        except Exception as e:
            logger.warning(f"Failed to extract PDF metadata details: {e}")
            metadata["metadata_error"] = str(e)
        
        return metadata