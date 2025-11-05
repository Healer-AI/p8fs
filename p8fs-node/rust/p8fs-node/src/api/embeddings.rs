use crate::models::{EmbeddingRequest, EmbeddingResponse};
use crate::services::EmbeddingService;
use axum::{
    extract::Json,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::post,
    Router,
};

pub fn routes() -> Router {
    Router::new().route("/", post(create_embeddings))
}

async fn create_embeddings(Json(request): Json<EmbeddingRequest>) -> Result<Json<EmbeddingResponse>, AppError> {
    let service = EmbeddingService::global();
    let service = service.lock().await;
    
    let response = service.embed(request.input).await?;
    
    Ok(Json(response))
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