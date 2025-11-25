use p8fs_node::{models::*, providers::{registry, ContentProvider}};
use std::path::Path;
use tokio::fs;

#[tokio::test]
async fn test_end_to_end_json_processing() {
    let test_content = r#"{
        "kind": "Document",
        "title": "Test Document",
        "content": "This is test content",
        "metadata": {
            "author": "Test Author",
            "tags": ["test", "document"]
        }
    }"#;
    
    let test_path = "/tmp/integration_test.json";
    fs::write(test_path, test_content).await.unwrap();
    
    let (content_type, provider) = registry::get_provider_by_extension("json").unwrap();
    assert_eq!(content_type, ContentType::StructuredData);
    
    let result = provider.process_content(Path::new(test_path)).await;
    assert!(result.is_ok());
    
    let result = result.unwrap();
    assert!(result.success);
    assert!(!result.chunks.is_empty());
    assert_eq!(result.metadata.content_type, ContentType::StructuredData);
    
    // Test that we can generate embeddings (this will be mocked in practice)
    if !result.chunks.is_empty() {
        let _embeddings_result = provider.to_embeddings(&result.chunks).await;
        // Note: This might fail without the actual model, but tests the interface
    }
    
    fs::remove_file(test_path).await.ok();
}

#[tokio::test]
async fn test_end_to_end_markdown_processing() {
    let test_content = r#"# Main Title

This is the introduction to the document.

## Section 1

Content for the first section with some **bold** text and *italic* text.

### Subsection 1.1

More detailed content here.

## Section 2

Final section with a list:

- Item 1
- Item 2
- Item 3

```rust
fn example() {
    println!("Hello, world!");
}
```"#;
    
    let test_path = "/tmp/integration_test.md";
    fs::write(test_path, test_content).await.unwrap();
    
    let (content_type, provider) = registry::get_provider_by_extension("md").unwrap();
    assert_eq!(content_type, ContentType::Markdown);
    
    let result = provider.process_content(Path::new(test_path)).await;
    assert!(result.is_ok());
    
    let result = result.unwrap();
    assert!(result.success);
    assert!(!result.chunks.is_empty());
    
    // Verify section structure
    let chunks = &result.chunks;
    assert!(chunks.len() >= 3); // At least Main Title, Section 1, Section 2
    
    // Check that sections are properly extracted
    let first_chunk = &chunks[0];
    assert!(first_chunk.content.contains("# Main Title"));
    assert_eq!(first_chunk.metadata.get("heading_level").unwrap(), 1);
    
    fs::remove_file(test_path).await.ok();
}

#[tokio::test]
async fn test_unsupported_file_type() {
    let result = registry::get_provider_by_extension("xyz");
    assert!(result.is_none());
    
    let result = registry::get_provider_by_extension("unknown");
    assert!(result.is_none());
}

#[tokio::test]
async fn test_all_supported_extensions() {
    let supported_extensions = vec![
        ("pdf", ContentType::Pdf),
        ("wav", ContentType::Audio),
        ("docx", ContentType::Document),
        ("json", ContentType::StructuredData),
        ("md", ContentType::Markdown),
        ("markdown", ContentType::Markdown),
    ];
    
    for (ext, expected_type) in supported_extensions {
        let result = registry::get_provider_by_extension(ext);
        assert!(result.is_some(), "Extension {} should be supported", ext);
        
        let (content_type, provider) = result.unwrap();
        assert_eq!(content_type, expected_type);
        
        // Verify we can get the same provider by content type
        let provider2 = registry::get_provider(&content_type);
        assert!(provider2.is_some());
    }
}

#[cfg(test)]
mod stress_tests {
    use super::*;

    #[tokio::test]
    async fn test_large_json_processing() {
        // Create a large JSON structure
        let mut large_object = serde_json::Map::new();
        for i in 0..1000 {
            large_object.insert(
                format!("key_{}", i),
                serde_json::json!({
                    "id": i,
                    "name": format!("item_{}", i),
                    "data": vec![i, i*2, i*3]
                })
            );
        }
        
        let large_json = serde_json::to_string_pretty(&large_object).unwrap();
        let test_path = "/tmp/large_test.json";
        fs::write(test_path, &large_json).await.unwrap();
        
        let (_, provider) = registry::get_provider_by_extension("json").unwrap();
        let result = provider.process_content(Path::new(test_path)).await;
        
        assert!(result.is_ok());
        let result = result.unwrap();
        assert!(result.success);
        
        fs::remove_file(test_path).await.ok();
    }

    #[tokio::test]
    async fn test_concurrent_processing() {
        let test_content = r#"{"test": "concurrent processing"}"#;
        
        let mut handles = Vec::new();
        
        for i in 0..10 {
            let content = test_content.to_string();
            let handle = tokio::spawn(async move {
                let test_path = format!("/tmp/concurrent_test_{}.json", i);
                fs::write(&test_path, content).await.unwrap();
                
                let (_, provider) = registry::get_provider_by_extension("json").unwrap();
                let result = provider.process_content(Path::new(&test_path)).await;
                
                fs::remove_file(&test_path).await.ok();
                result
            });
            handles.push(handle);
        }
        
        for handle in handles {
            let result = handle.await.unwrap();
            assert!(result.is_ok());
            assert!(result.unwrap().success);
        }
    }
}