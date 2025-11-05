"""QR code authentication utilities for P8FS.

This module provides QR code generation for various authentication flows:
- Device authorization (OAuth device flow)
- Direct login requests
- Custom authentication flows

Reference: p8fs-auth/docs/authentication-flows.md - Flow 2: Desktop Authentication via QR Code
"""

import base64
import io
import json
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import qrcode
from p8fs_cluster.config.settings import config
from pydantic import BaseModel, Field


class AuthQRRequest(BaseModel):
    """Authentication QR code request parameters."""
    
    # Required fields
    tenant_id: str = Field(..., description="Tenant identifier")
    auth_type: str = Field(..., description="Authentication type: device_flow, direct_login, custom")
    
    # Common optional fields
    client_id: str | None = Field(None, description="OAuth client ID")
    scope: list[str] | None = Field(None, description="Requested permissions")
    redirect_uri: str | None = Field(None, description="Callback URL after auth")
    state: str | None = Field(None, description="CSRF protection state")
    
    # Device flow specific
    device_code: str | None = Field(None, description="Device authorization code")
    user_code: str | None = Field(None, description="User-friendly verification code")
    verification_uri: str | None = Field(None, description="Verification URL")
    
    # Direct login specific  
    session_id: str | None = Field(None, description="Session identifier for login")
    challenge: str | None = Field(None, description="Cryptographic challenge")
    
    # Custom fields
    metadata: dict[str, Any] | None = Field(None, description="Additional custom data")
    expires_at: datetime | None = Field(None, description="QR code expiration")


def generate_auth_qr_code(
    tenant_id: str,
    auth_type: str = "device_flow",
    size: int = 400,
    error_correction: str = "M",
    format: str = "png",
    **kwargs: Any
) -> str:
    """Generate QR code for authentication.
    
    This is the main function for generating authentication QR codes.
    It supports multiple authentication flows and can be extended with kwargs.
    
    Reference: p8fs-auth/docs/authentication-flows.md - "Desktop displays QR code with user code"
    
    Args:
        tenant_id: Tenant identifier for multi-tenant isolation
        auth_type: Type of authentication flow
            - "device_flow": OAuth 2.1 device authorization
            - "direct_login": Direct mobile app login
            - "custom": Custom authentication flow
        size: QR code size in pixels (default: 400)
        error_correction: Error correction level: L, M, Q, H (default: M)
        format: Output format: png, svg (default: png)
        **kwargs: Additional parameters based on auth_type:
            
            For device_flow:
                - user_code: User-friendly code (required)
                - device_code: Device code (optional)
                - verification_uri: Base verification URL (optional)
                - client_id: OAuth client (optional)
                - scope: Requested permissions (optional)
                
            For direct_login:
                - session_id: Session to authenticate (required)
                - challenge: Cryptographic challenge (required)
                - redirect_uri: Where to go after login (optional)
                
            For custom:
                - Any parameters needed for custom flow
                
    Returns:
        Base64-encoded image data URL (data:image/png;base64,...)
        
    Examples:
        # Device flow QR code
        qr = generate_auth_qr_code(
            tenant_id="acme-corp",
            auth_type="device_flow",
            user_code="ABCD-1234",
            client_id="desktop-app"
        )
        
        # Direct login QR code
        qr = generate_auth_qr_code(
            tenant_id="acme-corp", 
            auth_type="direct_login",
            session_id="sess_123",
            challenge="challenge_xyz",
            redirect_uri="https://app.example.com/dashboard"
        )
        
        # Custom flow with metadata
        qr = generate_auth_qr_code(
            tenant_id="acme-corp",
            auth_type="custom",
            action="approve_transaction",
            transaction_id="tx_789",
            amount="$100.00",
            metadata={"merchant": "Coffee Shop"}
        )
    """
    # Create request object for validation
    request_data = {
        "tenant_id": tenant_id,
        "auth_type": auth_type,
        **kwargs
    }
    
    # Build QR code data based on auth type
    qr_data = _build_qr_data(request_data)
    
    # Generate QR code image
    qr_image = _create_qr_image(
        qr_data,
        size=size,
        error_correction=error_correction
    )
    
    # Convert to requested format
    if format.lower() == "png":
        return _image_to_data_url(qr_image, "png")
    elif format.lower() == "svg":
        # For SVG, regenerate with SVG factory
        return _create_qr_svg(qr_data, size=size)
    else:
        raise ValueError(f"Unsupported format: {format}")


