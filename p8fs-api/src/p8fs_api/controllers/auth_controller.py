"""Authentication controller delegating to p8fs-auth services.

  1. Device Creation: Device created: {device_id} email={email} trust={trust_level} has_imei={bool}
  2. Tenant Creation: Tenant created: {tenant_id} email={email} method={imei|random}
  3. Tenant Reuse: Tenant exists: {tenant_id} method={imei|random}
  4. Device Verification: Device verified: {device_id} email={email} tenant={tenant_id}
  5. Device Approval: Device approved: {device_id} upgraded to TRUSTED
  6. Dev Token Creation: Dev token created: device={device_id} tenant={tenant_id} email={email}

  Problem Warnings (WARNING level):

  1. Missing IMEI: No IMEI provided for device {device_id}, using random tenant ID
  2. Double Verification: Verification attempted on already verified device: {device_id} trust={trust_level}
  3. Invalid Verification Code: Invalid verification code for device: {device_id} attempts={attempts}
  4. Invalid Signature: Invalid signature for device verification: {device_id}
  
"""

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from p8fs_auth.models.repository import (
    get_auth_repository,
    get_login_event_repository,
    get_oauth_repository,
    get_token_repository,
    set_repository,
)
from p8fs_auth.services.auth_service import (
    AuthenticationService,
    AuthorizationPendingError,
    InvalidClientError,
    InvalidGrantError,
)
from p8fs_auth.services.device_service import DeviceManagementService
from p8fs_auth.services.jwt_key_manager import JWTKeyManager
from p8fs_auth.services.mobile_service import MobileAuthenticationService
from p8fs_cluster.logging.setup import get_logger

from ..models import (
    AuthTokenResponse,
    DeviceCodeResponse,
    RegistrationResponse,
    UserResponse,
)

logger = get_logger(__name__)


