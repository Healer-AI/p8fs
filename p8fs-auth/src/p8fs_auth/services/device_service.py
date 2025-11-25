"""Device management service for registration and approval flows.

This service handles device lifecycle management including:
- Device registration and QR code generation
- Device approval workflows
- Trust level management
- Device listing and revocation

Reference: p8fs-auth/docs/authentication-flows.md - Flow 2: Desktop Authentication via QR Code
Reference: p8fs-auth/docs/authentication-flows.md - Key Management Endpoints
"""

import base64
import io
from datetime import datetime, timedelta

import qrcode
from p8fs_cluster.config.settings import config

from ..models.auth import AuthMethod, Device, DeviceTrustLevel, LoginEvent
from ..models.repository import AbstractRepository
from .auth_service import AuthenticationService, InvalidGrantError


class DeviceManagementService:
    """Device lifecycle management service.
    
    Implements device management from:
    Reference: p8fs-auth/docs/authentication-flows.md - Device Authorization Grant
    
    Key features:
    - QR code generation for device pairing
    - Trust level progression 
    - Device approval workflows
    - Security event logging
    """
    
    def __init__(
        self,
        repository: AbstractRepository,
        auth_service: AuthenticationService
    ):
        self.repository = repository
        self.auth_service = auth_service
        
        # Set up repository aliases for different operations
        self.token_repository = repository
        self.auth_repository = repository
        self.login_event_repository = repository
        
        # Configuration from centralized settings
        # Reference: CLAUDE.md - "All configuration must come from centralized config"
        self.max_devices_per_user = getattr(config, 'auth_max_devices_per_user', 10)
        self.device_code_ttl = getattr(config, 'auth_device_code_ttl', 600)  # 10 minutes
        self.qr_code_size = getattr(config, 'auth_qr_code_size', 400)  # pixels
    
    async def initiate_device_flow(
        self,
        client_id: str,
        scope: list[str] | None = None
    ) -> dict[str, any]:
        """Initiate device authorization flow with QR code.
        
        Implements device flow initiation from:
        Reference: p8fs-auth/docs/authentication-flows.md - "Desktop app initiates OAuth device flow"
        
        This creates:
        1. Device and user codes
        2. Verification URIs
        3. QR code image data
        4. Polling parameters
        
        Args:
            client_id: OAuth client identifier
            scope: Requested permissions
            
        Returns:
            Device flow response with QR code
        """
        # Create device authorization using auth service
        # Reference: p8fs-auth/docs/authentication-flows.md - "Server returns device code and user code"
        device_token = await self.auth_service.create_device_authorization(
            client_id=client_id,
            scope=scope
        ) 
        
        # Generate QR code for mobile scanning
        # Reference: p8fs-auth/docs/authentication-flows.md - "Desktop displays QR code with user code"
        qr_code_data = self._generate_qr_code(device_token.verification_uri_complete)
        
        # Return device flow response
        return {
            "device_code": device_token.device_code,
            "user_code": device_token.user_code,
            "verification_uri": device_token.verification_uri,
            "verification_uri_complete": device_token.verification_uri_complete,
            "expires_in": device_token.expires_in,
            "interval": device_token.interval,
            "qr_code": qr_code_data  # Base64-encoded PNG image
        }
    
    def _generate_qr_code(self, data: str) -> str:
        """Generate QR code image for verification URI.
        
        Creates a QR code suitable for mobile scanning.
        
        Args:
            data: URL or data to encode
            
        Returns:
            Base64-encoded PNG image data
        """
        # Create QR code
        qr = qrcode.QRCode(
            version=1,  # Controls size (1 is smallest)
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,  # Pixel size of each box
            border=4,  # Border size in boxes
        )
        
        # Add data and optimize
        qr.add_data(data)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Resize to configured size
        img = img.resize((self.qr_code_size, self.qr_code_size))
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return f"data:image/png;base64,{img_data}"
    
    async def get_device_details(
        self,
        user_code: str
    ) -> dict[str, any]:
        """Get device details for approval screen.

        Implements device lookup from:
        Reference: p8fs-auth/docs/authentication-flows.md - "Mobile retrieves device details from server"

        Called when mobile app scans QR code.

        Args:
            user_code: User-friendly code from QR scan

        Returns:
            Device details for approval UI

        Raises:
            InvalidGrantError: Invalid or expired code
        """
        # Normalize user code: uppercase and remove hyphens
        user_code = user_code.upper().replace("-", "")

        # Find device token
        device_token = await self.token_repository.get_device_token_by_user_code(user_code)
        if not device_token:
            raise InvalidGrantError("Invalid user code")
        
        # Check expiration
        if (datetime.utcnow() - device_token.created_at).total_seconds() > self.device_code_ttl:
            raise InvalidGrantError("Device code expired")
        
        # Check if already approved
        if device_token.approved_at:
            raise InvalidGrantError("Device already approved")
        
        # Return device details for approval UI
        return {
            "user_code": device_token.user_code,
            "created_at": device_token.created_at.isoformat(),
            "expires_at": (
                device_token.created_at + timedelta(seconds=device_token.expires_in)
            ).isoformat(),
            "client_info": {
                "client_id": "desktop_app",  # Would lookup client details in production
                "client_name": "P8FS Desktop",
                "client_description": "Official P8FS desktop application"
            }
        }
    
    async def approve_device(
        self,
        user_code: str,
        user_id: str,
        device_id: str,
        device_name: str | None = None
    ) -> dict[str, any]:
        """Approve device from mobile app.
        
        Implements device approval from:
        Reference: p8fs-auth/docs/authentication-flows.md - "User approves device on mobile"
        
        Steps:
        1. Validate approval request
        2. Create device registration
        3. Issue OAuth tokens
        4. Log security event
        
        Args:
            user_code: Code from QR scan
            user_id: Authenticated user approving
            device_id: Mobile device performing approval
            device_name: Optional name for new device
            
        Returns:
            Approval confirmation
        """
        # Normalize user code: uppercase and remove hyphens
        user_code = user_code.upper().replace("-", "")
        
        # Get approving device to verify trust level
        approving_device = await self.auth_repository.get_device(device_id)
        if not approving_device:
            # For development, allow dev- prefixed devices without registration
            if device_id and device_id.startswith("dev-"):
                # Create a temporary device object for development
                from p8fs_auth.models.auth import Device, DeviceTrustLevel
                approving_device = Device(
                    device_id=device_id,
                    device_name="Development Device",
                    trust_level=DeviceTrustLevel.EMAIL_VERIFIED,
                    public_key="dev-public-key",  # Required field
                    email="dev@p8fs.local",  # Required field
                    created_at=datetime.utcnow()
                )
            else:
                raise InvalidGrantError("Approving device not found")
        
        # Verify approving device is trusted
        if approving_device.trust_level not in [
            DeviceTrustLevel.EMAIL_VERIFIED,
            DeviceTrustLevel.TRUSTED
        ]:
            raise InvalidGrantError("Approving device not verified")
        
        # Approve the device authorization
        # Reference: p8fs-auth/docs/authentication-flows.md - "Server issues OAuth tokens to desktop"
        await self.auth_service.approve_device_authorization(
            user_code=user_code,
            user_id=user_id,
            device_id=device_id
        )
        
        # Log approval event
        await self.login_event_repository.create_login_event(
            LoginEvent(
                user_id=user_id,
                device_id=device_id,
                auth_method=AuthMethod.DEVICE_CODE,
                success=True,
                metadata={
                    "action": "device_approval",
                    "user_code": user_code,
                    "device_name": device_name
                }
            )
        )
        
        return {
            "status": "approved",
            "message": "Device successfully authorized"
        }
    
    async def deny_device(
        self,
        user_code: str,
        user_id: str,
        device_id: str,
        reason: str | None = None
    ) -> dict[str, any]:
        """Deny device authorization request.
        
        Called when user rejects device pairing.
        
        Args:
            user_code: Code from QR scan
            user_id: User denying request
            device_id: Device performing denial
            reason: Optional denial reason
            
        Returns:
            Denial confirmation
        """
        # Normalize user code: uppercase and remove hyphens
        user_code = user_code.upper().replace("-", "")
        
        # Find device token
        device_token = await self.token_repository.get_device_token_by_user_code(user_code)
        if not device_token:
            raise InvalidGrantError("Invalid user code")
        
        # Mark as denied by deleting
        await self.token_repository.delete_device_token(device_token.device_code)
        
        # Log denial event
        await self.login_event_repository.create_login_event(
            LoginEvent(
                user_id=user_id,
                device_id=device_id,
                auth_method=AuthMethod.DEVICE_CODE,
                success=False,
                failure_reason=reason or "User denied device authorization",
                metadata={
                    "action": "device_denial",
                    "user_code": user_code
                }
            )
        )
        
        return {
            "status": "denied",
            "message": "Device authorization denied"
        }
    
    async def list_user_devices(
        self,
        user_id: str,
        include_revoked: bool = False
    ) -> list[dict[str, any]]:
        """List all devices for a user.
        
        Implements device listing from:
        Reference: p8fs-auth/docs/authentication-flows.md - "/api/v1/auth/devices - List authorized devices"
        
        Args:
            user_id: User identifier
            include_revoked: Whether to include revoked devices
            
        Returns:
            List of device information
        """
        # Get devices by email (using email as user_id for now)
        devices = await self.auth_repository.list_devices_by_email(user_id)
        
        # Filter and format devices
        device_list = []
        for device in devices:
            # Skip revoked unless requested
            if device.trust_level == DeviceTrustLevel.REVOKED and not include_revoked:
                continue
            
            # Get recent activity
            recent_events = await self.login_event_repository.get_login_events(
                user_id=user_id,
                start_date=datetime.utcnow() - timedelta(days=7),
                limit=1
            )
            
            last_activity = None
            if recent_events:
                last_activity = recent_events[0].created_at.isoformat()
            
            device_list.append({
                "device_id": device.device_id,
                "device_name": device.device_name,
                "trust_level": device.trust_level.value,
                "created_at": device.created_at.isoformat(),
                "last_used_at": device.last_used_at.isoformat() if device.last_used_at else None,
                "last_activity": last_activity,
                "is_current": False  # Would check against current session
            })
        
        # Sort by last used
        device_list.sort(
            key=lambda d: d["last_used_at"] or d["created_at"],
            reverse=True
        )
        
        return device_list
    
    async def revoke_device(
        self,
        device_id: str,
        user_id: str,
        revoked_by_device_id: str | None = None
    ) -> bool:
        """Revoke device access.
        
        Implements device revocation from:
        Reference: p8fs-auth/docs/authentication-flows.md - "/api/v1/auth/devices/{id} - Revoke device access"
        
        Args:
            device_id: Device to revoke
            user_id: User performing revocation
            revoked_by_device_id: Device performing revocation
            
        Returns:
            True if revoked successfully
        """
        # Get device
        device = await self.auth_repository.get_device(device_id)
        if not device:
            return False
        
        # Verify ownership
        if device.email != user_id:
            raise InvalidGrantError("Unauthorized to revoke device")
        
        # Update trust level
        device.trust_level = DeviceTrustLevel.REVOKED
        await self.auth_repository.update_device(device)
        
        # Revoke all tokens for device
        # In production would revoke by device_id
        count = await self.auth_service.token_repository.revoke_tokens_for_user(user_id)
        
        # Log revocation event
        await self.login_event_repository.create_login_event(
            LoginEvent(
                user_id=user_id,
                device_id=revoked_by_device_id or device_id,
                auth_method=AuthMethod.MOBILE_KEYPAIR,
                success=True,
                metadata={
                    "action": "device_revocation",
                    "revoked_device_id": device_id,
                    "tokens_revoked": count
                }
            )
        )
        
        return True
    
    async def upgrade_device_trust(
        self,
        device_id: str,
        user_id: str,
        target_level: DeviceTrustLevel,
        admin_approval: dict[str, any] | None = None
    ) -> Device:
        """Upgrade device trust level.
        
        Implements trust level management for:
        - Elevating EMAIL_VERIFIED to TRUSTED
        - Admin approval workflows
        - Biometric verification upgrades
        
        Args:
            device_id: Device to upgrade
            user_id: User requesting upgrade
            target_level: Desired trust level
            admin_approval: Optional admin approval data
            
        Returns:
            Updated device
        """
        # Get device
        device = await self.auth_repository.get_device(device_id)
        if not device:
            raise InvalidGrantError("Device not found")
        
        # Verify ownership
        if device.email != user_id:
            raise InvalidGrantError("Unauthorized to upgrade device")
        
        # Validate trust level progression
        current_level = device.trust_level
        
        # Can't upgrade from REVOKED
        if current_level == DeviceTrustLevel.REVOKED:
            raise InvalidGrantError("Cannot upgrade revoked device")
        
        # Can't downgrade
        if target_level.value <= current_level.value:
            raise InvalidGrantError("Cannot downgrade trust level")
        
        # EMAIL_VERIFIED -> TRUSTED requires admin approval or biometric
        if (
            current_level == DeviceTrustLevel.EMAIL_VERIFIED and
            target_level == DeviceTrustLevel.TRUSTED and
            not admin_approval
        ):
            raise InvalidGrantError("Admin approval required for TRUSTED status")
        
        # Update trust level
        device.trust_level = target_level
        device.last_used_at = datetime.utcnow()
        
        if admin_approval:
            device.metadata = device.metadata or {}
            device.metadata["admin_approval"] = admin_approval
        
        await self.auth_repository.update_device(device)
        
        # Log upgrade event
        await self.login_event_repository.create_login_event(
            LoginEvent(
                user_id=user_id,
                device_id=device_id,
                auth_method=AuthMethod.MOBILE_KEYPAIR,
                success=True,
                metadata={
                    "action": "trust_upgrade",
                    "from_level": current_level.value,
                    "to_level": target_level.value,
                    "admin_approval": bool(admin_approval)
                }
            )
        )
        
        return device