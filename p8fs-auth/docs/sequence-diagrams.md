# P8FS Authentication Sequence Diagrams

This document provides visual sequence diagrams for the P8FS authentication flows.

## Flow 1: Mobile Device Registration with IMEI-Based Tenant

```mermaid
sequenceDiagram
    participant User
    participant MobileApp
    participant API
    participant DB
    participant Email

    User->>MobileApp: Install app, enter email
    MobileApp->>MobileApp: Generate Ed25519 keypair
    MobileApp->>MobileApp: Get device IMEI (if available)

    MobileApp->>API: POST /api/v1/auth/register<br/>{email, public_key, device_info: {imei}}
    API->>API: Generate verification code (6 digits)
    API->>API: Create registration_id
    API->>DB: Store pending registration (KV, TTL 15min)
    API->>Email: Send verification code
    API-->>MobileApp: {registration_id, expires_in: 900}

    Email-->>User: Verification code: 123456
    User->>MobileApp: Enter code: 123456

    MobileApp->>API: POST /api/v1/auth/verify<br/>{registration_id, verification_code}
    API->>DB: Retrieve pending registration
    API->>API: Verify code matches
    API->>API: Generate device_id

    alt IMEI provided
        API->>API: tenant_id = tenant-{SHA256(imei)[:16]}
        Note right of API: Deterministic tenant creation
    else No IMEI
        API->>API: tenant_id = tenant-{random_hex(16)}
        Note right of API: Random tenant creation
    end

    API->>DB: Create tenant (tenant_id, email, public_key)
    API->>DB: Create device in tenant metadata
    API->>API: Generate JWT with claims:<br/>{sub: device_id, email, tenant, device_id}
    API->>DB: Store access & refresh tokens
    API->>DB: Delete pending registration

    API-->>MobileApp: {access_token (JWT), refresh_token,<br/>tenant_id, expires_in}
    MobileApp->>MobileApp: Store tokens securely
    MobileApp-->>User: Registration complete!
```

## Flow 2: Desktop Authentication via QR Code

```mermaid
sequenceDiagram
    participant Desktop
    participant API
    participant DB
    participant MobileApp
    participant User

    Desktop->>API: POST /oauth/device/code<br/>{client_id}
    API->>API: Generate device_code, user_code
    API->>DB: Store device authorization (KV, TTL 10min)
    API-->>Desktop: {device_code, user_code,<br/>verification_uri, expires_in: 600}

    Desktop->>Desktop: Display QR code with user_code
    Desktop->>User: Show "Scan QR with mobile app"

    User->>MobileApp: Scan QR code
    MobileApp->>MobileApp: Extract user_code from QR
    MobileApp->>API: GET /oauth/device/{user_code}<br/>Authorization: Bearer <mobile_token>
    API->>API: Extract tenant_id from JWT
    API->>DB: Retrieve device authorization
    API-->>MobileApp: {client_id, device_code, scope}

    MobileApp-->>User: Show: "Approve Desktop access?"
    User->>MobileApp: Tap "Approve"

    MobileApp->>API: POST /oauth/device/approve<br/>{user_code, approved: true}
    API->>API: Extract tenant_id from mobile JWT
    API->>DB: Update authorization status to "approved"
    API->>API: Generate access & refresh tokens for desktop
    API->>DB: Store tokens with tenant_id
    API-->>MobileApp: {success: true}

    loop Desktop polling (every 5 seconds)
        Desktop->>API: POST /oauth/token<br/>{grant_type: device_code, device_code}
        API->>DB: Check device authorization status

        alt Not yet approved
            API-->>Desktop: 400 authorization_pending
        else Approved
            API->>DB: Retrieve tokens
            API->>DB: Mark as consumed
            API-->>Desktop: {access_token (JWT), refresh_token,<br/>token_type: Bearer, expires_in}
            Desktop->>Desktop: Store tokens securely
        end
    end
```

## Flow 3: Token Refresh

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant DB

    Client->>API: POST /oauth/token<br/>{grant_type: refresh_token,<br/>refresh_token, client_id}
    API->>DB: Lookup refresh token

    alt Token valid and not expired
        API->>API: Extract tenant_id from stored token
        API->>API: Generate new JWT access token<br/>{sub, email, tenant, device_id}
        API->>DB: Generate new refresh token (rotation)
        API->>DB: Revoke old refresh token
        API->>DB: Store new tokens
        API-->>Client: {access_token (JWT), refresh_token,<br/>expires_in, scope}
    else Token invalid/expired/revoked
        API-->>Client: 400 invalid_grant
    end
