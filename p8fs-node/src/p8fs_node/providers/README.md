# P8FS Content Providers

This directory contains content providers that process different file types and convert them into searchable content chunks with embeddings. Each provider implements the `ContentProvider` interface to handle specific file formats.

## Content Provider Interface

All content providers must inherit from the abstract `ContentProvider` base class and implement the required methods:

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List

from p8fs_node.models.content import ContentProvider, ContentChunk, ContentMetadata, ContentType

class ContentProvider(ABC):
    @property
    @abstractmethod
    def supported_types(self) -> List[ContentType]:
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
    ) -> List[ContentChunk]:
        """Convert content to markdown chunks."""
        pass

    @abstractmethod
    async def to_metadata(
        self, content_path: str | Path, **options: Any
    ) -> ContentMetadata:
        """Extract metadata from content."""
        pass
```

## Available Providers

### Audio Provider (`audio.py`)
- **Supported Types**: `ContentType.AUDIO`
- **File Extensions**: `.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`, `.wma`
- **Features**:
  - Voice Activity Detection (VAD) with Silero and energy-based fallback
  - Audio transcription using OpenAI Whisper API
  - Smart audio segmentation and chunk merging
  - Comprehensive metadata extraction (duration, sample rate, channels)

### Document Provider (`document.py`)
- **Supported Types**: `ContentType.DOCUMENT`
- **File Extensions**: `.docx`, `.odt`, `.rtf`
- **Features**:
  - DOCX processing with python-docx (fallback to docx2txt)
  - ODT support using odfpy
  - RTF support using striprtf
  - Table extraction and markdown conversion
  - Document metadata extraction (author, dates, structure info)

### PDF Provider (`pdf.py`)
- **Supported Types**: `ContentType.PDF`
- **File Extensions**: `.pdf`
- **Features**:
  - Text extraction using PyMuPDF
  - Page-by-page processing
  - Metadata extraction

### Text Provider (`text.py`)
- **Supported Types**: `ContentType.TEXT`, `ContentType.MARKDOWN`
- **File Extensions**: `.txt`, `.md`, `.rst`, `.log`
- **Features**:
  - Smart encoding detection
  - Markdown structure preservation
  - Configurable chunking strategies

### Structured Data Provider (`structured.py`)
- **Supported Types**: `ContentType.JSON`, `ContentType.YAML`
- **File Extensions**: `.json`, `.yaml`, `.yml`
- **Features**:
  - JSON/YAML parsing and formatting
  - Special handling for "kind" documents
  - Schema validation support

## Creating a New Provider

Here's a step-by-step guide to implementing your own content provider:

### 1. Basic Provider Structure

```python
"""Custom content provider for [FILE_TYPE] files."""

import logging
from pathlib import Path
from typing import Any, List

from p8fs_node.models.content import (
    ContentChunk,
    ContentMetadata,
    ContentProvider,
    ContentType,
)
from p8fs_node.providers.mixins import BaseProviderMixin
from p8fs_node.utils.text import TextChunker, clean_text

logger = logging.getLogger(__name__)

