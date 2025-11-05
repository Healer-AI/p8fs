# P8FS Node - Rust Components

## Overview

The Rust components of P8FS Node provide high-performance content processing, embedding generation, and text manipulation. These components handle CPU-intensive operations that require maximum efficiency and memory safety.

## Architecture

### Core Components

- **Content Processing API**: RESTful endpoints for content transformation
- **Embedding Service**: High-performance vector generation
- **Content Providers**: Rust implementations of document processors
- **Text Processing Utilities**: Fast text cleaning and chunking

### Key Features

- Memory-safe content processing
- High-performance vector operations
- Concurrent processing with Tokio
- JSON API for Python integration
- Zero-copy text processing where possible

## Development Standards

### Code Quality

- Write minimal, efficient Rust code with clear intent
- Leverage Rust's type system for correctness
- Use zero-copy operations where possible
- Prioritize memory safety and performance
- Keep implementations lean and purposeful

### Rust Best Practices

- Use `Result<T, E>` for error handling
- Implement `Clone`, `Debug`, `Serialize` where appropriate
- Use `async`/`await` for I/O operations
- Prefer `Vec<T>` over arrays for dynamic data
- Use `String` for owned strings, `&str` for borrowed strings

### Testing Requirements

#### Unit Tests
- Test individual functions with `#[test]`
- Use `#[tokio::test]` for async tests
- Test error conditions and edge cases
- Validate JSON serialization/deserialization

#### Integration Tests
- Test complete API endpoints
- Use real file samples for processing
- Test Python-Rust interface
- Validate performance characteristics

## Project Structure

```
rust/
├── Cargo.toml                 # Project configuration
├── p8fs-node/
│   ├── Cargo.toml            # Binary crate configuration
│   └── src/
│       ├── main.rs           # Binary entry point
│       ├── lib.rs            # Library entry point
│       ├── api/              # REST API endpoints
│       │   ├── mod.rs
│       │   ├── content.rs    # Content processing endpoints
│       │   └── embeddings.rs # Embedding generation endpoints
│       ├── models/           # Data structures
│       │   └── mod.rs
│       ├── providers/        # Content processors
│       │   ├── mod.rs
│       │   ├── pdf.rs        # PDF processing
│       │   ├── audio.rs      # Audio transcription
│       │   └── registry.rs   # Provider registry
│       └── services/         # Core services
│           ├── mod.rs
│           └── embeddings.rs # Embedding service
└── tests/                    # Integration tests
    ├── api_tests.rs
    └── integration_tests.rs
```

## Configuration

Configuration follows Rust patterns with environment variables and structured config:

```rust
use serde::{Deserialize, Serialize};
use std::env;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Config {
    pub server_host: String,
    pub server_port: u16,
    pub embedding_model: String,
    pub max_chunk_size: usize,
    pub batch_size: usize,
}

impl Config {
    pub fn from_env() -> Result<Self, Box<dyn std::error::Error>> {
        Ok(Config {
            server_host: env::var("P8FS_RUST_HOST").unwrap_or_else(|_| "127.0.0.1".to_string()),
            server_port: env::var("P8FS_RUST_PORT")
                .unwrap_or_else(|_| "8080".to_string())
                .parse()?,
            embedding_model: env::var("P8FS_EMBEDDING_MODEL")
                .unwrap_or_else(|_| "text-embedding-3-small".to_string()),
            max_chunk_size: env::var("P8FS_MAX_CHUNK_SIZE")
                .unwrap_or_else(|_| "1000".to_string())
                .parse()?,
            batch_size: env::var("P8FS_BATCH_SIZE")
                .unwrap_or_else(|_| "32".to_string())
                .parse()?,
        })
    }
}
```

## API Design

### Content Processing API
```rust
use axum::{
    extract::{Multipart, Query},
    response::Json,
    Router,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Deserialize)]
pub struct ProcessRequest {
    pub file_type: String,
    pub chunk_size: Option<usize>,
}

#[derive(Debug, Serialize)]
pub struct ProcessResponse {
    pub chunks: Vec<ContentChunk>,
    pub metadata: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContentChunk {
    pub content: String,
    pub metadata: HashMap<String, String>,
    pub embedding: Option<Vec<f32>>,
}

pub async fn process_content(
    Query(params): Query<ProcessRequest>,
    mut multipart: Multipart,
) -> Result<Json<ProcessResponse>, Box<dyn std::error::Error>> {
    while let Some(field) = multipart.next_field().await? {
        let name = field.name().unwrap_or("unknown");
        let data = field.bytes().await?;
        
        let chunks = match params.file_type.as_str() {
            "pdf" => process_pdf(&data, params.chunk_size.unwrap_or(1000))?,
            "text" => process_text(&data, params.chunk_size.unwrap_or(1000))?,
            _ => return Err("Unsupported file type".into()),
        };
        
        return Ok(Json(ProcessResponse {
            chunks,
            metadata: HashMap::from([("processed_at".to_string(), 
                                   chrono::Utc::now().to_rfc3339())]),
        }));
    }
    
    Err("No file provided".into())
}
```

