# PDFium Python Integration Guide for P8FS

## Overview

PDFium is Google Chrome's PDF rendering engine, offering superior performance compared to pure Python libraries. For Python integration, we use **pypdfium2**, which provides Python bindings to the PDFium C++ library.

## Key Benefits

- **5-35x faster** than pypdf for text extraction
- **Better memory efficiency** for large PDFs
- **More accurate** text positioning and layout preservation
- **Native support** for encrypted PDFs
- **Cross-platform** with pre-built wheels

## Installation

```bash
# Basic installation
pip install pypdfium2

# For development with all features
pip install pypdfium2[dev]

# For V8/XFA support (JavaScript in PDFs)
PDFIUM_PLATFORM=auto-v8 pip install -v pypdfium2 --no-binary pypdfium2
```

## Basic Implementation for P8FS

### 1. Enhanced PDF Provider with PDFium

```python
import pypdfium2 as pdfium
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class PDFiumEnhancedProvider(PDFContentProvider):
    """Enhanced PDF provider using PDFium for better performance"""
    
    def __init__(self):
        super().__init__()
        self._has_pdfium = self._check_pdfium_available()
        
    def _check_pdfium_available(self) -> bool:
        try:
            import pypdfium2
            return True
        except ImportError:
            logger.warning("pypdfium2 not available, falling back to pypdf")
            return False
    
    async def extract_text_with_pdfium(self, pdf_path: Path) -> List[Dict[str, Any]]:
        """Extract text using PDFium with layout preservation"""
        pages_data = []
        
        try:
            # Load PDF document
            pdf = pdfium.PdfDocument(str(pdf_path))
            
            for page_index in range(len(pdf)):
                page = pdf[page_index]
                
                # Get page dimensions
                width = page.get_width()
                height = page.get_height()
                
                # Extract text with position information
                textpage = page.get_textpage()
                text = textpage.get_text_bounded()
                
                # Get text with bounding boxes for advanced layout analysis
                char_count = textpage.count_chars()
                
                # Extract structured text blocks
                text_blocks = []
                if char_count > 0:
                    # Get character-level information for precise layout
                    for i in range(textpage.count_rects()):
                        rect = textpage.get_rect(i)
                        rect_text = textpage.get_text_bounded(
                            left=rect[0], top=rect[1], 
                            right=rect[2], bottom=rect[3]
                        )
                        if rect_text.strip():
                            text_blocks.append({
                                'text': rect_text,
                                'bbox': rect,
                                'page': page_index + 1
                            })
                
                pages_data.append({
                    'page_num': page_index + 1,
                    'text': text,
                    'width': width,
                    'height': height,
                    'text_blocks': text_blocks,
                    'char_count': char_count
                })
                
                # Clean up page objects
                textpage.close()
                page.close()
            
            pdf.close()
            
        except Exception as e:
            logger.error(f"PDFium extraction error: {e}")
            raise
            
        return pages_data
    
    async def extract_images_with_pdfium(self, pdf_path: Path) -> List[Dict[str, Any]]:
        """Extract images from PDF using PDFium"""
        images_data = []
        
        pdf = pdfium.PdfDocument(str(pdf_path))
        
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            
            # Get images on page
            for image_index, image in enumerate(page.get_objects(filter=[pdfium.FPDF_PAGEOBJ_IMAGE])):
                try:
                    # Extract image bitmap
                    bitmap = image.get_bitmap()
                    pil_image = bitmap.to_pil()
                    
                    # Get image position
                    pos = image.get_pos()
                    
                    images_data.append({
                        'page': page_index + 1,
                        'index': image_index,
                        'position': pos,
                        'width': pil_image.width,
                        'height': pil_image.height,
                        'image': pil_image
                    })
                    
                    bitmap.close()
                except Exception as e:
                    logger.warning(f"Failed to extract image {image_index} from page {page_index + 1}: {e}")
            
            page.close()
        
        pdf.close()
        return images_data
    
    async def render_page_to_image(self, pdf_path: Path, page_num: int, scale: float = 2.0) -> Any:
        """Render a PDF page to image for OCR or visual analysis"""
        pdf = pdfium.PdfDocument(str(pdf_path))
        
        if page_num > len(pdf) or page_num < 1:
            raise ValueError(f"Invalid page number: {page_num}")
        
        page = pdf[page_num - 1]
        
        # Render with higher scale for better OCR accuracy
        bitmap = page.render(scale=scale, rotation=0)
        pil_image = bitmap.to_pil()
        
        page.close()
        pdf.close()
        
        return pil_image
```

### 2. Hybrid PDF Provider (Fallback Support)

