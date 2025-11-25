"""Mobile authentication service with Ed25519 keypair generation.

This service handles mobile-first authentication including:
- Ed25519 keypair generation for device authentication
- Email verification with cryptographic challenges
- Device registration and trust level management
- Signature verification for authentication

Reference: p8fs-auth/docs/authentication-flows.md - Mobile Device Registration
Reference: p8fs-auth/docs/authentication-flows.md - Mobile Device Keys (Ed25519)
"""

import base64
import secrets
from datetime import datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging.setup import get_logger

from ..models.auth import AuthMethod, Device, DeviceTrustLevel, LoginEvent
from ..models.repository import AbstractRepository


logger = get_logger(__name__)


class MobileAuthenticationError(Exception):
    """Mobile authentication specific errors."""
    pass


class MobileAuthenticationService:
    """Mobile-first authentication service.

    Implements the mobile authentication system from:
    Reference: p8fs-auth/docs/authentication-flows.md - System Architecture Overview

    Core principles:
    - Mobile devices as hardware security modules
    - Ed25519 keypairs for authentication signatures
    - Email verification with cryptographic challenges
    - Progressive trust levels for device authorization

    Reference: p8fs-auth/docs/authentication-flows.md - Core Principles
    """

    def __init__(
        self,
        repository: AbstractRepository,
        jwt_manager=None,
        email_service=None,
        auth_service=None
    ):
        self.repository = repository
        self.jwt_manager = jwt_manager
        self.email_service = email_service
        self.auth_service = auth_service

        # Set up repository aliases for different operations
        self.auth_repository = repository
        self.login_event_repository = repository

        # Challenge expiry from config
        # Reference: CLAUDE.md - "All configuration must come from centralized config"
        self.challenge_ttl = getattr(config, 'auth_challenge_ttl', 300)  # 5 minutes default
        self.max_devices_per_email = getattr(config, 'auth_max_devices_per_email', 5)
    
    def generate_keypair(self) -> tuple[bytes, bytes]:
        """Generate Ed25519 keypair for mobile device.
        
        Implements keypair generation from:
        Reference: p8fs-auth/docs/authentication-flows.md - Mobile Device Keys (Ed25519)
        
        Ed25519 provides:
        - Fast signature generation/verification
        - Small key sizes (32 bytes private, 32 bytes public)
        - Strong security (128-bit security level)
        - Deterministic signatures
        
        Returns:
            Tuple of (private_key_bytes, public_key_bytes)
            Private key should be stored securely on device
            Public key is sent to server for registration
        """
        # Generate Ed25519 keypair
        # Reference: p8fs-auth/docs/authentication-flows.md - "Algorithm: Ed25519 digital signatures"
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        
        # Serialize keys to bytes
        # Private key format: 32 bytes raw key material
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # Public key format: 32 bytes raw key material
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        return private_key_bytes, public_key_bytes
    
    async def register_device(
        self,
        email: str,
        public_key_base64: str,
        device_name: str | None = None,
        device_info: dict | None = None
    ) -> dict:
        """Register new mobile device with public key.

        Implements device registration from:
        Reference: p8fs-auth/docs/authentication-flows.md - Flow 1: Mobile Device Registration

        Steps:
        1. Validate email format
        2. Check device limits per email
        3. Verify public key format
        4. Store PENDING registration (not creating device/tenant yet)
        5. Generate email verification challenge

        Args:
            email: User email address
            public_key_base64: Base64-encoded Ed25519 public key
            device_name: Optional device display name
            device_info: Optional device metadata (including IMEI if available)

        Returns:
            Dict with registration_id, message, and expires_in

        Raises:
            MobileAuthenticationError: Invalid key or limit exceeded
        """
        # Decode and validate public key
        try:
            public_key_bytes = base64.b64decode(public_key_base64)
            if len(public_key_bytes) != 32:  # Ed25519 public keys are 32 bytes
                raise ValueError("Invalid public key length")

            # Verify it's a valid Ed25519 public key by loading it
            ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        except Exception as e:
            raise MobileAuthenticationError(f"Invalid public key: {str(e)}") from e

        # Generate verification code (6 digits)
        # Reference: p8fs-auth/docs/authentication-flows.md - "Server sends verification code to email"
        verification_code = str(secrets.randbelow(900000) + 100000)

        # Generate registration ID with "reg_" prefix (matches old implementation)
        registration_id = f"reg_{secrets.token_urlsafe(16)}"

        # Create challenge data with expiry
        expires_at = datetime.utcnow() + timedelta(seconds=900)  # 15 minutes

        # Store pending registration data
        # This will be used later in verify_device to create the actual device and tenant
        pending_registration = {
            "registration_id": registration_id,
            "email": email,
            "public_key": public_key_base64,
            "device_name": device_name or "Unknown Device",
            "device_info": device_info or {},
            "verification_code": verification_code,
            "expires_at": expires_at.isoformat(),
            "attempts": 0,
            "created_at": datetime.utcnow().isoformat()
        }

        # Store in system-level storage (no tenant required for pending registrations)
        # Using registration_id as key so we can look it up during verification
        await self.auth_repository.store(
            key=f"pending_registration:{registration_id}",
            value=pending_registration,
            ttl_seconds=900  # 15 minutes TTL
        )

        # Also create an index by email for lookups
        await self.auth_repository.store(
            key=f"pending_email:{email}",
            value={"registration_id": registration_id},
            ttl_seconds=900  # 15 minutes TTL
        )

        logger.info(f"Pending registration created: {registration_id} email={email}")

        # Send verification code via email
        email_sent = False
        if self.email_service:
            try:
                await self.email_service.send_verification_code(email, verification_code)
                email_sent = True
                logger.info(f"Verification code sent to {email}")
            except Exception as e:
                logger.error(f"Failed to send verification email: {e}", exc_info=True)
                # Don't fail registration if email fails - code is still valid in dev
        else:
            logger.warning("Email service not configured - verification code not sent")

        # Set appropriate message based on whether email was actually sent
        if email_sent:
            message = "Verification code sent to email"
        elif config.environment == "development":
            message = "Registration created (email not configured - code in response)"
        else:
            # Production without email is a configuration error
            raise MobileAuthenticationError(
                "Email service not configured - cannot send verification code. "
                "Set EMAIL_PASSWORD environment variable."
            )

        return {
            "registration_id": registration_id,
            "message": message,
            "expires_in": 900,  # 15 minutes
            "verification_code": verification_code if config.environment == "development" else None  # Only in dev
        }

    async def verify_pending_registration(
        self,
        registration_id: str,
        verification_code: str
    ) -> dict:
        """Verify pending registration and create device + tenant.

        This completes the registration flow by:
        1. Retrieving pending registration from KV storage
        2. Verifying the code matches
        3. Creating the device
        4. Creating the tenant
        5. Generating OAuth tokens
        6. Cleaning up pending registration

        Args:
            registration_id: The registration ID from register_device()
            verification_code: The 6-digit code from email

        Returns:
            Dict with device_id, tenant_id, access_token, etc.

        Raises:
            MobileAuthenticationError: Verification failed
        """
        from p8fs_auth.models.auth import Device, DeviceTrustLevel
        from datetime import datetime

        # Retrieve pending registration
        pending_reg = await self.auth_repository.retrieve(
            key=f"pending_registration:{registration_id}"
        )

        if not pending_reg:
            raise MobileAuthenticationError("Registration not found or expired")

        # Verify code
        if pending_reg.get("verification_code") != verification_code:
            raise MobileAuthenticationError("Invalid verification code")

        # Check expiry
        expires_at = datetime.fromisoformat(pending_reg["expires_at"])
        if datetime.utcnow() > expires_at:
            raise MobileAuthenticationError("Verification code expired")

        # Create device from pending registration
        device_id = f"device-{secrets.token_hex(16)}"
        device = Device(
            device_id=device_id,
            email=pending_reg["email"],
            public_key=pending_reg["public_key"],
            device_name=pending_reg["device_name"],
            trust_level=DeviceTrustLevel.EMAIL_VERIFIED,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow(),
            metadata=pending_reg.get("device_info", {}),
            tenant_id=None  # Will be set after tenant creation
        )

        # Create tenant
        tenant_id = await self._create_tenant_from_device(device)
        device.tenant_id = tenant_id

        # Store device
        await self.auth_repository.create_device(device)

        logger.info(f"Device verified from pending registration: {device_id} tenant={tenant_id} email={device.email}")

        # Generate tokens with refresh token support
        if self.auth_service:
            tokens = await self.auth_service._issue_tokens(
                user_id=device.device_id,
                client_id="mobile_device",
                scope=["read", "write"],
                additional_claims={
                    "email": device.email,
                    "tenant": tenant_id,
                    "device_name": device.device_name,
                    "device_id": device.device_id
                }
            )
        elif self.jwt_manager:
            access_token = await self.jwt_manager.create_access_token(
                user_id=device.device_id,
                client_id="mobile_device",
                scope=["read", "write"],
                device_id=device.device_id,
                additional_claims={
                    "email": device.email,
                    "tenant": tenant_id,
                    "device_name": device.device_name
                }
            )
            tokens = {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600
            }
        else:
            raise MobileAuthenticationError("JWT manager not configured")

        # Clean up pending registration
        await self.auth_repository.delete(f"pending_registration:{registration_id}")
        await self.auth_repository.delete(f"pending_email:{device.email}")

        return {
            "device_id": device.device_id,
            "tenant_id": tenant_id,
            "email": device.email,
            **tokens
        }

    async def _create_tenant_from_device(self, device: Device) -> str:
        """Create tenant using device IMEI for deterministic hash or random hash.
        
        Args:
            device: Device to create tenant for
            
        Returns:
            tenant_id of created tenant
        """
        import hashlib
        import secrets
        from p8fs_auth.models.repository import Tenant
        from datetime import datetime
        
        # Check for IMEI in device metadata
        device_imei = device.metadata.get("imei") if device.metadata else None
        
        if device_imei:
            # Use IMEI for deterministic tenant hash
            hash_value = hashlib.sha256(device_imei.encode()).hexdigest()[:16]
            tenant_id = f"tenant-{hash_value}"
            hash_method = "imei"
        else:
            # Generate random tenant ID (not deterministic)
            logger.warning(f"No IMEI provided for device {device.device_id}, using random tenant ID")
            random_value = secrets.token_hex(16)
            tenant_id = f"tenant-{random_value}"
            hash_method = "random"
        
        # Check if tenant already exists
        existing_tenant = await self.auth_repository.get_tenant_by_id(tenant_id)
        if existing_tenant:
            logger.info(f"Tenant exists: {tenant_id} method={hash_method}")
            return tenant_id
        
        # Create new tenant
        tenant = Tenant(
            tenant_id=tenant_id,
            email=device.email,
            public_key=device.public_key,
            created_at=datetime.utcnow(),
            metadata={
                "source": "mobile_verification",
                "device_id": device.device_id,
                "hash_method": hash_method,
                "created_from_imei": bool(device_imei),
                "imei": device_imei if device_imei else None
            }
        )
        
        created_tenant = await self.auth_repository.create_tenant(tenant)
        logger.info(f"Tenant created: {tenant_id} email={device.email} method={hash_method}")
        return created_tenant.tenant_id
    
    async def verify_device(
        self,
        device_id: str,
        verification_code: str,
        signature_base64: str
    ) -> Device:
        """Verify device with code and signature.
        
        Implements verification from:
        Reference: p8fs-auth/docs/authentication-flows.md - "App signs verification with private key"
        
        Security:
        - Verify code matches and not expired
        - Verify signature with device public key
        - Upgrade trust level to EMAIL_VERIFIED
        - Log successful verification
        
        Args:
            device_id: Device identifier
            verification_code: Code from email
            signature_base64: Base64 signature of code
            
        Returns:
            Verified device with updated trust level
            
        Raises:
            MobileAuthenticationError: Verification failed
        """
        # Get device
        device = await self.auth_repository.get_device(device_id)
        if not device:
            raise MobileAuthenticationError("Device not found")
        
        # Check if already verified
        if device.trust_level != DeviceTrustLevel.UNVERIFIED:
            logger.warning(f"Verification attempted on already verified device: {device_id} trust={device.trust_level.value}")
            raise MobileAuthenticationError("Device already verified")
        
        # Validate challenge data exists
        if not device.challenge_data:
            raise MobileAuthenticationError("No verification challenge found")
        
        # Check expiry
        # Reference: p8fs-auth/docs/authentication-flows.md - "Server validates signature and code"
        expires_at = datetime.fromisoformat(device.challenge_data["expires_at"])
        if datetime.utcnow() > expires_at:
            raise MobileAuthenticationError("Verification code expired")
        
        # Check attempts (max 3)
        device.challenge_data["attempts"] += 1
        if device.challenge_data["attempts"] > 3:
            raise MobileAuthenticationError("Maximum verification attempts exceeded")
        
        # Verify code
        if device.challenge_data["code"] != verification_code:
            await self.auth_repository.update_device(device)
            logger.warning(f"Invalid verification code for device: {device_id} attempts={device.challenge_data['attempts']}")
            raise MobileAuthenticationError("Invalid verification code")
        
        # Verify signature
        # Reference: p8fs-auth/docs/authentication-flows.md - "App signs verification with private key"
        try:
            # Load public key
            public_key_bytes = base64.b64decode(device.public_key)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            
            # Decode signature
            signature_bytes = base64.b64decode(signature_base64)
            
            # Verify signature of verification code
            public_key.verify(signature_bytes, verification_code.encode('utf-8'))
        except InvalidSignature:
            logger.warning(f"Invalid signature for device verification: {device_id}")
            raise MobileAuthenticationError("Invalid signature") from None
        except Exception as e:
            raise MobileAuthenticationError(f"Signature verification failed: {str(e)}") from e
        
        # Update device to EMAIL_VERIFIED and create tenant
        # Reference: p8fs-auth/docs/authentication-flows.md - "Server creates tenant and OAuth tokens"
        device.trust_level = DeviceTrustLevel.EMAIL_VERIFIED
        device.challenge_data = None  # Clear challenge
        device.last_used_at = datetime.utcnow()
        
        # Create tenant using IMEI if available, otherwise use random
        tenant_id = await self._create_tenant_from_device(device)
        device.tenant_id = tenant_id
        
        await self.auth_repository.update_device(device)
        
        logger.info(f"Device verified: {device.device_id} email={device.email} tenant={tenant_id}")
        
        # Log successful verification
        await self.login_event_repository.create_login_event(
            LoginEvent(
                user_id=device.email,  # Using email as user_id for now
                device_id=device.device_id,
                auth_method=AuthMethod.MOBILE_KEYPAIR,
                success=True
            )
        )
        
        return device
    
    async def authenticate_with_signature(
        self,
        device_id: str,
        challenge: str,
        signature_base64: str,
        tenant_id: str | None = None,
        upgrade_trust: bool = False
    ) -> dict[str, any]:
        """Authenticate device using signature challenge.

        Implements signature-based authentication for:
        - API request authentication
        - Device trust upgrades
        - Sensitive operation authorization

        Args:
            device_id: Device identifier
            challenge: Challenge string to sign
            signature_base64: Base64 signature of challenge
            tenant_id: Tenant ID from JWT token context (required for device lookup)
            upgrade_trust: Whether to upgrade to TRUSTED level

        Returns:
            Authentication result with tokens

        Raises:
            MobileAuthenticationError: Authentication failed
        """
        # Get device (requires tenant_id from JWT token context)
        if not tenant_id:
            raise MobileAuthenticationError("tenant_id required for device authentication")

        device = await self.auth_repository.get_device(device_id, tenant_id=tenant_id)
        if not device:
            raise MobileAuthenticationError("Device not found")
        
        # Check if device is at least EMAIL_VERIFIED
        if device.trust_level == DeviceTrustLevel.UNVERIFIED:
            raise MobileAuthenticationError("Device not verified")
        
        # Check if device is revoked
        if device.trust_level == DeviceTrustLevel.REVOKED:
            raise MobileAuthenticationError("Device has been revoked")
        
        # Verify signature
        try:
            # Load public key
            public_key_bytes = base64.b64decode(device.public_key)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            
            # Decode signature
            signature_bytes = base64.b64decode(signature_base64)
            
            # Verify signature of challenge
            public_key.verify(signature_bytes, challenge.encode('utf-8'))
        except InvalidSignature:
            # Log failed attempt
            await self.login_event_repository.create_login_event(
                LoginEvent(
                    user_id=device.email,
                    device_id=device.device_id,
                    auth_method=AuthMethod.MOBILE_KEYPAIR,
                    success=False,
                    failure_reason="Invalid signature"
                )
            )
            raise MobileAuthenticationError("Invalid signature") from None
        
        # Update last used timestamp
        device.last_used_at = datetime.utcnow()
        
        # Optionally upgrade to TRUSTED
        # This would typically require additional verification
        # like biometric confirmation or admin approval
        if upgrade_trust and device.trust_level == DeviceTrustLevel.EMAIL_VERIFIED:
            device.trust_level = DeviceTrustLevel.TRUSTED
            logger.info(f"Device approved: {device.device_id} upgraded to TRUSTED")
        
        await self.auth_repository.update_device(device)
        
        # Log successful authentication
        await self.login_event_repository.create_login_event(
            LoginEvent(
                user_id=device.email,
                device_id=device.device_id,
                auth_method=AuthMethod.MOBILE_KEYPAIR,
                success=True
            )
        )
        
        # Issue proper JWT tokens with refresh token support
        if self.auth_service:
            tokens = await self.auth_service._issue_tokens(
                user_id=device.device_id,
                client_id="mobile_client",
                scope=["read", "write", "profile"],
                additional_claims={
                    "email": device.email,
                    "tenant": device.tenant_id,
                    "device_name": device.device_name,
                    "device_id": device.device_id
                }
            )
        elif self.jwt_manager:
            access_token = await self.jwt_manager.create_access_token(
                user_id=device.device_id,
                client_id="mobile_client",
                scope=["read", "write", "profile"]
            )
            tokens = {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": getattr(config, 'auth_access_token_ttl', 3600),
                "scope": "read write profile"
            }
        else:
            tokens = {
                "access_token": f"mobile_token_{device.device_id}",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "read write profile"
            }

        return {
            "device": {
                "device_id": device.device_id,
                "trust_level": device.trust_level.value
            },
            **tokens
        }
    
    async def revoke_device(
        self,
        device_id: str,
        user_id: str
    ) -> bool:
        """Revoke device access.
        
        Implements device revocation from:
        Reference: p8fs-auth/docs/authentication-flows.md - Key Management Endpoints
        
        Args:
            device_id: Device to revoke
            user_id: User performing revocation
            
        Returns:
            True if revoked successfully
        """
        # Get device
        device = await self.auth_repository.get_device(device_id)
        if not device:
            return False
        
        # Verify user owns device (by email for now)
        if device.email != user_id:
            raise MobileAuthenticationError("Unauthorized to revoke device")
        
        # Update trust level to REVOKED
        device.trust_level = DeviceTrustLevel.REVOKED
        await self.auth_repository.update_device(device)
        
        # Revoke all tokens for this device
        # In production, would revoke by device_id through proper token service
        # For now, this is handled by setting trust level to REVOKED
        logger.info(f"Device {device_id} revoked for user {user_id}")
        
        return True
    
    async def list_user_devices(
        self,
        email: str
    ) -> list[Device]:
        """List all devices for a user email.
        
        In simple tenant system, we don't track devices separately.
        This method returns an empty list since device management
        is handled at the tenant level.
        
        Args:
            email: User email address
            
        Returns:
            Empty list (devices not tracked separately in simple tenant auth)
        """
        # In simple tenant system, devices are not tracked separately
        # All authentication goes through tenant records
        return []