# P8FS Node Module

## Module Overview

The P8FS Node module is a content processing engine with dual Python/Rust implementation. It handles file format conversion, embedding generation, and content transformation for various document types including PDF, audio, video, and structured documents.

## Architecture

### Core Components

- **Content Provider Registry**: Extensible system for different file formats
- **Embedding Service**: Vector generation for semantic search
- **Multi-Format Processors**: PDF, audio, video, document, and text processors
- **Rust High-Performance Components**: Performance-critical operations in Rust
- **Python Integration Layer**: Orchestration and higher-level logic

### Key Features

- Dual-language implementation (Python + Rust)
- Modular content provider architecture
- Streaming processing for large files
- Background embedding generation
- Auto-registration of processors

## Development Standards

### Code Quality

- Write minimal, efficient code with clear intent
- Avoid workarounds; implement proper solutions
- Prioritize maintainability over quick fixes
- Keep implementations lean and purposeful
- No comments unless absolutely necessary for complex processing logic

### Performance Philosophy

- Use Rust for CPU-intensive operations
- Use Python for orchestration and integration
- Stream processing for memory efficiency
- Async operations for I/O-bound tasks

### Testing Requirements

#### Unit Tests
- Mock file I/O and external services
- Test individual processors in isolation
- Validate content transformation logic
- Test provider registration system

#### Integration Tests
- Use real file samples for processing
- Test complete processing pipelines
- Validate embedding generation
- Test cross-language (Python-Rust) integration

### Configuration

All configuration must come from the centralized system in `p8fs_cluster.config.settings`. The node module uses embedding service configuration and processing parameters.

```python
# ✅ CORRECT - Use centralized config
from p8fs_cluster.config.settings import config

# Embedding service configuration
embedding_service = EmbeddingService(
    provider=config.embedding_provider,
    model=config.embedding_model,
    batch_size=config.embedding_batch_size
)

# Content processing configuration
max_chunk_size = config.content_max_chunk_size
overlap_size = config.content_overlap_size
```

```python
# ❌ WRONG - Don't hardcode processing parameters
# MAX_CHUNK_SIZE = 1000  # Hardcoded
# EMBEDDING_MODEL = "text-embedding-3-small"  # Hardcoded
```

## Content Provider Architecture

### Base Provider Pattern
```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from p8fs_node.models.content import ContentChunk

class BaseContentProvider(ABC):
    @abstractmethod
    async def can_process(self, file_path: str) -> bool:
        pass
    
    @abstractmethod
    async def extract_content(self, file_path: str) -> List[ContentChunk]:
        pass
    
    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        pass

class ContentChunk:
    def __init__(self, content: str, metadata: Dict[str, Any]):
        self.content = content
        self.metadata = metadata
        self.embedding: Optional[List[float]] = None
```

### Provider Implementation Example
```python
from p8fs_node.providers.base import BaseContentProvider
from p8fs_node.utils.text import clean_text, chunk_text

class PDFContentProvider(BaseContentProvider):
    def get_supported_extensions(self) -> List[str]:
        return ['.pdf']
    
    async def can_process(self, file_path: str) -> bool:
        return file_path.lower().endswith('.pdf')
    
    async def extract_content(self, file_path: str) -> List[ContentChunk]:
        # Use Rust component for PDF parsing
        raw_text = await self.rust_pdf_extractor.extract(file_path)
        
        # Clean and chunk text
        cleaned_text = clean_text(raw_text)
        chunks = chunk_text(cleaned_text, max_size=config.content_max_chunk_size)
        
        content_chunks = []
        for i, chunk in enumerate(chunks):
            metadata = {
                'source': file_path,
                'chunk_index': i,
                'file_type': 'pdf',
                'extracted_at': datetime.utcnow().isoformat()
            }
            content_chunks.append(ContentChunk(chunk, metadata))
        
        return content_chunks
```

