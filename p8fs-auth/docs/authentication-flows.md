# P8FS Authentication Flows & Endpoints

This document provides a comprehensive overview of the P8FS authentication system flows and required endpoints for OAuth 2.1 and keypair management.

## System Architecture Overview

P8FS implements a **mobile-first, zero-trust authentication system** combining OAuth 2.1 standards with cryptographic innovation. Mobile devices serve as primary authentication factors and hardware security modules, enabling secure access for desktop applications, APIs, and distributed storage.

### Core Principles

1. **Zero Trust Architecture**: All components start with no permissions
2. **Mobile-First Security**: Mobile devices hold primary authentication keys
3. **OAuth 2.1 Compliance**: Latest OAuth security standards
4. **End-to-End Encryption**: No plaintext secrets transmission
5. **Tenant Isolation**: Complete user account separation
6. **Derived Credentials**: S3/API keys generated deterministically

## Authentication Flows

### Flow 1: Mobile Device Registration

Primary onboarding flow for new users with mobile devices.

```
1. User installs mobile app
2. App generates Ed25519 keypair locally
3. User enters email address
4. App sends registration request with public key
5. Server creates pending registration
6. Server sends verification code to email
7. User enters code in app
8. App signs verification with private key
9. Server validates signature and code
10. Server creates tenant and OAuth tokens
11. User authenticated on mobile device
```

