"""Unit tests for authentication."""

from fastapi.testclient import TestClient
from p8fs_api.main import app

client = TestClient(app)


class TestAuthEndpoints:
    """Test authentication endpoints."""
    
    def test_device_code_generation(self):
        """Test OAuth device code generation."""
        response = client.post(
            "/api/v1/oauth/device/code",
            data={"client_id": "test_client"},
            headers={"host": "localhost"}
        )
        
        if response.status_code != 200:
            print(f"Error response: {response.status_code} - {response.text}")
        assert response.status_code == 200
        data = response.json()
        
        assert "device_code" in data
        assert "user_code" in data
        assert "verification_uri" in data
        assert data["expires_in"] == 600
        assert data["interval"] == 5
    
    def test_device_registration(self):
        """Test mobile device registration."""
        # Generate a valid base64-encoded 32-byte public key (Ed25519 format)
        import base64
        import secrets
        valid_public_key = base64.b64encode(secrets.token_bytes(32)).decode('utf-8')
        
        response = client.post(
            "/api/v1/oauth/device/register",
            json={
                "email": "test@example.com",
                "public_key": valid_public_key,
                "device_info": {
                    "platform": "ios",
                    "version": "16.0"
                }
            },
            headers={"host": "localhost"}
        )
        
        if response.status_code != 200:
            print(f"Device registration error: {response.status_code} - {response.text}")
        assert response.status_code == 200
        data = response.json()
        
        assert "registration_id" in data
        assert data["expires_in"] == 900
    
    def test_token_endpoint_missing_params(self):
        """Test token endpoint with missing parameters."""
        response = client.post(
            "/api/v1/oauth/token",
            data={"grant_type": "authorization_code"},
            headers={"host": "localhost"}
        )
        
        # Should fail due to missing required parameters
        if response.status_code != 422:
            print(f"Token endpoint error: Expected 422, got {response.status_code} - {response.text}")
        assert response.status_code == 422
    
    def test_userinfo_without_auth(self):
        """Test userinfo endpoint without authentication."""
        response = client.get("/api/v1/oauth/userinfo", headers={"host": "localhost"})

        # FastAPI's HTTPBearer returns 403 when no Authorization header is present
        if response.status_code != 403:
            print(f"Userinfo endpoint error: Expected 403, got {response.status_code} - {response.text}")
        assert response.status_code == 403

    def test_auth_disabled_setting(self):
        """Test that P8FS_AUTH_DISABLED setting bypasses JWT validation."""
        import os
        from unittest.mock import patch

        # Test with auth disabled
        with patch.dict(os.environ, {"P8FS_AUTH_DISABLED": "true"}):
            # Reload config to pick up environment variable
            from p8fs_cluster.config.settings import P8FSConfig
            test_config = P8FSConfig()
            assert test_config.auth_disabled is True

            # Test chat endpoint without proper auth token (should work with auth disabled)
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-4.1-mini",
                    "messages": [{"role": "user", "content": "test"}],
                    "stream": False
                },
                headers={
                    "host": "localhost",
                    "Authorization": "Bearer fake-token"
                }
            )

            # With auth disabled, this should not return 401
            # Note: May return other errors depending on downstream services,
            # but importantly NOT 401 Unauthorized
            if response.status_code == 401:
                print(f"Auth disabled test failed: Got 401 when auth should be disabled")
            assert response.status_code != 401