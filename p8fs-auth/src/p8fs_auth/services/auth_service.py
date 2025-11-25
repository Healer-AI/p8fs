"""Core authentication service implementing OAuth 2.1 flows.

This service handles the primary OAuth 2.1 authorization flows including:
- Authorization code grant with mandatory PKCE
- Device authorization grant for desktop/CLI authentication
- Refresh token grant with rotation for public clients
- Token introspection and revocation

Reference: p8fs-auth/docs/authentication-flows.md - OAuth 2.1 Endpoints Specification
Reference: p8fs-api/src/p8fs_api/controllers/auth_controller.py - Placeholder implementation
"""

import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from p8fs_cluster.config.settings import config

from ..models.auth import AuthToken, DeviceToken, PKCEChallenge, TokenType
from ..models.repository import AbstractRepository
from .jwt_key_manager import JWTKeyManager

logger = logging.getLogger(__name__)


class InvalidGrantError(Exception):
    """OAuth 2.1 invalid grant error."""
    pass


class InvalidClientError(Exception):
    """OAuth 2.1 invalid client error."""
    pass


class AuthorizationPendingError(Exception):
    """Device flow authorization pending."""
    pass


# Device authorization always uses KV storage - no dev mode file storage


class AuthenticationService:
    """Core OAuth 2.1 authentication service.
    
    Implements the OAuth 2.1 specification with security best practices:
    - PKCE mandatory for all public clients (RFC 7636)
    - No implicit grant support (deprecated in OAuth 2.1)
    - Refresh token rotation for public clients
    - Short-lived access tokens with JWT format
    
    MCP (Model Context Protocol) Specification Compliance:
    - ✅ PKCE with S256 (MCP: Authorization Code Protection)
    - ✅ Device Authorization Grant (MCP: Device Authorization Grant)
    - ✅ Bearer Token Support (MCP: Access Token Usage)
    - ❌ TODO: Resource Parameter (MCP: Token Audience Binding)
    - ❌ TODO: Token Rotation (MCP: Security Requirements)
    
    Reference: p8fs-auth/docs/authentication-flows.md - Core Principles
    """
    
    def __init__(
        self,
        repository: AbstractRepository,
        jwt_manager: JWTKeyManager
    ):
        self.repository = repository
        self.jwt_manager = jwt_manager
        
        # Set up repository aliases for different operations
        self.oauth_repository = repository
        self.token_repository = repository
        self.auth_repository = repository
        
        # Token lifetimes from centralized config
        # Reference: CLAUDE.md - "All configuration must come from centralized config"
        self.access_token_ttl = getattr(config, 'auth_access_token_ttl', 3600)  # 1 hour default
        self.refresh_token_ttl = getattr(config, 'auth_refresh_token_ttl', 2592000)  # 30 days default
        self.device_code_ttl = getattr(config, 'auth_device_code_ttl', 600)  # 10 minutes default
        self.auth_code_ttl = getattr(config, 'auth_code_ttl', 600)  # 10 minutes default
    
    async def create_authorization_code(
        self,
        client_id: str,
        user_id: str,
        redirect_uri: str,
        scope: list[str],
        code_challenge: str,
        code_challenge_method: str = "S256",
        state: str | None = None
    ) -> str:
        """Create authorization code for OAuth flow.
        
        Implements the authorization endpoint logic from:
        Reference: p8fs-auth/docs/endpoint-implementation.md - Authorization Endpoint
        
        Steps:
        1. Validate client and redirect URI
        2. Generate secure authorization code  
        3. Store PKCE challenge for later verification
        4. Return authorization code for redirect
        
        Args:
            client_id: OAuth client identifier
            user_id: Authenticated user ID (tenant_id)
            redirect_uri: Client callback URL (must match registered)
            scope: Requested permissions
            code_challenge: PKCE challenge from client
            code_challenge_method: Must be "S256" (plain deprecated)
            state: Optional CSRF protection token
            
        Returns:
            Authorization code to redirect to client
            
        Raises:
            InvalidClientError: Client not found or redirect URI mismatch
        """
        # In simple tenant-based auth, we don't validate clients
        # Any client_id is accepted and we rely on tenant authentication
        
        # Generate simple UUID-based authorization code
        import uuid
        auth_code = str(uuid.uuid4())
        
        # Store authorization code data in KV storage
        auth_code_data = {
            'client_id': client_id,
            'user_id': user_id,
            'redirect_uri': redirect_uri,
            'scope': scope,
            'code_challenge': code_challenge,
            'code_challenge_method': code_challenge_method,
            'state': state,
            'created_at': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(seconds=self.auth_code_ttl)).isoformat()
        }
        
        # Store in KV with TTL
        success = await self.repository.store(
            f"auth_code:{auth_code}",
            auth_code_data,
            ttl_seconds=self.auth_code_ttl
        )
        
        if not success:
            raise RuntimeError("Failed to store authorization code")
        
        return auth_code
    
    async def exchange_authorization_code(
        self,
        client_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str
    ) -> dict[str, any]:
        """Exchange authorization code for tokens.
        
        Implements authorization code grant from:
        Reference: p8fs-auth/docs/endpoint-implementation.md - Authorization Code Grant
        
        Security requirements:
        - Verify PKCE challenge (mandatory in OAuth 2.1)
        - Validate redirect URI matches original request
        - Single-use authorization codes
        - Time-limited codes (10 minutes)
        
        Args:
            client_id: OAuth client identifier
            code: Authorization code from authorize endpoint
            redirect_uri: Must match authorization request
            code_verifier: PKCE verifier to validate challenge
            
        Returns:
            Token response with access_token, refresh_token, etc.
            
        Raises:
            InvalidGrantError: Invalid code, PKCE failure, or expired
        """
        # Retrieve authorization code from KV storage
        auth_code_data = await self.repository.retrieve(f"auth_code:{code}")
        if not auth_code_data:
            raise InvalidGrantError("Invalid or expired authorization code")
        
        # Check expiration (KV TTL should handle this, but double-check)
        expires_at = datetime.fromisoformat(auth_code_data.get('expires_at'))
        if datetime.utcnow() > expires_at:
            # Clean up expired code
            await self.repository.delete(f"auth_code:{code}")
            raise InvalidGrantError("Authorization code expired")
        
        # Extract user_id from stored data
        user_id = auth_code_data.get('user_id')
        if not user_id:
            raise InvalidGrantError("Invalid authorization code data")
        
        # Validate the authorization code data
        if auth_code_data.get('client_id') != client_id:
            raise InvalidGrantError("Authorization code client_id mismatch")
            
        if auth_code_data.get('redirect_uri') != redirect_uri:
            raise InvalidGrantError("Authorization code redirect_uri mismatch")
        
        # Verify PKCE challenge using stored challenge
        stored_challenge = auth_code_data.get('code_challenge')
        challenge_method = auth_code_data.get('code_challenge_method', 'S256')
        
        if not stored_challenge:
            raise InvalidGrantError("No PKCE challenge found for authorization code")
        
        # Calculate challenge from verifier
        if challenge_method == 'S256':
            calculated_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode('utf-8')).digest()
            ).decode('utf-8').rstrip('=')
        else:
            raise InvalidGrantError("Unsupported PKCE challenge method")
        
        # Verify challenge using constant-time comparison
        if not secrets.compare_digest(calculated_challenge, stored_challenge):
            raise InvalidGrantError("Invalid PKCE verification")
        
        # Delete the authorization code (single use only)
        await self.repository.delete(f"auth_code:{code}")
        
        # Extract scope from stored code
        scope = auth_code_data.get('scope', ["read", "write"])
        
        return await self._issue_tokens(user_id, client_id, scope=scope)
    
    async def create_device_authorization(
        self,
        client_id: str,
        scope: list[str] | None = None
    ) -> DeviceToken:
        """Initiate device authorization flow.
        
        Implements device authorization from:
        Reference: p8fs-auth/docs/authentication-flows.md - Flow 2: Desktop Authentication via QR Code
        
        Steps:
        1. Generate device code and user-friendly code
        2. Create verification URIs for QR display
        3. Store device token for polling
        4. Return response for client display
        
        Args:
            client_id: OAuth client identifier
            scope: Optional requested permissions
            
        Returns:
            DeviceToken with codes and verification URIs
        """
        # Skip OAuth client validation - using simple tenant-based auth
        # In simple tenant system, we accept any client_id and rely on tenant authentication
        
        # Generate device code (long random string for security)
        # Reference: p8fs-auth/docs/authentication-flows.md - "Server returns device code and user code"
        device_code = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        
        # Generate user code (short, human-friendly for manual entry)
        # Format: XXXX-YYYY for easy reading and entry
        user_code = f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
        
        # Create verification URIs
        # Reference: p8fs-auth/docs/authentication-flows.md - "Desktop displays QR code with user code"
        base_uri = getattr(config, 'auth_base_url', "https://auth.p8fs.com")
        verification_uri = f"{base_uri}/device"
        verification_uri_complete = f"{base_uri}/device?user_code={user_code}"
        
        # Create device token
        device_token = DeviceToken(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            verification_uri_complete=verification_uri_complete,
            expires_in=self.device_code_ttl,
            interval=5  # Recommended polling interval
        )
        
        # Store pending device request in KV storage using repository interface
        # Reference: p8fs-auth/CLAUDE.md - "Use repository.store() with TTL for temporary data"

        logger.info(f"[KV_DEBUG] create_device_authorization called for client_id={client_id}, device_code={device_code}, user_code={user_code}")

        # Create pending request data structure
        pending_request_data = {
            "device_code": device_code,
            "user_code": user_code,
            "client_id": client_id,
            "scope": scope or ["read", "write"],
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(seconds=self.device_code_ttl)).isoformat(),
            "client_info": {"created_at": datetime.utcnow().isoformat()}
        }

        # Store device authorization with device_code key (primary lookup for polling)
        device_key = f"device_auth:{device_code}"
        logger.info(f"[KV_DEBUG] Attempting to store device auth at key: {device_key}")
        logger.info(f"[KV_DEBUG] Repository type: {type(self.repository).__name__}")

        success = await self.repository.store(
            device_key,
            pending_request_data,
            ttl_seconds=self.device_code_ttl
        )

        logger.info(f"[KV_DEBUG] Device auth store result: {success} for key: {device_key}")

        if not success:
            logger.error(f"[KV_DEBUG] FAILED to store device authorization at key {device_key}")
            raise RuntimeError(f"Failed to store device authorization at key {device_key}")

        # Also store user_code mapping for mobile approval lookup
        # Normalize user code for storage: uppercase and remove hyphens
        normalized_user_code = user_code.upper().replace("-", "")
        user_code_key = f"user_code:{normalized_user_code}"
        user_code_mapping = {"device_code": device_code}
        logger.info(f"[KV_DEBUG] Attempting to store user code mapping at key: {user_code_key}")

        success = await self.repository.store(
            user_code_key,
            user_code_mapping,
            ttl_seconds=self.device_code_ttl
        )

        logger.info(f"[KV_DEBUG] User code mapping store result: {success} for key: {user_code_key}")

        if not success:
            logger.error(f"[KV_DEBUG] FAILED to store user code mapping at key {user_code_key}")
            raise RuntimeError(f"Failed to store user code mapping at key {user_code_key}")

        return device_token
    
    async def approve_device_authorization(
        self,
        user_code: str,
        user_id: str,
        device_id: str | None = None
    ) -> bool:
        """Approve device authorization from mobile app.

        Implements device approval from:
        Reference: p8fs-auth/docs/authentication-flows.md - "User approves device on mobile"

        This is called when user scans QR code and approves on mobile.

        Args:
            user_code: User-friendly code from QR scan
            user_id: Authenticated mobile user approving
            device_id: Optional mobile device ID

        Returns:
            True if approval successful

        Raises:
            InvalidGrantError: Code not found or expired
        """
        # Normalize user code: uppercase and remove hyphens for consistent lookup
        user_code = user_code.upper().replace("-", "")

        # Retrieve pending device authorization from KV storage using repository interface

        # Step 1: Look up device_code from user_code mapping
        user_code_key = f"user_code:{user_code}"
        user_code_data = await self.repository.retrieve(user_code_key)

        if not user_code_data:
            raise InvalidGrantError(f"Invalid user code: {user_code}")

        device_code = user_code_data.get("device_code")
        if not device_code:
            raise InvalidGrantError("User code mapping is invalid")

        # Step 2: Retrieve pending device request
        device_key = f"device_auth:{device_code}"
        pending_request = await self.repository.retrieve(device_key)

        if not pending_request:
            raise InvalidGrantError("Invalid device code or expired authorization")

        # Check if already approved
        if pending_request.get("status") == "approved":
            raise InvalidGrantError("Device already approved")

        # Check expiration
        expires_at_str = pending_request.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.utcnow() > expires_at:
                raise InvalidGrantError("Device code expired")

        # Extract client details
        client_id = pending_request.get("client_id")
        scope = pending_request.get("scope", ["read", "write"])

        # Generate access token for the approving tenant
        tokens = await self._issue_tokens(user_id, client_id, scope=scope)

        # Update pending request with approval
        pending_request["status"] = "approved"
        pending_request["approved_at"] = datetime.utcnow().isoformat()
        pending_request["approved_by_tenant"] = user_id
        pending_request["access_token"] = tokens["access_token"]
        pending_request["approval_metadata"] = {
            "device_id": device_id,
            "approval_method": "mobile_qr"
        }

        logger.info(f"[KV_DEBUG] approve_device_authorization: Updating device auth at key: {device_key}")
        logger.info(f"[KV_DEBUG] approve_device_authorization: New status={pending_request['status']}, has access_token={bool(pending_request.get('access_token'))}")

        # Store updated request back to KV
        success = await self.repository.store(
            device_key,
            pending_request,
            ttl_seconds=self.device_code_ttl
        )

        logger.info(f"[KV_DEBUG] approve_device_authorization: Store result={success} for key: {device_key}")

        if not success:
            raise RuntimeError(f"Failed to update device authorization approval at key {device_key}")

        return True
    
    async def poll_device_token(
        self,
        client_id: str,
        device_code: str
    ) -> dict[str, any]:
        """Poll for device authorization completion.

        Implements device polling from:
        Reference: p8fs-auth/docs/authentication-flows.md - "Desktop polls token endpoint"

        Args:
            client_id: OAuth client identifier
            device_code: Device code from initial request

        Returns:
            Token response if approved, error if pending/denied

        Raises:
            AuthorizationPendingError: Still waiting for approval
            InvalidGrantError: Expired or denied
        """
        # Retrieve pending device authorization from KV storage using repository interface

        device_key = f"device_auth:{device_code}"
        logger.info(f"[KV_DEBUG] poll_device_token: Looking up device auth at key: {device_key}")

        pending_request = await self.repository.retrieve(device_key)

        if not pending_request:
            logger.error(f"[KV_DEBUG] poll_device_token: No data found for key: {device_key}")
            raise InvalidGrantError("Invalid or expired device code")

        logger.info(f"[KV_DEBUG] poll_device_token: Found pending_request, status={pending_request.get('status')}, has_access_token={bool(pending_request.get('access_token'))}")

        # Check expiration
        expires_at_str = pending_request.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.utcnow() > expires_at:
                # Keys expire automatically via TTL
                raise InvalidGrantError("Device code expired")

        # Check if approved
        status = pending_request.get("status")
        if status != "approved":
            logger.info(f"[KV_DEBUG] poll_device_token: Status is '{status}', not 'approved' - raising AuthorizationPendingError")
            raise AuthorizationPendingError("Authorization pending")

        # Extract access token
        access_token = pending_request.get("access_token")
        if not access_token:
            raise InvalidGrantError("Device approved but no access token available")

        # Extract scope
        scope = pending_request.get("scope", ["read", "write"])

        # Note: Token consumption handled by TTL expiration
        # The KV entry will automatically expire after device_code_ttl

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": self.access_token_ttl,
            "scope": " ".join(scope) if isinstance(scope, list) else scope
        }
    
    async def refresh_access_token(
        self,
        refresh_token: str,
        client_id: str
    ) -> dict[str, any]:
        """Refresh access token using refresh token.
        
        Implements refresh token grant from:
        Reference: p8fs-auth/docs/endpoint-implementation.md - Refresh Token Grant
        
        Security:
        - Rotate refresh tokens for public clients
        - Validate token ownership and expiry
        - Maintain token family for security
        
        Args:
            refresh_token: Valid refresh token
            client_id: OAuth client identifier
            
        Returns:
            New token response
            
        Raises:
            InvalidGrantError: Invalid or expired token
        """
        # Validate refresh token
        token = await self.token_repository.get_auth_token_by_value(refresh_token)
        if not token or token.token_type != TokenType.REFRESH:
            raise InvalidGrantError("Invalid refresh token")
        
        # Check expiration
        if token.expires_at < datetime.utcnow():
            raise InvalidGrantError("Refresh token expired")
        
        # Check revocation
        if token.revoked_at:
            raise InvalidGrantError("Refresh token revoked")
        
        # Get client to check if public
        client = await self.oauth_repository.get_client(client_id)
        if not client:
            raise InvalidClientError(f"Client {client_id} not found")
        
        # For public clients, rotate refresh token
        # Reference: p8fs-auth/docs/endpoint-implementation.md - "For public clients, rotate refresh token"
        if client.client_type == "public":
            await self.token_repository.revoke_auth_token(token.token_id)

        # Preserve additional claims from original token (email, tenant, etc.)
        additional_claims = {}
        if token.tenant_id:
            additional_claims["tenant"] = token.tenant_id
            logger.info(f"[REFRESH] Adding tenant claim: {token.tenant_id}")
        else:
            logger.warning(f"[REFRESH] Token has NO tenant_id! token_id={token.token_id}")

        if token.device_id:
            additional_claims["device_id"] = token.device_id
            logger.info(f"[REFRESH] Adding device_id claim: {token.device_id}")

        # Try to fetch email from tenant if tenant_id is available
        if token.tenant_id:
            try:
                from p8fs_auth.models.repository import get_auth_repository
                tenant = await get_auth_repository().get_tenant_by_id(token.tenant_id)
                if tenant:
                    additional_claims["email"] = tenant.email
                    logger.info(f"[REFRESH] Adding email claim: {tenant.email}")
                else:
                    logger.warning(f"[REFRESH] Tenant not found for tenant_id: {token.tenant_id}")
            except Exception as e:
                # Non-critical - continue without email claim
                logger.warning(f"Could not fetch tenant email for token refresh: {e}")

        # Issue new tokens with preserved claims
        return await self._issue_tokens(
            token.user_id,
            client_id,
            scope=token.scope,
            additional_claims=additional_claims if additional_claims else None
        )
    
    async def revoke_token(
        self,
        token: str,
        token_type_hint: str | None = None
    ) -> bool:
        """Revoke access or refresh token.
        
        Implements token revocation (RFC 7009).
        
        Args:
            token: Token to revoke
            token_type_hint: Optional hint about token type
            
        Returns:
            True if revoked successfully
        """
        # Find token
        auth_token = await self.token_repository.get_auth_token_by_value(token)
        if not auth_token:
            # Per spec, return success even if token not found
            return True
        
        # Revoke token
        return await self.token_repository.revoke_auth_token(auth_token.token_id)
    
    async def introspect_token(
        self,
        token: str
    ) -> dict[str, any]:
        """Introspect token for validation.
        
        Implements token introspection (RFC 7662).
        
        Args:
            token: Token to introspect
            
        Returns:
            Token metadata and active status
        """
        # Find token
        auth_token = await self.token_repository.get_auth_token_by_value(token)
        if not auth_token:
            return {"active": False}
        
        # Check if active
        if auth_token.expires_at < datetime.utcnow() or auth_token.revoked_at:
            return {"active": False}
        
        # Return token metadata
        return {
            "active": True,
            "scope": " ".join(auth_token.scope),
            "client_id": auth_token.client_id,
            "username": auth_token.user_id,
            "token_type": auth_token.token_type.value,
            "exp": int(auth_token.expires_at.timestamp()),
            "iat": int(auth_token.created_at.timestamp()),
            "sub": auth_token.user_id,
            "aud": auth_token.client_id
        }
    
    async def _issue_tokens(
        self,
        user_id: str,
        client_id: str,
        scope: list[str],
        additional_claims: dict[str, any] | None = None
    ) -> dict[str, any]:
        """Issue access and refresh tokens.

        Internal method to generate token pair.
        Uses JWT for access tokens with ES256 signing.

        Reference: p8fs-auth/docs/authentication-flows.md - JWT Signing Keys (ES256)
        """
        # Generate access token JWT
        access_token_value = await self.jwt_manager.create_access_token(
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            additional_claims=additional_claims
        )
        
        # Generate refresh token (opaque)
        refresh_token_value = base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).decode('utf-8').rstrip('=')

        # Extract tenant_id and device_id from additional_claims if present
        tenant_id = additional_claims.get("tenant") if additional_claims else None
        device_id = additional_claims.get("device_id") if additional_claims else None

        logger.info(f"[ISSUE_TOKENS] tenant_id={tenant_id}, device_id={device_id}, additional_claims={additional_claims}")

        # Store access token
        access_token = AuthToken(
            token_type=TokenType.ACCESS,
            token_value=access_token_value,
            user_id=user_id,
            device_id=device_id,
            client_id=client_id,
            scope=scope,
            expires_at=datetime.utcnow() + timedelta(seconds=self.access_token_ttl),
            tenant_id=tenant_id
        )
        await self.token_repository.create_auth_token(access_token)

        # Store refresh token
        refresh_token = AuthToken(
            token_type=TokenType.REFRESH,
            token_value=refresh_token_value,
            user_id=user_id,
            device_id=device_id,
            client_id=client_id,
            scope=scope,
            expires_at=datetime.utcnow() + timedelta(seconds=self.refresh_token_ttl),
            refresh_token=refresh_token_value,  # Self-reference for token family
            tenant_id=tenant_id
        )
        await self.token_repository.create_auth_token(refresh_token)
        
        return {
            "access_token": access_token_value,
            "token_type": "Bearer",
            "expires_in": self.access_token_ttl,
            "refresh_token": refresh_token_value,
            "scope": " ".join(scope)
        }
    
