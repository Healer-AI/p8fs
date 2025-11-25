# P8FS Authentication Endpoint Implementation Guide

This document provides detailed implementation specifications for all P8FS authentication endpoints, including request/response formats, validation rules, and error handling.

## OAuth 2.1 Endpoint Implementation

### Authorization Endpoint

```python
@router.get("/oauth/authorize")
async def authorization_endpoint(
    client_id: str,
    response_type: Literal["code"],
    redirect_uri: str,
    scope: Optional[str] = None,
    state: Optional[str] = None,
    code_challenge: str,
    code_challenge_method: Literal["S256"] = "S256"
):
    """OAuth 2.1 authorization endpoint with mandatory PKCE."""
```

**Validation Rules:**
- `client_id` must be registered OAuth client
- `response_type` must be "code" (no implicit grant)
- `redirect_uri` must exactly match registered URI
- `code_challenge` must be valid base64url-encoded string
- `code_challenge_method` must be "S256"

**Implementation Steps:**
1. Validate client_id and redirect_uri
2. Generate authorization code (10-minute TTL)
3. Store PKCE challenge with authorization code
4. Redirect to client with authorization code and state

### Token Endpoint

```python
@router.post("/oauth/token")
async def token_endpoint(
    grant_type: str,
    client_id: str,
    code: Optional[str] = None,
    redirect_uri: Optional[str] = None,
    code_verifier: Optional[str] = None,
    refresh_token: Optional[str] = None,
    device_code: Optional[str] = None
):
    """OAuth 2.1 token endpoint supporting multiple grant types."""
```

**Grant Type Handlers:**

#### Authorization Code Grant
```python
if grant_type == "authorization_code":
    # Validate authorization code
    auth_code = await get_authorization_code(code)
    if not auth_code or auth_code.expired():
        raise InvalidGrantError()
    
    # Verify PKCE challenge
    if not verify_pkce(code_verifier, auth_code.code_challenge):
        raise InvalidGrantError()
    
    # Issue tokens
    return await issue_tokens(auth_code.user_id, client_id)
```

#### Refresh Token Grant
```python
if grant_type == "refresh_token":
    # Validate refresh token
    token = await validate_refresh_token(refresh_token)
    if not token:
        raise InvalidGrantError()
    
    # For public clients, rotate refresh token
    if client.is_public:
        await revoke_refresh_token(refresh_token)
    
    return await issue_tokens(token.user_id, client_id)
```

#### Device Code Grant
```python
if grant_type == "urn:ietf:params:oauth:grant-type:device_code":
    # Validate device code
    device = await get_device_code(device_code)
    if not device or not device.approved:
        raise AuthorizationPendingError()
    
    return await issue_tokens(device.user_id, client_id)
```

### Device Authorization Endpoint

```python
@router.post("/oauth/device/code")
async def device_authorization(
    client_id: str,
    scope: Optional[str] = None
):
    """Generate device and user codes for device flow."""
    
    # Generate codes
    device_code = generate_secure_code(43)  # URL-safe, 43 chars
    user_code = generate_user_code()        # Human-readable, 8 chars
    
    # Store device request
    await store_device_request(
        device_code=device_code,
        user_code=user_code,
        client_id=client_id,
        scope=scope,
        expires_in=600
    )
    
    return DeviceCodeResponse(
        device_code=device_code,
        user_code=user_code,
        verification_uri="https://auth.p8fs.com/device",
        verification_uri_complete=f"https://auth.p8fs.com/device?user_code={user_code}",
        expires_in=600,
        interval=5
    )
```

## Mobile Authentication Endpoints

### Device Registration

