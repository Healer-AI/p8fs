# P8FS Node Module

Core processing unit handling embeddings, inference, and content processors for the P8FS smart content management system.
The RUST version exposes a HTTP endpoint to get embeddings, and perform other indexing functionality e.g. adding graph nodes as well as other ML model interence features.
By adding these in the RUST module we can keep python code lighter and we can also allow the Postgres database to fetch these services.

## Overview

The p8fs-node module is the computational workhorse of P8FS, designed to run anywhere and handle all content processing tasks. It manages document parsing, audio transcription, image analysis, embedding generation, and other ML inference tasks. This module can be deployed as standalone workers scaled by KEDA based on workload.

## CLI Usage

The p8fs-node module provides a CLI for processing individual files with content providers:

```bash
# Process a file and show summary
uv run p8fs-node process path/to/file.pdf

# Process without saving to storage
uv run p8fs-node process path/to/file.docx --no-save-to-storage

# Process with JSON output
uv run p8fs-node process path/to/file.wav --output-format json

# Skip embedding generation for faster processing
uv run p8fs-node process path/to/file.md --no-generate-embeddings

# List all available content providers
uv run p8fs-node list-providers

# Test which provider handles a file
uv run p8fs-node test-file path/to/file.xlsx
```

### Command Options

- `--output-format` - Output format (json, yaml) - default: json
- `--generate-embeddings` - Generate embeddings (default: True)
- `--extended` - Use extended processing (default: False)  
- `--save-to-storage` - Save chunks to storage (default: True)

**Note**: For production use, prefer the **p8fs CLI** which provides full integration with the storage worker and database persistence.

## Architecture

### Components to Port

#### 1. Content Processors (`src/p8fs/workers/processors/`)
- **PDF Processor**: PDF parsing, text extraction, layout analysis
- **Audio Processor**: Transcription with Whisper, speaker diarization
- **Image Processor**: OCR, object detection, scene analysis
- **Video Processor**: Frame extraction, temporal analysis
- **Document Processor**: DOCX, TXT, Markdown parsing
- **Web Processor**: HTML parsing, content extraction

#### 2. Embedding Services (`src/p8fs/services/embeddings/`)
- **Text Embeddings**: Multiple model support (sentence-transformers, FastEmbed)
- **Image Embeddings**: Visual feature extraction
- **Audio Embeddings**: Acoustic feature extraction
- **Multimodal Embeddings**: Cross-modal representations
- **Embedding Cache**: Efficient caching and retrieval

#### 3. Worker Infrastructure (`src/p8fs/workers/`)
- **Storage Event Worker**: Process file upload events
- **Tiered Storage Router**: Route by file size/type
- **Dreaming Worker**: Background AI processing
- **User Insight Worker**: Behavioral analysis
- **MinIO Event Worker**: S3 event processing
- **Scheduled Workers**: Cron-based tasks

#### 4. ML Inference (`src/p8fs/services/ml/`)
- **Transcription Service**: Faster Whisper integration
- **OCR Service**: Text extraction from images
- **Classification Service**: Content categorization
- **Summarization Service**: Document summarization
- **Entity Extraction**: Named entity recognition

#### 5. Event Processing (`src/p8fs/workers/events/`)
- **NATS Integration**: JetStream consumers
- **Event Router**: Smart event distribution
- **Retry Logic**: Exponential backoff
- **Dead Letter Queue**: Failed event handling
- **Event Monitoring**: Processing metrics

#### 6. Media Processing (`src/p8fs/services/media/`)
- **Image Processing**: Resize, format conversion
- **Audio Processing**: Format conversion, chunking
- **Video Processing**: Thumbnail generation
- **Metadata Extraction**: EXIF, ID3, etc.

## Refactoring Plan

### Phase 1: Worker Foundation
1. Create base worker class with lifecycle management
2. Implement NATS JetStream integration
3. Set up event routing and retry mechanisms
4. Build worker scaling configuration

### Phase 2: Content Processors
1. Implement modular processor interface
2. Port PDF processing with layout preservation
3. Add audio transcription with Whisper
4. Create image analysis pipeline
5. Build document parsing framework

