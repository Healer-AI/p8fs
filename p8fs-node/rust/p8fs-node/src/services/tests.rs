#[cfg(test)]
mod tests {
    use super::super::embeddings::*;
    use crate::models::{EmbeddingRequest, EmbeddingResponse};
    use std::sync::Arc;

    #[tokio::test]
    async fn test_embedding_service_creation() {
        let service = EmbeddingService::new();
        assert!(service.is_ok(), "Failed to create embedding service");
    }

    #[tokio::test]
    async fn test_embedding_service_global_instance() {
        let service1 = EmbeddingService::global();
        let service2 = EmbeddingService::global();
        
        assert!(Arc::ptr_eq(&service1, &service2), "Global instances should be the same");
    }

    #[tokio::test]
    #[ignore] // This test requires the model to be downloaded
    async fn test_embed_single_text() {
        let service = EmbeddingService::new().unwrap();
        let texts = vec!["Hello world".to_string()];
        
        let result = service.embed(texts).await;
        assert!(result.is_ok(), "Embedding generation failed");
        
        let response = result.unwrap();
        assert_eq!(response.embeddings.len(), 1);
        assert_eq!(response.dimensions, 384);
        assert_eq!(response.model, "all-MiniLM-L6-v2");
    }

    #[tokio::test]
    #[ignore] // This test requires the model to be downloaded
    async fn test_embed_multiple_texts() {
        let service = EmbeddingService::new().unwrap();
        let texts = vec![
            "First text".to_string(),
            "Second text".to_string(),
            "Third text".to_string(),
        ];
        
        let result = service.embed(texts.clone()).await;
        assert!(result.is_ok(), "Embedding generation failed");
        
        let response = result.unwrap();
        assert_eq!(response.embeddings.len(), texts.len());
        
        for embedding in &response.embeddings {
            assert_eq!(embedding.len(), 384);
        }
    }

    #[tokio::test]
    #[ignore] // This test requires the model to be downloaded
    async fn test_embed_empty_text() {
        let service = EmbeddingService::new().unwrap();
        let texts = vec!["".to_string()];
        
        let result = service.embed(texts).await;
        assert!(result.is_ok(), "Should handle empty text");
    }
}