```python
@router.post("/api/v1/auth/register")
async def register_device(request: DeviceRegistrationRequest):
    """Register new mobile device with email verification."""
    
    # Validate public key format
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(request.public_key)
        )
    except Exception:
        raise ValidationError("Invalid public key format")
    
    # Check for existing registration
    existing = await get_user_by_email(request.email)
    if existing:
        raise ConflictError("Email already registered")
    
    # Generate verification code
    verification_code = generate_numeric_code(6)
    registration_id = generate_uuid()
    
    # Store pending registration
    await store_pending_registration(
        registration_id=registration_id,
        email=request.email,
        public_key=request.public_key,
        device_info=request.device_info,
        verification_code=verification_code,
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    
    # Send verification email
    await send_verification_email(
        email=request.email,
        code=verification_code,
        qr_url=f"https://auth.p8fs.com/verify?code={verification_code}"
    )
    
    return RegistrationResponse(
        registration_id=registration_id,
        expires_in=900
    )
```

### Email Verification

```python
@router.post("/api/v1/auth/verify")
async def verify_registration(request: VerificationRequest):
    """Complete device registration with email verification."""
    
    # Get pending registration
    registration = await get_pending_registration(request.registration_id)
    if not registration or registration.expired():
        raise InvalidRequestError("Invalid or expired registration")
    
    # Verify code
    if registration.verification_code != request.verification_code:
        await increment_verification_attempts(request.registration_id)
        raise InvalidRequestError("Invalid verification code")
    
    # Verify signature challenge
    challenge = f"{registration.email}:{request.verification_code}"
    if not verify_signature(
        message=challenge.encode(),
        signature=request.challenge_signature,
        public_key=registration.public_key
    ):
        raise InvalidRequestError("Invalid signature")
    
    # Create user and tenant
    user = await create_user(
        email=registration.email,
        public_key=registration.public_key,
        device_info=registration.device_info
    )
    
    # Issue OAuth tokens
    tokens = await issue_tokens(user.id, "mobile_client")
    
    # Clean up registration
    await delete_pending_registration(request.registration_id)
    
    return AuthenticationResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=user
    )
```

### Device Approval

```python
@router.post("/oauth/device/approve")
async def approve_device(
    request: DeviceApprovalRequest,
    current_user: User = Depends(get_current_user)
):
    """Approve device authorization from mobile app."""
    
    # Get device request
    device_request = await get_device_request_by_user_code(request.user_code)
    if not device_request or device_request.expired():
        raise InvalidRequestError("Invalid or expired user code")
    
    if request.approved:
        # Mark device as approved
        await approve_device_request(
            device_code=device_request.device_code,
            user_id=current_user.id,
            device_name=request.device_name
        )
        
        # Log approval event
        await log_device_approval(
            user_id=current_user.id,
            device_code=device_request.device_code,
            client_id=device_request.client_id
        )
    else:
        # Mark device as rejected
        await reject_device_request(device_request.device_code)
    
    return {"status": "approved" if request.approved else "rejected"}
```

## Credential Management Endpoints

### S3 Credentials Derivation

```python
@router.get("/api/v1/credentials/s3")
async def get_s3_credentials(
    current_user: User = Depends(get_current_user),
    session_id: Optional[str] = None
):
    """Derive S3 credentials from user session."""
    
    # Use current session or specified session
    if not session_id:
        session_id = current_user.current_session_id
    
    # Derive credentials using HKDF
    credentials = await derive_s3_credentials(
        session_id=session_id,
        tenant_id=current_user.tenant_id,
        device_id=current_user.current_device_id
    )
    
    return S3CredentialsResponse(
        access_key=credentials.access_key,
        secret_key=credentials.secret_key,
        session_token=credentials.session_token,
        expires_in=3600,
        bucket=f"tenant-{current_user.tenant_id}",
        region="us-east-1",
        endpoint_url="https://s3.p8fs.com"
    )
```

### API Key Generation

```python
@router.get("/api/v1/credentials/api")
async def generate_api_key(
    current_user: User = Depends(get_current_user),
    expires_in: int = 86400  # 24 hours default
):
    """Generate temporary API key for programmatic access."""
    
    # Generate API key with JWT
    api_key = jwt.encode(
        {
            "sub": current_user.id,
            "tenant": current_user.tenant_id,
            "device": current_user.current_device_id,
            "type": "api_key",
            "exp": datetime.utcnow() + timedelta(seconds=expires_in),
            "iat": datetime.utcnow()
        },
        key=get_jwt_signing_key(),
        algorithm="ES256"
    )
    
    # Store API key metadata
    await store_api_key_metadata(
        key_id=generate_uuid(),
        user_id=current_user.id,
        expires_at=datetime.utcnow() + timedelta(seconds=expires_in)
    )
    
    return APIKeyResponse(
        api_key=f"pk_live_{api_key}",
        expires_in=expires_in
    )
```

