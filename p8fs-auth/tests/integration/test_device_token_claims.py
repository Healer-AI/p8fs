"""Integration test for device JWT token claims.

Verifies that device tokens include proper tenant claim.
Tests the fix for: device tokens missing tenant claim causing auth failures.
"""

import base64
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from p8fs_auth.services.mobile_service import MobileAuthenticationService
from p8fs_auth.services.jwt_key_manager import JWTKeyManager
from p8fs_auth.services.auth_service import AuthenticationService


@pytest.fixture
async def real_repository():
    """Get the real P8FSAuthRepository for integration testing."""
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
async def auth_service(real_repository, jwt_manager):
    """Create authentication service with real dependencies."""
    return AuthenticationService(
        repository=real_repository,
        jwt_manager=jwt_manager
    )


@pytest.fixture
async def mobile_service(real_repository, auth_service):
    """Create mobile authentication service with real dependencies."""
    return MobileAuthenticationService(
        repository=real_repository,
        auth_service=auth_service
    )


def decode_jwt_without_verification(token: str) -> dict:
    """Decode JWT token without signature verification (for testing claims)."""
    return jwt.decode(token, options={"verify_signature": False})


@pytest.mark.integration
class TestDeviceTokenClaims:
    """Test that device JWT tokens contain required claims."""

    async def test_device_token_contains_tenant_claim(self, mobile_service, jwt_manager):
        """Test that device token includes tenant claim after verification."""
        # Generate Ed25519 keypair
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key_bytes = private_key.public_key().public_bytes_raw()
        public_key_b64 = base64.b64encode(public_key_bytes).decode('utf-8')

        email = f"tenant-test-{pytest.__version__}@example.com"

        # Step 1: Register device
        registration = await mobile_service.register_device(
            email=email,
            public_key_base64=public_key_b64,
            device_name="Test Device",
            device_info={"platform": "iOS", "imei": "123456789012345"}
        )

        registration_id = registration["registration_id"]
        verification_code = registration["verification_code"]

        # Step 2: Verify device (this generates the JWT token)
        result = await mobile_service.verify_pending_registration(
            registration_id=registration_id,
            verification_code=verification_code
        )

        # Step 3: Check that token was returned
        assert "access_token" in result, "Token should be returned after verification"
        access_token = result["access_token"]

        # Step 4: Decode JWT and verify claims
        claims = decode_jwt_without_verification(access_token)

        print(f"\n🔍 JWT Claims: {claims}")

        # Critical assertions
        assert "tenant" in claims or "tenant_id" in claims, \
            f"Token missing tenant claim! Claims: {claims}"

        tenant = claims.get("tenant") or claims.get("tenant_id")
        assert tenant is not None, "Tenant value is None"
        assert tenant.startswith("tenant-"), \
            f"Tenant should start with 'tenant-', got: {tenant}"

        # Additional expected claims
        assert "sub" in claims, "Token missing 'sub' claim"
        assert "email" in claims, "Token missing 'email' claim"
        assert "device_id" in claims, "Token missing 'device_id' claim"
        assert claims["email"] == email, f"Email mismatch: {claims['email']} != {email}"

        print(f"✅ Token contains tenant claim: {tenant}")

    async def test_device_authentication_token_contains_tenant(self, mobile_service):
        """Test that authentication with signature also includes tenant claim."""
        # Generate Ed25519 keypair
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key_bytes = private_key.public_key().public_bytes_raw()
        public_key_b64 = base64.b64encode(public_key_bytes).decode('utf-8')

        email = f"auth-test-{pytest.__version__}@example.com"

        # Step 1: Register and verify device
        registration = await mobile_service.register_device(
            email=email,
            public_key_base64=public_key_b64,
            device_name="Test Device",
            device_info={"platform": "iOS"}
        )

        registration_id = registration["registration_id"]
        verification_code = registration["verification_code"]

        verify_result = await mobile_service.verify_pending_registration(
            registration_id=registration_id,
            verification_code=verification_code
        )

        device_id = verify_result["device_id"]
        tenant_id = verify_result["tenant_id"]

        # Step 2: Authenticate with signature (passing tenant_id from JWT context)
        challenge = "test-challenge-12345"
        signature = private_key.sign(challenge.encode())
        signature_b64 = base64.b64encode(signature).decode()

        auth_result = await mobile_service.authenticate_with_signature(
            device_id=device_id,
            challenge=challenge,
            signature_base64=signature_b64,
            tenant_id=tenant_id  # From JWT token context
        )

        # Step 3: Verify token claims
        access_token = auth_result["access_token"]
        claims = decode_jwt_without_verification(access_token)

        print(f"\n🔍 Auth JWT Claims: {claims}")

        # Critical assertion
        assert "tenant" in claims or "tenant_id" in claims, \
            f"Auth token missing tenant claim! Claims: {claims}"

        tenant = claims.get("tenant") or claims.get("tenant_id")
        assert tenant.startswith("tenant-"), \
            f"Tenant should start with 'tenant-', got: {tenant}"

        print(f"✅ Auth token contains tenant claim: {tenant}")


if __name__ == "__main__":
    import asyncio

    async def run_tests():
        """Run tests manually."""
        # Setup
        from p8fs_api.repositories.auth_repository import P8FSAuthRepository

        repo = P8FSAuthRepository()
        jwt_mgr = JWTKeyManager()
        auth_svc = AuthenticationService(repository=repo, jwt_manager=jwt_mgr)
        mobile_svc = MobileAuthenticationService(repository=repo, auth_service=auth_svc)

        test_instance = TestDeviceTokenClaims()

        try:
            print("🧪 Running: test_device_token_contains_tenant_claim")
            await test_instance.test_device_token_contains_tenant_claim(mobile_svc, jwt_mgr)
            print("✅ PASSED\n")

            print("🧪 Running: test_device_authentication_token_contains_tenant")
            await test_instance.test_device_authentication_token_contains_tenant(mobile_svc)
            print("✅ PASSED\n")

            print("🎉 All tests passed!")
        except AssertionError as e:
            print(f"❌ Test failed: {e}")
            raise

    asyncio.run(run_tests())
