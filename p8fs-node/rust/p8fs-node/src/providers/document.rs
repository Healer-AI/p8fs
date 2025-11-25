use crate::models::{ContentChunk, ContentMetadata, ContentProcessingResult, ContentType};
use crate::providers::ContentProvider;
use crate::services::EmbeddingService;
use async_trait::async_trait;
use docx_rs::{read_docx, Docx};
use std::collections::HashMap;
use std::path::Path;

pub struct DocumentProvider;

impl DocumentProvider {
    pub fn new() -> Self {
        Self
    }

    fn extract_text_from_docx(&self, docx: &Docx) -> String {
        let mut text = String::new();
        
        for child in &docx.document.children {
            match child {
                docx_rs::DocumentChild::Paragraph(p) => {
                    let mut para_text = String::new();
                    for run in &p.children {
                        if let docx_rs::ParagraphChild::Run(r) = run {
                            for text_child in &r.children {
                                if let docx_rs::RunChild::Text(t) = text_child {
                                    para_text.push_str(&t.text);
                                }
                            }
                        }
                    }
                    if !para_text.trim().is_empty() {
                        text.push_str(&para_text);
                        text.push_str("\n\n");
                    }
                }
                docx_rs::DocumentChild::Table(_) => {
                    text.push_str("| Table Content |\n|---------------|\n| *[Table data extracted from DOCX]* |\n\n");
                }
                _ => {}
            }
        }
        
        text.trim().to_string()
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
impl ContentProvider for DocumentProvider {
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
        let file_bytes = tokio::fs::read(file_path).await?;
        
        let text = tokio::task::spawn_blocking(move || -> anyhow::Result<String> {
            let docx = read_docx(&file_bytes)?;
            let provider = DocumentProvider::new();
            Ok(provider.extract_text_from_docx(&docx))
        })
        .await??;

        let chunk_texts = self.chunk_text(&text, 1000, 200);
        
        let chunks: Vec<ContentChunk> = chunk_texts
            .into_iter()
            .enumerate()
            .map(|(i, content)| {
                let mut metadata = HashMap::new();
                metadata.insert("chunk_index".to_string(), serde_json::json!(i));
                metadata.insert("source".to_string(), serde_json::json!("docx"));
                metadata.insert("section".to_string(), serde_json::json!(format!("Document Section {}", i + 1)));
                
                // Format content as markdown with proper structure
                let markdown_content = if i == 0 {
                    format!("# Document Content\n\n{}", content.trim())
                } else {
                    format!("## Section {}\n\n{}", i + 1, content.trim())
                };
                
                ContentChunk {
                    id: format!("doc_chunk_{}", i),
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
            content_type: ContentType::Document,
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