```python
class HybridPDFProvider(PDFContentProvider):
    """PDF provider that uses PDFium when available, falls back to pypdf"""
    
    def __init__(self):
        super().__init__()
        self._init_backends()
    
    def _init_backends(self):
        """Initialize available PDF backends in order of preference"""
        self.backends = []
        
        # Try PDFium first (fastest)
        try:
            import pypdfium2
            self.backends.append(('pdfium', self._extract_with_pdfium))
        except ImportError:
            logger.info("PDFium not available")
        
        # Try PyMuPDF (fast, good quality)
        try:
            import fitz
            self.backends.append(('pymupdf', self._extract_with_pymupdf))
        except ImportError:
            logger.info("PyMuPDF not available")
        
        # Fallback to pypdf (pure Python)
        try:
            import pypdf
            self.backends.append(('pypdf', self._extract_with_pypdf))
        except ImportError:
            logger.warning("No PDF backends available!")
    
    async def extract_text(self, pdf_path: Path) -> str:
        """Extract text using the best available backend"""
        for backend_name, backend_func in self.backends:
            try:
                logger.info(f"Extracting with {backend_name}")
                return await backend_func(pdf_path)
            except Exception as e:
                logger.warning(f"{backend_name} extraction failed: {e}")
                continue
        
        raise RuntimeError("All PDF extraction backends failed")
    
    async def _extract_with_pdfium(self, pdf_path: Path) -> str:
        """Fast extraction using PDFium"""
        import pypdfium2 as pdfium
        
        pdf = pdfium.PdfDocument(str(pdf_path))
        text_parts = []
        
        for page in pdf:
            textpage = page.get_textpage()
            text_parts.append(textpage.get_text_bounded())
            textpage.close()
            page.close()
        
        pdf.close()
        return "\n\n".join(text_parts)
```

### 3. Advanced Features with PDFium

```python
class AdvancedPDFProcessor:
    """Advanced PDF processing using PDFium capabilities"""
    
    async def extract_tables_with_layout(self, pdf_path: Path) -> List[Dict]:
        """Extract tables using PDFium's precise layout information"""
        import pypdfium2 as pdfium
        
        pdf = pdfium.PdfDocument(str(pdf_path))
        tables = []
        
        for page_num, page in enumerate(pdf):
            textpage = page.get_textpage()
            
            # Get all text with precise positions
            char_boxes = []
            for i in range(textpage.count_chars()):
                char_box = textpage.get_charbox(i)
                char = chr(textpage.get_unicode_char(i))
                char_boxes.append({
                    'char': char,
                    'left': char_box[0],
                    'bottom': char_box[1],
                    'right': char_box[2],
                    'top': char_box[3]
                })
            
            # Detect table structure based on alignment
            table_regions = self._detect_table_regions(char_boxes)
            
            for region in table_regions:
                table_text = textpage.get_text_bounded(
                    left=region['left'],
                    top=region['top'],
                    right=region['right'],
                    bottom=region['bottom']
                )
                
                tables.append({
                    'page': page_num + 1,
                    'bounds': region,
                    'text': table_text,
                    'structured': self._parse_table_structure(table_text)
                })
            
            textpage.close()
            page.close()
        
        pdf.close()
        return tables
    
    async def extract_forms_data(self, pdf_path: Path) -> Dict[str, Any]:
        """Extract form fields and values"""
        import pypdfium2 as pdfium
        
        pdf = pdfium.PdfDocument(str(pdf_path))
        forms_data = {}
        
        # Check if PDF has forms
        if pdf.get_formtype() != pdfium.FORMTYPE_NONE:
            formfill = pdf.init_forms()
            
            for page in pdf:
                # Get form fields on page
                # Note: Full forms API requires additional implementation
                pass
        
        pdf.close()
        return forms_data
    
    async def extract_metadata_enhanced(self, pdf_path: Path) -> Dict[str, Any]:
        """Extract comprehensive metadata using PDFium"""
        import pypdfium2 as pdfium
        
        pdf = pdfium.PdfDocument(str(pdf_path))
        
        metadata = {
            'page_count': len(pdf),
            'version': pdf.get_version(),
            'is_linearized': pdf.is_linearized(),
            'file_identifiers': pdf.get_identifiers(),
        }
        
        # Get standard metadata
        for key in ['Title', 'Author', 'Subject', 'Keywords', 'Creator', 'Producer', 'CreationDate', 'ModDate']:
            value = pdf.get_metadata_value(key)
            if value:
                metadata[key.lower()] = value
        
        # Get page-level information
        pages_info = []
        for page in pdf:
            page_info = {
                'width': page.get_width(),
                'height': page.get_height(),
                'rotation': page.get_rotation(),
                'has_transparency': page.has_transparency(),
            }
            pages_info.append(page_info)
            page.close()
        
        metadata['pages'] = pages_info
        pdf.close()
        
        return metadata
```

### 4. Integration with P8FS Pipeline

