# Document Parsers - Advanced Content Extraction

## Overview

P8FS provides multiple document parsing systems for extracting structured content from various file formats. This document covers production-ready parsers for PDF, DOCX, images, audio, and other formats.

## Kreuzberg Parser (p8fs-node)

The Kreuzberg Parser in `p8fs-node` provides advanced document processing with production-ready features.

### Features

- **Multi-Format Support**: PDF, DOCX, images, audio, video
- **Embedded File Processing**: Extracts and processes files within documents
- **Structured Metadata Extraction**: Automatic extraction of document metadata
- **Production Deployment Patterns**: Scalable worker architecture
- **Content Provider System**: Modular providers for each format

### Architecture

```
┌────────────────────────────────────────────────────────┐
│                  Kreuzberg Parser                      │
└────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐
    │ PDF Provider│ │DOCX Provider│ │Audio Provider│
    └─────────────┘ └───────────┘ └─────────────┘
           │               │               │
    ┌──────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐
    │  Text       │ │  Text     │ │ Transcription│
    │  Extraction │ │ Extraction│ │              │
    └─────────────┘ └───────────┘ └─────────────┘
           │               │               │
           └───────────────┼───────────────┘
                           │
                    ┌──────▼──────┐
                    │  Structured │
                    │   Content   │
                    └─────────────┘
```

### Usage

```python
from p8fs_node.processors.kreuzberg import KreuzbergParser

# Initialize parser
parser = KreuzbergParser()

# Parse document
result = await parser.parse(
    file_path="/path/to/document.pdf",
    extract_metadata=True,
    extract_embedded=True
)

# Access structured content
print(result.text)
print(result.metadata)
print(result.embedded_files)
```

### Content Providers

#### PDF Provider

Extracts text and metadata from PDF files:

```python
from p8fs_node.providers.pdf import PDFProvider

provider = PDFProvider()
content = await provider.extract(file_path="document.pdf")

# Access content
print(content.text)          # Extracted text
print(content.pages)         # Page count
print(content.metadata)      # PDF metadata
print(content.embedded)      # Embedded files
```

**Features**:
- Multi-page text extraction
- Metadata extraction (title, author, creation date)
- Embedded file detection and extraction
- Table detection and extraction
- Image extraction

#### DOCX Provider

Processes Microsoft Word documents:

```python
from p8fs_node.providers.docx import DOCXProvider

provider = DOCXProvider()
content = await provider.extract(file_path="document.docx")

# Access content
print(content.text)          # Document text
print(content.paragraphs)    # Paragraph structure
print(content.tables)        # Table data
print(content.images)        # Embedded images
```

**Features**:
- Paragraph-level extraction
- Table extraction with structure preservation
- Image extraction
- Style and formatting metadata
- Embedded object detection

#### Audio Provider

Transcribes audio files to text:

```python
from p8fs_node.providers.audio import AudioProvider

provider = AudioProvider()
content = await provider.extract(file_path="recording.wav")

# Access transcription
print(content.text)          # Transcribed text
print(content.duration)      # Audio duration
print(content.segments)      # Time-stamped segments
print(content.language)      # Detected language
```

**Features**:
- Multi-format support (WAV, MP3, M4A, FLAC)
- Timestamp generation for segments
- Language detection
- Speaker diarization (optional)
- Integration with transcription services

#### Image Provider

Extracts text from images using OCR:

```python
from p8fs_node.providers.image import ImageProvider

provider = ImageProvider()
content = await provider.extract(file_path="scan.png")

# Access OCR results
print(content.text)          # Extracted text
print(content.confidence)    # OCR confidence scores
print(content.regions)       # Text regions with coordinates
```

**Features**:
- OCR with multiple engines (Tesseract, cloud services)
- Multi-language support
- Region detection with coordinates
- Confidence scoring
- Image preprocessing (rotation, enhancement)

### Deployment Patterns

#### Worker Architecture

Deploy Kreuzberg Parser as distributed workers:

```python
from p8fs_node.workers.document_processor import DocumentProcessorWorker

# Initialize worker
worker = DocumentProcessorWorker(
    worker_id="doc-processor-1",
    nats_url="nats://nats-server:4222",
    queue_name="document.processing"
)

# Start processing
await worker.start()
```

**Worker Configuration**:
```yaml
workers:
  document_processor:
    replicas: 3
    queue: document.processing
    memory: 512Mi
    cpu: 500m
    scaling:
      min: 1
      max: 10
      target_queue_depth: 50
```

#### KEDA Scaling

Scale workers based on queue depth:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: document-processor-scaler
spec:
  scaleTargetRef:
    name: document-processor
  minReplicaCount: 1
  maxReplicaCount: 10
  triggers:
  - type: nats-jetstream
    metadata:
      natsServerMonitoringEndpoint: "nats-server:8222"
      queueName: "document.processing"
      targetQueueDepth: "50"
