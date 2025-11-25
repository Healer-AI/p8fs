"""P8FS Authentication Module Entry Point.

This module provides authentication services for the P8FS system.
Import services and utilities from here for use in other modules.
"""

from p8fs_auth.crypto.encryption import EncryptionService
from p8fs_auth.services.auth_service import AuthenticationService
from p8fs_auth.services.credential_service import CredentialService
from p8fs_auth.services.device_service import DeviceManagementService
from p8fs_auth.services.jwt_key_manager import JWTKeyManager
from p8fs_auth.services.mobile_service import MobileAuthenticationService
from p8fs_auth.utils.qr_auth import (
    generate_auth_qr_code,
    generate_device_flow_qr,
    generate_login_qr,
    parse_qr_auth_data,
)

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

if __name__ == "__main__":
    print("P8FS Authentication Module")
    print("Use the CLI tool: p8fs-auth --help")
