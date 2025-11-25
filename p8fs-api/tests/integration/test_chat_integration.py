"""Integration tests for chat functionality."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from src.p8fs_api.main import app


@pytest.fixture
def mock_user():
    """Mock user for testing."""
    return {
        "id": "test-user-123",
        "email": "test@example.com", 
        "tenant_id": "test-tenant"
    }


@pytest.fixture
def auth_headers():
    """Mock auth headers."""
    return {"Authorization": "Bearer test-token"}


@pytest.fixture 
def chat_request():
    """Sample chat request."""
    return {
        "messages": [
            {"role": "user", "content": "Hello, how are you?"}
        ],
        "model": "gpt-4o-mini",
        "stream": False
    }


@pytest.fixture
def streaming_chat_request():
    """Sample streaming chat request."""
    return {
        "messages": [
            {"role": "user", "content": "Tell me a story"}
        ],
        "model": "gpt-4o-mini", 
        "stream": True
    }


@pytest.mark.integration
@patch('p8fs_api.middleware.auth.get_current_user')
@patch('p8fs.services.llm.memory_proxy.MemoryProxy')
async def test_chat_completion(mock_memory_proxy, mock_get_user, chat_request, auth_headers, mock_user):
    """Test non-streaming chat completion."""
    # Setup mocks
    mock_get_user.return_value = type('User', (), mock_user)()
    mock_proxy_instance = AsyncMock()
    mock_proxy_instance.run.return_value = "Hello! I'm doing well, thank you for asking."
    mock_memory_proxy.return_value = mock_proxy_instance
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/v1/chat/completions", 
            json=chat_request,
            headers=auth_headers
        )
    
    print(f"Response status: {response.status_code}")
    if response.status_code != 200:
        print(f"Response body: {response.text}")
    assert response.status_code == 200
    data = response.json()
    
    assert data["object"] == "chat.completion"
    assert data["model"] == "gpt-4o-mini"
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["choices"][0]["message"]["content"] == "Hello! I'm doing well, thank you for asking."
    assert data["choices"][0]["finish_reason"] == "stop"
    assert "usage" in data


@pytest.mark.integration
@patch('p8fs_api.middleware.auth.get_current_user') 
@patch('p8fs.services.llm.memory_proxy.MemoryProxy')
async def test_chat_completion_with_agent(mock_memory_proxy, mock_get_user, chat_request, auth_headers, mock_user):
    """Test chat completion with agent routing via header."""
    # Setup mocks
    mock_get_user.return_value = type('User', (), mock_user)()
    mock_proxy_instance = AsyncMock()
    mock_proxy_instance.run.return_value = "Research agent response here."
    mock_memory_proxy.return_value = mock_proxy_instance
    
    headers = {**auth_headers, "X-P8-Agent": "research-agent"}
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=chat_request,
            headers=headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] == "Research agent response here."


@pytest.mark.integration
@patch('p8fs_api.middleware.auth.get_current_user')
@patch('p8fs.services.llm.memory_proxy.MemoryProxy') 
async def test_agent_specific_endpoint(mock_memory_proxy, mock_get_user, chat_request, auth_headers, mock_user):
    """Test agent-specific endpoint."""
    # Setup mocks
    mock_get_user.return_value = type('User', (), mock_user)()
    mock_proxy_instance = AsyncMock()
    mock_proxy_instance.run.return_value = "Analysis agent response."
    mock_memory_proxy.return_value = mock_proxy_instance
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/v1/agent/analysis-agent/chat/completions",
            json=chat_request,
            headers=auth_headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] == "Analysis agent response."


@pytest.mark.integration
@patch('p8fs_api.middleware.auth.get_current_user')
@patch('p8fs.services.llm.memory_proxy.MemoryProxy')
async def test_streaming_chat_completion(mock_memory_proxy, mock_get_user, streaming_chat_request, auth_headers, mock_user):
    """Test streaming chat completion."""
    # Setup mocks
    mock_get_user.return_value = type('User', (), mock_user)()
    mock_proxy_instance = AsyncMock()
    
    async def mock_stream(question, context):
        chunks = ["Once", " upon", " a", " time..."]
        for chunk in chunks:
            yield chunk
    
    mock_proxy_instance.stream = mock_stream
    mock_memory_proxy.return_value = mock_proxy_instance
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        async with client.stream(
            "POST",
            "/v1/chat/completions",
            json=streaming_chat_request,
            headers=auth_headers
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
            
            chunks = []
            async for chunk in response.aiter_text():
                if chunk.startswith("data: "):
                    data_part = chunk[6:].strip()
                    if data_part and data_part != "[DONE]":
                        chunk_data = json.loads(data_part)
                        chunks.append(chunk_data)
            
            # Verify we got streaming chunks
            assert len(chunks) > 0
            assert chunks[0]["object"] == "chat.completion.chunk"
            assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"


@pytest.mark.integration
async def test_list_models():
    """Test models endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/v1/models")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["object"] == "list"
    assert len(data["data"]) > 0
    
    # Check that expected models are included
    model_ids = [model["id"] for model in data["data"]]
    assert "gpt-4o-mini" in model_ids
    assert "gpt-4o" in model_ids
    assert "claude-3-5-sonnet-20241022" in model_ids


@pytest.mark.integration
async def test_get_specific_model():
    """Test getting specific model information."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/v1/models/gpt-4o-mini")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == "gpt-4o-mini"
    assert data["object"] == "model"
    assert "created" in data


@pytest.mark.integration
async def test_chat_without_auth():
    """Test chat endpoint without authentication."""
    chat_request = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "gpt-4o-mini"
    }
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/v1/chat/completions", json=chat_request)
    
    assert response.status_code == 401


@pytest.mark.integration
@patch('p8fs_api.middleware.auth.get_current_user')
async def test_chat_with_empty_messages(mock_get_user, auth_headers, mock_user):
    """Test chat completion with empty messages."""
    mock_get_user.return_value = type('User', (), mock_user)()
    
    chat_request = {
        "messages": [],
        "model": "gpt-4o-mini"
    }
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=chat_request, 
            headers=auth_headers
        )
    
    assert response.status_code == 400