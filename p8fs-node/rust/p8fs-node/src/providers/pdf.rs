use crate::models::{ContentChunk, ContentMetadata, ContentProcessingResult, ContentType};
use crate::providers::ContentProvider;
use crate::services::EmbeddingService;
use async_trait::async_trait;
use pdf_extract::extract_text;
use std::collections::HashMap;
use std::path::Path;

pub struct PdfProvider;

impl PdfProvider {
    pub fn new() -> Self {
        Self
    }

    fn chunk_text(&self, text: &str, chunk_size: usize, overlap: usize) -> Vec<String> {
        let chars: Vec<char> = text.chars().collect();
        let mut chunks = Vec::new();
        let mut start = 0;

        while start < chars.len() {
            let end = (start + chunk_size).min(chars.len());
            let chunk: String = chars[start..end].iter().collect();
            chunks.push(chunk);
            
            if end >= chars.len() {
                break;
            }
            
            start = end - overlap;
        }

        chunks
    }
}

#[async_trait]
impl ContentProvider for PdfProvider {
    async fn process_content(&self, file_path: &Path) -> anyhow::Result<ContentProcessingResult> {
        let chunks = self.to_markdown_chunks(file_path).await?;
        let metadata = self.to_metadata(file_path).await?;
        
        Ok(ContentProcessingResult {
            success: true,
            chunks,
            metadata,
            error: None,
        })
    }

    async fn to_markdown_chunks(&self, file_path: &Path) -> anyhow::Result<Vec<ContentChunk>> {
        let text = tokio::task::spawn_blocking({
            let path = file_path.to_owned();
            move || extract_text(&path)
        })
        .await??;

        let chunk_texts = self.chunk_text(&text, 1000, 200);
        
        let chunks: Vec<ContentChunk> = chunk_texts
            .into_iter()
            .enumerate()
            .map(|(i, content)| {
                let mut metadata = HashMap::new();
                metadata.insert("chunk_index".to_string(), serde_json::json!(i));
                metadata.insert("source".to_string(), serde_json::json!("pdf"));
                metadata.insert("page_reference".to_string(), serde_json::json!(format!("Page ~{}", i + 1)));
                
                // Format content as markdown with proper structure
                let markdown_content = if i == 0 {
                    format!("# PDF Document Content\n\n{}", content.trim())
                } else {
                    format!("## Section {}\n\n{}", i + 1, content.trim())
                };
                
                ContentChunk {
                    id: format!("pdf_chunk_{}", i),
                    content: markdown_content,
                    metadata,
                }
            })
            .collect();

        Ok(chunks)
    }

    async fn to_metadata(&self, file_path: &Path) -> anyhow::Result<ContentMetadata> {
        let file_metadata = tokio::fs::metadata(file_path).await?;
        
        Ok(ContentMetadata {
            content_type: ContentType::Pdf,
            file_name: file_path.file_name().map(|n| n.to_string_lossy().to_string()),
            file_size: Some(file_metadata.len()),
            created_at: None,
            modified_at: None,
            author: None,
            title: None,
            language: None,
            additional: HashMap::new(),
        })
    }

    async fn to_embeddings(&self, chunks: &[ContentChunk]) -> anyhow::Result<Vec<Vec<f32>>> {
        let service = EmbeddingService::global();
        let service = service.lock().await;
        
        let texts: Vec<String> = chunks.iter().map(|c| c.content.clone()).collect();
        let response = service.embed(texts).await?;
        
        Ok(response.data.into_iter().map(|d| d.embedding).collect())
    }
}