```

## Flow 4: Device Re-authentication with Signature

**CRITICAL**: This flow requires tenant_id from JWT token context!

```mermaid
sequenceDiagram
    participant Device
    participant API
    participant AuthMiddleware
    participant MobileService
    participant DB

    Note over Device: Access token expired,<br/>need to re-authenticate

    Device->>Device: Generate random challenge (nonce)
    Device->>Device: Sign challenge with Ed25519 private key

    Device->>API: POST /api/v1/auth/devices/authenticate<br/>Authorization: Bearer <expired_or_valid_token><br/>{device_id, challenge, signature}

    API->>AuthMiddleware: Extract JWT from Authorization header
    AuthMiddleware->>AuthMiddleware: Decode JWT (even if expired)
    AuthMiddleware->>AuthMiddleware: Extract tenant claim

    alt Token missing tenant claim
        AuthMiddleware-->>API: 401 Unauthorized
        API-->>Device: 401 AUTH_INVALID_TOKEN_TENANT
    else Token has tenant claim
        AuthMiddleware->>API: Pass tenant_id to endpoint

        API->>MobileService: authenticate_with_signature(<br/>device_id, challenge, signature, tenant_id)

        MobileService->>DB: get_device(device_id, tenant_id)

        alt Device not found in tenant
            MobileService-->>API: MobileAuthenticationError
            API-->>Device: 404 Device not found
        else Device found
            MobileService->>MobileService: Load device public key from DB
            MobileService->>MobileService: Verify signature(challenge, signature, public_key)

            alt Signature invalid
                MobileService-->>API: MobileAuthenticationError
                API-->>Device: 401 Invalid signature
            else Signature valid
                MobileService->>MobileService: Generate new JWT with claims:<br/>{sub: device_id, email, tenant, device_id}
                MobileService->>DB: Store new access & refresh tokens
                MobileService-->>API: {access_token (JWT), refresh_token}
                API-->>Device: 200 {access_token, refresh_token,<br/>expires_in, token_type: Bearer}
                Device->>Device: Store new tokens
            end
        end
    end
```

## JWT Token Structure

All access tokens are JWTs with the following claims:

```json
{
  "iss": "p8fs-auth",
  "aud": "p8fs-api",
  "sub": "device-abc123...",
  "user_id": "device-abc123...",
  "email": "user@example.com",
  "tenant": "tenant-e27a7686b8028cfe",
  "device_id": "device-abc123...",
  "device_name": "iPhone 14",
  "client_id": "mobile_device",
  "scope": "read write",
  "exp": 1731877277,
  "iat": 1731873677,
  "jti": "b7f01c8d-1e18-4a1c-8a85-fd1327082fe2",
  "kid": "file-key"
}
```

**Critical Claims**:
- `tenant`: Required for all authenticated requests, enables tenant-scoped resource access
- `device_id`: Links token to specific device for security auditing
- `sub`: Subject (device_id for device tokens, user_id for user tokens)

## Key Implementation Notes

### Tenant Scoping Requirements

1. **All device lookups must include tenant_id**:
   ```python
   # ✅ CORRECT
   device = await auth_repo.get_device(device_id, tenant_id=user.tenant_id)

   # ❌ WRONG - Will return None in production
   device = await auth_repo.get_device(device_id)
   ```

2. **Extract tenant from JWT context**:
   ```python
   # Auth middleware provides tenant_id from JWT
   async def endpoint(user: User = Depends(get_current_user)):
       tenant_id = user.tenant_id  # From JWT 'tenant' claim
   ```

3. **Device registration includes tenant in JWT**:
   ```python
   # mobile_service.py:294-303
   tokens = await self.auth_service._issue_tokens(
       user_id=device.device_id,
       client_id="mobile_device",
       scope=["read", "write"],
       additional_claims={
           "email": device.email,
           "tenant": tenant_id,  # ← CRITICAL
           "device_name": device.device_name,
           "device_id": device.device_id
       }
   )
   ```

### IMEI-Based Tenant Generation

```python
# mobile_service.py:336-382
if device_info and device_info.get("imei"):
    # Deterministic tenant ID from IMEI
    imei = device_info["imei"]
    imei_hash = hashlib.sha256(imei.encode()).hexdigest()[:16]
    tenant_id = f"tenant-{imei_hash}"
else:
    # Random tenant ID
    tenant_id = f"tenant-{secrets.token_hex(16)}"
```

**Benefits**:
- Same IMEI → Same tenant (device replacement/reinstall preserves data)
- Different IMEI → Different tenant (multi-device isolation)
- No IMEI → Random tenant (legacy/test devices)
