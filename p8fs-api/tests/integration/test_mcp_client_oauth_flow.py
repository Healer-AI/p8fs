"""Test MCP client OAuth flow against P8FS OAuth implementation.

This test simulates how an MCP client would authenticate with our OAuth server,
following the patterns described at https://gofastmcp.com/clients/auth/oauth
"""

import asyncio
import base64
import hashlib
import json
import secrets
from urllib.parse import urlencode

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
def mcp_base_url():
    """Base URL for MCP server."""
    return "http://testserver/api/mcp"


@pytest.fixture
def oauth_base_url():
    """Base URL for OAuth endpoints."""
    return "http://testserver/api/v1/oauth"


class MockMCPClient:
    """Mock MCP client that simulates the OAuth flow described in FastMCP docs."""
    
    def __init__(self, mcp_url: str, client_id: str = "mcp_client"):
        self.mcp_url = mcp_url
        self.client_id = client_id
        self.token = None
        
    async def discover_oauth_config(self, http_client) -> dict:
        """Step 1: Discover OAuth configuration.
        
        MCP clients first try to discover OAuth endpoints from the MCP server.
        """
        # Try MCP discovery endpoint first
        discovery_url = self.mcp_url.replace("/api/mcp", "/api/mcp/auth/discovery")
        response = await http_client.get(discovery_url)
        
        if response.status_code == 200:
            return response.json()
        
        # Fallback to well-known OpenID configuration
        wellknown_url = self.mcp_url.replace("/api/mcp", "/api/v1/oauth/.well-known/openid-configuration")
        response = await http_client.get(wellknown_url)
        
        if response.status_code == 200:
            return response.json()
            
        raise Exception("Failed to discover OAuth configuration")
    
    def generate_pkce_challenge(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge."""
        # Generate code verifier (43-128 chars)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        
        # Generate code challenge (SHA256 of verifier)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    async def start_device_flow(self, http_client, device_auth_endpoint: str) -> dict:
        """Step 2: Start device authorization flow.
        
        This is the preferred flow for MCP clients as it doesn't require
        a redirect URI or local callback server.
        """
        response = await http_client.post(
            device_auth_endpoint,
            data={
                "client_id": self.client_id,
                "scope": "read write"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if response.status_code != 200:
            raise Exception(f"Device flow failed: {response.text}")
            
        return response.json()
    
    async def poll_for_token(self, http_client, token_endpoint: str, device_code: str) -> dict:
        """Step 3: Poll token endpoint until authorization completes."""
        max_attempts = 10
        interval = 5  # seconds
        
        for attempt in range(max_attempts):
            response = await http_client.post(
                token_endpoint,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": self.client_id,
                    "device_code": device_code
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code == 200:
                return response.json()
            
            error_data = response.json()
            if error_data.get("error") == "authorization_pending":
                # Still waiting for user approval
                await asyncio.sleep(interval)
                continue
            else:
                raise Exception(f"Token poll failed: {error_data}")
        
        raise Exception("Timeout waiting for device authorization")
    
    async def make_authenticated_request(self, http_client, endpoint: str, token: str) -> dict:
        """Make an authenticated request to the MCP server."""
        response = await http_client.post(
            endpoint,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "about",
                    "arguments": {}
                }
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code != 200:
            raise Exception(f"Authenticated request failed: {response.text}")
            
        return response.json()


class TestMCPClientOAuthFlow:
    """Test suite for MCP client OAuth flow."""
    
    @pytest.mark.asyncio
    async def test_oauth_discovery(self, mcp_base_url):
        """Test that MCP clients can discover OAuth configuration."""
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            mcp_client = MockMCPClient(mcp_base_url)
            
            # Discover OAuth configuration
            oauth_config = await mcp_client.discover_oauth_config(client)
            
            # Verify required endpoints are present
            assert "device_authorization_endpoint" in oauth_config
            assert "token_endpoint" in oauth_config
            assert "authorization_endpoint" in oauth_config
            assert "jwks_uri" in oauth_config
            
            # Verify endpoints are correctly formed
            assert oauth_config["device_authorization_endpoint"].endswith("/api/v1/oauth/device_authorization")
            assert oauth_config["token_endpoint"].endswith("/api/v1/oauth/token")
    
    @pytest.mark.asyncio
    async def test_wellknown_discovery(self):
        """Test OpenID Connect well-known discovery endpoint."""
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/api/v1/oauth/.well-known/openid-configuration")
            
            assert response.status_code == 200
            config = response.json()
            
            # Verify OpenID configuration
            assert config["issuer"] == "http://testserver"
            assert "device_authorization_endpoint" in config
            assert "token_endpoint" in config
            assert "jwks_uri" in config
    
    @pytest.mark.asyncio 
    async def test_jwks_endpoint(self):
        """Test JWKS endpoint for public key discovery."""
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/api/v1/oauth/.well-known/jwks.json")
            
            assert response.status_code == 200
            jwks = response.json()
            
            # Verify JWKS structure
            assert "keys" in jwks
            assert len(jwks["keys"]) > 0
            assert jwks["keys"][0]["kty"] in ["RSA", "EC"]
            assert jwks["keys"][0]["use"] == "sig"
    
    @pytest.mark.asyncio
    async def test_device_flow_initiation(self, mcp_base_url):
        """Test device authorization flow initiation."""
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            mcp_client = MockMCPClient(mcp_base_url)
            
            # Discover OAuth config
            oauth_config = await mcp_client.discover_oauth_config(client)
            
            # Start device flow
            device_response = await mcp_client.start_device_flow(
                client, 
                oauth_config["device_authorization_endpoint"]
            )
            
            # Verify device flow response
            assert "device_code" in device_response
            assert "user_code" in device_response
            assert "verification_uri" in device_response
            assert "expires_in" in device_response
            assert "interval" in device_response
    
    def test_pkce_generation(self):
        """Test PKCE code verifier and challenge generation."""
        mcp_client = MockMCPClient("http://test")
        
        code_verifier, code_challenge = mcp_client.generate_pkce_challenge()
        
        # Verify PKCE parameters
        assert len(code_verifier) >= 43  # Minimum length
        assert len(code_verifier) <= 128  # Maximum length
        assert len(code_challenge) > 0
        
        # Verify challenge is SHA256 of verifier
        expected_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        assert code_challenge == expected_challenge
    
    @pytest.mark.asyncio
    async def test_authorization_endpoint_redirect(self):
        """Test that authorization endpoint exists and handles requests."""
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            # Try to access authorization endpoint (should require auth)
            response = await client.get(
                "/api/v1/oauth/authorize",
                params={
                    "response_type": "code",
                    "client_id": "mcp_client",
                    "redirect_uri": "http://localhost:8080/callback",
                    "scope": "read write",
                    "state": "random-state",
                    "code_challenge": "test-challenge",
                    "code_challenge_method": "S256"
                }
            )
            
            # Should require authentication (401 or redirect to login)
            assert response.status_code in [401, 302, 303]
    
    @pytest.mark.asyncio
    async def test_token_endpoint_errors(self):
        """Test token endpoint error responses."""
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            # Test invalid grant type
            response = await client.post(
                "/api/v1/oauth/token",
                data={
                    "grant_type": "invalid_grant_type",
                    "client_id": "mcp_client"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            assert response.status_code == 400
            error = response.json()
            assert error["error"] == "unsupported_grant_type"
            
            # Test missing device code
            response = await client.post(
                "/api/v1/oauth/token",
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": "mcp_client"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            assert response.status_code == 400
            error = response.json()
            assert "error" in error
    
    @pytest.mark.asyncio
    async def test_mcp_auth_required(self, mcp_base_url):
        """Test that MCP endpoints require authentication."""
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            # Try to call MCP tool without auth
            response = await client.post(
                f"{mcp_base_url}/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "about",
                        "arguments": {}
                    }
                }
            )
            
            # MCP endpoints might redirect (307) or return 401
            assert response.status_code in [307, 401]
            if response.status_code == 307:
                # Follow redirect for actual error
                redirect_url = response.headers.get("location", "")
                if redirect_url:
                    redirect_response = await client.post(redirect_url, json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "about",
                            "arguments": {}
                        }
                    })
                    assert redirect_response.status_code == 401
            error = response.json()
            assert error["error"] == "authentication_required"
            assert "oauth_discovery" in error
            assert "instructions" in error


def test_oauth_flow_documentation():
    """Test that demonstrates the complete OAuth flow for documentation."""
    print("\n📚 MCP Client OAuth Flow Example\n")
    
    print("1. Discovery Phase:")
    print("   - Client discovers OAuth endpoints from MCP server")
    print("   - Falls back to .well-known/openid-configuration if needed")
    
    print("\n2. Device Authorization Flow:")
    print("   - Client requests device code from /api/v1/oauth/device_authorization")
    print("   - User approves via mobile app using user_code")
    print("   - Client polls /api/v1/oauth/token until approved")
    
    print("\n3. Token Usage:")
    print("   - Client includes token in Authorization: Bearer header")
    print("   - Token is validated by MCP server middleware")
    print("   - Client can now access MCP tools")
    
    print("\n4. Token Management:")
    print("   - Tokens cached locally for reuse")
    print("   - Automatic refresh when expired (future)")
    
    print("\nSee test cases above for implementation details.")


if __name__ == "__main__":
    # Run tests directly for development
    pytest.main([__file__, "-v", "-s"])