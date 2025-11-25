"""OAuth 2.1 Authentication Router with MCP Compliance.
See spec https://www.ietf.org/archive/id/draft-ietf-oauth-v2-1-13.html#section-5.2
See also open-id https://openid.net/specs/openid-connect-core-1_0.html which sits on top of oauth

Our auth system allows for phones to be registered and creating tenants. 
The phone generates a keypair and it alone can approve devices.
We generate JWT tokens first when the device is registered and after when devices are approved.
To approve devices a login/device page is shown with a QR code and 8 digit code that the mobile app can approve securely.
After that JWT tokens are managed using standard Oauth specification with token refresh etc.

This module implements the OAuth 2.1 authorization framework as specified in:
- RFC 6749: The OAuth 2.0 Authorization Framework
- RFC 7636: Proof Key for Code Exchange (PKCE)
- RFC 8628: OAuth 2.0 Device Authorization Grant
- OAuth 2.1 Draft: Consolidated best practices

MCP (Model Context Protocol) Specification Compliance:
The implementation follows MCP's authorization requirements from:
https://modelcontextprotocol.io/specification/draft/basic/authorization

Implemented MCP Sections:
✅ Authorization Server Discovery
   - OpenID Connect Discovery at /.well-known/openid-configuration
   - OAuth 2.0 Authorization Server Metadata
   
✅ PKCE (Proof Key for Code Exchange)
   - Mandatory S256 code challenge method
   - No support for plain method (deprecated)
   
✅ Device Authorization Grant
   - Enhanced with QR code generation
   - Mobile-first authentication flow
   
✅ Bearer Token Usage
   - Authorization header with Bearer scheme
   - Token validation in middleware
   
⚠️ Partially Implemented:
   - Dynamic Client Registration (basic implementation)
   - Token introspection and revocation
   
❌ Not Implemented (TODO):
   - Resource parameter for token audience binding
   - OAuth 2.0 Protected Resource Metadata (RFC9728)
   - Refresh token rotation for public clients
   - Token family tracking for security
   
⚠️ OpenID Connect Status:
   - Discovery endpoint claims OpenID support but not fully implemented
   - Strong JWT infrastructure with ES256 signing already in place
   - No ID tokens issued (only access tokens)
   - Userinfo endpoint deprecated and non-compliant
   - No 'openid' scope handling
   
   Path to OpenID Connect Compliance:
   - Minimal changes needed due to existing JWT infrastructure
   - Add ID token generation when 'openid' scope requested
   - Fix userinfo endpoint to accept Bearer tokens
   - Add nonce parameter support
   - Separate access token (API) and ID token (identity) concerns
   
   Recommendation: Implement minimal OpenID support using existing JWT infrastructure

Architecture:
The router is split into three sub-routers:
1. public_router: No authentication required (OAuth endpoints)
2. protected_router: JWT authentication required (user endpoints)
3. dev_router: Development-only endpoints with special auth

All OAuth operations delegate to AuthController which uses p8fs-auth services.
"""

from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, Form, Header, Query, Request, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from p8fs_cluster.config.settings import config
from pydantic import BaseModel

from ..controllers import AuthController
from ..middleware import User, get_current_user
from ..models import (
    AuthTokenResponse,
    AuthorizationParams,
    DeviceCodeResponse,
    DeviceVerificationPageContext,
    RegistrationResponse,
)
from p8fs_auth.services.jwt_key_manager import JWTKeyManager
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

# Public OAuth endpoints (no auth required)
public_router = APIRouter(prefix="/api/v1/oauth", tags=["Authentication - Public"])

# Protected OAuth endpoints (JWT auth required)
protected_router = APIRouter(
    prefix="/api/v1/oauth",
    tags=["Authentication - Protected"],
    dependencies=[Depends(get_current_user)],
)

# Development endpoints (dev token auth required)
dev_router = APIRouter(prefix="/api/v1/auth/dev", tags=["Development"])

