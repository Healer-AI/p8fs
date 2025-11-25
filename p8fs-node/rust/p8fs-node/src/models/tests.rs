#[cfg(test)]
mod tests {
    use super::super::*;
    use serde_json::json;

    #[test]
    fn test_content_type_serialization() {
        let ct = ContentType::Pdf;
        let serialized = serde_json::to_string(&ct).unwrap();
        assert_eq!(serialized, "\"PDF\"");
        
        let deserialized: ContentType = serde_json::from_str(&serialized).unwrap();
        assert_eq!(deserialized, ContentType::Pdf);
    }

    #[test]
    fn test_content_chunk_creation() {
        let mut metadata = HashMap::new();
        metadata.insert("test".to_string(), json!("value"));
        
        let chunk = ContentChunk {
            id: "test_chunk".to_string(),
            content: "Test content".to_string(),
            metadata: metadata.clone(),
        };
        
        assert_eq!(chunk.id, "test_chunk");
        assert_eq!(chunk.content, "Test content");
        assert_eq!(chunk.metadata.get("test").unwrap(), &json!("value"));
    }

    #[test]
    fn test_content_metadata_serialization() {
        let metadata = ContentMetadata {
            content_type: ContentType::Markdown,
            file_name: Some("test.md".to_string()),
            file_size: Some(1024),
            created_at: None,
            modified_at: None,
            author: Some("Test Author".to_string()),
            title: Some("Test Title".to_string()),
            language: Some("en".to_string()),
            additional: HashMap::new(),
        };
        
        let serialized = serde_json::to_string(&metadata).unwrap();
        let deserialized: ContentMetadata = serde_json::from_str(&serialized).unwrap();
        
        assert_eq!(deserialized.content_type, ContentType::Markdown);
        assert_eq!(deserialized.file_name, Some("test.md".to_string()));
        assert_eq!(deserialized.file_size, Some(1024));
        assert_eq!(deserialized.author, Some("Test Author".to_string()));
    }

    #[test]
    fn test_content_processing_result() {
        let chunk = ContentChunk {
            id: "chunk1".to_string(),
            content: "Content".to_string(),
            metadata: HashMap::new(),
        };
        
        let metadata = ContentMetadata {
            content_type: ContentType::Text,
            file_name: Some("test.txt".to_string()),
            file_size: Some(100),
            created_at: None,
            modified_at: None,
            author: None,
            title: None,
            language: None,
            additional: HashMap::new(),
        };
        
        let result = ContentProcessingResult {
            success: true,
            chunks: vec![chunk],
            metadata,
            error: None,
        };
        
        assert!(result.success);
        assert_eq!(result.chunks.len(), 1);
        assert!(result.error.is_none());
    }

    #[test]
    fn test_embedding_request() {
        let request = EmbeddingRequest {
            input: vec!["Hello".to_string(), "World".to_string()],
            model: Some("test-model".to_string()),
            encoding_format: Some("float".to_string()),
            dimensions: Some(384),
        };
        
        assert_eq!(request.input.len(), 2);
        assert_eq!(request.model, Some("test-model".to_string()));
        assert_eq!(request.dimensions, Some(384));
    }

    #[test]
    fn test_embedding_response() {
        let data = vec![
            EmbeddingData {
                object: "embedding".to_string(),
                embedding: vec![0.1, 0.2, 0.3],
                index: 0,
            },
            EmbeddingData {
                object: "embedding".to_string(),
                embedding: vec![0.4, 0.5, 0.6],
                index: 1,
            },
        ];
        
        let response = EmbeddingResponse {
            object: "list".to_string(),
            data: data.clone(),
            model: "test-model".to_string(),
            usage: Usage {
                prompt_tokens: 4,
                total_tokens: 4,
            },
        };
        
        assert_eq!(response.data.len(), 2);
        assert_eq!(response.data[0].embedding.len(), 3);
        assert_eq!(response.model, "test-model");
        assert_eq!(response.object, "list");
        assert_eq!(response.usage.total_tokens, 4);
    }
}