### Auto-Registration System
```python
from p8fs_node.providers.registry import ContentProviderRegistry
from p8fs_node.providers.auto_register import auto_register_providers

class ContentProviderRegistry:
    def __init__(self):
        self.providers = {}
    
    def register(self, provider: BaseContentProvider):
        for ext in provider.get_supported_extensions():
            self.providers[ext] = provider
    
    def get_provider(self, file_path: str) -> Optional[BaseContentProvider]:
        _, ext = os.path.splitext(file_path)
        return self.providers.get(ext.lower())

# Auto-register all providers
registry = ContentProviderRegistry()
auto_register_providers(registry)
```

## Embedding Service Integration

### Embedding Generation
```python
from p8fs_node.services.embeddings import EmbeddingService
from typing import List

class ContentProcessor:
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.registry = ContentProviderRegistry()
    
    async def process_file(self, file_path: str) -> List[ContentChunk]:
        # Get appropriate provider
        provider = self.registry.get_provider(file_path)
        if not provider:
            raise ValueError(f"No provider for file type: {file_path}")
        
        # Extract content chunks
        chunks = await provider.extract_content(file_path)
        
        # Generate embeddings in batches
        texts = [chunk.content for chunk in chunks]
        embeddings = await self.embedding_service.embed_batch(texts)
        
        # Assign embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        
        return chunks
```

### Batch Processing
```python
from p8fs_node.services.embeddings import EmbeddingService

class BatchEmbeddingProcessor:
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.batch_size = config.embedding_batch_size
    
    async def process_batch(self, content_chunks: List[ContentChunk]) -> List[ContentChunk]:
        # Process in batches for efficiency
        for i in range(0, len(content_chunks), self.batch_size):
            batch = content_chunks[i:i + self.batch_size]
            texts = [chunk.content for chunk in batch]
            
            embeddings = await self.embedding_service.embed_batch(texts)
            
            for chunk, embedding in zip(batch, embeddings):
                chunk.embedding = embedding
        
        return content_chunks
```

## Rust Integration

The node module includes high-performance Rust components for CPU-intensive operations. See `rust/CLAUDE.md` for Rust-specific development guidelines.

### Python-Rust Interface
```python
import subprocess
import json
from typing import List

class RustEmbeddingService:
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        # Call Rust binary with JSON input
        input_data = json.dumps({'texts': texts})
        
        process = await asyncio.create_subprocess_exec(
            './rust/target/release/p8fs-node',
            '--embed',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate(input_data.encode())
        
        if process.returncode != 0:
            raise RuntimeError(f"Rust embedding failed: {stderr.decode()}")
        
        result = json.loads(stdout.decode())
        return result['embeddings']
```

## Testing Approach

### Test Structure
```
tests/
├── unit/
│   ├── providers/
│   │   ├── test_audio.py
│   │   ├── test_pdf.py
│   │   ├── test_structured.py
│   │   └── test_text.py
│   └── utils/
│       └── test_text.py
├── integration/
│   ├── providers/
│   │   ├── test_audio_integration.py
│   │   ├── test_pdf_integration.py
│   │   └── test_structured_integration.py
│   └── run_all_integration_tests.py
└── sample_data/
    ├── audio/
    │   └── sample.wav
    ├── documents/
    │   └── sample.pdf
    └── text/
        └── sample.txt
```

### Running Tests
```bash
# Unit tests with mocks
pytest tests/unit/ -v

# Integration tests with real files
pytest tests/integration/ -v

# Rust component tests
cd rust && cargo test

# All tests
pytest tests/ -v && cd rust && cargo test
```

### Example Test Patterns

#### Unit Test with File Mocking
```python
from unittest.mock import Mock, patch, AsyncMock
import pytest
from p8fs_node.providers.pdf import PDFContentProvider

@patch('p8fs_node.providers.pdf.extract_pdf_text')
async def test_pdf_provider_extract_content(mock_extract):
    mock_extract.return_value = "Sample PDF content"
    provider = PDFContentProvider()
    
    chunks = await provider.extract_content("test.pdf")
    
    assert len(chunks) > 0
    assert chunks[0].content == "Sample PDF content"
    assert chunks[0].metadata['file_type'] == 'pdf'
```