### Embedding Service
```rust
use reqwest::Client;
use serde_json::json;
use tokio::sync::Semaphore;
use std::sync::Arc;

pub struct EmbeddingService {
    client: Client,
    api_key: String,
    model: String,
    semaphore: Arc<Semaphore>,
}

impl EmbeddingService {
    pub fn new(api_key: String, model: String, max_concurrent: usize) -> Self {
        Self {
            client: Client::new(),
            api_key,
            model,
            semaphore: Arc::new(Semaphore::new(max_concurrent)),
        }
    }
    
    pub async fn embed_batch(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, Box<dyn std::error::Error>> {
        let _permit = self.semaphore.acquire().await?;
        
        let response = self.client
            .post("https://api.openai.com/v1/embeddings")
            .header("Authorization", format!("Bearer {}", self.api_key))
            .json(&json!({
                "model": self.model,
                "input": texts
            }))
            .send()
            .await?;
            
        let result: serde_json::Value = response.json().await?;
        
        let embeddings: Vec<Vec<f32>> = result["data"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| {
                item["embedding"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_f64().unwrap() as f32)
                    .collect()
            })
            .collect();
            
        Ok(embeddings)
    }
}
```

## Content Providers

### PDF Processing
```rust
use pdf_extract;
use regex::Regex;

pub fn process_pdf(data: &[u8], chunk_size: usize) -> Result<Vec<ContentChunk>, Box<dyn std::error::Error>> {
    // Extract text from PDF bytes
    let text = pdf_extract::extract_text_from_mem(data)?;
    
    // Clean and chunk the text
    let cleaned = clean_text(&text);
    let chunks = chunk_text(&cleaned, chunk_size);
    
    let mut content_chunks = Vec::new();
    for (index, chunk) in chunks.into_iter().enumerate() {
        let mut metadata = HashMap::new();
        metadata.insert("chunk_index".to_string(), index.to_string());
        metadata.insert("file_type".to_string(), "pdf".to_string());
        metadata.insert("processed_at".to_string(), chrono::Utc::now().to_rfc3339());
        
        content_chunks.push(ContentChunk {
            content: chunk,
            metadata,
            embedding: None,
        });
    }
    
    Ok(content_chunks)
}

fn clean_text(text: &str) -> String {
    // Remove extra whitespace and normalize
    let re = Regex::new(r"\s+").unwrap();
    re.replace_all(text.trim(), " ").to_string()
}

fn chunk_text(text: &str, max_size: usize) -> Vec<String> {
    let mut chunks = Vec::new();
    let sentences: Vec<&str> = text.split('.').collect();
    
    let mut current_chunk = String::new();
    
    for sentence in sentences {
        if current_chunk.len() + sentence.len() > max_size && !current_chunk.is_empty() {
            chunks.push(current_chunk.trim().to_string());
            current_chunk = String::new();
        }
        
        current_chunk.push_str(sentence);
        current_chunk.push('.');
    }
    
    if !current_chunk.is_empty() {
        chunks.push(current_chunk.trim().to_string());
    }
    
    chunks
}
```

### Audio Processing
```rust
use whisper_rs::{WhisperContext, WhisperContextParameters, FullParams, SamplingStrategy};
use hound;

pub async fn process_audio(audio_data: &[u8]) -> Result<Vec<ContentChunk>, Box<dyn std::error::Error>> {
    // Load Whisper model
    let ctx = WhisperContext::new_with_params(
        "models/ggml-base.bin",
        WhisperContextParameters::default()
    )?;
    
    // Decode audio data
    let audio_samples = decode_audio(audio_data)?;
    
    // Set up transcription parameters
    let mut params = FullParams::new(SamplingStrategy::default());
    params.set_n_threads(4);
    params.set_translate(false);
    params.set_language(Some("en"));
    
    // Transcribe audio
    let mut state = ctx.create_state()?;
    state.full(params, &audio_samples)?;
    
    let num_segments = state.full_n_segments()?;
    let mut chunks = Vec::new();
    
    for i in 0..num_segments {
        let start_time = state.full_get_segment_t0(i)?;
        let end_time = state.full_get_segment_t1(i)?;
        let text = state.full_get_segment_text(i)?;
        
        if !text.trim().is_empty() {
            let mut metadata = HashMap::new();
            metadata.insert("start_time".to_string(), (start_time as f32 / 100.0).to_string());
            metadata.insert("end_time".to_string(), (end_time as f32 / 100.0).to_string());
            metadata.insert("file_type".to_string(), "audio".to_string());
            
            chunks.push(ContentChunk {
                content: text.trim().to_string(),
                metadata,
                embedding: None,
            });
        }
    }
    
    Ok(chunks)
}

fn decode_audio(data: &[u8]) -> Result<Vec<f32>, Box<dyn std::error::Error>> {
    let cursor = std::io::Cursor::new(data);
    let reader = hound::WavReader::new(cursor)?;
    
    let samples: Result<Vec<f32>, _> = reader
        .into_samples()
        .map(|s| s.map(|sample: i16| sample as f32 / 32768.0))
        .collect();
        
    Ok(samples?)
}
```