```

### Integration with Agentic System

Kreuzberg Parser outputs can be processed by agentic system:

```python
from p8fs_node.processors.kreuzberg import KreuzbergParser
from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.models.agentlets.document_analysis import DocumentAnalyzer

# Step 1: Parse document
parser = KreuzbergParser()
document = await parser.parse("research_paper.pdf")

# Step 2: Analyze with agent
proxy = MemoryProxy(model_context=DocumentAnalyzer)
analysis = await proxy.parse_content(
    content=document.text,
    context=context
)

# Step 3: Save structured results
await save_resource(
    type="document_analysis",
    content=analysis.model_dump()
)
```

### Performance

**PDF Parsing** (10-page document):
- Text extraction: ~1-2 seconds
- With OCR: ~10-15 seconds per page
- Metadata extraction: <1 second

**Audio Transcription** (1-hour recording):
- Whisper model: ~5-10 minutes
- Cloud services: ~2-5 minutes
- Cost: $0.006/minute (OpenAI Whisper API)

**DOCX Processing** (50-page document):
- Text extraction: ~1-2 seconds
- Table extraction: ~3-5 seconds
- Image extraction: ~2-3 seconds

## Markdown Parser (Built-in)

Simple markdown parsing for structured content:

```python
from p8fs.utils.markdown import MarkdownParser

parser = MarkdownParser()
document = parser.parse(markdown_text)

# Access structure
print(document.headings)     # H1, H2, H3 structure
print(document.paragraphs)   # Paragraph content
print(document.code_blocks)  # Code blocks
print(document.links)        # External links
```

## Plain Text Parser (Built-in)

Extract structured content from plain text:

```python
from p8fs.utils.text import TextParser

parser = TextParser()
document = parser.parse(text_content)

# Access analysis
print(document.sentences)    # Sentence boundaries
print(document.paragraphs)   # Paragraph structure
print(document.word_count)   # Word statistics
```

## Custom Content Providers

Create custom providers for specialized formats:

```python
from p8fs_node.providers.base import BaseContentProvider

class CustomProvider(BaseContentProvider):
    """Custom content provider for specialized format."""

    supported_formats = [".custom"]

    async def extract(self, file_path: str) -> dict:
        """Extract content from custom format."""
        # Implementation
        return {
            'text': extracted_text,
            'metadata': metadata_dict,
            'embedded': embedded_files
        }

    async def validate(self, file_path: str) -> bool:
        """Validate file format."""
        # Implementation
        return True
```

## Best Practices

### 1. Format Detection

Always detect format before processing:

```python
from p8fs_node.utils.format_detection import detect_format

format_type = detect_format(file_path)
provider = get_provider_for_format(format_type)
content = await provider.extract(file_path)
```

### 2. Error Handling

Handle extraction failures gracefully:

```python
try:
    content = await parser.parse(file_path)
except ParsingError as e:
    logger.error(f"Failed to parse {file_path}: {e}")
    # Fallback to basic text extraction
    content = await basic_text_extraction(file_path)
```

### 3. Memory Management

Use streaming for large documents:

```python
async for chunk in parser.parse_stream(large_file):
    # Process chunk immediately
    await process_chunk(chunk)
```

### 4. Caching

Cache parsed results to avoid reprocessing:

```python
from p8fs.utils.cache import FileCache

cache = FileCache()
cache_key = f"parsed_{file_hash}"

cached = cache.get(cache_key)
if cached:
    return cached

content = await parser.parse(file_path)
cache.set(cache_key, content, ttl=3600)
```

## Testing

### Unit Tests

```python
import pytest
from p8fs_node.providers.pdf import PDFProvider

@pytest.mark.unit
async def test_pdf_extraction():
    provider = PDFProvider()
    content = await provider.extract("tests/samples/test.pdf")

    assert content.text is not None
    assert content.pages > 0
    assert content.metadata is not None
```

### Integration Tests

```python
@pytest.mark.integration
async def test_kreuzberg_full_pipeline():
    parser = KreuzbergParser()
    result = await parser.parse(
        "tests/samples/complex_document.pdf",
        extract_metadata=True,
        extract_embedded=True
    )

    assert result.text
    assert result.metadata
    assert len(result.embedded_files) > 0
```

## Related Documentation

- **Agentic System**: `07-agentic-system.md` - Structured content analysis
- **Memory Proxy**: `02 memory-proxy.md` - Content processing workflows
- **p8fs-node README**: Complete Kreuzberg Parser documentation

## Implementation Files

- `p8fs-node/src/p8fs_node/processors/kreuzberg.py` - Main parser
- `p8fs-node/src/p8fs_node/providers/` - Content providers
- `p8fs-node/src/p8fs_node/workers/document_processor.py` - Worker implementation