### Phase 3: Embedding Pipeline
1. Design embedding service abstraction
2. Implement text embedding models
3. Add multimodal embedding support
4. Create embedding cache layer

### Phase 4: ML Services
1. Set up model management system
2. Implement inference pipeline
3. Add model versioning support
4. Create performance monitoring

### Phase 5: Event System
1. Build robust event processing
2. Implement dead letter queues
3. Add event replay capability
4. Create monitoring dashboard

## Testing Strategy

### Unit Tests
- Processor output validation
- Embedding consistency checks
- Event handling logic
- Model inference accuracy

### Integration Tests
- End-to-end processing flows
- NATS event consumption
- Storage integration
- Performance benchmarks

### Load Tests
- Concurrent file processing
- Event queue capacity
- Memory usage under load
- GPU utilization

## Dependencies

### ML Libraries
- sentence-transformers: Text embeddings
- faster-whisper: Audio transcription
- PyTorch: Deep learning framework
- FAISS: Vector operations
- OpenCV: Image processing

### Processing Libraries
- **Kreuzberg**: PDF parsing with PDFium and Tesseract OCR (default)
- PyPDF2/pymupdf: PDF parsing (fallback)
- python-docx: Word documents
- Pillow: Image manipulation
- ffmpeg-python: Video processing
- BeautifulSoup: HTML parsing

**Note**: Kreuzberg requires Tesseract for OCR functionality. Install via:
- macOS: `brew install tesseract`
- Ubuntu/Debian: `apt-get install tesseract-ocr`
- Docker: Included in the p8fs-eco image

### Infrastructure
- NATS: Event streaming
- KEDA: Autoscaling
- TiKV: Job queuing
- S3/MinIO: File storage

### External Services
- p8fs: Storage and indexing
- p8fs-auth: Access validation

## Configuration

Environment variables for node operations:
- `P8FS_NODE_ID`: Unique node identifier
- `P8FS_NATS_URL`: NATS connection string
- `P8FS_WORKER_CONCURRENCY`: Parallel processing limit
- `P8FS_MODEL_CACHE_PATH`: ML model storage
- `P8FS_EMBEDDING_BATCH_SIZE`: Batch processing size
- `P8FS_GPU_ENABLED`: Enable GPU acceleration
- `P8FS_MEMORY_LIMIT`: Worker memory constraint
- `P8FS_PROCESSING_TIMEOUT`: Max processing time

## Processing Pipeline

### Content Flow
1. **Event Reception**: File upload triggers event
2. **Content Analysis**: Determine file type and size
3. **Processor Selection**: Route to appropriate processor
4. **Feature Extraction**: Extract text, metadata, features
5. **Embedding Generation**: Create vector representations
6. **Index Update**: Send to p8fs for storage

### Processor Architecture
```python
class ContentProcessor(ABC):
    async def process(file_path: Path) -> ProcessResult
    async def extract_text() -> str
    async def extract_metadata() -> Dict
    async def generate_preview() -> bytes
```

### Worker Lifecycle
1. **Initialization**: Load models and configs
2. **Event Subscription**: Connect to NATS streams
3. **Processing Loop**: Consume and process events
4. **Health Reporting**: Regular health checks
5. **Graceful Shutdown**: Complete in-flight work

## Performance Optimization

### Resource Management
- Model loading on-demand
- Shared model instances
- Memory pooling
- GPU scheduling

### Batching Strategy
- Aggregate similar tasks
- Optimize GPU utilization
- Reduce model loading overhead

### Caching Layers
- Processed content cache
- Embedding cache
- Model prediction cache

## Scaling Configuration

### KEDA Triggers
- NATS JetStream lag
- CPU/Memory utilization
- Custom metrics from processors
- Queue depth thresholds

### Resource Limits
- CPU: 2-4 cores per worker
- Memory: 4-8GB per worker
- GPU: Optional, shared pool
- Storage: 10GB local cache

## Monitoring

### Metrics
- Processing rate (files/second)
- Error rate by file type
- Processing latency percentiles
- Model inference time
- Queue depth and lag

### Logging
- Structured JSON logs
- Correlation IDs
- Processing stages
- Error details with context