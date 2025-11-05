use crate::models::ContentType;
use crate::providers::{ContentProvider, audio::AudioProvider, document::DocumentProvider, json::JsonProvider, markdown::MarkdownProvider, pdf::PdfProvider};
use once_cell::sync::Lazy;
use std::collections::HashMap;
use std::sync::Arc;

#[cfg(test)]
#[path = "registry_tests.rs"]
mod tests;

pub type ProviderFactory = Arc<dyn ContentProvider>;

static REGISTRY: Lazy<HashMap<ContentType, ProviderFactory>> = Lazy::new(|| {
    let mut registry = HashMap::new();
    
    registry.insert(ContentType::Pdf, Arc::new(PdfProvider::new()) as ProviderFactory);
    registry.insert(ContentType::Audio, Arc::new(AudioProvider::new()) as ProviderFactory);
    registry.insert(ContentType::Document, Arc::new(DocumentProvider::new()) as ProviderFactory);
    registry.insert(ContentType::StructuredData, Arc::new(JsonProvider::new()) as ProviderFactory);
    registry.insert(ContentType::Markdown, Arc::new(MarkdownProvider::new()) as ProviderFactory);
    
    registry
});

pub fn get_provider(content_type: &ContentType) -> Option<ProviderFactory> {
    REGISTRY.get(content_type).cloned()
}

pub fn get_provider_by_extension(extension: &str) -> Option<(ContentType, ProviderFactory)> {
    let content_type = match extension.to_lowercase().as_str() {
        "pdf" => ContentType::Pdf,
        "wav" => ContentType::Audio,
        "docx" => ContentType::Document,
        "json" => ContentType::StructuredData,
        "md" | "markdown" => ContentType::Markdown,
        _ => return None,
    };
    
    get_provider(&content_type).map(|provider| (content_type, provider))
}