"""Unit tests for JWT key manager.

Tests ES256 key generation, token creation/verification, and key rotation
with appropriate mocking for external dependencies.

Reference: p8fs-auth/src/p8fs_auth/services/jwt_key_manager.py
"""

import asyncio
import json
from datetime import datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jose import JWTError, jwt

from p8fs_auth.services.jwt_key_manager import JWTKeyManager


@pytest.fixture
def jwt_manager():
    """Create JWT manager with mocked config."""
    # The JWTKeyManager now uses getattr with defaults
    # so we don't need to mock the config
    manager = JWTKeyManager()
    
    return manager


class TestKeyGeneration:
    """Test ES256 keypair generation.
    
    Reference: p8fs-auth/docs/authentication-flows.md - JWT Signing Keys (ES256)
    """
    
    def test_generate_es256_keypair(self, jwt_manager):
        """Test ES256 keypair generation produces valid keys."""
        # Generate keypair
        private_key, public_key = jwt_manager._generate_es256_keypair()
        
        # Verify key types
        assert isinstance(private_key, ec.EllipticCurvePrivateKey)
        assert isinstance(public_key, ec.EllipticCurvePublicKey)
        
        # Verify curve is P-256
        assert isinstance(private_key.curve, ec.SECP256R1)
        assert isinstance(public_key.curve, ec.SECP256R1)
    
    def test_ensure_current_key_creates_initial_key(self, jwt_manager):
        """Test that initial key is created on startup."""
        # Manager should have a current key after init
        assert jwt_manager._current_key_id is not None
        assert len(jwt_manager._keys) == 1
        
        # Verify key structure
        current_key = jwt_manager._keys[jwt_manager._current_key_id]
        assert "private_key" in current_key
        assert "public_key" in current_key
        assert "created_at" in current_key
        assert "public_key_pem" in current_key
        assert "public_key_jwk" in current_key
        assert current_key["retired_at"] is None
    
    def test_public_key_to_jwk_format(self, jwt_manager):
        """Test conversion of EC public key to JWK format."""
        # Get current key
        current_key = jwt_manager._keys[jwt_manager._current_key_id]
        jwk = current_key["public_key_jwk"]
        
        # Verify JWK structure
        assert jwk["kty"] == "EC"
        assert jwk["crv"] == "P-256"
        assert jwk["use"] == "sig"
        assert jwk["alg"] == "ES256"
        assert jwk["kid"] == jwt_manager._current_key_id
        assert "x" in jwk  # x coordinate
        assert "y" in jwk  # y coordinate


class TestTokenCreation:
    """Test JWT token creation.
    
    Reference: p8fs-api/src/p8fs_api/middleware/auth.py - JWT token structure
    """
    
    @pytest.mark.asyncio
    async def test_create_access_token_structure(self, jwt_manager):
        """Test access token has correct structure and claims."""
        # Create token
        token = await jwt_manager.create_access_token(
            user_id="test-user",
            client_id="test-client",
            scope=["read", "write"],
            device_id="test-device"
        )
        
        # Decode token without verification to inspect structure
        header = jwt.get_unverified_header(token)
        claims = jwt.get_unverified_claims(token)
        
        # Verify header
        assert header["alg"] == "ES256"
        assert header["kid"] == jwt_manager._current_key_id
        
        # Verify standard claims
        assert claims["iss"] == "p8fs-auth"  # Using default
        assert claims["aud"] == "p8fs-api"  # Using default
        assert claims["sub"] == "test-user"
        assert claims["user_id"] == "test-user"
        assert claims["client_id"] == "test-client"
        assert claims["scope"] == "read write"
        assert claims["device_id"] == "test-device"
        assert "exp" in claims
        assert "iat" in claims
        assert "jti" in claims
        assert "kid" in claims
    
    @pytest.mark.asyncio
    async def test_create_access_token_expiration(self, jwt_manager):
        """Test token expiration is set correctly."""
        # Create token
        token = await jwt_manager.create_access_token(
            user_id="test-user",
            client_id="test-client",
            scope=["read"]
        )
        
        # Decode and check expiration
        claims = jwt.get_unverified_claims(token)
        exp_time = datetime.fromtimestamp(claims["exp"])
        iat_time = datetime.fromtimestamp(claims["iat"])
        
        # Should expire in ~1 hour (3600 seconds)
        duration = exp_time - iat_time
        assert 3595 <= duration.total_seconds() <= 3605
    
    @pytest.mark.asyncio
    async def test_create_access_token_additional_claims(self, jwt_manager):
        """Test adding custom claims to token."""
        # Create token with additional claims
        additional = {
            "tenant_id": "test-tenant",
            "custom_claim": "custom_value"
        }
        
        token = await jwt_manager.create_access_token(
            user_id="test-user",
            client_id="test-client",
            scope=["read"],
            additional_claims=additional
        )
        
        # Verify additional claims included
        claims = jwt.get_unverified_claims(token)
        assert claims["tenant_id"] == "test-tenant"
        assert claims["custom_claim"] == "custom_value"


