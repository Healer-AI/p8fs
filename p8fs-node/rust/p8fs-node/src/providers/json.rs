use crate::models::{ContentChunk, ContentMetadata, ContentProcessingResult, ContentType};
use crate::providers::ContentProvider;
use crate::services::EmbeddingService;
use async_trait::async_trait;
use serde_json::Value;
use std::collections::HashMap;
use std::path::Path;

pub struct JsonProvider;

impl JsonProvider {
    pub fn new() -> Self {
        Self
    }

    fn json_to_markdown(&self, value: &Value, indent: usize) -> String {
        let indent_str = "  ".repeat(indent);
        
        match value {
            Value::Null => "null".to_string(),
            Value::Bool(b) => b.to_string(),
            Value::Number(n) => n.to_string(),
            Value::String(s) => format!("\"{}\"", s),
            Value::Array(arr) => {
                let items: Vec<String> = arr
                    .iter()
                    .enumerate()
                    .map(|(i, v)| format!("{}[{}]: {}", indent_str, i, self.json_to_markdown(v, indent + 1)))
                    .collect();
                format!("[\n{}\n{}]", items.join(",\n"), indent_str)
            }
            Value::Object(obj) => {
                if obj.contains_key("kind") {
                    format!("## {}\n{}", 
                        obj.get("kind").and_then(|v| v.as_str()).unwrap_or("Unknown"),
                        self.object_to_markdown(obj, indent)
                    )
                } else {
                    self.object_to_markdown(obj, indent)
                }
            }
        }
    }

    fn object_to_markdown(&self, obj: &serde_json::Map<String, Value>, indent: usize) -> String {
        let indent_str = "  ".repeat(indent);
        let entries: Vec<String> = obj
            .iter()
            .map(|(k, v)| {
                if k == "kind" {
                    return String::new();
                }
                format!("{}- **{}**: {}", indent_str, k, self.json_to_markdown(v, indent + 1))
            })
            .filter(|s| !s.is_empty())
            .collect();
        
        entries.join("\n")
    }

    fn extract_chunks(&self, value: &Value, path: String) -> Vec<(String, String, HashMap<String, Value>)> {
        let mut chunks = Vec::new();
        
        match value {
            Value::Object(obj) => {
                if obj.contains_key("kind") {
                    let content = self.json_to_markdown(value, 0);
                    let mut metadata = HashMap::new();
                    metadata.insert("path".to_string(), Value::String(path.clone()));
                    metadata.insert("kind".to_string(), obj.get("kind").cloned().unwrap_or(Value::Null));
                    chunks.push((path.clone(), content, metadata));
                }
                
                for (key, val) in obj {
                    let new_path = if path.is_empty() {
                        key.clone()
                    } else {
                        format!("{}.{}", path, key)
                    };
                    chunks.extend(self.extract_chunks(val, new_path));
                }
            }
            Value::Array(arr) => {
                for (i, val) in arr.iter().enumerate() {
                    let new_path = format!("{}[{}]", path, i);
                    chunks.extend(self.extract_chunks(val, new_path));
                }
            }
            _ => {}
        }
        
        if chunks.is_empty() && !path.is_empty() {
            let content = self.json_to_markdown(value, 0);
            let mut metadata = HashMap::new();
            metadata.insert("path".to_string(), Value::String(path.clone()));
            chunks.push((path, content, metadata));
        }
        
        chunks
    }
}

#[async_trait]
impl ContentProvider for JsonProvider {
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
        let json_value: Value = serde_json::from_str(&content)?;
        
        let raw_chunks = self.extract_chunks(&json_value, String::new());
        
        let chunks: Vec<ContentChunk> = raw_chunks
            .into_iter()
            .enumerate()
            .map(|(i, (path, content, mut metadata))| {
                metadata.insert("chunk_index".to_string(), serde_json::json!(i));
                metadata.insert("source".to_string(), serde_json::json!("json"));
                
                ContentChunk {
                    id: format!("json_chunk_{}_{}", i, path.replace('.', "_").replace('[', "").replace(']', "")),
                    content,
                    metadata,
                }
            })
            .collect();

        Ok(chunks)
    }

    async fn to_metadata(&self, file_path: &Path) -> anyhow::Result<ContentMetadata> {
        let file_metadata = tokio::fs::metadata(file_path).await?;
        
        Ok(ContentMetadata {
            content_type: ContentType::StructuredData,
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