auth_controller = AuthController()
jwt_key_manager = JWTKeyManager()

# Setup Jinja2 templates
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


class DeviceRegistrationRequest(BaseModel):
    """Device registration request."""

    email: str
    public_key: str
    device_info: dict[str, Any]


class VerificationRequest(BaseModel):
    """Email verification request."""

    registration_id: str
    verification_code: str
    challenge_signature: str


class DeviceApprovalRequest(BaseModel):
    """Device approval request with optional device-bound authentication."""

    user_code: str
    approved: bool
    device_name: str | None = None
    challenge: str | None = None  # Challenge that was signed (e.g., "approve:{user_code}")
    signature: str | None = None  # Base64-encoded Ed25519 signature of challenge


# Public OAuth 2.1 Endpoints


@public_router.post("/token", response_model=AuthTokenResponse)
async def token_endpoint(
    grant_type: str = Form(),
    client_id: str = Form(),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    code_verifier: str | None = Form(None),
    refresh_token: str | None = Form(None),
    device_code: str | None = Form(None),
    resource: str | None = Form(None),  # MCP Token Audience Binding
):
    """OAuth 2.1 token endpoint.

    MCP Specification: Token Endpoint
    - Implements authorization_code, refresh_token, device_code grants
    - Supports resource parameter for token audience binding (MCP compliance)
    
    OpenID Connect Gap:
    - Does NOT issue ID tokens for authorization_code grant
    - Only returns access_token and refresh_token
    - Minimal changes needed for OpenID compliance:
      1. Check for 'openid' scope in token request
      2. Generate ID token using existing JWT infrastructure
      3. Add id_token field to AuthTokenResponse
      4. Include client_id as audience for ID tokens
    """
    return await auth_controller.token_endpoint(
        grant_type=grant_type,
        client_id=client_id,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        refresh_token=refresh_token,
        device_code=device_code,
        resource=resource,
    )


# Removed /device/code - use standard /device_authorization endpoint instead


@public_router.post("/device_authorization", response_model=DeviceCodeResponse)
async def device_authorization_standard(
    client_id: str = Form(), scope: str | None = Form(None)
):
    """OAuth 2.0 Device Authorization Grant endpoint (RFC 8628).

    MCP Specification: Device Authorization Grant
    Implements the standard OAuth device flow with enhancements:

    Request:
    - client_id: OAuth client identifier (required)
    - scope: Space-delimited list of requested scopes (optional)

    Response (DeviceCodeResponse):
    - device_code: Long code for polling token endpoint
    - user_code: Short code for user entry (format: XXXX-YYYY)
    - verification_uri: URL for user to visit
    - verification_uri_complete: URL with user_code pre-filled
    - expires_in: Lifetime in seconds (default: 600)
    - interval: Minimum polling interval in seconds (default: 5)
    - qr_code: Base64-encoded QR code image (P8FS enhancement)

    This endpoint supports both standard OAuth device flow and our enhanced
    QR code flow for mobile authentication.
    """
    return await auth_controller.device_authorization(client_id=client_id, scope=scope)


# Backward compatibility alias for /device/code
@public_router.post("/device/code", response_model=DeviceCodeResponse, include_in_schema=False)
async def device_code_legacy(
    client_id: str = Form(), scope: str | None = Form(None)
):
    """Legacy endpoint for backward compatibility. Use /device_authorization instead."""
    return await auth_controller.device_authorization(client_id=client_id, scope=scope)


# Removed /device/token - use standard /token endpoint with device_code grant type
# Example: POST /api/v1/oauth/token
#   grant_type=urn:ietf:params:oauth:grant-type:device_code
#   device_code=xxx
#   client_id=xxx


