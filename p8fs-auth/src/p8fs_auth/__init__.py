"""P8FS Authentication Module

Mobile-first authentication system with OAuth 2.1 compliance and end-to-end encryption.
"""

from .crypto.encryption import EncryptionService
from .services.auth_service import AuthenticationService
from .services.credential_service import CredentialService
from .services.device_service import DeviceManagementService
from .services.jwt_key_manager import JWTKeyManager
from .services.mobile_service import MobileAuthenticationService
from .utils.qr_auth import (
    generate_auth_qr_code,
    generate_device_flow_qr,
    generate_login_qr,
    parse_qr_auth_data,
)

__version__ = "0.1.0"

__all__ = [
    # Services
    "AuthenticationService",
    "MobileAuthenticationService",
    "DeviceManagementService",
    "JWTKeyManager",
    "CredentialService",
    "EncryptionService",
    # QR utilities
    "generate_auth_qr_code",
    "generate_device_flow_qr",
    "generate_login_qr",
    "parse_qr_auth_data"
]