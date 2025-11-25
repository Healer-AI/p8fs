"""Response models for the P8FS API.

These are temporary stubs and will be defined in libraries like p8fs and p8fs-auth
"""

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    version: str
    services: dict[str, str]


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str | None = None


class AuthTokenResponse(BaseModel):
    """OAuth token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str | None = None
    scope: str | None = None
    tenant_id: str | None = None


class ChatMessage(BaseModel):
    """Chat message model."""

    role: str
    content: str
    name: str | None = None


class ChatRequest(BaseModel):
    """Chat completion request."""

    messages: list[ChatMessage]
    model: str = "gpt-3.5-turbo"
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    """Chat completion response."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, int] | None = None


class ChatStreamResponse(BaseModel):
    """Chat streaming response chunk."""

    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[dict[str, Any]]


class DeviceCodeResponse(BaseModel):
    """OAuth device code response."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int
    qr_code: str | None = None  # Base64-encoded PNG image


class RegistrationResponse(BaseModel):
    """Device registration response."""

    registration_id: str
    message: str
    expires_in: int


class UserResponse(BaseModel):
    """User information response."""

    id: str
    email: str
    tenant_id: str
    created_at: str


class AuthorizationParams(BaseModel):
    """OAuth authorization flow parameters."""
    
    response_type: str
    redirect_uri: str
    scope: str | None = None
    state: str | None = None
    code_challenge: str | None = None
    code_challenge_method: str | None = None


class DeviceVerificationMetadata(BaseModel):
    """Metadata for device verification page automation."""
    
    user_code: str
    device_code: str
    client_id: str
    expires_in: int
    poll_interval: int
    verification_uri: str
    verification_uri_complete: str
    authorization_params: AuthorizationParams | None = None
    
    @classmethod
    def from_device_response(
        cls,
        device_response: DeviceCodeResponse,
        client_id: str,
        authorization_params: AuthorizationParams | None = None
    ) -> "DeviceVerificationMetadata":
        """Create metadata from device response."""
        return cls(
            user_code=device_response.user_code,
            device_code=device_response.device_code,
            client_id=client_id,
            expires_in=device_response.expires_in,
            poll_interval=device_response.interval,
            verification_uri=device_response.verification_uri,
            verification_uri_complete=device_response.verification_uri_complete,
            authorization_params=authorization_params
        )


class DeviceVerificationPageContext(BaseModel):
    """Context data for device verification page template."""
    
    qr_code_data: str
    user_code: str
    device_code: str
    client_id: str
    expires_in: int
    poll_interval: int
    json_metadata: str
    auth_flow: bool
    redirect_uri: str | None = None
    state: str | None = None
    
    @classmethod
    def from_device_response(
        cls,
        device_response: DeviceCodeResponse,
        client_id: str,
        auth_flow_params: dict[str, Any] | None = None
    ) -> "DeviceVerificationPageContext":
        """Create page context from device response and parameters."""
        # Create authorization params if provided
        authorization_params = None
        if auth_flow_params and auth_flow_params.get("response_type") and auth_flow_params.get("redirect_uri"):
            authorization_params = AuthorizationParams(**auth_flow_params)
        
        # Create metadata
        metadata = DeviceVerificationMetadata.from_device_response(
            device_response=device_response,
            client_id=client_id,
            authorization_params=authorization_params
        )
        
        # Return context
        return cls(
            qr_code_data=device_response.qr_code or "",
            user_code=device_response.user_code,
            device_code=device_response.device_code,
            client_id=client_id,
            expires_in=device_response.expires_in,
            poll_interval=device_response.interval,
            json_metadata=metadata.model_dump_json(),
            auth_flow=bool(authorization_params),
            redirect_uri=auth_flow_params.get("redirect_uri") if auth_flow_params else None,
            state=auth_flow_params.get("state") if auth_flow_params else None
        )
