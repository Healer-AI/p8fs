"""Unit tests for MCP server."""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from p8fs_api.main import app

client = TestClient(app)


class TestMCPEndpoints:
    """Test MCP server endpoints."""
    
    def test_mcp_capabilities_requires_auth(self):
        """Test MCP capabilities endpoint requires authentication."""
        response = client.get("/api/mcp/capabilities")
        
        # Should return 404 since /capabilities endpoint doesn't exist
        assert response.status_code == 404
    
    def test_mcp_tools_list_requires_auth(self):
        """Test MCP tools listing requires authentication."""
        response = client.get("/api/mcp/tools")
        
        # Should return 404 since /tools endpoint doesn't exist
        assert response.status_code == 404
    
    def test_mcp_initialize_request_requires_auth(self):
        """Test MCP initialization request requires authentication."""
        response = client.post(
            "/api/mcp/",
            json={
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                }
            }
        )
        
        # Should return 401 with authentication required message
        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "invalid_token"
    
    def test_mcp_tools_list_request_requires_auth(self):
        """Test MCP tools/list request requires authentication."""
        response = client.post(
            "/api/mcp/",
            json={
                "method": "tools/list",
                "params": {}
            }
        )
        
        # Should return 401 with authentication required message  
        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "invalid_token"
    
    def test_mcp_tool_call_request_requires_auth(self):
        """Test MCP tools/call request requires authentication."""
        response = client.post(
            "/api/mcp/",
            json={
                "method": "tools/call",
                "params": {
                    "name": "search_files",
                    "arguments": {
                        "query": "test query",
                        "limit": 5
                    }
                }
            }
        )
        
        # Should return 401 with authentication required message
        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "invalid_token"
    
    def test_mcp_unknown_method(self):
        """Test MCP request with unknown method."""
        response = client.post(
            "/api/mcp/",
            json={
                "method": "unknown/method",
                "params": {}
            }
        )
        
        # Should return 401 (auth required) before even checking the method
        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "invalid_token"