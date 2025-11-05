use crate::models::EmbeddingResponse;
use embed_anything::embeddings::embed::TextEmbedder;
use once_cell::sync::OnceCell;
use std::env;
use std::sync::Arc;
use tokio::sync::Mutex;

static EMBEDDING_SERVICE: OnceCell<Arc<Mutex<EmbeddingService>>> = OnceCell::new();

pub struct EmbeddingService {
    embedder: TextEmbedder,
    model_name: String,
    dimensions: usize,
}

impl EmbeddingService {
    pub fn new() -> anyhow::Result<Self> {
        let model_name = env::var("EMBEDDING_MODEL")
            .unwrap_or_else(|_| "sentence-transformers/all-MiniLM-L6-v2".to_string());
        
        let dimensions = env::var("EMBEDDING_DIMENSIONS")
            .unwrap_or_else(|_| "384".to_string())
            .parse::<usize>()
            .unwrap_or(384);

        let embedder = TextEmbedder::from_pretrained_hf(&model_name, &model_name, None, None, None)?;
        
        let short_model_name = model_name
            .split('/')
            .last()
            .unwrap_or(&model_name)
            .to_string();
        
        Ok(Self {
            embedder,
            model_name: short_model_name,
            dimensions,
        })
    }

    pub async fn embed(&self, texts: Vec<String>) -> anyhow::Result<EmbeddingResponse> {
        let text_refs: Vec<&str> = texts.iter().map(|s| s.as_str()).collect();
        let embeddings = self.embedder.embed(&text_refs, None, None).await?;
        
        let data: Vec<crate::models::EmbeddingData> = embeddings
            .into_iter()
            .enumerate()
            .map(|(index, embedding_result)| {
                use embed_anything::embeddings::embed::EmbeddingResult;
                let embedding = match embedding_result {
                    EmbeddingResult::DenseVector(vec) => vec,
                    _ => panic!("Unexpected embedding result type"),
                };
                crate::models::EmbeddingData {
                    object: "embedding".to_string(),
                    embedding,
                    index,
                }
            })
            .collect();

        let total_tokens: usize = texts.iter().map(|t| t.split_whitespace().count()).sum();
        
        Ok(EmbeddingResponse {
            object: "list".to_string(),
            data,
            model: self.model_name.clone(),
            usage: crate::models::Usage {
                prompt_tokens: total_tokens,
                total_tokens,
            },
        })
    }

    pub fn global() -> Arc<Mutex<EmbeddingService>> {
        EMBEDDING_SERVICE
            .get_or_init(|| {
                Arc::new(Mutex::new(
                    EmbeddingService::new().expect("Failed to initialize embedding service"),
                ))
            })
            .clone()
    }
}