**Required Endpoints:**
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/verify`

### Flow 2: Desktop Authentication via QR Code

Secure device pairing using mobile as authentication source.

```
1. Desktop app initiates OAuth device flow
2. Server returns device code and user code
3. Desktop displays QR code with user code
4. User scans QR with authenticated mobile app
5. Mobile retrieves device details from server
6. User approves device on mobile
7. Desktop polls token endpoint
8. Server issues OAuth tokens to desktop
9. Desktop authenticated via mobile approval
```

**Required Endpoints:**
- `POST /oauth/device/code`
- `POST /oauth/device/token`
- `GET /oauth/device/{user_code}`
- `POST /oauth/device/approve`

### Flow 3: API Access Token Flow

Standard OAuth 2.1 token refresh and access.

```
1. Client uses refresh token
2. Server validates refresh token
3. Server issues new access token
4. Client uses access token for API calls
5. Server validates bearer token
6. API request authorized
```

**Required Endpoints:**
- `POST /oauth/token`
- `POST /oauth/revoke`
- `POST /oauth/introspect`

### Flow 4: S3 Credential Derivation

Deterministic credential generation for storage access.

```
1. Client requests S3 credentials
2. Server derives credentials from session
3. Server returns temporary S3 keys
4. Client uses keys for storage operations
5. Storage validates keys via webhook
6. Storage operation authorized
```

**Required Endpoints:**
- `GET /api/v1/credentials/s3`
- `POST /internal/s3/validate`

## Keypair Management System

### Key Types & Algorithms

#### Mobile Device Keys (Ed25519)
- **Purpose**: Device authentication and challenge signing
- **Algorithm**: Ed25519 digital signatures
- **Storage**: Mobile device secure keychain/keystore
- **Scope**: Per-device unique keypair
- **Security**: Private key never leaves device, biometric protection

#### JWT Signing Keys (ES256)
- **Purpose**: Sign and verify JWT tokens
- **Algorithm**: ECDSA with P-256 curve (ES256)
- **Storage**: System-wide key in TiKV
- **Scope**: System-wide single signing key
- **Management**: Automatic rotation with zero downtime

**JWT Key Configuration for Developers:**

In development environments, JWT keys are configured via environment variables rather than generated dynamically:

1. **Generate ES256 Key Pair**:
   ```bash
   uv run python scripts/dev/generate_jwt_keys.py
   ```

2. **Set Environment Variables**:
   ```bash
   export P8FS_JWT_PRIVATE_KEY_PEM="-----BEGIN PRIVATE KEY-----..."
   export P8FS_JWT_PUBLIC_KEY_PEM="-----BEGIN PUBLIC KEY-----..."
   ```

3. **Production Configuration**:
   - In production, keys are managed by Kubernetes secrets
   - Keys are injected via ConfigMap into the environment
   - Key rotation is handled by updating the K8s secret

**Important**: If JWT keys are not configured, the authentication service will fail to start with a clear error message indicating that `P8FS_JWT_PRIVATE_KEY_PEM` and `P8FS_JWT_PUBLIC_KEY_PEM` must be set.

#### Key Exchange Keys (X25519)
- **Purpose**: Device pairing and secure communication
- **Algorithm**: X25519 ECDH key agreement
- **Duration**: Ephemeral, 10-minute TTL
- **Security**: Perfect forward secrecy

#### Credential Derivation (HKDF-SHA256)
- **Purpose**: Generate S3/API credentials deterministically
- **Algorithm**: HKDF-SHA256 key derivation
- **Inputs**: session_id, tenant_id, device_id, purpose
- **Benefits**: No stored secrets, reproducible keys

### Key Management Endpoints

| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|---------------|
| `/api/v1/auth/keypair/rotate` | POST | Rotate device keypair | Bearer token |
| `/api/v1/auth/devices` | GET | List authorized devices | Bearer token |
| `/api/v1/auth/devices/{id}` | DELETE | Revoke device access | Bearer token |
| `/api/v1/credentials/rotate` | POST | Force credential rotation | Bearer token |

## OAuth 2.1 Endpoints Specification

### Authorization Server Endpoints

#### Authorization Endpoint
```
GET /oauth/authorize
```
**Purpose**: OAuth 2.1 authorization code flow initiation
**Parameters**:
- `client_id` (required): OAuth client identifier
- `response_type=code` (required): Authorization code flow
- `redirect_uri` (required): Client callback URL
- `scope` (optional): Requested permissions
- `state` (recommended): CSRF protection token
- `code_challenge` (required): PKCE challenge
- `code_challenge_method=S256` (required): PKCE method

**Response**: Redirect to client with authorization code

#### Token Endpoint
```
POST /oauth/token
```
**Purpose**: Exchange authorization code for access tokens
**Content-Type**: `application/x-www-form-urlencoded`
**Parameters**:
- `grant_type` (required): `authorization_code`, `refresh_token`, or `urn:ietf:params:oauth:grant-type:device_code`
- `code` (auth code): Authorization code from authorize endpoint
- `redirect_uri` (auth code): Must match authorization request
- `code_verifier` (auth code): PKCE verifier
- `refresh_token` (refresh): Refresh token for new access token
- `device_code` (device): Device code from device flow
- `client_id` (required): OAuth client identifier

**Response** (OAuth 2.1 Compliant):
```json
{
  "access_token": "eyJhbGciOiJFUzI1NiIsImtpZCI6ImZpbGUta2V5IiwidHlwIjoiSldUIn0...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "6O00Tml8g5-HNeNWYpkOYNWOP7y9nAhCzeWbqaW1XAs",
  "scope": "read write"
}
```

**Token Types**:
- **access_token**: JWT with ES256 signature (verifiable, short-lived)
- **refresh_token**: Opaque random token (32 bytes base64, long-lived)

#### Device Authorization Endpoint
```
POST /oauth/device/code
```
**Purpose**: Initiate device authorization flow
**Parameters**:
- `client_id` (required): OAuth client identifier
- `scope` (optional): Requested permissions

**Response**:
```json
{
  "device_code": "abc123",
  "user_code": "WXYZ-1234",
  "verification_uri": "https://auth.p8fs.com/device",
  "verification_uri_complete": "https://auth.p8fs.com/device?user_code=WXYZ-1234",
  "expires_in": 600,
  "interval": 5
}
```

#### Token Revocation Endpoint
```
POST /oauth/revoke
```
**Purpose**: Revoke access or refresh tokens
**Parameters**:
- `token` (required): Token to revoke
- `token_type_hint` (optional): `access_token` or `refresh_token`
- `client_id` (required): OAuth client identifier

#### Token Introspection Endpoint
```
POST /oauth/introspect
```
**Purpose**: Validate and inspect tokens
**Parameters**:
- `token` (required): Token to introspect
- `token_type_hint` (optional): Token type hint

**Response**:
```json
{
  "active": true,
  "client_id": "client123",
  "username": "user@example.com",
  "scope": "read write",
  "exp": 1640995200,
  "iat": 1640991600
}
```

### Mobile Authentication Endpoints

#### Device Registration
```
POST /api/v1/auth/register
```
**Purpose**: Register new mobile device
**Request Body**:
```json
{
  "email": "user@example.com",
  "public_key": "302a300506032b657003210000...",
  "device_info": {
    "platform": "ios",
    "version": "16.0",
    "model": "iPhone14,2"
  }
}
```

**Response**:
```json
{
  "registration_id": "reg_abc123",
  "expires_in": 900
}
```

### Developer Endpoints

These endpoints are available only in development environments (`P8FS_ENVIRONMENT=development`) to facilitate testing and development workflows.

#### Dev Device Registration
```
POST /api/v1/auth/dev/register
```
**Purpose**: Register device with pre-approved email for development
**Request Body**:
```json
{
  "email": "dev@example.com",
  "public_key": "302a300506032b657003210000...",
  "device_info": {
    "platform": "macos",
    "version": "14.0",
    "model": "MacBookPro18,1",
    "imei": "optional-device-identifier"
  }
}
```

**Response** (OAuth 2.1 Compliant):
```json
{
  "access_token": "eyJhbGciOiJFUzI1NiIsImtpZCI6ImZpbGUta2V5IiwidHlwIjoiSldUIn0...",
  "refresh_token": "6O00Tml8g5-HNeNWYpkOYNWOP7y9nAhCzeWbqaW1XAs",
  "token_type": "Bearer",
  "expires_in": 86400,
  "tenant_id": "tenant-abc123"
}
```

**Token Structure**:
- **access_token**: JWT signed with ES256 (ECDSA P-256 curve)
  - Contains: user_id, client_id, scope, device_id, email, tenant
  - Lifetime: 24 hours (86400 seconds)
  - Verifiable with public key from `/.well-known/jwks.json`

- **refresh_token**: Opaque token (base64-encoded random 32 bytes)
  - Used for obtaining new access tokens via `/oauth/token` with `grant_type=refresh_token`
  - Lifetime: 30 days
  - Not a JWT - cannot be verified client-side

**Features**:
- Bypasses email verification for pre-approved emails
- Automatically creates tenant and device
- Returns OAuth 2.1 compliant tokens immediately
- Supports deterministic tenant ID generation via IMEI
- Saves tokens to `~/.p8fs/auth/token.json` when using CLI

**Security Note**: This endpoint is disabled in production environments

#### Email Verification
```
POST /api/v1/auth/verify
```
**Purpose**: Verify email code and complete registration
**Request Body**:
```json
{
  "registration_id": "reg_abc123",
  "verification_code": "123456",
  "challenge_signature": "304402201a2b3c..."
}
```

**Response** (OAuth 2.1 Compliant):
```json
{
  "access_token": "eyJhbGciOiJFUzI1NiIsImtpZCI6ImZpbGUta2V5IiwidHlwIjoiSldUIn0...",
  "refresh_token": "6O00Tml8g5-HNeNWYpkOYNWOP7y9nAhCzeWbqaW1XAs",
  "token_type": "Bearer",
  "expires_in": 3600,
  "tenant_id": "tenant_def456"
}
```

**Note**: User information (id, email) is embedded in the JWT access token claims, not returned separately

#### Device Approval
```
POST /oauth/device/approve
```
**Purpose**: Approve device from mobile app
**Request Body**:
```json
{
  "user_code": "WXYZ-1234",
  "approved": true,
  "device_name": "MacBook Pro"
}
```

### Credential Management Endpoints

#### S3 Credentials
```
GET /api/v1/credentials/s3
```
**Purpose**: Get S3 access credentials
**Response**:
```json
{
  "access_key": "AKIA...",
  "secret_key": "abc123...",
  "session_token": "def456...",
  "expires_in": 3600,
  "bucket": "tenant-def456",
  "region": "us-east-1"
}
```

#### API Key Generation
```
GET /api/v1/credentials/api
```
**Purpose**: Generate API key for programmatic access
**Response**:
```json
{
  "api_key": "pk_live_abc123...",
  "expires_in": 86400
}
```

## Client-Side Implementation Requirements

### Mobile App Requirements

1. **Cryptographic Key Generation**
   - Generate Ed25519 keypair using secure random
   - Store private key in platform keychain (iOS) or keystore (Android)
   - Require biometric authentication for key access

2. **Registration Flow Implementation**
   - Collect email address securely
   - Send registration request with public key
   - Handle verification code input
   - Sign challenges with private key

3. **Device Approval Flow**
   - Scan QR codes or handle deep links
   - Display device information for approval
   - Sign approval requests

4. **Token Management**
   - Store OAuth tokens securely
   - Implement automatic refresh
   - Handle token expiration gracefully

### Desktop App Requirements

1. **OAuth Device Flow**
   - Implement complete device authorization flow
   - Generate and display QR codes
   - Poll token endpoint with exponential backoff
   - Handle user rejection gracefully

2. **Credential Management**
   - Request fresh credentials as needed
   - Cache credentials securely
   - Handle credential expiration

3. **Error Handling**
   - Implement proper retry logic
   - Handle network errors
   - Provide clear user feedback

### API Client Requirements

1. **Authentication Headers**
   - Include Bearer tokens in Authorization header
   - Support API key authentication
   - Handle authentication errors (401/403)

2. **Token Refresh**
   - Implement automatic token refresh
   - Handle refresh token rotation
   - Queue requests during refresh

## Security Implementation Details

### OAuth 2.1 Compliance

P8FS implements OAuth 2.1 security best practices:

1. **Token Structure**:
   - **Access Tokens**: JWT with ES256 signature (ECDSA P-256 curve)
     - Self-contained with user claims (user_id, email, tenant, device_id)
     - Verifiable using public key from `/.well-known/jwks.json`
     - Cannot be revoked (rely on short expiration)

   - **Refresh Tokens**: Opaque random tokens (32 bytes base64)
     - Generated using `secrets.token_bytes(32)`
     - Not JWTs - server-side validation only
     - Can be revoked via `/oauth/revoke`
     - Rotated on each use for public clients

2. **Refresh Token Flow**:
   ```
   POST /oauth/token
   Content-Type: application/x-www-form-urlencoded

   grant_type=refresh_token
   &refresh_token=6O00Tml8g5-HNeNWYpkOYNWOP7y9nAhCzeWbqaW1XAs
   &client_id=my-client
   ```

   Response includes new access token and rotated refresh token (for public clients)

3. **Token Generation** (Implementation Reference):
   - Access tokens: `JWTKeyManager.create_access_token()` at p8fs-auth/src/p8fs_auth/services/jwt_key_manager.py:378
   - Refresh tokens: `base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')` at p8fs-auth/src/p8fs_auth/services/auth_service.py:540

### Token Security
- **Access Token Lifetime**: 1 hour (3600 seconds) for API, 24 hours (86400 seconds) for dev
- **Refresh Token Lifetime**: 30 days (2592000 seconds)
- **Device Code Lifetime**: 10 minutes (600 seconds)
- **Verification Code Lifetime**: 15 minutes (900 seconds)

### Rate Limiting
- Authentication endpoints: 5 requests/minute per IP
- Token endpoint: 10 requests/minute per client
- S3 validation webhook: 1000 requests/second

### Cryptographic Standards
- **Signatures**: Ed25519 for device authentication
- **Key Exchange**: X25519 for device pairing
- **Encryption**: ChaCha20-Poly1305 AEAD
- **Key Derivation**: HKDF-SHA256
- **JWT Signing**: ES256 (ECDSA with P-256)

### Security Headers
All endpoints must include appropriate security headers:
- `Strict-Transport-Security`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Content-Security-Policy`

This authentication system provides enterprise-grade security with mobile-first convenience, ensuring both usability and protection for the P8FS distributed storage platform.