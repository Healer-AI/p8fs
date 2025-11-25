#!/usr/bin/env python3
"""
Integration test for P8FS MCP server using FastMCP Client with OAuth.

This test demonstrates the complete OAuth 2.1 device flow + MCP integration:
1. OAuth device authorization request
2. Device approval with JWT token
3. Token exchange for access token
4. MCP session initialization with FastMCP Client
5. Tool listing and execution

Prerequisites:
- P8FS API server running on localhost:8001
- Primary device registered with JWT token at ~/.p8fs/auth/token.json
- PostgreSQL or TiDB running for KV storage

Run with:
    uv run pytest tests/integration/test_mcp_fastmcp_client.py -v
"""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastmcp import Client


class BearerAuth(httpx.Auth):
    """Custom httpx auth for Bearer token."""

    def __init__(self, token: str):
        self.token = token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


@pytest.fixture
def base_url():
    """Base URL for P8FS API server."""
    return "http://localhost:8001"


@pytest.fixture
def jwt_token():
    """Get JWT token from registered device."""
    token_file = Path.home() / ".p8fs" / "auth" / "token.json"
    if not token_file.exists():
        pytest.skip(
            "No JWT token found. Register device first: "
            "uv run python -m p8fs_api.cli.device --local register --email test@example.com"
        )

    with open(token_file) as f:
        return json.load(f)["access_token"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_oauth_device_flow(base_url, jwt_token):
    """Test OAuth 2.1 device authorization grant flow."""
    async with httpx.AsyncClient() as client:
        # Step 1: Request device code
        resp = await client.post(
            f"{base_url}/api/v1/oauth/device_authorization",
            data={"client_id": "test-client", "scope": "mcp:access"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        device_data = resp.json()

        assert "device_code" in device_data
        assert "user_code" in device_data
        assert "verification_uri" in device_data

        device_code = device_data["device_code"]
        user_code = device_data["user_code"]

        # Step 2: Approve device with JWT token
        resp = await client.post(
            f"{base_url}/api/v1/oauth/device/approve",
            json={
                "user_code": user_code,
                "approved": True,
                "device_name": "test-mcp-client",
            },
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        # Step 3: Exchange device code for token
        await asyncio.sleep(1)  # Wait for approval to propagate

        resp = await client.post(
            f"{base_url}/api/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": "test-client",
                "device_code": device_code,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        token_data = resp.json()

        assert "access_token" in token_data
        assert token_data["token_type"] == "Bearer"
        assert "expires_in" in token_data

        return token_data["access_token"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_session_with_fastmcp_client(base_url, jwt_token):
    """Test MCP session initialization and tool calls with FastMCP Client."""

    # First, get access token via OAuth flow
    access_token = await test_oauth_device_flow(base_url, jwt_token)

    # Use FastMCP Client with Bearer auth
    mcp_client = Client(f"{base_url}/api/mcp", auth=BearerAuth(access_token))

    async with mcp_client:
        # Test 1: List tools
        tools = await mcp_client.list_tools()
        assert len(tools) > 0

        tool_names = [tool.name for tool in tools]
        assert "about" in tool_names
        assert "user_info" in tool_names

        # Test 2: Call about tool
        result = await mcp_client.call_tool("about", {})
        assert not result.is_error
        assert result.data is not None
        assert "P8FS" in str(result.data)

        # Test 3: Call user_info tool
        user_result = await mcp_client.call_tool("user_info", {})
        assert not user_result.is_error
        assert user_result.data is not None

        if isinstance(user_result.data, dict):
            assert user_result.data.get("authenticated") is True

        # Test 4: List resources
        resources = await mcp_client.list_resources()
        assert isinstance(resources, list)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_authentication_required(base_url):
    """Test that MCP server rejects requests without authentication."""

    async with httpx.AsyncClient() as client:
        # Try to initialize without token
        resp = await client.post(
            f"{base_url}/api/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )

        # Should return 401 Unauthorized
        assert resp.status_code == 401


if __name__ == "__main__":
    """Run tests directly for manual testing."""
    import sys

    # Run all tests
    pytest.main([__file__, "-v", "-s"])