@public_router.post("/revoke")
async def revoke_token(
    token: str = Form(),
    token_type_hint: str | None = Form(None),
    client_id: str = Form(),
):
    """OAuth 2.0 Token Revocation (RFC 7009).

    MCP Consideration: Token Lifecycle Management
    While MCP doesn't explicitly require revocation, it's a security best practice.

    Parameters:
    - token: The token to revoke (access or refresh)
    - token_type_hint: Hint about token type ('access_token' or 'refresh_token')
    - client_id: Client that issued the token

    Current Implementation:
    - TODO: OAuth 2.1 COMPLIANCE - Actually revoke tokens in auth service (currently returns success)
    - TODO: SECURITY - Revoke entire token family for refresh tokens to prevent replay attacks
    - TODO: SECURITY - Notify active sessions of revocation for immediate logout
    """
    return await auth_controller.revoke_token(
        token=token, token_type_hint=token_type_hint
    )


@public_router.post("/introspect")
async def introspect_token(
    token: str = Form(), token_type_hint: str | None = Form(None)
):
    """OAuth 2.0 Token Introspection (RFC 7662).

    MCP Use Case: Token Validation
    Resource servers can use this to validate tokens and get metadata.

    Response includes:
    - active: Boolean indicating if token is valid
    - scope: Granted scopes
    - client_id: Client that requested the token
    - username: Resource owner (tenant_id)
    - exp: Expiration timestamp

    TODO: MCP COMPLIANCE - Include 'aud' claim in introspection response for resource binding validation
    """
    return await auth_controller.introspect_token(
        token=token, token_type_hint=token_type_hint
    )


@public_router.post("/register")
async def register_client(request: Request):
    """OAuth 2.0 Dynamic Client Registration (RFC 7591).

    MCP Specification: Dynamic Client Registration
    Status: Partial implementation - returns static configuration

    TODO: OAuth 2.1 COMPLIANCE for full RFC 7591 compliance:
    - Generate unique client_id for each registration (currently static)
    - Store client metadata persistently in database
    - Validate redirect_uris against allowed patterns
    - Issue client credentials for confidential clients
    - Implement client management endpoints (GET, PUT, DELETE)

    Current implementation limitations:
    - Accepts any client_name and returns static MCP client config
    - Supports public clients only (no client_secret)
    - Fixed grant types and response types without validation
    """
    # Get registration data from request body
    registration_data = await request.json()

    # Default client registration response for MCP clients
    client_id = registration_data.get("client_name", "mcp_client")

    # Build response with only non-null fields
    response = {
        "client_id": client_id,
        "client_secret": "",  # Empty string for public client
        "client_id_issued_at": 1732320000,
        "client_secret_expires_at": 0,  # Never expires
        "redirect_uris": registration_data.get("redirect_uris", []),
        "grant_types": [
            "authorization_code",
            "refresh_token",
            "urn:ietf:params:oauth:grant-type:device_code",
        ],
        "response_types": ["code"],
        "client_name": registration_data.get("client_name", "MCP Client"),
        "scope": registration_data.get("scope", "read write"),
        "contacts": registration_data.get("contacts", []),
        "token_endpoint_auth_method": "none",  # Public client
    }

    # Add optional fields only if provided
    if "client_uri" in registration_data:
        response["client_uri"] = registration_data["client_uri"]
    if "logo_uri" in registration_data:
        response["logo_uri"] = registration_data["logo_uri"]
    if "tos_uri" in registration_data:
        response["tos_uri"] = registration_data["tos_uri"]
    if "policy_uri" in registration_data:
        response["policy_uri"] = registration_data["policy_uri"]
    if "software_id" in registration_data:
        response["software_id"] = registration_data["software_id"]
    if "software_version" in registration_data:
        response["software_version"] = registration_data["software_version"]

    return response


@public_router.post("/device/register", response_model=RegistrationResponse)
async def register_device(request: DeviceRegistrationRequest):
    """Register new mobile device."""
    return await auth_controller.register_device(
        email=request.email,
        public_key=request.public_key,
        device_info=request.device_info,
    )


