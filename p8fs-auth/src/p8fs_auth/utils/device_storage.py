"""Device credential storage for local development and CLI usage.

This module provides utilities for storing and retrieving device credentials,
JWT tokens, and keypairs in the ~/.p8fs/auth directory for local development.

Reference: p8fs-auth/docs/authentication-flows.md - Mobile Device Keys (Ed25519)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class DeviceStorage:
    """Manage device credentials in local storage.

    Supports two modes:
    - Legacy: Single device at ~/.p8fs/auth/token.json
    - Multi-device: Per-device storage at ~/.p8fs/auth/devices/{device_id}/token.json
    """

    def __init__(self, storage_dir: Optional[Path] = None, device_id: Optional[str] = None):
        """Initialize device storage.

        Args:
            storage_dir: Custom storage directory, defaults to ~/.p8fs/auth
            device_id: Device identifier for multi-device mode (e.g., 'device-001')
                      If None, uses legacy single-device mode
        """
        base_dir = storage_dir or (Path.home() / ".p8fs" / "auth")

        # Multi-device mode: use devices/<device_id>/ subdirectory
        if device_id:
            self.storage_dir = base_dir / "devices" / device_id
            self.device_id = device_id
        else:
            # Legacy mode: use base auth directory
            self.storage_dir = base_dir
            self.device_id = None

        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.token_file = self.storage_dir / "token.json"
        self.device_file = self.storage_dir / "device.json"
        self.device_flow_file = self.storage_dir / "device_flow.json"

    def save_token(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: Optional[int] = None,
        token_type: str = "Bearer",
        tenant_id: Optional[str] = None,
        email: Optional[str] = None,
        base_url: Optional[str] = None,
        device_keys: Optional[dict[str, str]] = None,
        **metadata
    ) -> Path:
        """Save JWT tokens and metadata to storage.

        Args:
            access_token: JWT access token
            refresh_token: Optional refresh token
            expires_in: Token lifetime in seconds
            token_type: Token type (default: Bearer)
            tenant_id: Tenant identifier
            email: User email
            base_url: Server base URL
            device_keys: Device keypair (private_key_pem, public_key_pem, public_key_b64)
            **metadata: Additional metadata to store

        Returns:
            Path to saved token file
        """
        from time import time

        token_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": token_type,
            "expires_in": expires_in or 86400,
            "tenant_id": tenant_id,
            "created_at": time(),
            "email": email,
            "base_url": base_url or "http://localhost:8001",
            **metadata
        }

        if device_keys:
            token_data["device_keys"] = device_keys

        with open(self.token_file, 'w') as f:
            json.dump(token_data, f, indent=2)

        return self.token_file

    def load_token(self) -> Optional[dict[str, Any]]:
        """Load JWT token from storage.

        Returns:
            Token data dictionary or None if not found
        """
        if not self.token_file.exists():
            return None

        try:
            with open(self.token_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def get_access_token(self) -> Optional[str]:
        """Get current access token.

        Returns:
            Access token string or None if not found/expired
        """
        token_data = self.load_token()
        if not token_data:
            return None

        return token_data.get("access_token")

    def is_token_expired(self) -> bool:
        """Check if stored token is expired.

        Returns:
            True if expired or not found, False if valid
        """
        from time import time

        token_data = self.load_token()
        if not token_data:
            return True

        created_at = token_data.get("created_at", 0)
        expires_in = token_data.get("expires_in", 3600)

        return (time() - created_at) >= expires_in

    def save_device_info(
        self,
        device_id: str,
        device_name: Optional[str] = None,
        trust_level: Optional[str] = None,
        tenant_id: Optional[str] = None,
        **metadata
    ) -> Path:
        """Save device information.

        Args:
            device_id: Device identifier
            device_name: Device display name
            trust_level: Device trust level
            tenant_id: Associated tenant ID
            **metadata: Additional device metadata

        Returns:
            Path to saved device file
        """
        device_data = {
            "device_id": device_id,
            "device_name": device_name,
            "trust_level": trust_level,
            "tenant_id": tenant_id,
            "updated_at": datetime.utcnow().isoformat(),
            **metadata
        }

        with open(self.device_file, 'w') as f:
            json.dump(device_data, f, indent=2)

        return self.device_file

    def load_device_info(self) -> Optional[dict[str, Any]]:
        """Load device information.

        Returns:
            Device data dictionary or None if not found
        """
        if not self.device_file.exists():
            return None

        try:
            with open(self.device_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def get_device_keys(self) -> Optional[dict[str, str]]:
        """Get device keypair from storage.

        Returns:
            Dictionary with private_key_pem, public_key_pem, public_key_b64 or None
        """
        token_data = self.load_token()
        if not token_data:
            return None

        return token_data.get("device_keys")

    def get_base_url(self, default: str = "http://localhost:8001") -> str:
        """Get configured base URL.

        Args:
            default: Default URL if not configured

        Returns:
            Base URL string
        """
        token_data = self.load_token()
        if token_data and "base_url" in token_data:
            return token_data["base_url"]
        return default

    def clear(self) -> None:
        """Clear all stored credentials."""
        if self.token_file.exists():
            self.token_file.unlink()
        if self.device_file.exists():
            self.device_file.unlink()
        if self.device_flow_file.exists():
            self.device_flow_file.unlink()

    def save_device_flow(
        self,
        device_code: str,
        user_code: str,
        verification_uri: str,
        verification_uri_complete: str,
        expires_in: int,
        interval: int = 5,
        client_id: str = "p8fs-cli"
    ) -> Path:
        """Save device authorization flow state.

        Used when initiating OAuth device flow to store the device_code
        for later polling.

        Args:
            device_code: Long secure device code for polling
            user_code: Short human-friendly code for display
            verification_uri: Base verification URL
            verification_uri_complete: Complete verification URL with user_code
            expires_in: Seconds until codes expire
            interval: Recommended polling interval
            client_id: OAuth client identifier

        Returns:
            Path to saved flow file
        """
        from time import time

        flow_data = {
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": verification_uri,
            "verification_uri_complete": verification_uri_complete,
            "expires_in": expires_in,
            "interval": interval,
            "client_id": client_id,
            "created_at": time(),
            "status": "pending"
        }

        with open(self.device_flow_file, 'w') as f:
            json.dump(flow_data, f, indent=2)

        return self.device_flow_file

    def load_device_flow(self) -> Optional[dict[str, Any]]:
        """Load device authorization flow state.

        Returns:
            Flow data dictionary or None if not found
        """
        if not self.device_flow_file.exists():
            return None

        try:
            with open(self.device_flow_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def update_device_flow_status(self, status: str) -> None:
        """Update device flow status.

        Args:
            status: New status (pending, approved, expired, consumed)
        """
        flow_data = self.load_device_flow()
        if flow_data:
            flow_data["status"] = status
            flow_data["updated_at"] = datetime.utcnow().isoformat()

            with open(self.device_flow_file, 'w') as f:
                json.dump(flow_data, f, indent=2)

    def is_device_flow_expired(self) -> bool:
        """Check if device flow has expired.

        Returns:
            True if expired or not found, False if still valid
        """
        from time import time

        flow_data = self.load_device_flow()
        if not flow_data:
            return True

        created_at = flow_data.get("created_at", 0)
        expires_in = flow_data.get("expires_in", 600)

        return (time() - created_at) >= expires_in

    @staticmethod
    def list_devices(storage_dir: Optional[Path] = None) -> list[str]:
        """List all registered device IDs.

        Args:
            storage_dir: Custom storage directory, defaults to ~/.p8fs/auth

        Returns:
            List of device IDs
        """
        base_dir = storage_dir or (Path.home() / ".p8fs" / "auth")
        devices_dir = base_dir / "devices"

        if not devices_dir.exists():
            return []

        device_ids = []
        for device_dir in devices_dir.iterdir():
            if device_dir.is_dir() and (device_dir / "token.json").exists():
                device_ids.append(device_dir.name)

        return sorted(device_ids)

    def __repr__(self) -> str:
        device_info = f", device_id={self.device_id}" if self.device_id else ""
        return f"DeviceStorage(storage_dir={self.storage_dir}{device_info})"