class CustomContentProvider(BaseProviderMixin, ContentProvider):
    """Content provider for custom file types."""

    @property
    def supported_types(self) -> List[ContentType]:
        """Return list of supported content types."""
        return [ContentType.UNKNOWN]  # Replace with your content type

    @property
    def provider_name(self) -> str:
        """Return the name of the provider."""
        return "custom_provider"

    async def to_markdown_chunks(
        self, content_path: str | Path, extended: bool = False, **options: Any
    ) -> List[ContentChunk]:
        """Convert content to markdown chunks."""
        file_path = Path(content_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            # 1. Extract content from your file format
            text_content, metadata = await self._extract_content(file_path, **options)
            
            if not text_content.strip():
                logger.warning(f"No content extracted from {file_path}")
                return self._create_placeholder_chunks(file_path)
            
            # 2. Clean and chunk the text
            cleaned_text = clean_text(text_content)
            chunks = TextChunker.chunk_by_characters(
                cleaned_text, 
                chunk_size=2048, 
                overlap=200
            )
            
            # 3. Create content chunks
            content_chunks = []
            for i, chunk in enumerate(chunks):
                if chunk.strip():
                    chunk_metadata = {
                        **metadata,
                        "chunk_index": i,
                        "chunk_count": len(chunks),
                    }
                    content_chunks.append(
                        ContentChunk(
                            id=f"{file_path.stem}_chunk_{i}",
                            content=chunk,
                            metadata=chunk_metadata,
                        )
                    )
            
            return content_chunks
            
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return self._create_placeholder_chunks(file_path)

    async def to_metadata(self, content_path: str | Path, **options: Any) -> ContentMetadata:
        """Extract metadata from content."""
        file_path = Path(content_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Extract basic file metadata
        from p8fs_node.utils.text import FileUtils
        stats = FileUtils.get_file_stats(file_path)
        
        # Add your custom metadata extraction here
        custom_metadata = await self._extract_custom_metadata(file_path)
        
        return ContentMetadata(
            title=stats["stem"],
            file_path=str(file_path),
            file_size=stats["size"],
            created_date=stats["created"],
            modified_date=stats["modified"],
            content_type="custom",
            extraction_method=self.provider_name,
            properties={
                "file_hash": stats["hash"],
                "original_filename": stats["name"],
                "file_extension": stats["suffix"],
                **custom_metadata,
            },
        )

    async def _extract_content(self, file_path: Path, **options: Any) -> tuple[str, dict]:
        """Extract content from the file format."""
        # Implement your file format parsing here
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        metadata = {
            "source": str(file_path),
            "file_type": file_path.suffix.lower().replace(".", ""),
            "extraction_method": self.provider_name,
        }
        
        return content, metadata

    async def _extract_custom_metadata(self, file_path: Path) -> dict:
        """Extract format-specific metadata."""
        # Add your custom metadata extraction logic
        return {
            "custom_property": "custom_value",
        }

    def _create_placeholder_chunks(self, file_path: Path) -> List[ContentChunk]:
        """Create placeholder chunks when processing fails."""
        placeholder_content = f"""# {file_path.name}

This is a placeholder for custom content.

**File**: {file_path.name}
**Provider**: {self.provider_name}

## Processing Status

The file could not be processed due to an error.

*Note: This is placeholder content.*"""

        chunk = ContentChunk(
            id=f"{file_path.stem}_placeholder_chunk_0",
            content=placeholder_content,
            chunk_type="placeholder",
            position=0,
            metadata={
                "is_placeholder": True,
                "provider": self.provider_name,
                "source": str(file_path),
            }
        )

        return [chunk]
```

### 2. Using Mixins for Common Functionality

The system provides several mixins to reduce code duplication:

#### BaseProviderMixin
Provides common embedding generation functionality:

```python
from p8fs_node.providers.mixins import BaseProviderMixin

class MyProvider(BaseProviderMixin, ContentProvider):
    # Your provider automatically gets:
    # - generate_embeddings() method
    # - Common utilities
    pass
```

#### PlaceholderProviderMixin
Provides standardized placeholder generation:

```python
from p8fs_node.providers.mixins import PlaceholderProviderMixin

class MyProvider(PlaceholderProviderMixin, ContentProvider):
    # Automatically implements to_markdown_chunks() with placeholders
    # Good for providers under development
    pass
```

### 3. Text Processing Utilities

Use the provided text utilities for consistent processing:

```python
from p8fs_node.utils.text import (
    TextChunker,
    clean_text,
    extract_metadata_from_text,
    truncate_text
)

# Smart text chunking with boundary detection
chunks = TextChunker.chunk_by_characters(text, chunk_size=2048, overlap=200)

# Or sentence-based chunking
sentence_chunks = TextChunker.chunk_by_sentences(text, max_sentences=5)

# Text cleaning and normalization
cleaned = clean_text(raw_text)

# Extract text statistics
stats = extract_metadata_from_text(text)
# Returns: {'word_count': 150, 'char_count': 800, 'sentence_count': 12, 'paragraph_count': 3}
```

### 4. File Utilities

Use file utilities for consistent metadata extraction:

```python
from p8fs_node.utils.text import FileUtils

# Get comprehensive file statistics
stats = FileUtils.get_file_stats(file_path)
# Returns: {'size': 1024, 'created': datetime, 'modified': datetime, 'name': 'file.txt', ...}

# Calculate file hash
file_hash = FileUtils.get_file_hash(file_path)

# Detect text encoding
encoding = FileUtils.detect_encoding(file_path)
```

### 5. Error Handling Best Practices

```python
async def to_markdown_chunks(self, content_path: str | Path, **options: Any) -> List[ContentChunk]:
    file_path = Path(content_path)
    
    try:
        # Main processing logic
        content = await self._process_file(file_path)
        return self._create_chunks(content)
        
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise  # Let file errors propagate
        
    except ImportError as e:
        logger.warning(f"Missing dependencies for {file_path}: {e}")
        return self._create_placeholder_chunks(file_path)
        
    except Exception as e:
        logger.error(f"Unexpected error processing {file_path}: {e}")
        return self._create_placeholder_chunks(file_path)
```

### 6. Provider Registration

Add your provider to the registry in `registry.py`:

```python
from p8fs_node.providers.custom import CustomContentProvider

# Register with file extensions
PROVIDER_REGISTRY = {
    # ... existing providers
    '.custom': CustomContentProvider,
    '.myext': CustomContentProvider,
}
```

## Advanced Features

### Configurable Processing Options

Support processing options through the `**options` parameter:

```python
async def to_markdown_chunks(self, content_path: str | Path, extended: bool = False, **options: Any) -> List[ContentChunk]:
    # Extract processing options
    preserve_formatting = options.get('preserve_formatting', False)
    extract_images = options.get('extract_images', True)
    chunk_size = options.get('chunk_size', 2048)
    
    # Use options in processing
    if preserve_formatting:
        # Enhanced processing
        pass
```

### Async Processing

For I/O intensive operations, use async patterns:

```python
import aiofiles
import asyncio

async def _extract_content(self, file_path: Path) -> str:
    # Async file reading
    async with aiofiles.open(file_path, 'r') as f:
        content = await f.read()
    
    # Async external API calls
    async with httpx.AsyncClient() as client:
        response = await client.post('https://api.example.com/process', json={'content': content})
    
    return response.json()['result']
```

### Batch Processing

For providers that can efficiently process multiple files:

```python
async def process_batch(self, file_paths: List[Path]) -> List[List[ContentChunk]]:
    """Process multiple files efficiently."""
    tasks = [self.to_markdown_chunks(path) for path in file_paths]
    return await asyncio.gather(*tasks)
```

## Testing Your Provider

Create unit tests for your provider:

```python
import pytest
from pathlib import Path
from p8fs_node.providers.custom import CustomContentProvider

@pytest.mark.asyncio
async def test_custom_provider():
    provider = CustomContentProvider()
    
    # Test with sample file
    chunks = await provider.to_markdown_chunks("test_file.custom")
    
    assert len(chunks) > 0
    assert chunks[0].content
    assert chunks[0].metadata
    
    # Test metadata extraction
    metadata = await provider.to_metadata("test_file.custom")
    assert metadata.title
    assert metadata.file_size > 0
```

## Performance Considerations

- Use streaming for large files to avoid memory issues
- Implement chunking strategies appropriate for your content type
- Cache expensive operations when possible
- Use async I/O for network requests or large file operations
- Consider using the Rust components for CPU-intensive processing

## Integration with P8FS

Your provider will automatically:
- Generate embeddings for semantic search
- Store chunks in the P8FS memory vault
- Support filtering and retrieval operations
- Integrate with the scaling infrastructure

The provider system is designed to be extensible and maintainable, allowing you to focus on the specific logic for your file format while leveraging the common infrastructure for chunking, embeddings, and storage.