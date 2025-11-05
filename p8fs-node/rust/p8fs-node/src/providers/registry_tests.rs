#[cfg(test)]
mod tests {
    use super::super::registry::*;
    use crate::models::ContentType;

    #[test]
    fn test_get_provider_by_content_type() {
        let pdf_provider = get_provider(&ContentType::Pdf);
        assert!(pdf_provider.is_some(), "PDF provider should exist");

        let audio_provider = get_provider(&ContentType::Audio);
        assert!(audio_provider.is_some(), "Audio provider should exist");

        let document_provider = get_provider(&ContentType::Document);
        assert!(document_provider.is_some(), "Document provider should exist");

        let json_provider = get_provider(&ContentType::StructuredData);
        assert!(json_provider.is_some(), "JSON provider should exist");

        let markdown_provider = get_provider(&ContentType::Markdown);
        assert!(markdown_provider.is_some(), "Markdown provider should exist");

        let unknown_provider = get_provider(&ContentType::Unknown);
        assert!(unknown_provider.is_none(), "Unknown provider should not exist");
    }

    #[test]
    fn test_get_provider_by_extension() {
        let test_cases = vec![
            ("pdf", Some(ContentType::Pdf)),
            ("PDF", Some(ContentType::Pdf)), // Test case insensitivity
            ("wav", Some(ContentType::Audio)),
            ("WAV", Some(ContentType::Audio)),
            ("docx", Some(ContentType::Document)),
            ("DOCX", Some(ContentType::Document)),
            ("json", Some(ContentType::StructuredData)),
            ("JSON", Some(ContentType::StructuredData)),
            ("md", Some(ContentType::Markdown)),
            ("markdown", Some(ContentType::Markdown)),
            ("MD", Some(ContentType::Markdown)),
            ("txt", None), // Unsupported extension
            ("xyz", None), // Non-existent extension
            ("", None),    // Empty extension
        ];

        for (extension, expected) in test_cases {
            let result = get_provider_by_extension(extension);
            
            match expected {
                Some(expected_type) => {
                    assert!(result.is_some(), "Extension {} should be supported", extension);
                    let (content_type, _) = result.unwrap();
                    assert_eq!(content_type, expected_type, 
                        "Extension {} should map to {:?}", extension, expected_type);
                }
                None => {
                    assert!(result.is_none(), "Extension {} should not be supported", extension);
                }
            }
        }
    }

    #[test]
    fn test_provider_consistency() {
        let extensions = vec!["pdf", "wav", "docx", "json", "md"];
        
        for extension in extensions {
            let (content_type, provider1) = get_provider_by_extension(extension).unwrap();
            let provider2 = get_provider(&content_type).unwrap();
            
            // Both providers should be the same instance (Arc comparison)
            assert!(Arc::ptr_eq(&provider1, &provider2), 
                "Providers for {} should be the same instance", extension);
        }
    }
}