## Testing Approach

### Unit Tests
```rust
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_text_chunking() {
        let text = "First sentence. Second sentence. Third sentence.";
        let chunks = chunk_text(text, 25);
        
        assert_eq!(chunks.len(), 2);
        assert!(chunks[0].contains("First sentence"));
        assert!(chunks[1].contains("Third sentence"));
    }
    
    #[tokio::test]
    async fn test_embedding_service() {
        let service = EmbeddingService::new(
            "test-key".to_string(),
            "text-embedding-3-small".to_string(),
            1
        );
        
        // Mock the HTTP client for testing
        // In real tests, use a test server or mock framework
    }
}
```

### Integration Tests
```rust
// tests/integration_tests.rs
use p8fs_node::{api, Config};
use axum::body::Body;
use axum::http::{Method, Request};
use tower::ServiceExt;

#[tokio::test]
async fn test_content_processing_api() {
    let config = Config::from_env().unwrap();
    let app = api::create_router(config);
    
    // Test PDF processing endpoint
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/process?file_type=pdf")
                .header("content-type", "multipart/form-data")
                .body(Body::empty())
                .unwrap()
        )
        .await
        .unwrap();
    
    assert_eq!(response.status(), 200);
}
```

## Building and Running

### Development Build
```bash
# Debug build
cargo build

# Run tests
cargo test

# Run with logging
RUST_LOG=debug cargo run
```

### Production Build
```bash
# Optimized release build
cargo build --release

# Run production binary
./target/release/p8fs-node
```

### Docker Build
```dockerfile
FROM rust:1.70 as builder

WORKDIR /app
COPY . .
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/target/release/p8fs-node /usr/local/bin/p8fs-node

EXPOSE 8080
CMD ["p8fs-node"]
```

## Dependencies

Key Rust dependencies in `Cargo.toml`:

```toml
[dependencies]
tokio = { version = "1.0", features = ["full"] }
axum = "0.7"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
reqwest = { version = "0.11", features = ["json"] }
pdf-extract = "0.6"
whisper-rs = "0.10"
hound = "3.4"
regex = "1.7"
chrono = { version = "0.4", features = ["serde"] }
tracing = "0.1"
tracing-subscriber = "0.3"
anyhow = "1.0"
```

## Performance Optimizations

### Memory Management
- Use `Box<[T]>` for large arrays
- Prefer `&str` over `String` for read-only data
- Use `Vec::with_capacity()` when size is known
- Implement `Drop` for custom cleanup

### Concurrency
```rust
use tokio::sync::Semaphore;
use std::sync::Arc;

async fn process_files_concurrently(files: Vec<String>) -> Result<Vec<ProcessResult>, Box<dyn std::error::Error>> {
    let semaphore = Arc::new(Semaphore::new(10)); // Limit concurrent processing
    let mut handles = Vec::new();
    
    for file in files {
        let permit = semaphore.clone();
        let handle = tokio::spawn(async move {
            let _permit = permit.acquire().await.unwrap();
            process_single_file(file).await
        });
        handles.push(handle);
    }
    
    let mut results = Vec::new();
    for handle in handles {
        results.push(handle.await??);
    }
    
    Ok(results)
}
```

## Error Handling

Use Rust's `Result` type consistently:

```rust
use anyhow::{Context, Result};

pub async fn process_content(data: &[u8], file_type: &str) -> Result<Vec<ContentChunk>> {
    match file_type {
        "pdf" => process_pdf(data).context("Failed to process PDF"),
        "audio" => process_audio(data).await.context("Failed to process audio"),
        "text" => process_text(data).context("Failed to process text"),
        _ => Err(anyhow::anyhow!("Unsupported file type: {}", file_type)),
    }
}
```

## Python Integration

The Rust components expose a JSON API for Python integration:

```rust
// Binary entry point for Python subprocess calls
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    
    match args.get(1).map(String::as_str) {
        Some("--embed") => {
            let input: EmbedRequest = serde_json::from_reader(std::io::stdin())?;
            let service = EmbeddingService::new(/* config */);
            let embeddings = service.embed_batch(input.texts).await?;
            println!("{}", serde_json::to_string(&EmbedResponse { embeddings })?);
        }
        Some("--process") => {
            // Handle content processing
        }
        _ => {
            // Start HTTP server for persistent service
            start_server().await?;
        }
    }
    
    Ok(())
}
```

This Rust implementation provides high-performance content processing while maintaining clean interfaces with the Python components of the P8FS system.