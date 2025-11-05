"""Authentication models for P8FS Auth module."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class DeviceTrustLevel(str, Enum):
    """Device trust levels."""
    UNVERIFIED = "unverified"
    EMAIL_VERIFIED = "email_verified" 
    TRUSTED = "trusted"
    REVOKED = "revoked"


class TokenType(str, Enum):
    """OAuth token types."""
    ACCESS = "access_token"
    REFRESH = "refresh_token"
    DEVICE = "device_code"
    USER = "user_code"


class AuthMethod(str, Enum):
    """Authentication methods."""
    MOBILE_KEYPAIR = "mobile_keypair"
    PASSWORD = "password"
    DEVICE_CODE = "device_code"


class Device(BaseModel):
    """Mobile device registration."""
    device_id: str = Field(..., description="Unique device identifier")
    public_key: str = Field(..., description="Ed25519 public key (base64)")
    email: str = Field(..., description="Associated email address")
    device_name: str | None = Field(None, description="Device display name")
    trust_level: DeviceTrustLevel = Field(DeviceTrustLevel.UNVERIFIED)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = Field(None)
    challenge_data: dict[str, Any] | None = Field(None, description="Verification challenge")
    tenant_id: str | None = Field(None, description="Tenant isolation")


class DeviceToken(BaseModel):
    """Device authorization flow tokens."""
    device_code: str = Field(..., description="Device verification code")
    user_code: str = Field(..., description="User-friendly code for approval")
    verification_uri: str = Field(..., description="URL for device approval")
    verification_uri_complete: str | None = Field(None, description="Complete verification URL")
    expires_in: int = Field(600, description="Expiration time in seconds")
    interval: int = Field(5, description="Polling interval in seconds")
    device_id: str | None = Field(None, description="Associated device ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: datetime | None = Field(None)
    access_token: str | None = Field(None)


class AuthToken(BaseModel):
    """OAuth access/refresh tokens."""
    token_id: str = Field(default_factory=lambda: str(uuid4()))
    token_type: TokenType = Field(...)
    token_value: str = Field(..., description="JWT token string")
    user_id: str = Field(..., description="Associated user ID")
    device_id: str | None = Field(None, description="Associated device ID")
    client_id: str = Field(..., description="OAuth client ID")
    scope: list[str] = Field(default_factory=list, description="Token scopes")
    expires_at: datetime = Field(..., description="Token expiration")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    revoked_at: datetime | None = Field(None)
    refresh_token: str | None = Field(None, description="Associated refresh token")
    tenant_id: str | None = Field(None, description="Tenant isolation")


class LoginEvent(BaseModel):
    """Authentication event logging."""
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = Field(..., description="User identifier")
    device_id: str | None = Field(None, description="Device identifier")
    auth_method: AuthMethod = Field(..., description="Authentication method used")
    success: bool = Field(..., description="Whether authentication succeeded")
    ip_address: str | None = Field(None, description="Client IP address")
    user_agent: str | None = Field(None, description="Client user agent")
    location: dict[str, Any] | None = Field(None, description="Geolocation data")
    anomaly_score: float | None = Field(None, description="Security anomaly score")
    failure_reason: str | None = Field(None, description="Failure description")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str | None = Field(None, description="Tenant isolation")


class OAuthClient(BaseModel):
    """OAuth 2.1 client configuration."""
    client_id: str = Field(..., description="OAuth client identifier")
    client_name: str = Field(..., description="Human-readable client name")
    client_type: str = Field(..., description="public or confidential")
    redirect_uris: list[str] = Field(default_factory=list, description="Valid redirect URIs")
    grant_types: list[str] = Field(default_factory=list, description="Allowed grant types")
    scopes: list[str] = Field(default_factory=list, description="Available scopes")
    token_endpoint_auth_method: str = Field("none", description="Token endpoint auth method")
    require_pkce: bool = Field(True, description="Require PKCE for security")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str | None = Field(None, description="Tenant isolation")


class PKCEChallenge(BaseModel):
    """PKCE challenge data."""
    code_challenge: str = Field(..., description="PKCE code challenge")
    code_challenge_method: str = Field("S256", description="Challenge method")
    code_verifier: str | None = Field(None, description="Code verifier for validation")
    state: str | None = Field(None, description="OAuth state parameter")
    created_at: datetime = Field(default_factory=datetime.utcnow)