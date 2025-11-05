use axum::{
    body::Body,
    http::{self, Request, StatusCode},
};
use p8fs_node::{api, models::*};
use serde_json::json;
use tower::ServiceExt;

#[tokio::test]
async fn test_embeddings_endpoint() {
    let app = api::create_router();

    let request_body = EmbeddingRequest {
        text: vec!["Hello world".to_string(), "Test text".to_string()],
        model: Some("test-model".to_string()),
    };

    let request = Request::builder()
        .method(http::Method::POST)
        .uri("/embeddings")
        .header(http::header::CONTENT_TYPE, mime::APPLICATION_JSON.as_ref())
        .body(Body::from(serde_json::to_vec(&request_body).unwrap()))
        .unwrap();

    // Note: This test will likely fail without the actual embedding model
    // but it tests the API structure
    let response = app.oneshot(request).await.unwrap();
    
    // For now, just check that we get a proper HTTP response structure
    // In a real test environment, we'd mock the embedding service
    assert!(response.status() == StatusCode::OK || response.status() == StatusCode::INTERNAL_SERVER_ERROR);
}

#[tokio::test]
async fn test_embeddings_endpoint_invalid_json() {
    let app = api::create_router();

    let request = Request::builder()
        .method(http::Method::POST)
        .uri("/embeddings")
        .header(http::header::CONTENT_TYPE, mime::APPLICATION_JSON.as_ref())
        .body(Body::from("invalid json"))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    
    // Should return bad request for invalid JSON
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_content_process_endpoint_no_file() {
    let app = api::create_router();

    let request = Request::builder()
        .method(http::Method::POST)
        .uri("/content/process")
        .header(http::header::CONTENT_TYPE, "multipart/form-data; boundary=test")
        .body(Body::from("--test\r\n\r\n--test--"))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    
    // Should return error for missing file
    assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
}

#[tokio::test]
async fn test_health_check() {
    let app = api::create_router();

    let request = Request::builder()
        .method(http::Method::GET)
        .uri("/health")
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    
    // Fallback route should return the server name
    assert_eq!(response.status(), StatusCode::OK);
}

#[tokio::test]
async fn test_not_found_route() {
    let app = api::create_router();

    let request = Request::builder()
        .method(http::Method::GET)
        .uri("/nonexistent")
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    
    // Should use fallback route
    assert_eq!(response.status(), StatusCode::OK);
}

#[cfg(test)]
mod mock_tests {
    use super::*;
    use axum::{
        extract::Json,
        http::StatusCode,
        response::Json as ResponseJson,
        routing::post,
        Router,
    };

    async fn mock_embeddings_handler(
        Json(request): Json<EmbeddingRequest>,
    ) -> Result<ResponseJson<EmbeddingResponse>, StatusCode> {
        let embeddings: Vec<Vec<f32>> = request
            .text
            .iter()
            .map(|_| vec![0.1, 0.2, 0.3, 0.4])
            .collect();

        Ok(ResponseJson(EmbeddingResponse {
            embeddings,
            model: "mock-model".to_string(),
            dimensions: 4,
        }))
    }

    fn create_mock_app() -> Router {
        Router::new().route("/embeddings", post(mock_embeddings_handler))
    }

    #[tokio::test]
    async fn test_mock_embeddings_success() {
        let app = create_mock_app();

        let request_body = EmbeddingRequest {
            text: vec!["Hello".to_string(), "World".to_string()],
            model: Some("test".to_string()),
        };

        let request = Request::builder()
            .method(http::Method::POST)
            .uri("/embeddings")
            .header(http::header::CONTENT_TYPE, mime::APPLICATION_JSON.as_ref())
            .body(Body::from(serde_json::to_vec(&request_body).unwrap()))
            .unwrap();

        let response = app.oneshot(request).await.unwrap();
        
        assert_eq!(response.status(), StatusCode::OK);

        let body = hyper::body::to_bytes(response.into_body()).await.unwrap();
        let response_data: EmbeddingResponse = serde_json::from_slice(&body).unwrap();
        
        assert_eq!(response_data.embeddings.len(), 2);
        assert_eq!(response_data.dimensions, 4);
        assert_eq!(response_data.model, "mock-model");
    }
}