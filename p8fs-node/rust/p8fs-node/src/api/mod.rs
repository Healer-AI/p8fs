pub mod content;
pub mod embeddings;

use axum::Router;

pub fn create_router() -> Router {
    Router::new()
        .nest("/embeddings", embeddings::routes())
        .nest("/content", content::routes())
}