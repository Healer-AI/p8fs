# P8FS Node - Rust Implementation

A lightweight Rust implementation of the p8fs-node content processing system with embedding generation and file processing capabilities.

## Features

- **Embedding Service**: Text embeddings using EmbedAnything (sentence-transformers/all-MiniLM-L6-v2)
- **Content Processors**: PDF, Audio (WAV), Document (DOCX), JSON, and Markdown
- **HTTP API**: RESTful endpoints for embeddings and content processing
- **Provider Registry**: Extensible system for adding new content types

## API Endpoints

### Generate Embeddings (OpenAI Compatible)

```bash
curl -X POST http://127.0.0.1:3000/api/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": ["Hello world", "This is a test"],
    "model": "all-MiniLM-L6-v2",
    "encoding_format": "float"
  }'
```

Response format:
```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding", 
      "embedding": [0.1, 0.2, ...],
      "index": 0
    }
  ],
  "model": "all-MiniLM-L6-v2",
  "usage": {
    "prompt_tokens": 4,
    "total_tokens": 4
  }
}
```

### Process Content

```bash
# Auto-detect content type by file extension
curl -X POST http://127.0.0.1:3000/api/v1/content/process \
  -F "file=@document.pdf"

# Specify content type explicitly  
curl -X POST http://127.0.0.1:3000/api/v1/content/process/pdf \
  -F "file=@document.pdf"
```

Response format:
```json
{
  "success": true,
  "chunks": [
    {
      "id": "chunk_id", 
      "content": "extracted content",
      "metadata": {
        "chunk_index": 0,
        "source": "pdf"
      }
    }
  ],
  "metadata": {
    "content_type": "PDF",
    "file_name": "document.pdf",
    "file_size": 12345,
    "created_at": null,
    "modified_at": null,
    "author": null,
    "title": null,
    "language": null,
    "additional": {}
  },
  "error": null
}
```

## Running the Server

### Local Development

```bash
cd p8fs-node
cargo run
```

The server will start on `http://localhost:3000`

### Environment Variables

- `EMBEDDING_MODEL`: Model to use (default: `sentence-transformers/all-MiniLM-L6-v2`)
- `EMBEDDING_DIMENSIONS`: Expected embedding dimensions (default: `384`)
- `RUST_LOG`: Log level (default: `info`)

### Docker Deployment

#### Quick Build Command

```bash
# Build the Docker image (may take 10-15 minutes on first build)
docker build --no-cache -t p8fs-node .

# Run the container
docker run -d --name p8fs-node -p 3000:3000 -e EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2 p8fs-node

# Check container status
docker logs p8fs-node
```

**Note:** Use `--no-cache` flag to ensure the latest code is built into the image. The initial build downloads and compiles many dependencies, so allow extra time.

#### Testing Docker Container

```bash
# Test server health
curl http://127.0.0.1:3000/
# Should return: "p8fs-node server"

# Test content processing
echo "# Test Document" > test.md
curl -X POST -F "file=@test.md" http://127.0.0.1:3000/api/v1/content/process

# Test embeddings (requires model download on first use)
curl -X POST -H "Content-Type: application/json" \
  -d '{"input":["Hello world"]}' \
  http://127.0.0.1:3000/api/v1/embeddings
```

#### Alternative Options

```bash
# Quick start using convenience script
./build-and-run.sh

# Build with custom tag
docker build -t p8fs-node:latest .

# Production deployment with docker-compose
docker-compose -f docker-compose.prod.yml up -d

# With nginx proxy (optional)
docker-compose -f docker-compose.prod.yml --profile proxy up -d

# Development with auto-reload
docker-compose up

# Run integration tests
docker-compose --profile test up
```

## Example Usage

```rust
use p8fs_node::providers::registry;
use std::path::Path;

// Get provider by file extension
let (content_type, provider) = registry::get_provider_by_extension("pdf").unwrap();

// Process content
let result = provider.process_content(Path::new("document.pdf")).await?;

// Get embeddings for the chunks
let embeddings = provider.to_embeddings(&result.chunks).await?;
```

## Content Processors

Each processor extracts content, converts it to **markdown format**, and preserves original file metadata:

- **PDF**: Text extraction formatted as markdown with section headers and page references
- **Audio (WAV)**: Segment metadata formatted as structured markdown with technical details
- **Document (DOCX)**: Text and structure extraction formatted as markdown with proper paragraphs and tables
- **JSON**: Hierarchical parsing with markdown headers based on "kind" field and structured formatting
- **Markdown**: Native markdown content with section-based chunking preserving original structure