class AuthController:
    """Handles authentication operations using p8fs-auth services."""

    def __init__(self):
        # Initialize repository implementation using p8fs-api's auth repository
        from ..repositories.auth_repository import P8FSAuthRepository

        repository = P8FSAuthRepository()
        set_repository(repository)

        # Initialize p8fs-auth repositories
        self.oauth_repo = get_oauth_repository()
        self.token_repo = get_token_repository()
        self.auth_repo = get_auth_repository()
        self.login_event_repo = get_login_event_repository()
        self.jwt_manager = JWTKeyManager()

        # Initialize authentication service with unified repository
        self.auth_service = AuthenticationService(
            repository=self.auth_repo, jwt_manager=self.jwt_manager
        )

        # Initialize device management service
        self.device_service = DeviceManagementService(
            repository=self.auth_repo, auth_service=self.auth_service
        )

        # Initialize email service
        from p8fs.services.email.email_service import EmailService
        self.email_service = EmailService()

        # Initialize mobile authentication service
        self.mobile_service = MobileAuthenticationService(
            repository=self.auth_repo,
            jwt_manager=self.jwt_manager,
            email_service=self.email_service,
            auth_service=self.auth_service
        )

    async def token_endpoint(self, grant_type: str, **kwargs) -> AuthTokenResponse:
        """Handle OAuth token requests delegating to p8fs-auth.
        
        MCP Specification Sections:
        - Token Endpoint: Standard OAuth 2.1 token exchange
        - Token Audience Binding: Accepts resource parameter for MCP compliance
        - Security Requirements: TODO - refresh token rotation
        """
        # TODO: MCP COMPLIANCE - Implement proper resource parameter validation (RFC 8707)
        # Currently only logs the resource parameter but doesn't validate token audience binding
        # Need to: 1) Validate resource URI, 2) Add 'aud' claim to token, 3) Enforce in middleware
        resource = kwargs.get("resource")
        if resource:
            logger.info(f"Token request with resource parameter: {resource}")
        try:
            if grant_type == "authorization_code":
                # Exchange authorization code for tokens
                result = await self.auth_service.exchange_authorization_code(
                    client_id=kwargs.get("client_id"),
                    code=kwargs.get("code"),
                    redirect_uri=kwargs.get("redirect_uri"),
                    code_verifier=kwargs.get("code_verifier"),
                )
            elif grant_type == "refresh_token":
                # TODO: OAuth 2.1 COMPLIANCE - Implement refresh token rotation for public clients
                # Current implementation doesn't rotate refresh tokens, required for OAuth 2.1 security
                # Need to: 1) Generate new refresh token, 2) Track token families, 3) Invalidate old tokens
                result = await self.auth_service.refresh_access_token(
                    refresh_token=kwargs.get("refresh_token"),
                    client_id=kwargs.get("client_id"),
                )
            elif grant_type == "urn:ietf:params:oauth:grant-type:device_code":
                # Device code flow - use KV storage for pending requests
                device_code = kwargs.get("device_code")
                client_id = kwargs.get("client_id")

                # Poll device token from KV storage
                result = await self.auth_service.poll_device_token(
                    client_id=client_id,
                    device_code=device_code,
                )
            # TODO: MCP COMPLIANCE - Add token exchange grant type support
            # elif grant_type == "urn:ietf:params:oauth:grant-type:token-exchange":
            #     # Token exchange flow for MCP compliance
            #     result = await self.auth_service.exchange_token(
            #         subject_token=kwargs.get("subject_token"),
            #         subject_token_type=kwargs.get("subject_token_type"),
            #         audience=kwargs.get("audience"),
            #     )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "unsupported_grant_type"},
                )

            return AuthTokenResponse(
                access_token=result["access_token"],
                token_type="Bearer",
                expires_in=result.get("expires_in", 3600),
                refresh_token=result.get("refresh_token"),
                scope=result.get("scope", ""),
            )

        except InvalidGrantError as e:
            logger.error(f"Invalid grant: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_grant", "error_description": str(e)},
            )
        except InvalidClientError as e:
            logger.error(f"Invalid client: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_client", "error_description": str(e)},
            )
        except AuthorizationPendingError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "authorization_pending"},
            )
        except Exception as e:
            logger.error(f"Token endpoint error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "server_error", "error_description": str(e)},
            )

    async def device_authorization(
        self, client_id: str, scope: str = None
    ) -> DeviceCodeResponse:
        """Generate device code for device flow using p8fs-auth."""
        try:
            # Parse scope string into list if provided
            scope_list = scope.split() if scope else ["read", "write"]

            # Request device authorization from p8fs-auth device service
            # Device authorization stored in KV storage (kv_storage table or TiKV)
            result = await self.device_service.initiate_device_flow(
                client_id=client_id, scope=scope_list
            )

            return DeviceCodeResponse(
                device_code=result["device_code"],
                user_code=result["user_code"],
                verification_uri=result["verification_uri"],
                verification_uri_complete=result["verification_uri_complete"],
                expires_in=result["expires_in"],
                interval=result["interval"],
                qr_code=result.get("qr_code"),  # Pass QR code from device service
            )

        except InvalidClientError as e:
            logger.error(f"Invalid client in device authorization: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_client", "error_description": str(e)},
            )
        except Exception as e:
            logger.error(f"Device authorization error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "server_error", "message": str(e)},
            )

    async def device_token(self, device_code: str, client_id: str) -> AuthTokenResponse:
        """Poll for device token using p8fs-auth."""
        # This is handled by token_endpoint with device_code grant type
        return await self.token_endpoint(
            grant_type="urn:ietf:params:oauth:grant-type:device_code",
            device_code=device_code,
            client_id=client_id,
        )

    async def register_device(
        self, email: str, public_key: str, device_info: dict[str, Any]
    ) -> RegistrationResponse:
        """Register new mobile device using p8fs-auth."""
        try:
            # Extract device name from device_info if provided
            device_name = (
                device_info.get("device_name")
                or f"{device_info.get('platform', 'Unknown')} {device_info.get('model', 'Device')}"
            )

            # Register device with mobile service, passing full device_info
            # This returns a dict with registration_id, message, and expires_in
            result = await self.mobile_service.register_device(
                email=email,
                public_key_base64=public_key,
                device_name=device_name,
                device_info=device_info,  # Pass full device_info including potential IMEI
            )

            return RegistrationResponse(
                registration_id=result["registration_id"],
                message=result["message"],
                expires_in=result["expires_in"]
            )

        except Exception as e:
            logger.error(f"Device registration error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"registration_failed: {str(e)}",
            )

    async def verify_registration(
        self, registration_id: str, verification_code: str, challenge_signature: str
    ) -> AuthTokenResponse:
        """Verify device registration using p8fs-auth."""
        try:
            # Verify pending registration and complete device setup
            # This retrieves pending registration, verifies code, creates device/tenant, and issues tokens
            result = await self.mobile_service.verify_pending_registration(
                registration_id=registration_id,
                verification_code=verification_code
            )

            return AuthTokenResponse(
                access_token=result["access_token"],
                token_type="Bearer",
                expires_in=result.get("expires_in", 3600),
                refresh_token=result.get("refresh_token"),
                tenant_id=result["tenant_id"],
            )

        except Exception as e:
            logger.error(f"Registration verification error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Verification failed: {str(e)}",
            )

    async def approve_device(
        self,
        user_code: str,
        approved: bool,
        device_name: str = None,
        user_id: str = None,
        device_id: str = None,
        challenge: str = None,
        signature: str = None,
    ) -> dict[str, str]:
        """Approve device from mobile app using p8fs-auth.

        Supports device-bound authentication via Ed25519 signature verification.
        If challenge and signature are provided, verifies the signature matches
        the approving device's public key.

        Args:
            user_code: Device authorization user code
            approved: Whether to approve or deny
            device_name: Optional device name
            user_id: Tenant ID of approving user
            device_id: Device ID of approving device
            challenge: Optional challenge message that was signed
            signature: Optional Base64-encoded Ed25519 signature of challenge

        Returns:
            Status and message dictionary
        """
        try:
            # If signature provided, verify device-bound authentication
            if challenge and signature:
                logger.info(f"Verifying device-bound authentication for approval")

                # Get the approving device's public key
                device = await self.auth_repo.get_device(device_id, tenant_id=user_id)
                if not device:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Approving device not found",
                    )

                # Verify signature with device's public key
                import base64
                from cryptography.hazmat.primitives.asymmetric import ed25519
                from cryptography.exceptions import InvalidSignature

                try:
                    # Load public key
                    public_key_bytes = base64.b64decode(device.public_key)
                    public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)

                    # Decode signature
                    signature_bytes = base64.b64decode(signature)

                    # Verify signature
                    public_key.verify(signature_bytes, challenge.encode('utf-8'))
                    logger.info(f"✓ Device-bound authentication verified for device {device_id}")

                except InvalidSignature:
                    logger.warning(f"Invalid signature for device approval from {device_id}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid device signature",
                    )
                except Exception as e:
                    logger.error(f"Signature verification error: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Signature verification failed: {str(e)}",
                    )

            if approved:
                # Approve device with device service
                result = await self.device_service.approve_device(
                    user_code=user_code,
                    user_id=user_id,
                    device_id=device_id,
                    device_name=device_name,
                )
                return {
                    "status": "approved",
                    "message": result.get("message", "Device approved successfully"),
                }
            else:
                # Deny device
                result = await self.device_service.deny_device(
                    user_code=user_code,
                    user_id=user_id,
                    device_id=device_id,
                    reason="User denied authorization",
                )
                return {
                    "status": "denied",
                    "message": result.get("message", "Device authorization denied"),
                }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Device approval error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Device approval failed: {str(e)}",
            )

    async def revoke_token(
        self, token: str, token_type_hint: str = None
    ) -> dict[str, str]:
        """Revoke access or refresh token using p8fs-auth."""
        try:
            # Use auth service to revoke token
            success = await self.auth_service.revoke_token(
                token=token, token_type_hint=token_type_hint
            )

            return {"status": "revoked" if success else "not_found"}

        except Exception as e:
            logger.error(f"Token revocation error: {e}", exc_info=True)
            # Per OAuth spec, always return success even on error
            return {"status": "revoked"}

    async def get_user_info(self, user_id: str) -> UserResponse:
        """Get user information from p8fs-auth.
        Deprecate - we dont have users just tenants
        """
        try:
            # Get user devices to find email
            # This is a simplified approach - in production, user info would come from a user service
            devices = await self.auth_repo.get_user_devices(user_id)

            if devices:
                # Use email from first device
                email = devices[0].email
                tenant_id = devices[0].tenant_id or "default"
                created_at = devices[0].created_at.isoformat()
            else:
                raise Exception("No devices for user in get user info")

            return UserResponse(
                id=user_id, email=email, tenant_id=tenant_id, created_at=created_at
            )

        except Exception as e:
            logger.error(f"Get user info error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "user_not_found", "error_description": str(e)},
            )

    async def authorization_endpoint(
        self,
        client_id: str,
        response_type: str,
        redirect_uri: str,
        scope: str = None,
        state: str = None,
        code_challenge: str = None,
        code_challenge_method: str = "S256",
        user_id: str = None,
    ) -> dict[str, str]:
        """Handle OAuth 2.1 authorization requests."""
        try:
            # Validate response_type
            if response_type != "code":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "unsupported_response_type",
                        "error_description": "Only 'code' response type is supported",
                    },
                )

            # Validate PKCE is provided (mandatory in OAuth 2.1)
            if not code_challenge:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "invalid_request",
                        "error_description": "PKCE code_challenge is required",
                    },
                )

            if code_challenge_method != "S256":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "invalid_request",
                        "error_description": "Only S256 code_challenge_method is supported",
                    },
                )

            # Parse scope
            scope_list = scope.split() if scope else ["read"]

            # Use auth service to create authorization code
            auth_code = await self.auth_service.create_authorization_code(
                client_id=client_id,
                user_id=user_id,
                redirect_uri=redirect_uri,
                scope=scope_list,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                state=state
            )

            # Build redirect response
            redirect_params = {"code": auth_code}
            if state:
                redirect_params["state"] = state

            return redirect_params

        except InvalidClientError as e:
            logger.error(f"Invalid client in authorization: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_client", "error_description": str(e)},
            )
        except Exception as e:
            logger.error(f"Authorization endpoint error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "server_error", "error_description": str(e)},
            )

    async def introspect_token(
        self, token: str, token_type_hint: str = None
    ) -> dict[str, Any]:
        """Introspect token for validation using p8fs-auth."""
        try:
            # Use auth service to introspect token
            introspection = await self.auth_service.introspect_token(token=token)

            return introspection

        except Exception as e:
            logger.error(f"Token introspection error: {e}", exc_info=True)
            # Per OAuth spec, return inactive on error
            return {"active": False}

    async def get_oauth_discovery(self, request) -> dict[str, Any]:
        """Build OAuth discovery document with dynamic URLs."""
        from p8fs_cluster.config.settings import config

        # Always use the Host header from the request to determine base URL
        # This ensures the OAuth endpoints match the actual deployment URL
        host = request.headers.get('host', 'localhost:8000')
        scheme = request.url.scheme

        # In production, ensure we use https
        if config.environment == "production" and scheme == "http":
            scheme = "https"

        base_url = f"{scheme}://{host}"

        # Ensure no trailing slash
        base_url = base_url.rstrip("/")
        
        return {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/api/v1/oauth/authorize",
            "token_endpoint": f"{base_url}/api/v1/oauth/token",
            "device_authorization_endpoint": f"{base_url}/api/v1/oauth/device_authorization",
            "device_verification_uri": f"{base_url}/api/v1/oauth/device",
            "userinfo_endpoint": f"{base_url}/api/v1/oauth/userinfo",
            "jwks_uri": f"{base_url}/api/v1/oauth/.well-known/jwks.json",
            "registration_endpoint": f"{base_url}/api/v1/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token", 
                "urn:ietf:params:oauth:grant-type:device_code"
            ],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256", "ES256"],
            "scopes_supported": ["openid", "profile", "email", "read", "write"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
            "claims_supported": ["sub", "email", "tenant", "device"],
            # MCP-specific additions
            "resource_indicators_supported": True,
            "authorization_audience": [base_url],
        }

    async def dev_register_device(
        self,
        email: str,
        public_key: str,
        device_info: dict[str, Any],
        dev_token: str,
        dev_email: str,
        dev_code: str,
    ) -> AuthTokenResponse:
        """Development endpoint for immediate device registration and token issuance."""
        from p8fs_cluster.config.settings import config

        # Validate dev token
        if not config.dev_token_secret or dev_token != config.dev_token_secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_dev_token",
                    "error_description": "Invalid development token",
                },
            )

        try:
            # For development, create tenant directly if it doesn't exist
            tenant = await self.auth_repo.get_tenant_by_email(email)
            if not tenant:
                # Use default dev tenant from config, or create deterministic one
                from p8fs_cluster.config.settings import config
                
                # Check if there's a default dev tenant in config
                tenant_id = getattr(config, 'dev_tenant_id', 'tenant-test')
                
                # If not using default, create deterministic tenant based on email hash
                if tenant_id == 'tenant-test':
                    # Use the default dev tenant
                    pass
                else:
                    import hashlib
                    email_hash = hashlib.sha256(email.encode()).hexdigest()[:16]
                    tenant_id = f"tenant-{email_hash}"

                from p8fs_auth.models.repository import Tenant

                tenant = Tenant(
                    tenant_id=tenant_id,
                    email=email,
                    public_key=public_key,
                    created_at=datetime.utcnow(),
                    metadata={"dev_created": True, "source": "dev_endpoint"},
                )
                tenant = await self.auth_repo.create_tenant(tenant)

                # Create sample moments for new tenant
                try:
                    from p8fs.utils.sample_data import initialize_tenant_sample_data
                    result = await initialize_tenant_sample_data(tenant_id)
                    logger.info(f"Sample data initialized for new tenant {tenant_id}: {result.get('moments_created', 0)} moments, {result.get('sessions_created', 0)} sessions")
                except Exception as e:
                    logger.warning(f"Failed to create sample data for tenant {tenant_id}: {e}", exc_info=True)

            # Create device with deterministic ID based on email + device info
            device_name = device_info.get("device_name", "Dev Device")
            device_type = device_info.get("device_type", "unknown")
            platform = device_info.get("platform", "dev")

            from p8fs_auth.models.auth import Device, DeviceTrustLevel
            import hashlib

            # Create deterministic device ID based on email + device characteristics
            # This allows the same device/email combo to always get the same ID
            device_fingerprint = (
                f"{email}:{device_name}:{device_type}:{platform}:{public_key[:16]}"
            )
            device_hash = hashlib.sha256(device_fingerprint.encode()).hexdigest()[:16]
            device_id = f"dev-{device_hash}"

            device = Device(
                device_id=device_id,
                tenant_id=tenant.tenant_id,
                email=email,
                device_name=device_name,
                public_key=public_key,
                trust_level=DeviceTrustLevel.TRUSTED,  # Skip verification for dev
                metadata=device_info,
                created_at=datetime.utcnow(),
                last_seen=datetime.utcnow(),
            )

            await self.auth_repo.create_device(device)

            # Generate and store tokens using auth service (includes refresh token persistence)
            tokens = await self.auth_service._issue_tokens(
                user_id=device.device_id,
                client_id="p8fs-dev-client",
                scope=["read", "write"],
                additional_claims={
                    "email": email,
                    "tenant": tenant.tenant_id
                }
            )

            logger.info(
                f"Dev token created: device={device.device_id} tenant={tenant.tenant_id} email={email}"
            )

            return AuthTokenResponse(
                access_token=tokens["access_token"],
                token_type="Bearer",
                expires_in=tokens.get("expires_in", 3600),
                refresh_token=tokens.get("refresh_token"),
                tenant_id=tenant.tenant_id,
            )

        except Exception as e:
            logger.error(f"Dev registration error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "dev_registration_failed",
                    "error_description": str(e),
                },
            )
