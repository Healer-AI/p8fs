use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[cfg(test)]
mod tests;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "UPPERCASE")]
pub enum ContentType {
    Pdf,
    Audio,
    Video,
    Image,
    Text,
    Markdown,
    StructuredData,
    Document,
    Spreadsheet,
    Presentation,
    Archive,
    Code,
    Email,
    Web,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContentChunk {
    pub id: String,
    pub content: String,
    pub metadata: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContentMetadata {
    pub content_type: ContentType,
    pub file_name: Option<String>,
    pub file_size: Option<u64>,
    pub created_at: Option<String>,
    pub modified_at: Option<String>,
    pub author: Option<String>,
    pub title: Option<String>,
    pub language: Option<String>,
    pub additional: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContentProcessingResult {
    pub success: bool,
    pub chunks: Vec<ContentChunk>,
    pub metadata: ContentMetadata,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmbeddingRequest {
    pub input: Vec<String>,
    pub model: Option<String>,
    pub encoding_format: Option<String>,
    pub dimensions: Option<usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmbeddingData {
    pub object: String,
    pub embedding: Vec<f32>,
    pub index: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Usage {
    pub prompt_tokens: usize,
    pub total_tokens: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmbeddingResponse {
    pub object: String,
    pub data: Vec<EmbeddingData>,
    pub model: String,
    pub usage: Usage,
}