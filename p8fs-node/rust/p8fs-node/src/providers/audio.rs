use crate::models::{ContentChunk, ContentMetadata, ContentProcessingResult, ContentType};
use crate::providers::ContentProvider;
use crate::services::EmbeddingService;
use async_trait::async_trait;
use hound::{WavReader, WavSpec};
use std::collections::HashMap;
use std::path::Path;

pub struct AudioProvider;

impl AudioProvider {
    pub fn new() -> Self {
        Self
    }

    fn extract_wav_info(&self, file_path: &Path) -> anyhow::Result<(WavSpec, Vec<i16>)> {
        let mut reader = WavReader::open(file_path)?;
        let spec = reader.spec();
        let samples: Vec<i16> = reader.samples::<i16>().collect::<Result<Vec<_>, _>>()?;
        Ok((spec, samples))
    }

    fn segment_audio(&self, samples: &[i16], sample_rate: u32, segment_duration_secs: f32) -> Vec<(usize, usize)> {
        let samples_per_segment = (sample_rate as f32 * segment_duration_secs) as usize;
        let mut segments = Vec::new();
        let mut start = 0;

        while start < samples.len() {
            let end = (start + samples_per_segment).min(samples.len());
            segments.push((start, end));
            start = end;
        }

        segments
    }
}

#[async_trait]
impl ContentProvider for AudioProvider {
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
        let (spec, samples) = tokio::task::spawn_blocking({
            let path = file_path.to_owned();
            move || {
                let provider = AudioProvider::new();
                provider.extract_wav_info(&path)
            }
        })
        .await??;

        let segments = self.segment_audio(&samples, spec.sample_rate, 30.0);
        
        let chunks: Vec<ContentChunk> = segments
            .into_iter()
            .enumerate()
            .map(|(i, (start, end))| {
                let mut metadata = HashMap::new();
                metadata.insert("segment_index".to_string(), serde_json::json!(i));
                metadata.insert("start_sample".to_string(), serde_json::json!(start));
                metadata.insert("end_sample".to_string(), serde_json::json!(end));
                metadata.insert("sample_rate".to_string(), serde_json::json!(spec.sample_rate));
                metadata.insert("channels".to_string(), serde_json::json!(spec.channels));
                metadata.insert("bits_per_sample".to_string(), serde_json::json!(spec.bits_per_sample));
                
                ContentChunk {
                    id: format!("audio_segment_{}", i),
                    content: format!("## Audio Segment {}\n\n**Duration:** {:.1}s - {:.1}s  \n**Samples:** {} - {}  \n**Sample Rate:** {} Hz  \n**Channels:** {}  \n**Bit Depth:** {} bits\n\n*[Audio content analysis would go here - transcription, audio features, etc.]*", 
                        i + 1,
                        start as f32 / spec.sample_rate as f32,
                        end as f32 / spec.sample_rate as f32,
                        start,
                        end,
                        spec.sample_rate,
                        spec.channels,
                        spec.bits_per_sample
                    ),
                    metadata,
                }
            })
            .collect();

        Ok(chunks)
    }

    async fn to_metadata(&self, file_path: &Path) -> anyhow::Result<ContentMetadata> {
        let file_metadata = tokio::fs::metadata(file_path).await?;
        
        let (spec, samples) = tokio::task::spawn_blocking({
            let path = file_path.to_owned();
            move || {
                let provider = AudioProvider::new();
                provider.extract_wav_info(&path)
            }
        })
        .await??;

        let duration_secs = samples.len() as f32 / spec.sample_rate as f32;
        
        let mut additional = HashMap::new();
        additional.insert("duration_seconds".to_string(), serde_json::json!(duration_secs));
        additional.insert("sample_rate".to_string(), serde_json::json!(spec.sample_rate));
        additional.insert("channels".to_string(), serde_json::json!(spec.channels));
        additional.insert("bits_per_sample".to_string(), serde_json::json!(spec.bits_per_sample));

        Ok(ContentMetadata {
            content_type: ContentType::Audio,
            file_name: file_path.file_name().map(|n| n.to_string_lossy().to_string()),
            file_size: Some(file_metadata.len()),
            created_at: None,
            modified_at: None,
            author: None,
            title: None,
            language: None,
            additional,
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