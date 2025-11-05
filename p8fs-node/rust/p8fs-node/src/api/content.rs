use crate::models::ContentProcessingResult;
use crate::providers::registry;
use axum::{
    extract::{Multipart, Path as AxumPath},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use std::path::Path;
use tokio::fs;
use tokio::io::AsyncWriteExt;

pub fn routes() -> Router {
    Router::new()
        .route("/process", post(process_file))
        .route("/process/:content_type", post(process_file_with_type))
}

async fn process_file(mut multipart: Multipart) -> Result<Json<ContentProcessingResult>, AppError> {
    while let Some(field) = multipart.next_field().await? {
        if field.name() == Some("file") {
            let file_name = field.file_name()
                .ok_or_else(|| anyhow::anyhow!("No filename provided"))?
                .to_string();
            
            let extension = Path::new(&file_name)
                .extension()
                .and_then(|ext| ext.to_str())
                .ok_or_else(|| anyhow::anyhow!("No file extension"))?;
            
            let (_content_type, provider) = registry::get_provider_by_extension(extension)
                .ok_or_else(|| anyhow::anyhow!("Unsupported file type: {}", extension))?;
            
            let temp_path = format!("/tmp/{}", file_name);
            let mut file = fs::File::create(&temp_path).await?;
            
            let bytes = field.bytes().await?.to_vec();
            file.write_all(&bytes).await?;
            file.flush().await?;
            
            let result = provider.process_content(Path::new(&temp_path)).await?;
            
            fs::remove_file(&temp_path).await.ok();
            
            return Ok(Json(result));
        }
    }
    
    Err(anyhow::anyhow!("No file provided").into())
}

async fn process_file_with_type(
    AxumPath(content_type): AxumPath<String>,
    mut multipart: Multipart,
) -> Result<Json<ContentProcessingResult>, AppError> {
    let content_type = serde_json::from_str(&format!("\"{}\"", content_type.to_uppercase()))?;
    let provider = registry::get_provider(&content_type)
        .ok_or_else(|| anyhow::anyhow!("Unsupported content type: {:?}", content_type))?;
    
    while let Some(field) = multipart.next_field().await? {
        if field.name() == Some("file") {
            let file_name = field.file_name()
                .unwrap_or("upload")
                .to_string();
            
            let temp_path = format!("/tmp/{}", file_name);
            let mut file = fs::File::create(&temp_path).await?;
            
            let bytes = field.bytes().await?.to_vec();
            file.write_all(&bytes).await?;
            file.flush().await?;
            
            let result = provider.process_content(Path::new(&temp_path)).await?;
            
            fs::remove_file(&temp_path).await.ok();
            
            return Ok(Json(result));
        }
    }
    
    Err(anyhow::anyhow!("No file provided").into())
}

pub struct AppError(anyhow::Error);

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Internal error: {}", self.0),
        )
            .into_response()
    }
}

impl<E> From<E> for AppError
where
    E: Into<anyhow::Error>,
{
    fn from(err: E) -> Self {
        Self(err.into())
    }
}