@public_router.post("/device/verify", response_model=AuthTokenResponse)
async def verify_registration(request: VerificationRequest):
    """Verify device registration."""
    return await auth_controller.verify_registration(
        registration_id=request.registration_id,
        verification_code=request.verification_code,
        challenge_signature=request.challenge_signature,
    )


# .well-known endpoints - OAuth/OpenID discovery
# Implementing directly under /api/v1/oauth for client convenience
# Root level (/.well-known/*) also available for standards compliance

@public_router.get("/.well-known/openid-configuration")
async def oauth_openid_configuration(request: Request):
    """OpenID Connect discovery document."""
    return await auth_controller.get_oauth_discovery(request)

@public_router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server(request: Request):
    """OAuth 2.1 authorization server metadata."""
    return await auth_controller.get_oauth_discovery(request)

@public_router.get("/.well-known/jwks.json")
async def oauth_jwks():
    """JSON Web Key Set for token verification."""
    from p8fs_auth.services.jwt_key_manager import JWTKeyManager
    jwt_manager = JWTKeyManager()
    return jwt_manager.get_jwks()


# TODO: CRITICAL MCP COMPLIANCE - Implement Protected Resource Metadata (RFC 9728)
# This endpoint is required for full MCP compliance to declare resource server capabilities
# @public_router.get("/.well-known/oauth-protected-resource")
# async def protected_resource_metadata(request: Request):
#     """OAuth 2.0 Protected Resource Metadata (RFC9728).
#
#     MCP Specification: Authorization Server Discovery
#     - Required for full MCP compliance
#     - Declares resource server capabilities
#     """
#     return {
#         "resource": config.base_url,
#         "authorization_servers": [
#             {"issuer": config.base_url}
#         ],
#         "bearer_methods_supported": ["header"],
#         "resource_signing_alg_values_supported": ["ES256"],
#         "resource_documentation": f"{config.base_url}/docs"
#     }


@public_router.get("/callback")
async def oauth_callback(
    request: Request,
    client_id: str = Query(...),
    response_type: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query(None),
    state: str = Query(None),
    code_challenge: str = Query(None),
    code_challenge_method: str = Query("S256"),
    authorization: str | None = Header(None),
    p8fs_access_token: str | None = Cookie(None),
):
    """Handle OAuth callback after device authentication.

    This endpoint checks for authentication (via header or cookie) and
    completes the authorization code flow by generating a code and
    redirecting to the client's callback URL.
    """
    # Try to get token from Authorization header first, then cookie
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif p8fs_access_token:
        token = p8fs_access_token

    if not token:
        # No token, redirect back to device flow
        query_params = {
            "client_id": client_id,
            "response_type": response_type,
            "redirect_uri": redirect_uri,
            "scope": scope or "read write",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }
        query_params = {k: v for k, v in query_params.items() if v is not None}
        query_string = urlencode(query_params)
        return RedirectResponse(
            url=f"/api/v1/oauth/device?{query_string}", status_code=status.HTTP_302_FOUND
        )

    try:
        # Verify the token using JWT manager directly
        jwt_manager = JWTKeyManager()
        try:
            payload = await jwt_manager.verify_token(token)
        except Exception as token_error:
            # Token verification failed (expired, invalid, etc.)
            logger.warning(
                f"Token verification failed in OAuth callback: {token_error}"
            )
            # Clear the invalid cookie and redirect to device flow
            query_params = {
                "client_id": client_id,
                "response_type": response_type,
                "redirect_uri": redirect_uri,
                "scope": scope or "read write",
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
            }
            query_params = {k: v for k, v in query_params.items() if v is not None}
            query_string = urlencode(query_params)
            response = RedirectResponse(
                url=f"/api/v1/oauth/device?{query_string}", status_code=status.HTTP_302_FOUND
            )
            # Clear the expired cookie
            response.delete_cookie("p8fs_access_token")
            return response

        # Extract user ID from payload
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            raise ValueError("Token missing user ID")

        # Generate authorization code
        redirect_params = await auth_controller.authorization_endpoint(
            client_id=client_id,
            response_type=response_type,
            redirect_uri=redirect_uri,
            scope=scope,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            user_id=user_id,
        )

        # Build redirect URL with code and state
        parsed_uri = urlparse(redirect_uri)
        if parsed_uri.query:
            existing_params = parse_qs(parsed_uri.query)
            for key, value in redirect_params.items():
                existing_params[key] = [value]
            new_query = urlencode(existing_params, doseq=True)
        else:
            new_query = urlencode(redirect_params)

        redirect_url = (
            f"{parsed_uri.scheme}://{parsed_uri.netloc}{parsed_uri.path}?{new_query}"
        )
        if parsed_uri.fragment:
            redirect_url += f"#{parsed_uri.fragment}"

        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        # On error, redirect to client with error
        error_params = {"error": "server_error", "error_description": str(e)}
        if state:
            error_params["state"] = state

        parsed_uri = urlparse(redirect_uri)
        error_query = urlencode(error_params)
        error_url = (
            f"{parsed_uri.scheme}://{parsed_uri.netloc}{parsed_uri.path}?{error_query}"
        )

        return RedirectResponse(url=error_url, status_code=status.HTTP_302_FOUND)


