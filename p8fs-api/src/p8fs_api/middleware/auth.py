"""Authentication middleware for JWT token validation."""


from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError as JWTError, ExpiredSignatureError
from p8fs_auth.services.jwt_key_manager import JWTKeyManager
from p8fs_cluster.logging.setup import get_logger
from p8fs_cluster.config.settings import config
from pydantic import BaseModel
from typing import Optional

logger = get_logger(__name__)

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


class User(BaseModel):
    """User model for authenticated requests."""
    id: str
    email: str
    tenant_id: str
    device_id: str | None = None


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str
    email: str
    tenant: str
    client: str = ""
    scope: list[str] = []
    device: str | None = None
    exp: int
    iat: int


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenPayload:
    """Verify JWT token and return payload.

    MCP Specification Section: Access Token Usage
    - Validates Bearer tokens from Authorization header
    - TODO: Add resource parameter validation for token audience binding
    """
    # If auth is disabled (local testing only), return a test token payload
    if config.auth_disabled:
        logger.warning("AUTH DISABLED: Bypassing JWT validation - only for local testing!")
        return TokenPayload(
            sub=config.default_tenant_id,
            email="test@local.dev",
            tenant=config.default_tenant_id,
            client="test-client",
            scope=["read", "write"],
            device=None,
            exp=9999999999,
            iat=0
        )

    token = credentials.credentials
    error_code = None
    error_detail = None

    try:
        # Use proper ES256 verification through JWTKeyManager
        jwt_manager = JWTKeyManager()
        payload = await jwt_manager.verify_token(token)

        # Log full payload for debugging (excluding sensitive fields)
        debug_payload = {k: v for k, v in payload.items() if k not in ['exp', 'iat', 'nbf']}
        logger.debug(f"Token payload received: {debug_payload}")

        # Validate required fields
        if not payload.get("sub") and not payload.get("user_id"):
            error_code = "AUTH_INVALID_TOKEN_SUBJECT"
            error_detail = "Token missing subject claim"
            logger.warning(f"Token validation failed: {error_detail} token={token[:20]}...")
            raise ValueError(error_detail)

        # For device flow tokens, the sub claim IS the tenant_id
        # Regular tokens have separate tenant claim
        tenant_value = payload.get("tenant") or payload.get("tenant_id")
        if not tenant_value:
            # Check if this is a device flow token where sub is tenant_id
            sub_value = payload.get("sub") or payload.get("user_id", "")
            logger.debug(f"Checking if sub is tenant_id: sub={sub_value}")
            if sub_value.startswith("tenant-"):
                logger.debug(f"Device flow token detected: using sub as tenant_id")
                tenant_value = sub_value
            else:
                error_code = "AUTH_INVALID_TOKEN_TENANT"
                error_detail = "Token missing tenant claim"
                logger.warning(f"Token validation failed: {error_detail}. Full payload: {debug_payload}")
                raise ValueError(error_detail)
        
        # Map JWT claims to our TokenPayload structure
        token_data = TokenPayload(
            sub=payload.get("sub") or payload.get("user_id"),
            email=payload.get("email", ""),
            tenant=tenant_value,
            client=payload.get("client_id", ""),
            scope=payload.get("scope", "").split() if isinstance(payload.get("scope"), str) else payload.get("scope", []),
            device=payload.get("device_id"),
            exp=payload.get("exp", 0),
            iat=payload.get("iat", 0)
        )
        
        logger.debug(f"Token verified: user={token_data.sub} tenant={token_data.tenant}")
        return token_data
        
    except ExpiredSignatureError:
        error_code = "AUTH_TOKEN_EXPIRED"
        error_detail = "Token has expired"
        logger.warning(f"Token validation failed: {error_detail} token={token[:20]}...")
    except JWTError as e:
        error_code = "AUTH_INVALID_TOKEN"
        error_detail = f"Token validation failed: {str(e)}"
        logger.warning(f"Token validation failed: {error_detail} token={token[:20]}...")
    except ValueError:
        # Already logged above
        pass
    except Exception as e:
        error_code = "AUTH_UNEXPECTED_ERROR"
        error_detail = f"Unexpected error validating token: {str(e)}"
        logger.error(f"Unexpected token validation error: {e}", exc_info=True)
    
    # Log the specific error for debugging
    logger.warning(f"Authentication failed: code={error_code} detail={error_detail}")
    
    # Return a simple string detail for now, with error code in headers
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"{error_code}: {error_detail}" if error_code else "Invalid authentication credentials",
        headers={
            "WWW-Authenticate": "Bearer",
            "X-Auth-Error-Code": error_code or "AUTH_INVALID_CREDENTIALS"
        },
    )


async def get_current_user(token_payload: TokenPayload = Depends(verify_token)) -> User:
    """Get current authenticated user from token."""
    return User(
        id=token_payload.sub,
        email=token_payload.email,
        tenant_id=token_payload.tenant,
        device_id=token_payload.device
    )


async def get_optional_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security)) -> Optional[TokenPayload]:
    """Get optional token payload without raising auth errors."""
    # If auth is disabled (local testing only), return a test token payload
    if config.auth_disabled:
        logger.debug("AUTH DISABLED: Bypassing JWT validation for optional token")
        return TokenPayload(
            sub=config.default_tenant_id,
            email="test@local.dev",
            tenant=config.default_tenant_id,
            client="test-client",
            scope=["read", "write"],
            device=None,
            exp=9999999999,
            iat=0
        )

    if not credentials:
        return None

    try:
        jwt_manager = JWTKeyManager()
        payload = await jwt_manager.verify_token(credentials.credentials)

        # Log full payload for debugging (excluding sensitive fields)
        debug_payload = {k: v for k, v in payload.items() if k not in ['exp', 'iat', 'nbf']}
        logger.debug(f"Optional token payload received: {debug_payload}")

        # Validate required fields
        if not payload.get("sub") and not payload.get("user_id"):
            logger.debug("Optional token missing subject claim")
            return None

        # For device flow tokens, the sub claim IS the tenant_id
        # Regular tokens have separate tenant claim
        tenant_value = payload.get("tenant") or payload.get("tenant_id")
        if not tenant_value:
            # Check if this is a device flow token where sub is tenant_id
            sub_value = payload.get("sub") or payload.get("user_id", "")
            if sub_value.startswith("tenant-"):
                logger.debug(f"Optional token: Device flow token detected, using sub as tenant_id")
                tenant_value = sub_value
            else:
                logger.warning(f"Optional token missing tenant claim. Full payload: {debug_payload}")
                return None

        return TokenPayload(
            sub=payload.get("sub") or payload.get("user_id"),
            email=payload.get("email", ""),
            tenant=tenant_value,
            client=payload.get("client_id", ""),
            scope=payload.get("scope", "").split() if isinstance(payload.get("scope"), str) else payload.get("scope", []),
            device=payload.get("device_id"),
            exp=payload.get("exp", 0),
            iat=payload.get("iat", 0)
        )
    except JWTError as e:
        logger.debug(f"Optional token validation failed: {e}")
        return None


