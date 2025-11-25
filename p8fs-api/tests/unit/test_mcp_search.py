"""Unit tests for MCP search_content tool."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from p8fs_api.routers.mcp_server import create_secure_mcp_server


@pytest.fixture
def mock_auth_provider():
    """Mock auth provider that bypasses authentication."""
    provider = MagicMock()
    provider.verify_token = AsyncMock(return_value=None)
    return provider


@pytest.fixture
def mcp_server(mock_auth_provider):
    """Create MCP server with mocked auth."""
    with patch('p8fs_api.routers.mcp_server.P8FSAuthProvider', return_value=mock_auth_provider):
        return create_secure_mcp_server()


@pytest.mark.asyncio
async def test_search_content_tool_exists(mcp_server):
    """Test that search_content tool is registered."""
    # Get all tools
    tools = await mcp_server.get_tools()
    tool_names = list(tools.keys())
    assert "search_content" in tool_names
    
    # Get the specific tool
    search_tool = await mcp_server.get_tool("search_content")
    
    assert search_tool is not None
    assert "semantic search" in search_tool.description.lower()


@pytest.mark.asyncio
async def test_search_content_resources(mcp_server):
    """Test searching resources model."""
    # Mock the repository and query
    with patch('p8fs.repository.TenantRepository.TenantRepository') as mock_repo_class:
        mock_repo = AsyncMock()
        mock_repo.query = AsyncMock(return_value=[
            {
                "id": "123",
                "content": "Test resource content",
                "score": 0.95,
                "metadata": {"type": "document"},
                "name": "test.pdf",
                "uri": "/path/to/test.pdf"
            }
        ])
        mock_repo_class.return_value = mock_repo
        
        # Get search tool
        search_tool = await mcp_server.get_tool("search_content")
        
        # Execute search by calling the function directly
        result = await search_tool.fn(
            query="test query",
            model="resources",
            limit=5
        )
        
        # Verify results
        assert result["status"] == "success"
        assert result["query"] == "test query"
        assert result["model"] == "resources"
        assert result["total_results"] == 1
        assert len(result["results"]) == 1
        
        # Verify result structure
        first_result = result["results"][0]
        assert first_result["id"] == "123"
        assert first_result["content"] == "Test resource content"
        assert first_result["score"] == 0.95
        assert first_result["name"] == "test.pdf"
        assert first_result["uri"] == "/path/to/test.pdf"


@pytest.mark.asyncio
async def test_search_content_session(mcp_server):
    """Test searching session model."""
    # Mock the repository and query
    with patch('p8fs.repository.TenantRepository.TenantRepository') as mock_repo_class:
        mock_repo = AsyncMock()
        mock_repo.query = AsyncMock(return_value=[
            {
                "id": "456",
                "content": "Conversation about AI",
                "score": 0.88,
                "metadata": {"timestamp": "2024-01-01"},
                "query": "What is machine learning?",
                "session_type": "chat"
            }
        ])
        mock_repo_class.return_value = mock_repo
        
        # Get search tool
        search_tool = await mcp_server.get_tool("search_content")
        
        # Execute search by calling the function directly
        result = await search_tool.fn(
            query="AI conversation",
            model="session",
            limit=10,
            threshold=0.5
        )
        
        # Verify results
        assert result["status"] == "success"
        assert result["model"] == "session"
        assert result["threshold"] == 0.5
        assert len(result["results"]) == 1
        
        # Verify session-specific fields
        first_result = result["results"][0]
        assert first_result["query"] == "What is machine learning?"
        assert first_result["session_type"] == "chat"


@pytest.mark.asyncio
async def test_search_content_invalid_model(mcp_server):
    """Test search with invalid model returns error."""
    # Get search tool
    search_tool = await mcp_server.get_tool("search_content")
    
    # Execute search with invalid model
    result = await search_tool.fn(
        query="test",
        model="invalid_model"
    )
    
    # Verify error response
    assert result["status"] == "error"
    assert "Unknown model" in result["message"]
    assert "resources, session" in result["message"]


@pytest.mark.asyncio
async def test_search_content_error_handling(mcp_server):
    """Test error handling in search."""
    # Mock repository to raise exception
    with patch('p8fs.repository.TenantRepository.TenantRepository') as mock_repo_class:
        mock_repo = AsyncMock()
        mock_repo.query = AsyncMock(side_effect=Exception("Database error"))
        mock_repo_class.return_value = mock_repo
        
        # Get search tool
        search_tool = await mcp_server.get_tool("search_content")
        
        # Execute search by calling the function directly
        result = await search_tool.fn(query="test")
        
        # Verify error response
        assert result["status"] == "error"
        assert "Database error" in result["message"]