# P8FS Auth Module

## Module Overview

The P8FS Auth module provides authentication and encryption functionality for the entire P8FS system. It implements mobile-first keypair generation, OAuth 2.1 token issuance, and end-to-end encryption capabilities with client-held keys.

## Architecture

### Core Components

- **Mobile Keypair Generation**: Client-side key generation for mobile devices
- **OAuth 2.1 Token Service**: Secure token issuance and validation
- **End-to-End Encryption**: Client-held key encryption utilities
- **Public Key Infrastructure**: Key management and distribution

### Key Features

- Mobile-optimized cryptographic operations
- OAuth 2.1 compliance with security best practices
- Zero-knowledge architecture with client-held keys
- Cross-platform encryption support

## Development Standards

### Code Quality

- Write minimal, efficient code with clear intent
- Avoid workarounds; implement proper solutions
- Prioritize maintainability over quick fixes
- Keep implementations lean and purposeful
- No comments unless absolutely necessary for complex cryptographic operations

### Security First Principles

- Never store private keys on the server
- Implement proper key rotation mechanisms
- Use industry-standard cryptographic libraries
- Validate all cryptographic inputs
- Implement constant-time operations where applicable

### Testing Requirements

#### Unit Tests
- Mock cryptographic operations for speed
- Test key generation and validation logic
- Validate token creation and verification
- Test encryption/decryption flows

#### Integration Tests
- Use real cryptographic operations
- Test complete authentication flows
- Validate cross-platform compatibility
- Test key exchange protocols

### Configuration

All configuration must come from the centralized system in `p8fs_cluster.config.settings`. Never hardcode cryptographic parameters or endpoints.

```python
# ✅ CORRECT - Use centralized config
from p8fs_cluster.config.settings import config

# Access auth-specific configuration
jwt_secret = config.auth_jwt_secret
token_expiry = config.auth_token_expiry
key_size = config.auth_key_size

# ✅ CORRECT - Use config for crypto parameters
def generate_keypair():
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=config.auth_key_size
    )
```

```python
# ❌ WRONG - Don't hardcode crypto parameters
# JWT_SECRET="hardcoded-secret"
# KEY_SIZE=2048

# ❌ WRONG - Don't hardcode configuration
def generate_keypair():
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048  # Hardcoded
    )
```

### Authentication Architecture

### Simple Tenant-Based Authentication

P8FS uses a minimal tenant-based authentication system with a single `Tenant` table for user management.

#### Tenant Model
```python
class Tenant:
    tenant_id: str      # Format: "tenant-{hash}" - unique identifier
    email: str          # User's email address
    public_key: str     # Client-generated public key (PEM format)
    # Future: payment_data, subscription_info, etc.
```

#### Database Operations

The system performs only two core database operations:

```python
# Get tenant by tenant_id
async def get_tenant(tenant_id: str) -> Tenant | None:
    """Retrieve tenant by their unique tenant_id."""
    return await repository.get_tenant_by_id(tenant_id)

# Store/update tenant
async def set_tenant(tenant: Tenant) -> Tenant:
    """Create or update tenant record."""
    return await repository.create_tenant(tenant) 
```

#### Session Management

Tenants are used to manage client sessions but we store minimal user data:

```python
from p8fs_cluster.config.settings import config
from p8fs.repository.TenantRepository import TenantRepository

class AuthService:
    def __init__(self):
        self.tenant_repo = TenantRepository()
    
    async def create_session(self, email: str, public_key: str) -> str:
        """Create new tenant session."""
        import hashlib
        
        # Generate tenant_id from email hash
        email_hash = hashlib.sha256(email.encode()).hexdigest()[:16]
        tenant_id = f"tenant-{email_hash}"
        
        # Create or update tenant record
        tenant = Tenant(
            tenant_id=tenant_id,
            email=email,
            public_key=public_key
        )
        
        await self.tenant_repo.create_tenant(tenant)
        return tenant_id
    
    async def validate_session(self, tenant_id: str) -> Tenant | None:
        """Validate tenant session."""
        return await self.tenant_repo.get_tenant_by_id(tenant_id)
```

#### JWT Token Integration

Tokens reference the tenant_id for session management:

```python
from p8fs_auth.services.jwt_key_manager import JWTKeyManager

class TokenService:
    def __init__(self):
        self.jwt_manager = JWTKeyManager()
    
    async def create_tenant_token(self, tenant_id: str, email: str) -> str:
        """Create JWT token for tenant session."""
        return await self.jwt_manager.create_access_token(
            user_id=tenant_id,  # Use tenant_id as user identifier
            client_id="p8fs_client",
            scope=["read", "write"],
            additional_claims={
                "email": email,
                "tenant": tenant_id
            }
        )
    
    async def verify_tenant_token(self, token: str) -> dict:
        """Verify token and return tenant claims."""
        payload = await self.jwt_manager.verify_token(token)
        return {
            "tenant_id": payload.get("user_id"),
            "email": payload.get("email"),
            "scope": payload.get("scope", "").split()
        }
```

## Testing Approach

### Test Structure
```
tests/
├── unit/
│   ├── test_keypair_generation.py
│   ├── test_token_service.py
│   └── test_encryption.py
└── integration/
    ├── test_auth_flow.py
    └── test_mobile_integration.py
```

### Running Tests
```bash
# Unit tests with mocks
pytest tests/unit/ -v

# Integration tests with real crypto
pytest tests/integration/ -v

# All tests
pytest tests/ -v
```

### Example Test Patterns

