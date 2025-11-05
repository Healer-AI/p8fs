use crate::models::{ContentChunk, ContentMetadata, ContentProcessingResult, ContentType};
use crate::providers::ContentProvider;
use crate::services::EmbeddingService;
use async_trait::async_trait;
use pulldown_cmark::{Event, Parser, Tag, TagEnd};
use std::collections::HashMap;
use std::path::Path;

pub struct MarkdownProvider;

impl MarkdownProvider {
    pub fn new() -> Self {
        Self
    }

    fn extract_sections(&self, markdown: &str) -> Vec<(String, String, usize)> {
        let mut sections = Vec::new();
        let parser = Parser::new(markdown);
        
        let mut current_section = String::new();
        let mut current_content = String::new();
        let mut current_level = 0;
        let mut in_code_block = false;
        
        for event in parser {
            match event {
                Event::Start(Tag::Heading { level, .. }) => {
                    if !current_section.is_empty() {
                        sections.push((current_section.clone(), current_content.trim().to_string(), current_level));
                    }
                    current_section.clear();
                    current_content.clear();
                    current_level = level as usize;
                }
                Event::End(TagEnd::Heading(_)) => {
                    current_content = format!("{}\n\n", current_section);
                }
                Event::Text(text) => {
                    if current_section.is_empty() && current_level > 0 {
                        current_section = text.to_string();
                    } else {
                        current_content.push_str(&text);
                    }
                }
                Event::Code(code) => {
                    current_content.push('`');
                    current_content.push_str(&code);
                    current_content.push('`');
                }
                Event::Start(Tag::CodeBlock(_)) => {
                    in_code_block = true;
                    current_content.push_str("```\n");
                }
                Event::End(TagEnd::CodeBlock) => {
                    in_code_block = false;
                    current_content.push_str("\n```\n");
                }
                Event::SoftBreak => {
                    if !in_code_block {
                        current_content.push(' ');
                    } else {
                        current_content.push('\n');
                    }
                }
                Event::HardBreak => {
                    current_content.push('\n');
                }
                _ => {}
            }
        }
        
        if !current_section.is_empty() || !current_content.is_empty() {
            sections.push((current_section, current_content.trim().to_string(), current_level));
        }
        
        if sections.is_empty() && !markdown.is_empty() {
            sections.push(("Document".to_string(), markdown.to_string(), 1));
        }
        
        sections
    }
}

#[async_trait]
impl ContentProvider for MarkdownProvider {
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
        let content = tokio::fs::read_to_string(file_path).await?;
        let sections = self.extract_sections(&content);
        
        let chunks: Vec<ContentChunk> = sections
            .into_iter()
            .enumerate()
            .map(|(i, (title, content, level))| {
                let mut metadata = HashMap::new();
                metadata.insert("chunk_index".to_string(), serde_json::json!(i));
                metadata.insert("section_title".to_string(), serde_json::json!(title));
                metadata.insert("heading_level".to_string(), serde_json::json!(level));
                metadata.insert("source".to_string(), serde_json::json!("markdown"));
                
                let full_content = if !title.is_empty() {
                    format!("{} {}\n\n{}", "#".repeat(level), title, content)
                } else {
                    content
                };
                
                ContentChunk {
                    id: format!("md_chunk_{}", i),
                    content: full_content,
                    metadata,
                }
            })
            .collect();

        Ok(chunks)
    }

    async fn to_metadata(&self, file_path: &Path) -> anyhow::Result<ContentMetadata> {
        let file_metadata = tokio::fs::metadata(file_path).await?;
        let content = tokio::fs::read_to_string(file_path).await?;
        
        let lines: Vec<&str> = content.lines().collect();
        let title = lines.iter()
            .find(|line| line.starts_with('#'))
            .map(|line| line.trim_start_matches('#').trim().to_string());
        
        Ok(ContentMetadata {
            content_type: ContentType::Markdown,
            file_name: file_path.file_name().map(|n| n.to_string_lossy().to_string()),
            file_size: Some(file_metadata.len()),
            created_at: None,
            modified_at: None,
            author: None,
            title,
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