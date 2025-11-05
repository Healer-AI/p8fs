"""Integration tests for complete authentication flows.

Tests end-to-end authentication scenarios with real cryptographic
operations and real database operations using P8FSAuthRepository.

Reference: p8fs-auth/docs/authentication-flows.md - Authentication Flows
"""

import base64
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from p8fs_auth.models.auth import (
    Device,
    DeviceTrustLevel,
)
from p8fs_auth.services.auth_service import AuthenticationService
from p8fs_auth.services.jwt_key_manager import JWTKeyManager
from p8fs_auth.services.mobile_service import MobileAuthenticationService


@pytest.fixture
async def real_repository():
    """Get the real P8FSAuthRepository for integration testing."""
    # Import here to avoid circular imports and ensure proper initialization
    try:
        from p8fs_api.repositories.auth_repository import P8FSAuthRepository
        return P8FSAuthRepository()
    except ImportError:
        pytest.skip("P8FSAuthRepository not available - requires p8fs-api module")


@pytest.fixture
async def jwt_manager():
    """Create JWT key manager for testing."""
    return JWTKeyManager()


@pytest.fixture
async def mobile_service(real_repository, jwt_manager):
    """Create mobile authentication service with real dependencies."""
    return MobileAuthenticationService(
        repository=real_repository,
        jwt_manager=jwt_manager
    )


@pytest.fixture
async def auth_service(real_repository, jwt_manager):
    """Create authentication service with real dependencies."""
    return AuthenticationService(
        repository=real_repository,
        jwt_manager=jwt_manager
    )


@pytest.fixture
def ed25519_keypair():
    """Generate Ed25519 keypair for testing."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Serialize public key for storage
    from cryptography.hazmat.primitives import serialization
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return {
        'private_key': private_key,
        'public_key': public_key,
        'public_key_pem': public_key_bytes.decode('utf-8')
    }


@pytest.mark.integration
class TestMobileAuthenticationFlow:
    """Test complete mobile authentication flow with real database operations."""
    
    async def test_device_registration_and_verification(self, mobile_service, ed25519_keypair):
        """Test complete device registration and email verification flow."""
        email = f"test-{pytest.__version__}@example.com"  # Unique email
        
        # Step 1: Register device
        device = await mobile_service.register_device(
            email=email,
            public_key=ed25519_keypair['public_key_pem'],
            device_name="Test iPhone"
        )
        
        assert device.email == email
        assert device.trust_level == DeviceTrustLevel.UNVERIFIED
        assert device.public_key == ed25519_keypair['public_key_pem']
        
        # Step 2: Verify device (simulate email verification)
        verification_result = await mobile_service.verify_device(
            device_id=device.device_id,
            verification_code=device.verification_code  # In real flow this comes from email
        )
        
        assert verification_result['success'] is True
        assert verification_result['device']['trust_level'] == DeviceTrustLevel.EMAIL_VERIFIED.value
    
    async def test_signature_authentication(self, mobile_service, ed25519_keypair):
        """Test signature-based authentication after device registration."""
        email = f"test-sig-{pytest.__version__}@example.com"
        
        # Register and verify device first
        device = await mobile_service.register_device(
            email=email,
            public_key=ed25519_keypair['public_key_pem'], 
            device_name="Test iPhone"
        )
        
        await mobile_service.verify_device(
            device_id=device.device_id,
            verification_code=device.verification_code
        )
        
        # Test signature authentication
        challenge = "test-challenge-12345"
        
        # Sign challenge with private key
        signature = ed25519_keypair['private_key'].sign(challenge.encode())
        signature_b64 = base64.b64encode(signature).decode()
        
        # Authenticate with signature
        auth_result = await mobile_service.authenticate_with_signature(
            device_id=device.device_id,
            challenge=challenge,
            signature_base64=signature_b64
        )
        
        assert 'access_token' in auth_result
        assert auth_result['token_type'] == 'Bearer'
        assert 'expires_in' in auth_result
        
        # Verify it's a proper JWT token (not mock)
        if hasattr(mobile_service, 'jwt_manager') and mobile_service.jwt_manager:
            # Should be a JWT token, not a mock token
            assert not auth_result['access_token'].startswith('mobile_token_')
            assert len(auth_result['access_token']) > 50  # JWTs are longer


@pytest.mark.integration 
class TestOAuthAuthenticationFlow:
    """Test OAuth 2.1 authentication flows with real database operations."""
    
    async def test_authorization_code_flow(self, auth_service):
        """Test OAuth authorization code exchange (will fail due to NotImplementedError)."""
        # This test should fail with NotImplementedError for now
        # since we properly fixed the hardcoded user_id issue
        
        with pytest.raises(NotImplementedError, match="Authorization code exchange not implemented"):
            await auth_service.exchange_authorization_code(
                client_id="test_client",
                code="test_code",
                redirect_uri="https://example.com/callback",
                code_verifier="test_verifier"
            )
    
    async def test_device_authorization_flow(self, auth_service):
        """Test device authorization flow initiation."""
        device_token = await auth_service.create_device_authorization(
            client_id="test_client",
            scope=["read", "write"]
        )
        
        assert device_token.device_code is not None
        assert device_token.user_code is not None
        assert device_token.verification_uri is not None
        assert device_token.expires_in > 0


@pytest.mark.integration
class TestJWTKeyManagement:
    """Test JWT key management with real cryptographic operations."""
    
    async def test_jwt_token_creation_and_verification(self, jwt_manager):
        """Test JWT token creation and verification with ES256."""
        # Create token
        token = await jwt_manager.create_access_token(
            user_id="test_user_123",
            client_id="test_client", 
            scope=["read", "write"]
        )
        
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are long
        
        # Verify token
        payload = await jwt_manager.verify_token(token)
        
        assert payload['user_id'] == "test_user_123"
        assert payload['client_id'] == "test_client" 
        assert payload['scope'] == "read write"
        assert 'exp' in payload
        assert 'iat' in payload
    
    async def test_jwks_endpoint_format(self, jwt_manager):
        """Test JWKS endpoint returns proper format."""
        jwks = await jwt_manager.get_jwks()
        
        assert 'keys' in jwks
        assert len(jwks['keys']) >= 1
        
        key = jwks['keys'][0]
        assert key['kty'] == 'EC'  # ES256 uses elliptic curve
        assert key['crv'] == 'P-256'
        assert key['alg'] == 'ES256'
        assert 'kid' in key
        assert 'x' in key
        assert 'y' in key