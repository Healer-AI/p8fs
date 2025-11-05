#[cfg(test)]
mod tests {
    use super::super::*;
    use crate::models::*;
    use std::collections::HashMap;
    use std::path::Path;
    use tokio::fs;

    mod json_provider_tests {
        use super::*;
        use super::super::json::JsonProvider;

        #[tokio::test]
        async fn test_json_provider_simple() {
            let provider = JsonProvider::new();
            let test_content = r#"{"name": "test", "value": 42}"#;
            let test_path = "/tmp/test_json_provider.json";
            
            fs::write(test_path, test_content).await.unwrap();
            
            let result = provider.process_content(Path::new(test_path)).await;
            assert!(result.is_ok());
            
            let result = result.unwrap();
            assert!(result.success);
            assert!(!result.chunks.is_empty());
            assert_eq!(result.metadata.content_type, ContentType::StructuredData);
            
            fs::remove_file(test_path).await.ok();
        }

        #[tokio::test]
        async fn test_json_provider_with_kind() {
            let provider = JsonProvider::new();
            let test_content = r#"{"kind": "TestObject", "name": "test", "data": [1, 2, 3]}"#;
            let test_path = "/tmp/test_json_kind.json";
            
            fs::write(test_path, test_content).await.unwrap();
            
            let chunks = provider.to_markdown_chunks(Path::new(test_path)).await;
            assert!(chunks.is_ok());
            
            let chunks = chunks.unwrap();
            assert!(!chunks.is_empty());
            
            let first_chunk = &chunks[0];
            assert!(first_chunk.content.contains("## TestObject"));
            assert!(first_chunk.metadata.contains_key("kind"));
            
            fs::remove_file(test_path).await.ok();
        }

        #[test]
        fn test_json_to_markdown() {
            let provider = JsonProvider::new();
            let value = serde_json::json!({
                "name": "test",
                "items": [1, 2, 3],
                "nested": {
                    "key": "value"
                }
            });
            
            let markdown = provider.json_to_markdown(&value, 0);
            assert!(markdown.contains("**name**"));
            assert!(markdown.contains("**items**"));
            assert!(markdown.contains("**nested**"));
        }
    }

    mod markdown_provider_tests {
        use super::*;
        use super::super::markdown::MarkdownProvider;

        #[tokio::test]
        async fn test_markdown_provider_sections() {
            let provider = MarkdownProvider::new();
            let test_content = r#"# Title

This is the introduction.

## Section 1

Content for section 1.

## Section 2

Content for section 2.

### Subsection 2.1

Nested content."#;
            let test_path = "/tmp/test_markdown.md";
            
            fs::write(test_path, test_content).await.unwrap();
            
            let chunks = provider.to_markdown_chunks(Path::new(test_path)).await;
            assert!(chunks.is_ok());
            
            let chunks = chunks.unwrap();
            assert_eq!(chunks.len(), 4); // Title, Section 1, Section 2, Subsection 2.1
            
            assert_eq!(chunks[0].metadata.get("section_title").unwrap(), "Title");
            assert_eq!(chunks[0].metadata.get("heading_level").unwrap(), 1);
            
            assert_eq!(chunks[2].metadata.get("section_title").unwrap(), "Section 2");
            assert_eq!(chunks[2].metadata.get("heading_level").unwrap(), 2);
            
            fs::remove_file(test_path).await.ok();
        }

        #[test]
        fn test_markdown_extract_sections() {
            let provider = MarkdownProvider::new();
            let markdown = "# Main Title\n\nIntro text\n\n## Section\n\nSection content";
            
            let sections = provider.extract_sections(markdown);
            assert_eq!(sections.len(), 2);
            
            assert_eq!(sections[0].0, "Main Title");
            assert_eq!(sections[0].2, 1); // heading level
            
            assert_eq!(sections[1].0, "Section");
            assert_eq!(sections[1].2, 2); // heading level
        }
    }

    mod pdf_provider_tests {
        use super::*;
        use super::super::pdf::PdfProvider;

        #[test]
        fn test_pdf_chunk_text() {
            let provider = PdfProvider::new();
            let text = "a".repeat(2500); // Long text
            
            let chunks = provider.chunk_text(&text, 1000, 200);
            
            assert!(chunks.len() > 2);
            assert_eq!(chunks[0].len(), 1000);
            
            // Check overlap
            let overlap_start = &chunks[0][800..];
            let next_start = &chunks[1][..200];
            assert_eq!(overlap_start, next_start);
        }
    }

    mod audio_provider_tests {
        use super::*;
        use super::super::audio::AudioProvider;

        #[test]
        fn test_audio_segment_calculation() {
            let provider = AudioProvider::new();
            let samples = vec![0i16; 44100 * 60]; // 60 seconds at 44.1kHz
            
            let segments = provider.segment_audio(&samples, 44100, 30.0);
            
            assert_eq!(segments.len(), 2); // Two 30-second segments
            assert_eq!(segments[0].0, 0);
            assert_eq!(segments[0].1, 44100 * 30);
            assert_eq!(segments[1].0, 44100 * 30);
            assert_eq!(segments[1].1, 44100 * 60);
        }
    }

    #[async_trait]
    impl ContentProvider for MockProvider {
        async fn process_content(&self, _file_path: &Path) -> anyhow::Result<ContentProcessingResult> {
            Ok(ContentProcessingResult {
                success: true,
                chunks: vec![],
                metadata: ContentMetadata {
                    content_type: ContentType::Unknown,
                    file_name: None,
                    file_size: None,
                    created_at: None,
                    modified_at: None,
                    author: None,
                    title: None,
                    language: None,
                    additional: HashMap::new(),
                },
                error: None,
            })
        }

        async fn to_markdown_chunks(&self, _file_path: &Path) -> anyhow::Result<Vec<ContentChunk>> {
            Ok(vec![])
        }

        async fn to_metadata(&self, _file_path: &Path) -> anyhow::Result<ContentMetadata> {
            Ok(ContentMetadata {
                content_type: ContentType::Unknown,
                file_name: None,
                file_size: None,
                created_at: None,
                modified_at: None,
                author: None,
                title: None,
                language: None,
                additional: HashMap::new(),
            })
        }

        async fn to_embeddings(&self, _chunks: &[ContentChunk]) -> anyhow::Result<Vec<Vec<f32>>> {
            Ok(vec![])
        }
    }

    struct MockProvider;
}