def generate_device_flow_qr(
    tenant_id: str,
    user_code: str,
    client_id: str,
    device_code: str | None = None,
    scope: list[str] | None = None,
    **kwargs: Any
) -> str:
    """Generate QR code specifically for OAuth device flow.
    
    Convenience function for device authorization flow.
    
    Reference: p8fs-auth/docs/authentication-flows.md - Flow 2: Desktop Authentication via QR Code
    
    Args:
        tenant_id: Tenant identifier
        user_code: User-friendly verification code (e.g., "ABCD-1234")
        client_id: OAuth client requesting authorization
        device_code: Optional device code for direct approval
        scope: Optional requested permissions
        **kwargs: Additional parameters (size, error_correction, etc.)
        
    Returns:
        Base64-encoded PNG image data URL
    """
    return generate_auth_qr_code(
        tenant_id=tenant_id,
        auth_type="device_flow",
        user_code=user_code,
        client_id=client_id,
        device_code=device_code,
        scope=scope,
        **kwargs
    )


def generate_login_qr(
    tenant_id: str,
    session_id: str,
    challenge: str,
    redirect_uri: str | None = None,
    expires_in: int = 300,
    **kwargs: Any
) -> str:
    """Generate QR code for direct login.
    
    Creates a QR code that mobile app can scan to authenticate a session.
    
    Args:
        tenant_id: Tenant identifier
        session_id: Session to authenticate
        challenge: Cryptographic challenge to sign
        redirect_uri: Optional post-login redirect
        expires_in: Expiration in seconds (default: 5 minutes)
        **kwargs: Additional parameters
        
    Returns:
        Base64-encoded PNG image data URL
    """
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    
    return generate_auth_qr_code(
        tenant_id=tenant_id,
        auth_type="direct_login",
        session_id=session_id,
        challenge=challenge,
        redirect_uri=redirect_uri,
        expires_at=expires_at,
        **kwargs
    )


def _build_qr_data(request: dict[str, Any]) -> str:
    """Build QR code data based on authentication type.
    
    Constructs the URL or data payload that will be encoded in the QR code.
    
    Args:
        request: Authentication request parameters
        
    Returns:
        String data to encode in QR code
    """
    auth_type = request.get("auth_type", "device_flow")
    base_url = getattr(config, 'auth_base_url', "https://auth.p8fs.com")
    
    if auth_type == "device_flow":
        # Build device flow verification URL
        # Reference: p8fs-auth/docs/authentication-flows.md - "verification_uri_complete"
        user_code = request.get("user_code")
        if not user_code:
            raise ValueError("user_code required for device_flow")
        
        # Build URL with query parameters
        params = {
            "user_code": user_code,
            "tenant_id": request["tenant_id"]
        }
        
        if request.get("client_id"):
            params["client_id"] = request["client_id"]
        
        if request.get("scope"):
            params["scope"] = " ".join(request["scope"])
            
        verification_uri = request.get("verification_uri", f"{base_url}/device")
        return f"{verification_uri}?{urlencode(params)}"
    
    elif auth_type == "direct_login":
        # Build direct login URL with p8fs:// scheme for mobile app
        session_id = request.get("session_id")
        challenge = request.get("challenge")
        
        if not session_id or not challenge:
            raise ValueError("session_id and challenge required for direct_login")
        
        # Use custom scheme for mobile app deep linking
        data = {
            "action": "login",
            "tenant_id": request["tenant_id"],
            "session_id": session_id,
            "challenge": challenge
        }
        
        if request.get("redirect_uri"):
            data["redirect_uri"] = request["redirect_uri"]
            
        if request.get("expires_at"):
            data["expires_at"] = request["expires_at"].isoformat()
        
        # Create p8fs:// URL for mobile app
        return f"p8fs://auth/login?{urlencode(data)}"
    
    elif auth_type == "custom":
        # For custom flows, encode all data as JSON
        custom_data = {
            "type": "p8fs_auth",
            "auth_type": "custom",
            "tenant_id": request["tenant_id"],
            "timestamp": datetime.utcnow().isoformat(),
            **{k: v for k, v in request.items() 
               if k not in ["auth_type", "tenant_id", "size", "error_correction", "format"]}
        }
        
        # For custom, encode as JSON for flexibility
        return json.dumps(custom_data, sort_keys=True)
    
    else:
        raise ValueError(f"Unsupported auth_type: {auth_type}")