**Key Features:**
- **Always returns markdown chunks**: All content is formatted as valid markdown
- **Preserves original metadata**: File size, name, timestamps from source files
- **Structured output**: Consistent ContentChunk format with metadata per chunk
- **Extensible**: Easy to add new content processors following the same pattern

## Testing

### Unit Tests

```bash
# Run all unit tests
cargo test --lib

# Run integration tests
cargo test --test '*'

# Run all tests including ignored ones (requires models)
cargo test -- --ignored

# Use the test script
./run_tests.sh
```

### API Testing with curl

After starting the server (`cargo run`), test the endpoints:

#### Test Content Processing

**Process Markdown File:**
```bash
# Create a test markdown file
cat > test.md << 'EOF'
# Test Document

This is a test markdown document.

## Section 1
Some content here.

## Section 2
More content with `code` and details.
EOF

# Process the file
curl -X POST -F "file=@test.md" http://127.0.0.1:3000/api/v1/content/process
```

**Process JSON File:**
```bash
# Create a test JSON file
cat > test.json << 'EOF'
{
  "kind": "example",
  "title": "Test Document", 
  "data": {
    "key": "value",
    "items": ["item1", "item2"]
  }
}
EOF

# Process the file
curl -X POST -F "file=@test.json" http://127.0.0.1:3000/api/v1/content/process
```

**Expected Response Format:**
```json
{
  "success": true,
  "chunks": [
    {
      "id": "md_chunk_0",
      "content": "# Test Document\n\nTest Document\n\nThis is a test markdown document.",
      "metadata": {
        "chunk_index": 0,
        "source": "markdown",
        "section_title": "Test Document",
        "heading_level": 1
      }
    },
    {
      "id": "pdf_chunk_0", 
      "content": "# PDF Document Content\n\nExtracted text from PDF formatted as markdown...",
      "metadata": {
        "chunk_index": 0,
        "source": "pdf",
        "page_reference": "Page ~1"
      }
    }
  ],
  "metadata": {
    "content_type": "MARKDOWN",
    "file_name": "test.md", 
    "file_size": 408,
    "created_at": null,
    "modified_at": null,
    "author": null,
    "title": "Test Document",
    "language": null,
    "additional": {}
  },
  "error": null
}
```

#### Test Embeddings API

**Generate Text Embeddings:**
```bash
curl -X POST http://127.0.0.1:3000/api/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": ["Hello world", "This is a test sentence"]
  }'
```

**Note:** The embedding model will be downloaded on first use, which may take time.

#### Test with Different File Types

**Process PDF (if you have a PDF file):**
```bash
curl -X POST -F "file=@document.pdf" http://127.0.0.1:3000/api/v1/content/process
```

**Process DOCX (if you have a DOCX file):**
```bash
curl -X POST -F "file=@document.docx" http://127.0.0.1:3000/api/v1/content/process
```

**Specify Content Type Explicitly:**
```bash
curl -X POST -F "file=@document.pdf" http://127.0.0.1:3000/api/v1/content/process/pdf
```

#### Automated Testing Scripts

**Test embedding API (bash):**
```bash
./test_embeddings.sh
```

**Test embedding API (python):**
```bash
python3 test_embeddings.py

# Or install requests first
pip install requests && python3 test_embeddings.py
```

### Test Structure

- **Unit Tests**: Located alongside source code (`src/*/tests.rs`)
  - Models: Serialization, data structure validation
  - Services: Embedding service functionality (mocked)
  - Providers: Content processing logic with test files
  - Registry: Provider lookup and registration

- **Integration Tests**: Located in `tests/` directory
  - End-to-end content processing workflows
  - API endpoint testing with mock responses
  - Concurrent processing and stress tests

## Troubleshooting

### Common Issues

**Server responds with "p8fs-node server":**
- Make sure you're using the correct API path: `/api/v1/content/process` (not `/api/content/process`)

**Embeddings API returns empty response:**
- The embedding model needs to download on first use (~50MB)
- Check server logs for download progress
- Ensure sufficient disk space and internet connectivity

**File processing fails:**
- Verify the file extension is supported (pdf, md, json, docx, wav)
- Check file permissions and that the file exists
- Review server logs for detailed error messages

**Compilation errors after updating dependencies:**
- Run `cargo clean` and `cargo build` to rebuild from scratch
- Check that all feature flags are properly configured in Cargo.toml

### Supported File Types