```python
# In your PDF provider
class P8FSPDFProvider(PDFContentProvider):
    """Production-ready PDF provider for P8FS"""
    
    def __init__(self):
        super().__init__()
        self.use_pdfium = self._check_pdfium_available()
        self.processor = PDFiumEnhancedProvider() if self.use_pdfium else None
    
    async def to_markdown_chunks(
        self, content_path: str | Path, extended: bool = False, **options: Any
    ) -> List[ContentChunk]:
        """Convert PDF to markdown chunks with optimal extraction"""
        
        if self.use_pdfium and self.processor:
            # Use PDFium for fast, accurate extraction
            pages_data = await self.processor.extract_text_with_pdfium(Path(content_path))
            
            # Combine text from all pages
            full_text = "\n\n".join(
                f"## Page {p['page_num']}\n\n{p['text']}" 
                for p in pages_data
            )
            
            # Add layout information if extended processing
            if extended:
                layout_info = {
                    'pages': len(pages_data),
                    'total_chars': sum(p['char_count'] for p in pages_data),
                    'has_images': await self._check_has_images(content_path)
                }
            else:
                layout_info = {}
            
        else:
            # Fallback to original implementation
            full_text = await self.extract_text(content_path)
            layout_info = {}
        
        # Use centralized MarkdownProcessor
        from p8fs_node.processors import MarkdownProcessor
        
        chunks, _ = await MarkdownProcessor.process(
            text=full_text,
            source_file=content_path,
            content_type=ContentType.PDF,
            extraction_method="pdfium" if self.use_pdfium else "pypdf",
            provider_metadata={'layout_info': layout_info},
            **options
        )
        
        return chunks
```

## Performance Optimizations

### 1. Parallel Page Processing

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class ParallelPDFProcessor:
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    async def process_pages_parallel(self, pdf_path: Path) -> List[str]:
        """Process PDF pages in parallel for large documents"""
        import pypdfium2 as pdfium
        
        # First pass: get page count
        pdf = pdfium.PdfDocument(str(pdf_path))
        page_count = len(pdf)
        pdf.close()
        
        # Process pages in parallel
        tasks = []
        for page_num in range(page_count):
            task = asyncio.create_task(
                asyncio.to_thread(self._process_single_page, pdf_path, page_num)
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        return results
    
    def _process_single_page(self, pdf_path: Path, page_num: int) -> str:
        """Process a single page (runs in thread)"""
        import pypdfium2 as pdfium
        
        pdf = pdfium.PdfDocument(str(pdf_path))
        page = pdf[page_num]
        textpage = page.get_textpage()
        text = textpage.get_text_bounded()
        
        textpage.close()
        page.close()
        pdf.close()
        
        return text
```

### 2. Memory-Efficient Streaming

```python
class StreamingPDFProcessor:
    """Process large PDFs without loading entire document in memory"""
    
    async def stream_text(self, pdf_path: Path, chunk_pages: int = 10):
        """Stream PDF text in chunks of pages"""
        import pypdfium2 as pdfium
        
        pdf = pdfium.PdfDocument(str(pdf_path))
        total_pages = len(pdf)
        
        for start_page in range(0, total_pages, chunk_pages):
            end_page = min(start_page + chunk_pages, total_pages)
            
            chunk_text = []
            for page_num in range(start_page, end_page):
                page = pdf[page_num]
                textpage = page.get_textpage()
                chunk_text.append(textpage.get_text_bounded())
                textpage.close()
                page.close()
            
            yield "\n\n".join(chunk_text)
        
        pdf.close()
```

## Comparison with pypdf

| Feature | pypdfium2 | pypdf |
|---------|-----------|-------|
| **Speed** | 0.003-0.1s per page | 0.024-3.5s per page |
| **Memory Usage** | Low (C++ backend) | Higher (pure Python) |
| **Dependencies** | C library (PDFium) | None (pure Python) |
| **Text Quality** | Excellent layout preservation | Good with spacing issues |
| **Table Support** | Layout info available | No built-in support |
| **Image Extraction** | Native support | Basic support |
| **Form Support** | Full forms API | Limited |
| **Platform Support** | All major platforms | Universal |
| **Installation** | pip install (wheels) | pip install |

## Best Practices

1. **Always provide fallback**: Not all environments can use PDFium
2. **Use page-by-page processing** for large PDFs to manage memory
3. **Leverage layout information** for better chunking strategies
4. **Cache extracted text** to avoid re-processing
5. **Handle encrypted PDFs** with password parameter
6. **Clean up resources** properly (close pages and documents)

## Troubleshooting

### Common Issues

1. **Import Error**: Ensure pypdfium2 is installed correctly
2. **Segmentation Fault**: Usually due to not closing resources properly
3. **Memory Leaks**: Always close textpage, page, and pdf objects
4. **Performance**: Use parallel processing for multi-page documents

### Debug Helpers

```python
import pypdfium2 as pdfium

# Check version
print(f"PDFium version: {pdfium.get_version()}")

# Enable logging
import logging
logging.getLogger('pypdfium2').setLevel(logging.DEBUG)
```

## Conclusion

PDFium integration provides significant performance benefits for P8FS:
- **5-35x faster** text extraction
- **Better accuracy** with layout preservation
- **Lower memory usage** for large documents
- **Additional capabilities** like forms and precise positioning

The hybrid approach ensures compatibility while leveraging PDFium's performance when available.