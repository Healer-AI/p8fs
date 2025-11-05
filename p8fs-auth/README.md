# P8FS Authentication Module

Authentication, authorization, and encryption services for P8FS.

Design notes:
- Abstract repository interface with execute, get, put and upsert(list[any]) methods for tenant storage
- Store and retrieve tenants with email and public key
- References p8fs-cluster via PYTHONPATH for centralized configuration
- Device registration flows and OAuth 2.1 server implementation
- QR code based login for device approval (e.g., MCP client passing token via Claude Desktop)
- Lean code with minimal lines, delegation to utilities for simple flow logic
- Test-first approach with later UI integration

## Overview

Mobile-first authentication system with OAuth 2.1 support, device registration, and end-to-end encryption. Handles JWT management, credential derivation, and cryptographic operations.

## Architecture

### Core Components

#### Authentication Service
- User verification and session management
- Multi-factor authentication
- Account lockout and security policies

#### OAuth 2.1 Server
- Authorization code, device flow, and refresh token grants
- PKCE (Proof Key for Code Exchange) support
- Dynamic client registration

#### Device Management
- Device registration and lifecycle
- Trust levels and capabilities
- Remote revocation
- Device-specific access policies

#### Credential Service
- Key derivation (PBKDF2/Argon2)
- Hierarchical key generation
- Key rotation mechanisms

#### JWT Management
- Token signing and verification
- Key rotation with zero downtime
- Multiple signing algorithms
- Token introspection

#### Encryption Tools
- File encryption/decryption
- Key exchange protocols
- Secure random generation

#### Security Events
- Login attempt tracking
- Security event logging
- Audit trail generation

## Implementation

### Repository Interface

```python
class AuthRepository:
    def execute(self, query: str) -> Any
    def get(self, key: str) -> Optional[Any]
    def put(self, key: str, value: Any) -> None
    def upsert(self, items: List[Any]) -> None
```

### Configuration

All configuration from `p8fs_cluster.config.settings`:
- JWT algorithms and expiry
- Session storage backend
- Device trust levels
- Security policies

### API Endpoints

#### Authentication
- `POST /auth/register` - User registration
- `POST /auth/login` - User authentication
- `POST /auth/logout` - Session termination
- `POST /auth/refresh` - Token refresh

#### OAuth 2.1
- `GET /oauth/authorize` - Authorization endpoint
- `POST /oauth/token` - Token endpoint
- `POST /oauth/revoke` - Token revocation
- `POST /oauth/introspect` - Token introspection

#### Devices
- `POST /devices/register` - Register device
- `GET /devices` - List user devices
- `DELETE /devices/{id}` - Revoke device
- `POST /devices/{id}/trust` - Update trust level

## Security

### Mobile-First
- Client-side key generation
- Device attestation
- Platform secure storage
- Biometric integration

### Token Architecture
- Access tokens: 15 minutes
- Refresh tokens: Rotation on use
- ID tokens: User claims
- Device tokens: Device capabilities

### Encryption
- At-rest encryption for sensitive data
- TLS 1.3 minimum
- End-to-end encryption for user files
- Hierarchical key derivation

## Testing

### Unit Tests
- Mock external dependencies
- Test authentication flows
- Validate JWT operations
- Test encryption functions

### Integration Tests
- Full OAuth 2.1 flows
- Device registration
- Token refresh
- Multi-device scenarios

### CLI Tools

#### Development JWT Generation
```bash
# Generate a development JWT token
python -m p8fs_auth.cli generate-jwt --email user@example.com --tenant-id 123

# Generate JWT with custom expiry (in seconds)
python -m p8fs_auth.cli generate-jwt --email user@example.com --expiry 3600

# Generate JWT with specific claims
python -m p8fs_auth.cli generate-jwt --email user@example.com --claims '{"role": "admin"}'
```

#### QR Code Generation for Device Auth
```bash
# Generate QR code for device pairing
python -m p8fs_auth.cli generate-qr --device-id device123 --auth-url https://example.com/auth

# Generate QR code and save to file
python -m p8fs_auth.cli generate-qr --device-id device123 --output qrcode.png
```

#### Token Validation
```bash
# Validate a JWT token
python -m p8fs_auth.cli validate-token --token eyJ...

# Validate and decode token contents
python -m p8fs_auth.cli validate-token --token eyJ... --decode
```

#### Device Management
```bash
# Register a new device
python -m p8fs_auth.cli register-device --device-name "My Phone" --public-key "..."

# List all devices for a user
python -m p8fs_auth.cli list-devices --email user@example.com

# Revoke device access
python -m p8fs_auth.cli revoke-device --device-id device123
```

## Dependencies

- cryptography - Cryptographic operations
- pyjwt - JWT handling
- passlib - Password hashing
- argon2-cffi - Argon2 hashing
- pyotp - TOTP/HOTP support
- qrcode - QR code generation
- rich - CLI formatting 