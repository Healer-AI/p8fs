"""Integration tests for FastMCP server connectivity and tool calls."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport
from src.p8fs_api.main import app


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def base_url():
    """Base URL for MCP endpoints."""
    return "http://testserver/api/mcp"


class TestFastMCPIntegration:
    """Integration tests for FastMCP server functionality."""
    
    def test_server_connectivity(self, client):
        """Test basic FastMCP server connectivity via initialize."""
        # FastMCP servers respond to initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client", 
                    "version": "1.0.0"
                }
            }
        }
        
        response = client.post("/api/mcp/", json=init_request)
        assert response.status_code == 200
        
        data = response.json()
        assert "result" in data
        result = data["result"]
        assert "protocolVersion" in result
        assert result["serverInfo"]["name"] == "p8fs-mcp-server"
    
    def test_tools_listing(self, client):
        """Test tools listing via FastMCP protocol."""
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        }
        
        response = client.post("/api/mcp/", json=tools_request)
        assert response.status_code == 200
        
        data = response.json()
        assert "result" in data
        result = data["result"]
        assert "tools" in result
        assert len(result["tools"]) >= 1
        
        # Check for our about tool
        tool_names = [tool["name"] for tool in result["tools"]]
        assert "about" in tool_names
    
    def test_about_tool_call(self, client):
        """Test calling the about tool via FastMCP."""
        tool_call_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "about",
                "arguments": {}
            }
        }
        
        response = client.post("/api/mcp/", json=tool_call_request)
        assert response.status_code == 200
        
        data = response.json()
        assert "result" in data
        result = data["result"]
        assert "content" in result
        
        # Check content contains expected information
        content = result["content"]
        assert len(content) > 0
        assert "text" in content[0]
        assert "P8FS" in content[0]["text"]
        assert "distributed content management system" in content[0]["text"]
    
    def test_jsonrpc_format(self, client):
        """Test that FastMCP properly handles JSON-RPC format."""
        # Test with missing jsonrpc field (should still work with FastMCP)
        request = {
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0.0"}
            }
        }
        
        response = client.post("/api/mcp/", json=request)
        # FastMCP should handle this gracefully
        assert response.status_code in [200, 400]  # Either works or proper error
    
    def test_unknown_tool_error(self, client):
        """Test error handling for unknown tool calls."""
        tool_call_request = {
            "jsonrpc": "2.0", 
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "unknown_tool",
                "arguments": {}
            }
        }
        
        response = client.post("/api/mcp/", json=tool_call_request)
        
        # FastMCP should return JSON-RPC error format
        data = response.json()
        assert "error" in data or response.status_code >= 400
    
    def test_invalid_json_error(self, client):
        """Test error handling for invalid JSON."""
        response = client.post(
            "/api/mcp/",
            content="invalid json",
            headers={"content-type": "application/json"}
        )
        assert response.status_code >= 400
    
    
    
    
    
    
    


@pytest.mark.asyncio
async def test_concurrent_fastmcp_requests():
    """Test handling of concurrent FastMCP requests."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # Create multiple concurrent about tool requests 
        requests = [
            {
                "jsonrpc": "2.0",
                "id": i,
                "method": "tools/call",
                "params": {
                    "name": "about",
                    "arguments": {}
                }
            }
            for i in range(3)
        ]
        
        # Execute requests concurrently
        tasks = [
            client.post("/api/mcp/", json=req)
            for req in requests
        ]
        
        responses = await asyncio.gather(*tasks)
        
        # Verify all requests completed successfully
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert "result" in data
            assert "content" in data["result"]
            assert "P8FS" in data["result"]["content"][0]["text"]


if __name__ == "__main__":
    # Run tests directly for development
    pytest.main([__file__, "-v"])