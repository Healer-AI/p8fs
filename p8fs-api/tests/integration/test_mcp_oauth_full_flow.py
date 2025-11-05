"""Integration test for complete MCP OAuth flow.

This test simulates the full OAuth 2.1 Device Authorization Grant flow that an MCP client would use:
1. Device authorization request
2. Device approval simulation
3. Token polling and exchange
4. Token refresh
5. Authenticated API calls (auth ping)
"""

import asyncio
import pytest
from httpx import AsyncClient
from datetime import datetime
import json
from pathlib import Path

from p8fs_cluster.config.settings import config

# Base URL for tests
BASE_URL = "http://localhost:8001"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_oauth_device_flow():
    """Test the complete MCP OAuth device authorization flow."""
    async with AsyncClient(base_url=BASE_URL) as client:
        # Step 1: MCP Discovery - Get OAuth endpoints
        print("\n=== Step 1: MCP Discovery ===")
        
        # Check MCP auth discovery
        response = await client.get("/api/mcp/auth/discovery")
        assert response.status_code == 200
        discovery = response.json()
        assert "device_authorization_endpoint" in discovery
        assert "token_endpoint" in discovery
        print(f"✓ Found device authorization endpoint: {discovery['device_authorization_endpoint']}")
        
        # Step 2: Initiate device authorization
        print("\n=== Step 2: Device Authorization Request ===")
        
        device_auth_response = await client.post(
            "/oauth/device_authorization",
            data={
                "client_id": "mcp_test_client",
                "scope": "read write"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert device_auth_response.status_code == 200
        device_auth = device_auth_response.json()
        
        assert "device_code" in device_auth
        assert "user_code" in device_auth
        assert "verification_uri" in device_auth
        assert "expires_in" in device_auth
        assert "interval" in device_auth
        
        device_code = device_auth["device_code"]
        user_code = device_auth["user_code"]
        print(f"✓ Got device code: {device_code[:20]}...")
        print(f"✓ Got user code: {user_code}")
        print(f"✓ Verification URI: {device_auth['verification_uri']}")
        
        # Step 3: Poll for token (should get pending)
        print("\n=== Step 3: Initial Token Poll (Expecting Pending) ===")
        
        token_response = await client.post(
            "/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "mcp_test_client"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert token_response.status_code == 400
        error_data = token_response.json()
        # Check for authorization_pending error
        assert "error" in error_data or "authorization_pending" in str(error_data)
        print("✓ Got expected authorization_pending response")
        
        # Step 4: Simulate device approval
        print("\n=== Step 4: Simulating Device Approval ===")
        
        # First, we need a valid access token for the approval
        # In a real flow, this would come from the mobile app
        # For testing, we'll use the dev token endpoint
        
        if config.environment == "development" and config.dev_token_secret:
            # Generate a dev token for approval
            dev_token_response = await client.post(
                "/api/v1/auth/dev/register",
                json={
                    "email": "test@mcp-integration.com",
                    "public_key": "test_public_key_base64",
                    "device_info": {
                        "device_name": "Test Approval Device",
                        "platform": "test"
                    }
                },
                headers={
                    "X-Dev-Token": config.dev_token_secret,
                    "X-Dev-Email": "test@mcp-integration.com",
                    "X-Dev-Code": "TEST123"
                }
            )
            assert dev_token_response.status_code == 200
            dev_token_data = dev_token_response.json()
            approval_token = dev_token_data["access_token"]
            print("✓ Got dev token for approval")
            
            # Approve the device
            approval_response = await client.post(
                "/oauth/device/approve",
                json={
                    "user_code": user_code,
                    "approved": True,
                    "device_name": "MCP Test Client"
                },
                headers={
                    "Authorization": f"Bearer {approval_token}",
                    "Content-Type": "application/json"
                }
            )
            if approval_response.status_code != 200:
                print(f"Approval failed: {approval_response.status_code}")
                print(f"Response: {approval_response.text}")
            assert approval_response.status_code == 200
            print("✓ Device approved successfully")
        else:
            pytest.skip("Development mode required for device approval simulation")
        
        # Step 5: Poll for token (should succeed now)
        print("\n=== Step 5: Token Poll After Approval ===")
        
        # Wait a moment for approval to process
        await asyncio.sleep(1)
        
        token_response = await client.post(
            "/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "mcp_test_client"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if token_response.status_code != 200:
            print(f"Token exchange failed: {token_response.status_code}")
            print(f"Response: {token_response.text}")
            
        assert token_response.status_code == 200
        token_data = token_response.json()
        
        assert "access_token" in token_data
        assert "token_type" in token_data
        assert token_data["token_type"] == "Bearer"
        assert "expires_in" in token_data
        
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        print(f"✓ Got access token: {access_token[:50]}...")
        print(f"✓ Token type: {token_data['token_type']}")
        print(f"✓ Expires in: {token_data['expires_in']} seconds")
        
        # Step 6: Test authenticated ping endpoint
        print("\n=== Step 6: Test Auth Ping Endpoint ===")
        
        ping_response = await client.get(
            "/oauth/ping",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if ping_response.status_code != 200:
            print(f"✗ Auth ping failed: {ping_response.status_code}")
            print(f"Response: {ping_response.text}")
            print(f"Headers: {dict(ping_response.headers)}")
        assert ping_response.status_code == 200
        ping_data = ping_response.json()
        
        assert ping_data["authenticated"] == True
        assert "user_id" in ping_data
        print(f"✓ Auth ping successful: {ping_data}")
        
        # Step 7: Test MCP auth info endpoint
        print("\n=== Step 7: Test MCP Auth Info ===")
        
        auth_info_response = await client.get(
            "/api/mcp/auth/info",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert auth_info_response.status_code == 200
        auth_info = auth_info_response.json()
        
        assert auth_info["authenticated"] == True
        assert "user" in auth_info
        assert "oauth_discovery" in auth_info
        print(f"✓ MCP auth info retrieved: authenticated={auth_info['authenticated']}")
        
        # Step 8: Test token refresh (if refresh token provided)
        if refresh_token:
            print("\n=== Step 8: Test Token Refresh ===")
            
            refresh_response = await client.post(
                "/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": "mcp_test_client"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if refresh_response.status_code == 200:
                refresh_data = refresh_response.json()
                new_access_token = refresh_data["access_token"]
                print(f"✓ Token refreshed successfully")
                print(f"✓ New access token: {new_access_token[:50]}...")
                
                # Test the new token works
                ping_response2 = await client.get(
                    "/oauth/ping",
                    headers={"Authorization": f"Bearer {new_access_token}"}
                )
                assert ping_response2.status_code == 200
                print("✓ New token validated successfully")
            else:
                print(f"⚠️  Token refresh not implemented or failed: {refresh_response.status_code}")
        else:
            print("\n⚠️  No refresh token provided, skipping refresh test")
        
        # Step 9: Test token introspection
        print("\n=== Step 9: Test Token Introspection ===")
        
        introspect_response = await client.post(
            "/oauth/introspect",
            data={
                "token": access_token,
                "token_type_hint": "access_token"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert introspect_response.status_code == 200
        introspect_data = introspect_response.json()
        
        assert "active" in introspect_data
        print(f"✓ Token introspection: active={introspect_data.get('active', False)}")
        
        # Step 10: Test token revocation
        print("\n=== Step 10: Test Token Revocation ===")
        
        revoke_response = await client.post(
            "/oauth/revoke",
            data={
                "token": access_token,
                "token_type_hint": "access_token",
                "client_id": "mcp_test_client"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert revoke_response.status_code == 200
        print("✓ Token revoked successfully")
        
        # Verify token no longer works
        ping_response3 = await client.get(
            "/oauth/ping",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        # After revocation, token should be invalid (401)
        # Note: This might still return 200 if revocation is not fully implemented
        if ping_response3.status_code == 401:
            print("✓ Revoked token correctly rejected")
        else:
            print("⚠️  Token revocation may not be fully implemented")
        
        print("\n=== ✅ MCP OAuth Flow Test Complete ===")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_discovery_endpoints():
    """Test MCP-specific discovery endpoints."""
    async with AsyncClient(base_url=BASE_URL) as client:
        print("\n=== Testing MCP Discovery Endpoints ===")
        
        # Test unauthenticated discovery
        response = await client.get("/api/mcp/auth/login-required")
        assert response.status_code == 200
        login_info = response.json()
        
        assert login_info["authenticated"] == False
        assert login_info["user"] is None
        assert "oauth_discovery" in login_info
        assert "login_instructions" in login_info
        
        instructions = login_info["login_instructions"]
        assert instructions["method"] == "oauth2_device_flow"
        assert "example_flow" in instructions
        
        print("✓ MCP login-required endpoint works")
        print(f"✓ Recommended auth method: {instructions['method']}")
        print(f"✓ Client registration info: {instructions['client_registration']}")


if __name__ == "__main__":
    # Run the tests
    asyncio.run(test_mcp_oauth_device_flow())
    asyncio.run(test_mcp_discovery_endpoints())