| Extension | Content Type | Provider |
|-----------|--------------|----------|
| `.md` | MARKDOWN | MarkdownProvider |
| `.json` | STRUCTUREDDATA | JsonProvider |
| `.pdf` | PDF | PdfProvider |
| `.docx` | DOCUMENT | DocumentProvider |
| `.wav` | AUDIO | AudioProvider |

### Logs and Debugging

Enable detailed logging:
```bash
RUST_LOG=debug cargo run
```

Check server health:
```bash
curl http://127.0.0.1:3000/health
# Should return "p8fs-node server" (fallback route)
```

## Future Development (TODO)

### Database Integration

**Planned: Repository and Database Provider Support**

Add database persistence for processed content chunks and metadata using TiDB (MySQL) and PostgreSQL providers:

#### New Components to Add:

1. **Repository Layer:**
   - `ContentRepository` trait for database operations
   - `TiDBRepository` implementation (MySQL-compatible)
   - `PostgreSQLRepository` implementation
   - Connection pooling and transaction management

2. **Enhanced Content Providers:**
   - Each provider will support saving chunks to database
   - Automatic embedding computation and storage
   - File metadata and resource tracking
   - Duplicate detection and upsert operations

3. **API Enhancements:**
   - Add `--save` parameter to content processing endpoints:
     ```bash
     curl -X POST -F "file=@document.pdf" \
          -F "save=true" \
          http://127.0.0.1:3000/api/v1/content/process
     ```
   - Return processing results with database IDs when saved
   - Batch processing endpoints for multiple files

#### Required Dependencies:

```toml
[dependencies]
# Database connectivity
sqlx = { version = "0.7", features = ["runtime-tokio-rustls", "mysql", "postgres", "chrono", "uuid"] }
sea-orm = { version = "0.12", features = ["sqlx-mysql", "sqlx-postgres", "runtime-tokio-rustls"] }

# Connection pooling
bb8 = "0.8"
bb8-postgres = "0.8"

# Migrations
sea-orm-migration = "0.12"

# UUID generation for chunk IDs
uuid = { version = "1.0", features = ["v4"] }

# Enhanced date/time handling
chrono = { version = "0.4", features = ["serde"] }
```

#### Implementation Plan:

1. **Study Python Repository Implementation:**
   - Reference `p8fs` Python repository patterns
   - Adapt upsert commands for Rust/SQL implementation
   - Maintain compatibility with existing database schema

2. **Database Schema (from Python implementation):**
   ```sql
   -- Content files tracking
   CREATE TABLE content_files (
       id UUID PRIMARY KEY,
       file_name VARCHAR(255),
       file_path TEXT,
       content_type VARCHAR(50),
       file_size BIGINT,
       file_hash VARCHAR(64),
       created_at TIMESTAMP,
       updated_at TIMESTAMP
   );

   -- Content chunks with embeddings
   CREATE TABLE content_chunks (
       id UUID PRIMARY KEY,
       file_id UUID REFERENCES content_files(id),
       chunk_index INTEGER,
       content TEXT,
       embedding VECTOR(384), -- or JSON for compatibility
       metadata JSONB,
       created_at TIMESTAMP
   );
   ```

3. **Modified Upsert Logic:**
   - Compute embeddings directly in Rust (not delegated to Python)
   - Batch insert chunks for better performance
   - Handle embedding vector storage (pgvector for PostgreSQL)
   - Implement conflict resolution for duplicate files

4. **Service Integration:**
   - Integrate with existing `EmbeddingService`
   - Add repository injection to content providers
   - Maintain backward compatibility (processing without saving)

#### Usage Examples (Planned):

```bash
# Process and save to database
curl -X POST -F "file=@document.pdf" -F "save=true" \
     http://127.0.0.1:3000/api/v1/content/process

# Process multiple files with batch save
curl -X POST -F "files=@doc1.pdf" -F "files=@doc2.md" -F "save=true" \
     http://127.0.0.1:3000/api/v1/content/process/batch

# Query saved chunks by file ID
curl http://127.0.0.1:3000/api/v1/content/files/{file_id}/chunks

# Search similar chunks using embeddings
curl -X POST -H "Content-Type: application/json" \
     -d '{"query": "search text", "limit": 10}' \
     http://127.0.0.1:3000/api/v1/content/search
```

This integration will enable the Rust node to function as both a processing service and a persistent content store, similar to the Python core but with direct embedding computation capabilities.

---

## Architecture

The system follows a trait-based design:

- `ContentProvider`: Core trait for all processors
- `ContentChunk`: Standardized chunk format with metadata
- `ContentProcessingResult`: Unified result type
- `EmbeddingService`: Global singleton for embedding generation
- Registry pattern for provider management