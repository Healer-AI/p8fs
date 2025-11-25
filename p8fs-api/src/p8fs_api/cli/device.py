"""Device management CLI commands for P8FS.

This module provides CLI commands for managing device authentication including:
- Device registration (register)
- Device approval (approve)
- Token validation (ping)
- Token refresh
- Multi-device testing (request-access, poll)

Usage:
    # Primary device (default - no --device-id)
    uv run python -m p8fs_api.cli.device register --email user@example.com
    uv run python -m p8fs_api.cli.device approve <user-code>
    uv run python -m p8fs_api.cli.device ping

    # Simulated device (with --device-id)
    uv run python -m p8fs_api.cli.device request-access --device-id device-001
    uv run python -m p8fs_api.cli.device approve <user-code>  # (no --device-id)
    uv run python -m p8fs_api.cli.device poll --device-id device-001
    uv run python -m p8fs_api.cli.device ping --device-id device-001

Reference: p8fs-auth/docs/authentication-flows.md - Mobile Device Registration
Reference: p8fs-auth/docs/dev-testing.md - Multi-Device Testing
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

import httpx
from p8fs_auth.services.mobile_service import MobileAuthenticationService
from p8fs_auth.utils.device_storage import DeviceStorage
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class DeviceCLI:
    """CLI interface for device management."""

    def __init__(self, local: bool = False, base_url: Optional[str] = None, device_id: Optional[str] = None):
        """Initialize device CLI.

        Args:
            local: Use local server (localhost:8001)
            base_url: Custom base URL (overrides local flag)
            device_id: Device identifier for multi-device mode (simulates other devices)
        """
        self.device_id = device_id
        self.storage = DeviceStorage(device_id=device_id)

        if base_url:
            self.base_url = base_url
        elif local:
            self.base_url = "http://localhost:8001"
        else:
            # Use eepis.ai as default production server
            self.base_url = self.storage.get_base_url("https://p8fs.eepis.ai")

        self.mobile_service = MobileAuthenticationService(
            repository=None,  # CLI doesn't need repository
            jwt_manager=None
        )

    async def register(
        self,
        email: str,
        device_name: Optional[str] = None,
        tenant: Optional[str] = None
    ) -> int:
        """Register a new device.

        Args:
            email: User email address
            device_name: Optional device name
            tenant: Optional tenant ID (for test-tenant)

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        print(f"Registering device for {email}...")
        print(f"Using server: {self.base_url}")

        try:
            # Generate Ed25519 keypair
            import base64
            from cryptography.hazmat.primitives import serialization

            private_key_bytes, public_key_bytes = self.mobile_service.generate_keypair()

            # Convert to PEM format for storage
            from cryptography.hazmat.primitives.asymmetric import ed25519
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)

            private_key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')

            public_key_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode('utf-8')

            public_key_b64 = base64.b64encode(public_key_bytes).decode('utf-8')

            # Use dev registration endpoint for test-tenant or development
            use_dev_endpoint = tenant == "test-tenant" or self.base_url.startswith("http://localhost")

            async with httpx.AsyncClient(timeout=30.0) as client:
                if use_dev_endpoint:
                    # Dev registration endpoint - immediate approval
                    print(f"Using dev registration endpoint...")

                    response = await client.post(
                        f"{self.base_url}/api/v1/auth/dev/register",
                        json={
                            "email": email,
                            "public_key": public_key_b64,
                            "device_info": {
                                "platform": "cli",
                                "device_name": device_name or "CLI Device",
                                "imei": f"cli-{email}"  # Deterministic device ID
                            }
                        },
                        headers={
                            "X-Dev-Token": config.dev_token_secret,
                            "X-Dev-Email": email,
                            "X-Dev-Code": "000000"
                        }
                    )
                else:
                    # Standard registration - requires verification
                    print(f"Using standard registration endpoint...")

                    response = await client.post(
                        f"{self.base_url}/api/v1/oauth/device/register",
                        json={
                            "email": email,
                            "public_key": public_key_b64,
                            "device_info": {
                                "platform": "cli",
                                "device_name": device_name or "CLI Device"
                            }
                        }
                    )

                if response.status_code == 200:
                    result = response.json()

                    if use_dev_endpoint:
                        # Dev endpoint returns tokens immediately
                        access_token = result.get("access_token")
                        refresh_token = result.get("refresh_token")
                        tenant_id = result.get("tenant_id") or tenant

                        # Save tokens and keys
                        self.storage.save_token(
                            access_token=access_token,
                            refresh_token=refresh_token,
                            expires_in=result.get("expires_in", 86400),
                            token_type="Bearer",
                            tenant_id=tenant_id,
                            email=email,
                            base_url=self.base_url,
                            device_keys={
                                "private_key_pem": private_key_pem,
                                "public_key_pem": public_key_pem,
                                "public_key_b64": public_key_b64
                            }
                        )

                        print(f"✓ Device registered successfully!")
                        print(f"  Tenant ID: {tenant_id}")
                        print(f"  Token saved to: {self.storage.token_file}")
                        return 0
                    else:
                        # Standard endpoint requires verification
                        registration_id = result.get("registration_id")
                        print(f"✓ Device registration initiated")
                        print(f"  Registration ID: {registration_id}")
                        print(f"\nPlease check your email for verification code")
                        print(f"Then run: uv run python -m p8fs_api.cli.device verify --code <code>")

                        # Save keys for verification step
                        self.storage.save_device_info(
                            device_id=registration_id,
                            device_name=device_name,
                            tenant_id=tenant,
                            email=email,
                            private_key_pem=private_key_pem,
                            public_key_pem=public_key_pem,
                            public_key_b64=public_key_b64
                        )
                        return 0
                else:
                    print(f"✗ Registration failed: {response.status_code}")
                    print(f"  Response: {response.text}")
                    return 1

        except Exception as e:
            print(f"✗ Registration error: {e}")
            logger.exception("Device registration failed")
            return 1

    async def approve(self, user_code: str) -> int:
        """Approve a device authorization request.

        This uses device-bound authentication by signing the approval
        with the device's Ed25519 private key, just like a real mobile app.

        Args:
            user_code: User code from QR scan (e.g., A1B2-C3D4)

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        print(f"Approving device with user code: {user_code}")
        print(f"Using server: {self.base_url}")

        # Get access token
        access_token = self.storage.get_access_token()
        if not access_token:
            print("✗ No access token found. Please register first:")
            print("  uv run python -m p8fs_api.cli.device register --email user@example.com")
            return 1

        # Get device keys for signing
        device_keys = self.storage.get_device_keys()
        if not device_keys or not device_keys.get("private_key_pem"):
            print("✗ No device keys found. Please register first:")
            print("  uv run python -m p8fs_api.cli.device register --email user@example.com")
            return 1

        # Check if token is expired
        if self.storage.is_token_expired():
            print("⚠ Token expired, attempting refresh...")
            refresh_result = await self.refresh()
            if refresh_result != 0:
                return refresh_result
            # Re-get the token after refresh
            access_token = self.storage.get_access_token()
            if not access_token:
                return 1

        try:
            # Sign the approval request with device private key
            import base64
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ed25519

            # Load private key
            private_key_pem = device_keys["private_key_pem"]
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode('utf-8'),
                password=None
            )

            # Create challenge message to sign
            # Format: "approve:{user_code}"
            challenge = f"approve:{user_code}"
            signature_bytes = private_key.sign(challenge.encode('utf-8'))
            signature_b64 = base64.b64encode(signature_bytes).decode('utf-8')

            print(f"📝 Signed approval request with device keypair")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/oauth/device/approve",
                    json={
                        "user_code": user_code,
                        "approved": True,
                        "device_name": "CLI Approved Device",
                        "challenge": challenge,
                        "signature": signature_b64
                    },
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    print(f"✓ Device approved successfully!")
                    if "message" in result:
                        print(f"  {result['message']}")
                    return 0
                elif response.status_code == 401:
                    print(f"✗ Authorization failed. Token may be expired or signature invalid.")
                    print(f"  Try registering again")
                    return 1
                elif response.status_code == 404:
                    print(f"✗ User code not found or expired: {user_code}")
                    return 1
                else:
                    print(f"✗ Approval failed: {response.status_code}")
                    print(f"  Response: {response.text}")
                    return 1

        except Exception as e:
            print(f"✗ Approval error: {e}")
            logger.exception("Device approval failed")
            return 1

    async def ping(self) -> int:
        """Test token validity by pinging auth endpoint.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        print(f"Testing token validity...")
        print(f"Using server: {self.base_url}")

        # Get access token
        access_token = self.storage.get_access_token()
        if not access_token:
            print("✗ No access token found. Please register first:")
            print("  uv run python -m p8fs_api.cli.device register --email user@example.com")
            return 1

        # Check if token appears expired locally
        if self.storage.is_token_expired():
            print("⚠ Token appears expired locally")
            print("  Testing with server anyway...")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/oauth/ping",
                    headers={
                        "Authorization": f"Bearer {access_token}"
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    print(f"✓ Token is valid!")
                    print(f"  Authenticated: {result.get('authenticated')}")
                    if result.get('user_id'):
                        print(f"  User ID: {result['user_id']}")
                    if result.get('email'):
                        print(f"  Email: {result['email']}")
                    if result.get('tenant_id'):
                        print(f"  Tenant ID: {result['tenant_id']}")
                    return 0
                elif response.status_code == 401:
                    print(f"✗ Token is invalid or expired")
                    print(f"  Response: {response.text}")
                    print(f"\nPlease register again:")
                    print(f"  uv run python -m p8fs_api.cli.device register --email user@example.com")
                    return 1
                else:
                    print(f"✗ Ping failed: {response.status_code}")
                    print(f"  Response: {response.text}")
                    return 1

        except httpx.ConnectError:
            print(f"✗ Cannot connect to server: {self.base_url}")
            print(f"  Make sure the server is running")
            return 1
        except Exception as e:
            print(f"✗ Ping error: {e}")
            logger.exception("Token ping failed")
            return 1

    async def refresh(self) -> int:
        """Refresh access token using refresh token.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        print("Refreshing access token...")
        print(f"Using server: {self.base_url}")

        # Get token data
        token_data = self.storage.load_token()
        if not token_data:
            print("✗ No token found. Please register first:")
            print("  uv run python -m p8fs_api.cli.device register --email user@example.com")
            return 1

        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            print("✗ No refresh token found. Device may need re-registration.")
            return 1

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/oauth/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": "cli_client"
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded"
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    new_access_token = result.get("access_token")
                    new_refresh_token = result.get("refresh_token", refresh_token)

                    # Update stored tokens
                    self.storage.save_token(
                        access_token=new_access_token,
                        refresh_token=new_refresh_token,
                        expires_in=result.get("expires_in", 3600),
                        token_type="Bearer",
                        tenant_id=token_data.get("tenant_id"),
                        email=token_data.get("email"),
                        base_url=self.base_url,
                        device_keys=token_data.get("device_keys")
                    )

                    print(f"✓ Token refreshed successfully!")
                    print(f"  New token expires in: {result.get('expires_in', 'N/A')} seconds")
                    return 0
                else:
                    print(f"✗ Token refresh failed: {response.status_code}")
                    print(f"  Response: {response.text}")
                    print(f"\nYou may need to register again:")
                    print(f"  uv run python -m p8fs_api.cli.device register --email user@example.com")
                    return 1

        except Exception as e:
            print(f"✗ Refresh error: {e}")
            logger.exception("Token refresh failed")
            return 1

    async def status(self) -> int:
        """Show device and token status.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        print("Device Status")
        print("=" * 50)

        # Check token storage
        token_data = self.storage.load_token()
        if not token_data:
            print("Status: Not registered")
            print(f"\nTo register:")
            print(f"  uv run python -m p8fs_api.cli.device register --email user@example.com")
            return 1

        print(f"Status: Registered")
        print(f"Email: {token_data.get('email', 'N/A')}")
        print(f"Tenant ID: {token_data.get('tenant_id', 'N/A')}")
        print(f"Server: {token_data.get('base_url', 'N/A')}")
        print(f"Token File: {self.storage.token_file}")

        # Check expiry
        if self.storage.is_token_expired():
            print(f"Token: Expired ✗")
            print(f"\nTo refresh token:")
            print(f"  uv run python -m p8fs_api.cli.device refresh")
        else:
            print(f"Token: Valid ✓")

        # Check device info
        device_info = self.storage.load_device_info()
        if device_info:
            print(f"\nDevice Info:")
            print(f"  Device ID: {device_info.get('device_id', 'N/A')}")
            print(f"  Device Name: {device_info.get('device_name', 'N/A')}")
            print(f"  Trust Level: {device_info.get('trust_level', 'N/A')}")

        return 0

    async def request_access(self, format: str = "text") -> int:
        """Request device authorization (OAuth device flow).

        This simulates a desktop/MCP client requesting access. The primary
        device must approve the request using the displayed user_code.

        Args:
            format: Output format ("text" or "json")

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        if not self.device_id:
            print("✗ --device-id is required for request-access command")
            print("  Example: device request-access --device-id device-001")
            return 1

        print(f"Requesting device authorization for: {self.device_id}")
        print(f"Using server: {self.base_url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/oauth/device/code",
                    data={
                        "client_id": f"cli-{self.device_id}",
                        "scope": "read write"
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    device_code = result.get("device_code")
                    user_code = result.get("user_code")
                    verification_uri = result.get("verification_uri")
                    verification_uri_complete = result.get("verification_uri_complete")
                    expires_in = result.get("expires_in", 600)
                    interval = result.get("interval", 5)

                    # Save device flow state
                    self.storage.save_device_flow(
                        device_code=device_code,
                        user_code=user_code,
                        verification_uri=verification_uri,
                        verification_uri_complete=verification_uri_complete,
                        expires_in=expires_in,
                        interval=interval,
                        client_id=f"cli-{self.device_id}"
                    )

                    if format == "json":
                        import json
                        print(json.dumps(result, indent=2))
                    else:
                        from rich.console import Console
                        from rich.panel import Panel
                        from rich.text import Text
                        from rich.table import Table
                        from io import StringIO

                        console = Console()

                        # Display QR code if available
                        qr_code_b64 = result.get("qr_code")
                        if qr_code_b64:
                            try:
                                import qrcode

                                # Generate terminal-friendly QR code from verification URI
                                qr = qrcode.QRCode(border=1)
                                qr.add_data(verification_uri_complete)
                                qr.make()

                                # Capture QR code ASCII output
                                qr_output = StringIO()
                                qr.print_ascii(out=qr_output, invert=True)
                                qr_text = qr_output.getvalue()

                                # Create rich panel with QR code
                                qr_panel = Panel(
                                    Text(qr_text, justify="center"),
                                    title="[bold cyan]📱 Scan with Mobile Device[/bold cyan]",
                                    border_style="cyan",
                                    padding=(1, 2)
                                )

                                console.print()
                                console.print(qr_panel)

                            except ImportError:
                                # Fallback if qrcode library not available
                                console.print(
                                    Panel(
                                        "[yellow]QR Code available but qrcode library not installed\nInstall with: uv add qrcode[/yellow]",
                                        title="[bold yellow]⚠️  QR Code Unavailable[/bold yellow]",
                                        border_style="yellow"
                                    )
                                )

                        # Create info table
                        table = Table(show_header=False, box=None, padding=(0, 2))
                        table.add_column(style="bold cyan", justify="right")
                        table.add_column(style="white")

                        table.add_row("User Code:", f"[bold green]{user_code}[/bold green]")
                        table.add_row("Expires in:", f"[yellow]{expires_in}[/yellow] seconds")
                        table.add_row("", "")
                        table.add_row("To approve:", f"[cyan]device approve {user_code}[/cyan]")
                        table.add_row("Then poll:", f"[cyan]device poll --device-id {self.device_id}[/cyan]")

                        # Create main panel
                        info_panel = Panel(
                            table,
                            title="[bold magenta]🔐 Device Authorization Request[/bold magenta]",
                            border_style="magenta",
                            padding=(1, 2)
                        )

                        console.print(info_panel)
                        console.print(f"[dim]✓ Device flow saved to: {self.storage.device_flow_file}[/dim]\n")

                    return 0
                else:
                    print(f"✗ Request failed: {response.status_code}")
                    print(f"  Response: {response.text}")
                    return 1

        except Exception as e:
            print(f"✗ Request error: {e}")
            logger.exception("Device authorization request failed")
            return 1

    async def poll(self) -> int:
        """Poll for device authorization token.

        This retrieves the token after the primary device has approved
        the authorization request.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        if not self.device_id:
            print("✗ --device-id is required for poll command")
            print("  Example: device poll --device-id device-001")
            return 1

        print(f"Polling for device token: {self.device_id}")
        print(f"Using server: {self.base_url}")

        # Load device flow state
        flow_data = self.storage.load_device_flow()
        if not flow_data:
            print("✗ No device flow found. Run request-access first:")
            print(f"  device request-access --device-id {self.device_id}")
            return 1

        # Check if expired
        if self.storage.is_device_flow_expired():
            print("✗ Device flow has expired. Please request access again.")
            self.storage.update_device_flow_status("expired")
            return 1

        device_code = flow_data.get("device_code")
        interval = flow_data.get("interval", 5)
        client_id = flow_data.get("client_id")

        try:
            import time

            max_attempts = 60
            attempt = 0

            while attempt < max_attempts:
                attempt += 1

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self.base_url}/api/v1/oauth/token",
                        data={
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                            "device_code": device_code,
                            "client_id": client_id
                        },
                        headers={
                            "Content-Type": "application/x-www-form-urlencoded"
                        }
                    )

                    if response.status_code == 200:
                        result = response.json()
                        access_token = result.get("access_token")
                        refresh_token = result.get("refresh_token")
                        expires_in = result.get("expires_in", 3600)
                        tenant_id = result.get("tenant_id")

                        # Save tokens
                        self.storage.save_token(
                            access_token=access_token,
                            refresh_token=refresh_token,
                            expires_in=expires_in,
                            token_type="Bearer",
                            tenant_id=tenant_id,
                            email=flow_data.get("email"),
                            base_url=self.base_url
                        )

                        # Mark flow as consumed
                        self.storage.update_device_flow_status("consumed")

                        print(f"✓ Device authorized successfully!")
                        print(f"  Tenant ID: {tenant_id}")
                        print(f"  Token saved to: {self.storage.token_file}")
                        print(f"\nYou can now use this device:")
                        print(f"  device ping --device-id {self.device_id}")
                        return 0

                    elif response.status_code == 400:
                        error_data = response.json()
                        error = error_data.get("error")

                        if error == "authorization_pending":
                            print(f"⏳ Waiting for approval... (attempt {attempt}/{max_attempts})")
                            time.sleep(interval)
                            continue
                        elif error == "slow_down":
                            print(f"⚠ Rate limited, increasing interval...")
                            interval += 5
                            time.sleep(interval)
                            continue
                        elif error == "expired_token":
                            print(f"✗ Device code expired. Please request access again.")
                            self.storage.update_device_flow_status("expired")
                            return 1
                        elif error == "access_denied":
                            print(f"✗ Authorization was denied by user.")
                            self.storage.update_device_flow_status("denied")
                            return 1
                        else:
                            print(f"✗ Token request failed: {error}")
                            return 1
                    else:
                        print(f"✗ Unexpected response: {response.status_code}")
                        print(f"  Response: {response.text}")
                        return 1

            print(f"✗ Polling timeout. User did not approve within time limit.")
            return 1

        except Exception as e:
            print(f"✗ Polling error: {e}")
            logger.exception("Device token polling failed")
            return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="P8FS Device Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Global flags
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local server (http://localhost:8001)"
    )
    parser.add_argument(
        "--base-url",
        help="Custom server base URL (overrides --local)"
    )
    parser.add_argument(
        "--device-id",
        help="Device identifier for multi-device mode (simulates other devices)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Register command
    register_parser = subparsers.add_parser(
        "register",
        help="Register a new device"
    )
    register_parser.add_argument(
        "--email",
        required=True,
        help="User email address"
    )
    register_parser.add_argument(
        "--device-name",
        help="Device display name"
    )
    register_parser.add_argument(
        "--tenant",
        help="Tenant ID (use 'test-tenant' for testing)"
    )

    # Approve command
    approve_parser = subparsers.add_parser(
        "approve",
        help="Approve a device authorization request"
    )
    approve_parser.add_argument(
        "user_code",
        help="User code from QR scan (e.g., A1B2-C3D4)"
    )

    # Ping command
    ping_parser = subparsers.add_parser(
        "ping",
        help="Test token validity"
    )

    # Refresh command
    refresh_parser = subparsers.add_parser(
        "refresh",
        help="Refresh access token"
    )

    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show device and token status"
    )

    # Request-access command (multi-device testing)
    request_access_parser = subparsers.add_parser(
        "request-access",
        help="Request device authorization (requires --device-id)"
    )
    request_access_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (text or json)"
    )

    # Poll command (multi-device testing)
    poll_parser = subparsers.add_parser(
        "poll",
        help="Poll for device authorization token (requires --device-id)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Create CLI instance
    cli = DeviceCLI(local=args.local, base_url=args.base_url, device_id=args.device_id)

    # Execute command
    if args.command == "register":
        exit_code = asyncio.run(
            cli.register(
                email=args.email,
                device_name=args.device_name,
                tenant=args.tenant
            )
        )
    elif args.command == "approve":
        exit_code = asyncio.run(cli.approve(args.user_code))
    elif args.command == "ping":
        exit_code = asyncio.run(cli.ping())
    elif args.command == "refresh":
        exit_code = asyncio.run(cli.refresh())
    elif args.command == "status":
        exit_code = asyncio.run(cli.status())
    elif args.command == "request-access":
        exit_code = asyncio.run(cli.request_access(format=args.format))
    elif args.command == "poll":
        exit_code = asyncio.run(cli.poll())
    else:
        parser.print_help()
        exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