#### Integration Test with Real Files
```python
import pytest
from p8fs_node.providers.pdf import PDFContentProvider

@pytest.mark.integration
async def test_pdf_integration():
    provider = PDFContentProvider()
    
    # Use real test PDF file
    chunks = await provider.extract_content("tests/sample_data/documents/sample.pdf")
    
    assert len(chunks) > 0
    assert all(chunk.content.strip() for chunk in chunks)
    assert all(chunk.metadata['source'].endswith('sample.pdf') for chunk in chunks)
```

## Specific Provider Implementations

### Audio Processing
```python
from p8fs_node.providers.audio import AudioContentProvider
import whisper

class AudioContentProvider(BaseContentProvider):
    def __init__(self):
        self.model = whisper.load_model("base")
    
    async def extract_content(self, file_path: str) -> List[ContentChunk]:
        # Transcribe audio using Whisper
        result = self.model.transcribe(file_path)
        
        # Create chunks from transcript segments
        chunks = []
        for segment in result['segments']:
            metadata = {
                'source': file_path,
                'start_time': segment['start'],
                'end_time': segment['end'],
                'file_type': 'audio'
            }
            chunks.append(ContentChunk(segment['text'], metadata))
        
        return chunks
```

### Document Processing
```python
from p8fs_node.providers.document import DocumentContentProvider
from docx import Document

class DocumentContentProvider(BaseContentProvider):
    def get_supported_extensions(self) -> List[str]:
        return ['.docx', '.doc']
    
    async def extract_content(self, file_path: str) -> List[ContentChunk]:
        if file_path.endswith('.docx'):
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        else:
            # Handle .doc files with different library
            paragraphs = await self._extract_doc_content(file_path)
        
        chunks = []
        for i, paragraph in enumerate(paragraphs):
            if paragraph.strip():
                metadata = {
                    'source': file_path,
                    'paragraph_index': i,
                    'file_type': 'document'
                }
                chunks.append(ContentChunk(paragraph, metadata))
        
        return chunks
```

## Worker Integration

### Storage Worker Integration
```python
from p8fs_node.workers.storage import StorageWorker
from p8fs.services.nats import NATSClient

class ContentProcessingWorker(StorageWorker):
    def __init__(self):
        super().__init__()
        self.content_processor = ContentProcessor()
    
    async def process_file_upload(self, file_path: str, user_id: str):
        # Process file through content providers
        chunks = await self.content_processor.process_file(file_path)
        
        # Store processed chunks in database
        for chunk in chunks:
            await self.store_content_chunk(chunk, user_id)
        
        # Publish completion event
        await self.nats_client.publish('content.processed', {
            'file_path': file_path,
            'user_id': user_id,
            'chunk_count': len(chunks)
        })
```

## Dependencies

- **whisper-openai**: Audio transcription
- **PyPDF2** / **pdfplumber**: PDF processing
- **python-docx**: Document processing
- **Pillow**: Image processing
- **opencv-python**: Video processing
- **p8fs-cluster**: Configuration and logging
- **p8fs**: Core services integration

## Development Workflow

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Build Rust components:
   ```bash
   cd rust
   cargo build --release
   ```

3. Run tests:
   ```bash
   pytest tests/ -v
   cd rust && cargo test
   ```

4. Process test files:
   ```bash
   python -m p8fs_node.cli process tests/sample_data/documents/sample.pdf
   ```

## Performance Considerations

- Use Rust for CPU-intensive text processing
- Stream large file processing to manage memory
- Batch embedding operations for efficiency
- Cache processed results to avoid recomputation
- Use async I/O for file operations