@public_router.get("/device", response_class=HTMLResponse)
async def device_verification_page(
    request: Request,
    user_code: str = Query(None),
    client_id: str = Query(None),
    scope: str = Query(None),
    response_type: str = Query(None),
    redirect_uri: str = Query(None),
    state: str = Query(None),
    code_challenge: str = Query(None),
    code_challenge_method: str = Query(None),
):
    """OAuth Device Verification URI - User-facing QR code page.

    MCP Specification: Device Authorization Grant
    This implements the verification_uri from device authorization response.

    Enhanced Features:
    - QR code generation for mobile scanning
    - Real-time polling status updates via JavaScript
    - Automatic redirect after approval (for authorization code flow)
    - Countdown timer showing expiration

    Query Parameters:
    - user_code: Pre-fill the user code if provided
    - client_id: Client requesting authorization
    - response_type: If 'code', integrates with authorization code flow
    - redirect_uri: Where to redirect after approval (for auth code flow)
    - code_challenge: PKCE challenge for authorization code flow

    The page handles two flows:
    1. Simple device flow: Shows QR code, polls for approval
    2. Authorization code + device flow: After approval, redirects with code
    """
    try:
        # Determine client ID early
        effective_client_id = client_id or "web_client"
        
        if user_code:
            # TODO: Look up existing device authorization by user_code
            # For now, just display the provided code
            device_response = DeviceCodeResponse(
                device_code="",  # Will be looked up
                user_code=user_code,
                verification_uri=f"{request.url.scheme}://{request.headers.get('host', 'localhost:8000')}/api/v1/oauth/device",
                verification_uri_complete=f"{request.url.scheme}://{request.headers.get('host', 'localhost:8000')}/api/v1/oauth/device?user_code={user_code}",
                expires_in=600,
                interval=5,
            )
        else:
            # Use determined client_id
            effective_scope = scope or "read write"

            # Initiate new device flow
            device_response = await auth_controller.device_authorization(
                client_id=effective_client_id, scope=effective_scope
            )

        # Create auth flow parameters if present
        auth_flow_params = None
        if response_type and redirect_uri:
            auth_flow_params = {
                "response_type": response_type,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
            }

        # Save device code to standard location for testing/approval (dev only)
        if config.debug:
            import os
            import json
            from datetime import datetime
            from pathlib import Path

            try:
                device_auth_file = Path.home() / ".p8fs" / "device_auth.json"
                device_auth_file.parent.mkdir(parents=True, exist_ok=True)

                device_auth_data = {
                    "user_code": device_response.user_code,
                    "device_code": device_response.device_code,
                    "client_id": effective_client_id,
                    "expires_in": device_response.expires_in,
                    "poll_interval": device_response.interval,
                    "verification_uri": device_response.verification_uri,
                    "verification_uri_complete": device_response.verification_uri_complete,
                    "created_at": datetime.utcnow().isoformat() + "Z"
                }

                with open(device_auth_file, 'w') as f:
                    json.dump(device_auth_data, f, indent=2)
            except Exception:
                pass

        # Create page context using Pydantic model
        page_context = DeviceVerificationPageContext.from_device_response(
            device_response=device_response,
            client_id=effective_client_id,
            auth_flow_params=auth_flow_params
        )

        # Render the QR code login page
        return templates.TemplateResponse(
            request,
            "qr_login.html",
            {
                **page_context.model_dump()
            },
        )

    except Exception as e:
        # Return error page
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head><title>Login Error</title></head>
            <body>
                <h1>Login Error</h1>
                <p>Failed to initialize device verification. Please try again.</p>
                <p>Error: {str(e)}</p>
                <a href="/api/v1/oauth/device">Try Again</a>
            </body>
            </html>
            """,
            status_code=500,
        )


@public_router.get("/authorize")
async def authorization_endpoint(
    request: Request,
    client_id: str = Query(...),
    response_type: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str | None = Query(None),
    state: str | None = Query(None),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query("S256"),
    authorization: str | None = Header(None),
    resource: str | None = Query(None),  # TODO: MCP requirement
):
    """OAuth 2.1 authorization endpoint with PKCE support and intelligent flow handling.

    MCP Specification: Authorization Code Protection
    - Mandatory PKCE with S256 code challenge method
    - TODO: Implement resource parameter for token audience binding
    
    OpenID Connect Note:
    - Does NOT currently handle OpenID parameters (nonce, prompt, id_token_hint)
    - Only OAuth 2.1 authorization code flow with PKCE
    - For OpenID support, minimal changes needed:
      1. Accept and store nonce parameter with authorization code
      2. Pass nonce through to ID token generation in token endpoint

    This endpoint provides a hybrid approach for MCP client authentication:

    1. **MCP Client Request**: When an MCP client (like Claude Desktop) initiates OAuth,
       it typically starts with the authorization code flow:
       GET /api/v1/oauth/authorize?response_type=code&client_id=Claude+Code&redirect_uri=...

    2. **Authentication Detection**: The endpoint checks for a valid JWT Bearer token
       in the Authorization header.

    3. **Automatic Flow Selection**:
       - **Authenticated**: With valid JWT token → processes authorization code flow,
         generates auth code, and redirects to client's callback URL
       - **Unauthenticated**: No/invalid token → redirects to device bound auth flow (/api/v1/oauth/device)
         with all parameters preserved

    4. **Device Flow Experience**: When redirected to /api/v1/oauth/device:
       - User sees QR code for mobile authentication
       - User code displayed for manual entry
       - All original OAuth parameters preserved
       - After mobile approval, original flow can complete

    5. **Flow Completion**: After device authentication:
       - Client receives JWT token from device flow
       - Can retry /api/v1/oauth/authorize with Bearer token
       - Original authorization code flow completes successfully

    This design allows MCP clients to use standard OAuth flows without implementing
    complex authentication detection logic. The endpoint intelligently routes to the
    appropriate flow based on authentication state.
    """
    # Check if user is authenticated
    if not authorization or not authorization.startswith("Bearer "):
        # Redirect to device flow for unauthenticated requests
        # Preserve all query parameters for later use
        query_params = {
            "client_id": client_id,
            "response_type": response_type,
            "redirect_uri": redirect_uri,
            "scope": scope or "read write",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }
        # Remove None values
        query_params = {k: v for k, v in query_params.items() if v is not None}
        query_string = urlencode(query_params)

        # Redirect to the device verification page
        device_url = f"/api/v1/oauth/device?{query_string}"
        return RedirectResponse(url=device_url, status_code=status.HTTP_302_FOUND)

    # For authenticated requests, get the current user
    try:
        from ..middleware import verify_jwt_token

        token = authorization.split(" ")[1]
        current_user = await verify_jwt_token(token)
    except Exception:
        # Invalid token, redirect to device flow
        query_params = {
            "client_id": client_id,
            "response_type": response_type,
            "redirect_uri": redirect_uri,
            "scope": scope or "read write",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }
        query_params = {k: v for k, v in query_params.items() if v is not None}
        query_string = urlencode(query_params)
        device_url = f"/api/v1/oauth/device?{query_string}"
        return RedirectResponse(url=device_url, status_code=status.HTTP_302_FOUND)

    # Get authorization code
    redirect_params = await auth_controller.authorization_endpoint(
        client_id=client_id,
        response_type=response_type,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        user_id=current_user.id,
    )

    # Build redirect URL
    parsed_uri = urlparse(redirect_uri)
    if parsed_uri.query:
        # Append to existing query parameters
        existing_params = parse_qs(parsed_uri.query)
        for key, value in redirect_params.items():
            existing_params[key] = [value]
        new_query = urlencode(existing_params, doseq=True)
    else:
        new_query = urlencode(redirect_params)

    # Construct final redirect URL
    redirect_url = (
        f"{parsed_uri.scheme}://{parsed_uri.netloc}{parsed_uri.path}?{new_query}"
    )
    if parsed_uri.fragment:
        redirect_url += f"#{parsed_uri.fragment}"

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


# Protected OAuth 2.1 Endpoints (JWT Required)


@protected_router.post("/device/approve")
async def approve_device(
    request: DeviceApprovalRequest, current_user: User = Depends(get_current_user)
):
    """Approve device from mobile app with optional device-bound authentication.

    Supports two authentication modes:
    1. JWT only: Uses bearer token from Authorization header
    2. Device-bound: JWT + Ed25519 signature of approval challenge

    Device-bound authentication provides stronger security by proving
    possession of the device's private key.
    """
    return await auth_controller.approve_device(
        user_code=request.user_code,
        approved=request.approved,
        device_name=request.device_name,
        user_id=current_user.tenant_id,  # Pass tenant_id, not device ID
        device_id=getattr(current_user, "device_id", None),
        challenge=request.challenge,
        signature=request.signature,
    )


@protected_router.get("/userinfo")
async def get_user_info(current_user: User = Depends(get_current_user)):
    """Get user information.
    
    OpenID Connect Note: 
    - This endpoint is DEPRECATED and not compliant with OpenID Connect
    - OpenID userinfo should accept access tokens and return standard claims
    - Current implementation requires JWT auth and returns non-standard format
    - Should be removed from discovery or reimplemented per OpenID spec
    """
    return await auth_controller.get_user_info(user_id=current_user.id)


@protected_router.get("/ping")
async def ping_auth(current_user: User = Depends(get_current_user)):
    """Test JWT token validity.
    
    Simple endpoint to verify if a JWT token is valid and not expired.
    Returns 200 with user info if valid, 401 if invalid/expired.
    
    Useful for:
    - MCP clients to check token validity before making requests
    - Health checks for authenticated services
    - Token refresh decisions
    """
    return {
        "authenticated": True,
        "user_id": current_user.id,
        "email": getattr(current_user, 'email', None),
        "tenant_id": getattr(current_user, 'tenant_id', None)
    }


# Development Endpoints (no authentication required)


@dev_router.post("/register", response_model=AuthTokenResponse)
async def dev_register_device(
    request: DeviceRegistrationRequest,
    x_dev_token: str = Header(..., alias="X-Dev-Token"),
    x_dev_email: str = Header(..., alias="X-Dev-Email"),
    x_dev_code: str = Header(..., alias="X-Dev-Code"),
):
    """Development endpoint for immediate device registration and token issuance."""
    return await auth_controller.dev_register_device(
        email=request.email,
        public_key=request.public_key,
        device_info=request.device_info,
        dev_token=x_dev_token,
        dev_email=x_dev_email,
        dev_code=x_dev_code,
    )