class TestTokenVerification:
    """Test JWT token verification.
    
    Reference: p8fs-api/src/p8fs_api/middleware/auth.py - verify_jwt_token
    """
    
    @pytest.mark.asyncio
    async def test_verify_valid_token(self, jwt_manager):
        """Test verification of valid token."""
        # Create token
        token = await jwt_manager.create_access_token(
            user_id="test-user",
            client_id="test-client",
            scope=["read", "write"]
        )
        
        # Verify token
        claims = await jwt_manager.verify_token(token)
        
        # Check claims returned
        assert claims["user_id"] == "test-user"
        assert claims["client_id"] == "test-client"
        assert claims["scope"] == "read write"
    
    @pytest.mark.asyncio
    async def test_verify_expired_token(self, jwt_manager):
        """Test verification fails for expired token."""
        # Create token with past expiration
        now = datetime.utcnow()
        claims = {
            "iss": "p8fs-auth",  # Use default issuer
            "aud": "p8fs-api",   # Use default audience
            "exp": now - timedelta(hours=1),  # Expired 1 hour ago
            "iat": now - timedelta(hours=2),
            "sub": "test-user",
            "user_id": "test-user"
        }
        
        # Get current key for signing
        current_key = jwt_manager._keys[jwt_manager._current_key_id]
        private_key = current_key["private_key"]
        
        # Create expired token
        token = jwt.encode(
            claims,
            private_key,
            algorithm="ES256",
            headers={"kid": jwt_manager._current_key_id}
        )
        
        # Verification should fail
        with pytest.raises(JWTError):
            await jwt_manager.verify_token(token, verify_expiration=True)
        
        # Should succeed when not verifying expiration
        verified_claims = await jwt_manager.verify_token(token, verify_expiration=False)
        assert verified_claims["user_id"] == "test-user"
    
    @pytest.mark.asyncio
    async def test_verify_invalid_signature(self, jwt_manager):
        """Test verification fails for invalid signature."""
        # Create token with one key
        token = await jwt_manager.create_access_token(
            user_id="test-user",
            client_id="test-client",
            scope=["read"]
        )
        
        # Tamper with token by modifying the payload
        parts = token.split('.')
        # Decode the payload (add padding if needed)
        payload = parts[1]
        # Add padding if needed
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding
        
        # Decode and modify
        import base64
        decoded = base64.urlsafe_b64decode(payload)
        claims = json.loads(decoded)
        claims["user_id"] = "hacker"
        
        # Re-encode without padding
        modified = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
        tampered_token = f"{parts[0]}.{modified}.{parts[2]}"
        
        # Verification should fail
        with pytest.raises(JWTError):
            await jwt_manager.verify_token(tampered_token)
    
    @pytest.mark.asyncio
    async def test_verify_wrong_audience(self, jwt_manager):
        """Test verification fails for wrong audience."""
        # Create token
        token = await jwt_manager.create_access_token(
            user_id="test-user",
            client_id="test-client",
            scope=["read"]
        )
        
        # Temporarily change expected audience
        original_audience = jwt_manager.audience
        jwt_manager.audience = "different-audience"
        
        # Verification should fail
        with pytest.raises(JWTError):
            await jwt_manager.verify_token(token, verify_audience=True)
        
        # Restore audience
        jwt_manager.audience = original_audience


class TestKeyRotation:
    """Test JWT key rotation.
    
    Reference: p8fs-auth/docs/authentication-flows.md - "Automatic rotation with zero downtime"
    """
    
    @pytest.mark.asyncio
    async def test_rotate_keys(self, jwt_manager):
        """Test manual key rotation."""
        # Get initial key
        initial_key_id = jwt_manager._current_key_id
        
        # Create token with initial key
        token1 = await jwt_manager.create_access_token(
            user_id="test-user",
            client_id="test-client",
            scope=["read"]
        )
        
        # Rotate keys
        await jwt_manager.rotate_keys()
        
        # Should have new current key
        assert jwt_manager._current_key_id != initial_key_id
        assert len(jwt_manager._keys) == 2
        
        # Old key should be retired
        old_key = jwt_manager._keys[initial_key_id]
        assert old_key["retired_at"] is not None
        
        # Create token with new key
        token2 = await jwt_manager.create_access_token(
            user_id="test-user",
            client_id="test-client",
            scope=["read"]
        )
        
        # Both tokens should verify (grace period)
        claims1 = await jwt_manager.verify_token(token1)
        claims2 = await jwt_manager.verify_token(token2)
        
        assert claims1["user_id"] == "test-user"
        assert claims2["user_id"] == "test-user"
    
    def test_jwks_includes_current_and_recent_keys(self, jwt_manager):
        """Test JWKS endpoint includes all active keys."""
        # Get initial JWKS
        jwks1 = jwt_manager.get_jwks()
        assert len(jwks1["keys"]) == 1
        
        # Rotate keys
        asyncio.run(jwt_manager.rotate_keys())
        
        # JWKS should include both keys during grace period
        jwks2 = jwt_manager.get_jwks()
        assert len(jwks2["keys"]) == 2
        
        # Verify both keys are different
        kid1 = jwks2["keys"][0]["kid"]
        kid2 = jwks2["keys"][1]["kid"]
        assert kid1 != kid2
    
    @pytest.mark.asyncio
    async def test_old_keys_cleaned_up(self, jwt_manager):
        """Test old retired keys are cleaned up after grace period."""
        # Create initial key
        initial_key_id = jwt_manager._current_key_id
        
        # Rotate keys
        await jwt_manager.rotate_keys()
        
        # Manually expire the old key beyond grace period
        old_key = jwt_manager._keys[initial_key_id]
        old_key["retired_at"] = datetime.utcnow() - timedelta(days=2)
        
        # Rotate again to trigger cleanup
        await jwt_manager.rotate_keys()
        
        # Old key should be removed
        assert initial_key_id not in jwt_manager._keys
        assert len(jwt_manager._keys) == 2  # Current + recently retired