## Internal Webhook Endpoints

### S3 Request Validation

```python
@router.post("/internal/s3/validate")
async def validate_s3_request(
    request: S3ValidationRequest,
    webhook_secret: str = Depends(verify_webhook_secret)
):
    """Validate S3 request credentials via webhook."""
    
    try:
        # Parse S3 credentials
        access_key = request.access_key
        signature = request.signature
        string_to_sign = request.string_to_sign
        
        # Derive expected credentials
        session_info = parse_access_key(access_key)
        expected_secret = derive_secret_key(
            session_id=session_info.session_id,
            tenant_id=session_info.tenant_id,
            device_id=session_info.device_id
        )
        
        # Verify signature
        expected_signature = hmac_sha256(expected_secret, string_to_sign)
        if not hmac.compare_digest(signature, expected_signature):
            return ValidationResponse(valid=False, reason="Invalid signature")
        
        # Check session validity
        session = await get_session(session_info.session_id)
        if not session or session.expired():
            return ValidationResponse(valid=False, reason="Session expired")
        
        # Check tenant access
        if request.bucket != f"tenant-{session_info.tenant_id}":
            return ValidationResponse(valid=False, reason="Access denied")
        
        return ValidationResponse(
            valid=True,
            tenant_id=session_info.tenant_id,
            user_id=session.user_id
        )
        
    except Exception as e:
        logger.error(f"S3 validation error: {e}")
        return ValidationResponse(valid=False, reason="Validation error")
```

## Error Handling

### OAuth 2.1 Error Responses

```python
class OAuthError(HTTPException):
    def __init__(self, error: str, error_description: str, status_code: int = 400):
        self.error = error
        self.error_description = error_description
        super().__init__(status_code=status_code)

class InvalidRequestError(OAuthError):
    def __init__(self, description: str = "Invalid request"):
        super().__init__("invalid_request", description)

class InvalidClientError(OAuthError):
    def __init__(self, description: str = "Invalid client"):
        super().__init__("invalid_client", description, 401)

class InvalidGrantError(OAuthError):
    def __init__(self, description: str = "Invalid grant"):
        super().__init__("invalid_grant", description)

class AuthorizationPendingError(OAuthError):
    def __init__(self):
        super().__init__("authorization_pending", "User has not approved the request")

class SlowDownError(OAuthError):
    def __init__(self):
        super().__init__("slow_down", "Polling too frequently", 400)
```

### Error Response Format

```json
{
  "error": "invalid_request",
  "error_description": "Missing required parameter: code_verifier",
  "error_uri": "https://docs.p8fs.com/errors#invalid_request"
}
```

## Rate Limiting Implementation

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/oauth/token")
@limiter.limit("10/minute")
async def token_endpoint(request: Request, ...):
    """Rate-limited token endpoint."""
    
@router.post("/api/v1/auth/register")  
@limiter.limit("5/minute")
async def register_device(request: Request, ...):
    """Rate-limited registration endpoint."""
```

## Security Middleware

```python
@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    return response
```

## Testing Requirements

### Unit Tests
- Test each endpoint with valid/invalid inputs
- Verify PKCE implementation
- Test signature verification
- Validate error responses

### Integration Tests
- Complete OAuth flows
- Device registration and approval
- Credential derivation
- Webhook validation

### Security Tests
- PKCE downgrade attacks
- Signature bypass attempts
- Token hijacking scenarios
- Rate limit validation

This implementation guide provides the foundation for building a secure, OAuth 2.1 compliant authentication system with mobile-first capabilities and enterprise-grade security features.