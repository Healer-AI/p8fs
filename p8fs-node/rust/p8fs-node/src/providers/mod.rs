pub mod pdf;
pub mod audio;
pub mod document;
pub mod json;
pub mod markdown;
pub mod registry;

#[cfg(test)]
mod tests;

use crate::models::{ContentChunk, ContentMetadata, ContentProcessingResult};
use async_trait::async_trait;
use std::path::Path;

#[async_trait]
pub trait ContentProvider: Send + Sync {
    async fn process_content(&self, file_path: &Path) -> anyhow::Result<ContentProcessingResult>;
    
    async fn to_markdown_chunks(&self, file_path: &Path) -> anyhow::Result<Vec<ContentChunk>>;
    
    async fn to_metadata(&self, file_path: &Path) -> anyhow::Result<ContentMetadata>;
    
    async fn to_embeddings(&self, chunks: &[ContentChunk]) -> anyhow::Result<Vec<Vec<f32>>>;
}