def _create_qr_image(
    data: str,
    size: int = 400,
    error_correction: str = "M"
) -> Any:
    """Create QR code image.
    
    Args:
        data: Data to encode
        size: Image size in pixels
        error_correction: Error correction level (L, M, Q, H)
        
    Returns:
        PIL Image object
    """
    # Map error correction levels
    ec_levels = {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H
    }
    
    ec_level = ec_levels.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M)
    
    # Create QR code
    qr = qrcode.QRCode(
        version=None,  # Auto-determine version based on data
        error_correction=ec_level,
        box_size=10,
        border=4,
    )
    
    qr.add_data(data)
    qr.make(fit=True)
    
    # Create image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Resize to requested size
    img = img.resize((size, size))
    
    return img


def _image_to_data_url(img: Any, format: str = "png") -> str:
    """Convert PIL image to data URL.
    
    Args:
        img: PIL Image object
        format: Image format (png, jpeg)
        
    Returns:
        Base64-encoded data URL
    """
    buffer = io.BytesIO()
    img.save(buffer, format=format.upper())
    img_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    mime_type = f"image/{format.lower()}"
    return f"data:{mime_type};base64,{img_data}"


def _create_qr_svg(data: str, size: int = 400) -> str:
    """Create QR code as SVG.
    
    Args:
        data: Data to encode
        size: SVG size
        
    Returns:
        SVG data URL
    """
    import qrcode.image.svg
    
    # Create QR code with SVG factory
    factory = qrcode.image.svg.SvgPathImage
    
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
        image_factory=factory
    )
    
    qr.add_data(data)
    qr.make(fit=True)
    
    # Create SVG
    img = qr.make_image()
    
    # Convert to string
    buffer = io.BytesIO()
    img.save(buffer)
    svg_data = buffer.getvalue().decode('utf-8')
    
    # Encode as data URL
    svg_b64 = base64.b64encode(svg_data.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{svg_b64}"


def parse_qr_auth_data(qr_data: str) -> dict[str, Any]:
    """Parse QR code data back into authentication parameters.
    
    Useful for mobile apps to understand what the QR code contains.
    
    Args:
        qr_data: Raw data from QR code scan
        
    Returns:
        Parsed authentication parameters
    """
    # Try to parse as URL first
    if qr_data.startswith(("https://", "http://", "p8fs://")):
        # Parse URL and extract parameters
        from urllib.parse import parse_qs, urlparse
        
        parsed = urlparse(qr_data)
        params = parse_qs(parsed.query)
        
        # Flatten single-value lists
        result = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
        
        # Determine auth type from URL
        if parsed.scheme == "p8fs":
            result["auth_type"] = "direct_login"
        elif "/device" in parsed.path:
            result["auth_type"] = "device_flow"
        
        return result
    
    # Try to parse as JSON (custom flows)
    try:
        data = json.loads(qr_data)
        if isinstance(data, dict) and data.get("type") == "p8fs_auth":
            return data
    except json.JSONDecodeError:
        pass
    
    # Unknown format
    return {"raw_data": qr_data}