#### Unit Test with Mocks
```python
from unittest.mock import Mock, patch
import pytest
from p8fs_auth.services.token_service import TokenService

@patch('p8fs_auth.services.token_service.config')
def test_token_creation(mock_config):
    mock_config.auth_jwt_secret = "test-secret"
    mock_config.auth_token_expiry = 3600
    
    service = TokenService()
    token = service.create_token("user123", "key_hash")
    
    assert token is not None
    decoded = service.verify_token(token)
    assert decoded['user_id'] == "user123"
```

#### Integration Test
```python
import pytest
from p8fs_auth.services.keypair_generator import MobileKeyGenerator
from p8fs_auth.services.encryption_service import EncryptionService

@pytest.mark.integration
def test_end_to_end_encryption():
    # Generate real keypair
    keypair = MobileKeyGenerator.generate_keypair()
    
    # Test encryption/decryption
    test_data = b"Secret message"
    encrypted = EncryptionService.encrypt_data(
        keypair['public_key'], 
        test_data
    )
    
    decrypted = EncryptionService.decrypt_data(
        keypair['private_key'], 
        encrypted
    )
    
    assert decrypted == test_data
```

## Security Considerations

### Key Management
- Private keys never leave the client device
- Public keys are distributed through secure channels
- Implement proper key rotation schedules
- Use secure key storage mechanisms

### Token Security
- Use short-lived tokens with refresh mechanism
- Implement proper token revocation
- Validate token signatures and expiry
- Use secure random generation for secrets

### Encryption Standards
- Use AES-256 for symmetric encryption
- Use RSA-2048+ for asymmetric encryption
- Implement proper padding (OAEP for RSA)
- Use secure hash functions (SHA-256+)

## Dependencies

- **cryptography**: Primary cryptographic library
- **PyJWT**: JWT token implementation
- **p8fs-cluster**: Configuration and logging

## Development Workflow

1. Install dependencies:
   ```bash
   pip install cryptography PyJWT
   ```

2. Run tests:
   ```bash
   pytest tests/ -v
   ```

3. Lint and type check:
   ```bash
   ruff check src/
   mypy src/
   ```

## Error Handling

Implement consistent error handling for cryptographic operations:

```python
from p8fs_auth.exceptions import (
    InvalidKeyError,
    TokenExpiredError,
    DecryptionError
)

class AuthenticationError(Exception):
    pass

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.auth_jwt_secret, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token")
```

## Mobile Integration

The auth module is designed for mobile-first usage:

```python
# Mobile client keypair generation
class MobileAuthClient:
    def __init__(self):
        self.keypair = None
    
    def initialize(self):
        self.keypair = MobileKeyGenerator.generate_keypair()
        # Store private key securely on device
        self._store_private_key_securely(self.keypair['private_key'])
    
    def get_public_key_for_registration(self) -> bytes:
        return self.keypair['public_key_pem']
    
    def decrypt_message(self, encrypted_data: bytes) -> bytes:
        private_key = self._load_private_key_securely()
        return EncryptionService.decrypt_data(private_key, encrypted_data)
```

## Performance Considerations

- Use async operations for cryptographic functions
- Implement proper connection pooling for token validation
- Cache public keys to avoid repeated lookups
- Use efficient serialization for key exchange

## Device Authorization Flow Implementation

The device authorization flow (OAuth Device Flow) is implemented using KV storage for temporary pending requests:

### Flow Architecture

1. **Desktop App Request** → Server stores pending request in KV storage
2. **Mobile User Approval** → Server updates pending request with approval
3. **Desktop App Polling** → Server returns token and cleans up request

### KV Storage for Pending Requests

Device authorization uses temporary KV storage independent of tenant data:

```python
from p8fs.models.device_auth import PendingDeviceRequest
from p8fs_auth.services.auth_service import AuthenticationService

auth_service = AuthenticationService(repository, jwt_manager)

# 1. Desktop requests device code
device_token = await auth_service.create_device_authorization(
    client_id="desktop_app",
    scope=["read", "write"]
)
# → Stores pending request in KV: device_auth:{device_code}

# 2. Mobile user approves via user_code  
await auth_service.approve_device_authorization(
    user_code="A1B2-C3D4",
    user_id="tenant-123",  # Tenant ID of mobile user
    device_id="mobile_device_456" 
)
# → Updates pending request with approval and access token

# 3. Desktop polls for token
tokens = await auth_service.poll_device_token(
    client_id="desktop_app", 
    device_code=device_token.device_code
)
# → Returns token and deletes pending request
```

### KV Storage Keys

**Primary Storage**: `device_auth:{device_code}` → PendingDeviceRequest
**User Code Lookup**: `user_code:{user_code}` → {device_code}

### Pending Request Structure

```python
class PendingDeviceRequest:
    device_code: str          # Long secure code for polling
    user_code: str            # Short human-friendly code  
    client_id: str            # Desktop app client ID
    scope: List[str]          # Requested permissions
    
    # Status tracking
    status: DeviceAuthStatus  # pending/approved/expired/consumed
    created_at: datetime      # Request timestamp
    expires_at: datetime      # TTL expiration
    
    # Approval data (set by mobile user)
    approved_at: datetime     # When approved
    approved_by_tenant: str   # Tenant ID that approved
    access_token: str         # Generated JWT token
```

### Provider-Specific KV Storage

- **PostgreSQL**: Uses `kv_storage` table with JSON values and TTL
- **TiKV**: Direct key-value storage with native TTL (production)
- **RocksDB**: Embedded storage (development)

### Device Metadata in Tenants

For ongoing device management, device info is stored in tenant metadata:

```json
{
  "devices": {
    "device_abc123": {
      "device_id": "device_abc123", 
      "public_key": "base64_key",
      "device_name": "iPhone 15",
      "trust_level": "EMAIL_VERIFIED",
      "last_used_at": "2025-01-15T15:45:00"
    }
  }
}
```

This separates temporary authorization flow state (KV storage) from persistent device management (tenant metadata).