#!/usr/bin/env python3
"""
Approve Device Authorization Requests for P8FS Development

This script simulates the mobile device approval flow for development/testing.
It uses the saved device keys from get_dev_jwt.py to approve pending device requests.

Usage:
    python dev_device_approve.py                           # Auto-detect from QR login page
    python dev_device_approve.py --detect                  # Explicitly auto-detect from QR page
    python dev_device_approve.py --user-code 1A09-DE7E    # Approve specific user code
    python dev_device_approve.py --auto                   # Auto-approve any pending request
    python dev_device_approve.py --list                   # List pending requests

The --detect option (default) automatically fetches the user code from the 
QR login page at http://localhost:8000/api/mcp/auth/qr-login, making it easy
to approve device authorizations initiated by Claude MCP or other clients.
"""

import argparse
import asyncio
import base64
import json
import os
import sys
from typing import Optional, Dict, Any
from html.parser import HTMLParser

import httpx
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Configuration
DEFAULT_BASE_URL = "http://localhost:8001"  # Default to 8001 for p8fs-api
DEFAULT_TOKEN_FILE = os.path.expanduser("~/.p8fs/auth/token.json")


async def refresh_dev_token(base_url: str, token_file: str = None) -> Optional[str]:
    """Generate a fresh dev token."""
    try:
        # Import the token generation script
        import subprocess
        import sys
        
        # Run the generate_dev_token.py script
        result = subprocess.run(
            [sys.executable, "scripts/dev/generate_dev_token.py"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            # Reload the token file
            token_file = token_file or DEFAULT_TOKEN_FILE
            with open(token_file) as f:
                token_data = json.load(f)
            return token_data.get("access_token")
        else:
            print(f"ERROR: Failed to generate token: {result.stderr}", file=sys.stderr)
            return None
            
    except Exception as e:
        print(f"ERROR: Failed to refresh token: {e}", file=sys.stderr)
        return None


class MetaTagParser(HTMLParser):
    """Parse HTML to extract p8fs-device-auth meta tag."""
    
    def __init__(self):
        super().__init__()
        self.device_auth_data = None
    
    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            attrs_dict = dict(attrs)
            if attrs_dict.get("name") == "p8fs-device-auth":
                content = attrs_dict.get("content", "")
                try:
                    self.device_auth_data = json.loads(content)
                except json.JSONDecodeError:
                    pass


def load_device_credentials(token_file: str) -> Optional[Dict[str, Any]]:
    """Load saved device credentials and keys."""
    try:
        with open(token_file) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Token file not found: {token_file}", file=sys.stderr)
        print("Run get_dev_jwt.py first to generate device credentials", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR: Failed to load token file: {e}", file=sys.stderr)
        return None


async def list_pending_requests(
    base_url: str,
    access_token: str
) -> Optional[list]:
    """List pending device authorization requests."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{base_url}/api/v1/auth/device/pending",
                headers={
                    "Authorization": f"Bearer {access_token}"
                }
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                print("No pending device authorization requests")
                return []
            else:
                print(f"ERROR: Failed to list requests: {response.status_code}", file=sys.stderr)
                print(f"Response: {response.text}", file=sys.stderr)
                return None
                
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return None


async def approve_device_request(
    user_code: str,
    base_url: str,
    access_token: str,
    device_keys: Dict[str, str],
    token_file: str = None
) -> bool:
    """Approve a device authorization request using the proper API endpoint."""
    
    print(f"Approving device request for user code: {user_code} via API")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Use the OAuth device approval endpoint
            response = await client.post(
                f"{base_url}/oauth/device/approve",
                json={
                    "user_code": user_code,  # Keep original format
                    "approved": True,
                    "device_name": "Dev Approval Script"
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 200:
                print("✓ Device authorization approved successfully via repository!")
                result = response.json()
                if "message" in result:
                    print(f"  {result['message']}")
                return True
            elif response.status_code == 401:
                # Check if token expired
                error_data = response.json()
                if error_data.get("message", "").startswith("AUTH_TOKEN_EXPIRED"):
                    print("Token expired, refreshing...")
                    
                    # Try to refresh the token
                    new_token = await refresh_dev_token(base_url, token_file)
                    if new_token:
                        print("✓ Token refreshed successfully")
                        # Retry with new token
                        return await approve_device_request(
                            user_code, base_url, new_token, device_keys, token_file
                        )
                    else:
                        print("ERROR: Failed to refresh token", file=sys.stderr)
                        return False
                else:
                    print(f"ERROR: Invalid authorization token", file=sys.stderr)
                    print(f"Response: {response.text}", file=sys.stderr)
                    return False
            elif response.status_code == 404:
                print(f"ERROR: User code not found or expired: {user_code}", file=sys.stderr)
                return False
            else:
                print(f"ERROR: Approval failed: {response.status_code}", file=sys.stderr)
                print(f"Response: {response.text}", file=sys.stderr)
                
                # Fallback to dev endpoint if available
                print("\nTrying development approval endpoint...")
                return await approve_via_dev_endpoint(
                    user_code, base_url, access_token, {"user_code": user_code, "approved": True}
                )
                
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return False


async def approve_via_dev_endpoint(
    user_code: str,
    base_url: str,
    access_token: str,
    approval_data: Dict[str, Any]
) -> bool:
    """Approve via development endpoint (fallback)."""
    dev_token = os.getenv("P8FS_DEV_TOKEN_SECRET")
    if not dev_token:
        print("ERROR: P8FS_DEV_TOKEN_SECRET not set for dev endpoint", file=sys.stderr)
        return False
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{base_url}/api/v1/auth/dev/device-approve",
                json=approval_data,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Dev-Token": dev_token,
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 200:
                print("✓ Device authorization approved via dev endpoint!")
                return True
            else:
                print(f"ERROR: Dev approval failed: {response.status_code}", file=sys.stderr)
                print(f"Response: {response.text}", file=sys.stderr)
                return False
                
        except Exception as e:
            print(f"ERROR: Dev endpoint error: {e}", file=sys.stderr)
            return False


async def fetch_user_code_from_qr_page(
    base_url: str = DEFAULT_BASE_URL,
    port: int = None
) -> Optional[str]:
    """Fetch user code from the device verification page.
    
    Args:
        base_url: Base URL with port (e.g., http://localhost:8001)
        port: Override port (deprecated, use base_url instead)
    """
    # Extract port from base_url if provided
    if port is None and ":" in base_url.split("//")[1]:
        port = int(base_url.split(":")[-1].split("/")[0])
    elif port is None:
        port = 8001  # Default to 8001
    
    # Try different ports: specified port, then 8001, then 8000
    ports_to_try = [port]
    if port != 8001:
        ports_to_try.append(8001)
    if port != 8000:
        ports_to_try.append(8000)
    
    for try_port in ports_to_try:
        try:
            # Check standard OAuth device endpoint first
            url = f"http://localhost:{try_port}/oauth/device"
            print(f"Checking device verification page at {url}...")
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                
                if response.status_code == 200:
                    # Parse HTML to extract metadata
                    parser = MetaTagParser()
                    parser.feed(response.text)
                    
                    if parser.device_auth_data:
                        user_code = parser.device_auth_data.get("user_code")
                        if user_code:
                            print(f"✓ Found active device authorization:")
                            print(f"  User Code: {user_code}")
                            print(f"  Client ID: {parser.device_auth_data.get('client_id')}")
                            print(f"  Expires in: {parser.device_auth_data.get('expires_in')}s")
                            return user_code
                    else:
                        print(f"  No active device authorization found on port {try_port}")
                        
        except Exception as e:
            print(f"  Could not reach QR login page on port {try_port}: {e}")
            continue
    
    return None


async def fetch_user_code_from_file() -> Optional[Dict[str, Any]]:
    """Fetch user code from saved device auth file."""
    # Try standard location first (saved by QR page)
    device_auth_file = os.path.expanduser("~/.p8fs/device_auth.json")
    
    if os.path.exists(device_auth_file):
        try:
            with open(device_auth_file) as f:
                data = json.load(f)
            
            # Check if code is expired
            from datetime import datetime, timezone, timedelta
            if "created_at" in data and "expires_in" in data:
                created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
                expires_at = created_at + timedelta(seconds=data["expires_in"])
                if expires_at < datetime.now(timezone.utc):
                    print(f"  Standard device code has expired")
                    return None
            
            print(f"✓ Found device authorization from QR page:")
            print(f"  User Code: {data['user_code']}")
            print(f"  Client ID: {data['client_id']}")
            print(f"  Created: {data.get('created_at', 'unknown')}")
            print(f"  File: ~/.p8fs/device_auth.json")
            
            return data
            
        except Exception as e:
            print(f"  Error reading device auth file: {e}")
    
    # Fallback to old location
    code_file = os.path.expanduser("~/.p8fs/auth/device_code/code.json")
    
    if not os.path.exists(code_file):
        return None
    
    try:
        with open(code_file) as f:
            data = json.load(f)
            
        # Check if code is expired
        from datetime import datetime
        if "expires_at" in data:
            expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
            if expires_at < datetime.utcnow():
                print(f"  Saved device code has expired (expired at {data['expires_at']})")
                return None
        
        print(f"✓ Found saved device authorization:")
        print(f"  User Code: {data['user_code']}")
        print(f"  Client ID: {data['client_id']}")
        print(f"  Status: {data.get('status', 'unknown')}")
        print(f"  Created: {data.get('created_at', 'unknown')}")
        print(f"  File: ~/.p8fs/auth/device_code/code.json")
        
        return data
        
    except Exception as e:
        print(f"  Error reading saved device code: {e}")
        return None


async def main():
    parser = argparse.ArgumentParser(
        description="Approve P8FS device authorization requests"
    )
    parser.add_argument(
        "--user-code",
        help="User code to approve (e.g., 1A09-DE7E)"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-approve the first pending request"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List pending device authorization requests"
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Automatically detect user code from QR login page"
    )
    parser.add_argument(
        "--token-file",
        default=DEFAULT_TOKEN_FILE,
        help=f"Token file with device credentials (default: {DEFAULT_TOKEN_FILE})"
    )
    parser.add_argument(
        "--url", "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of P8FS API (default: {DEFAULT_BASE_URL})"
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port override (defaults to port in --url or 8001)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not (args.user_code or args.auto or args.list or args.detect):
        # If no arguments, default to --detect
        args.detect = True
    
    print("P8FS Device Authorization Approval")
    print("=" * 40)
    
    # Load device credentials
    creds = load_device_credentials(args.token_file)
    if not creds:
        return 1
    
    access_token = creds.get("access_token")
    device_keys = creds.get("device_keys")
    
    if not access_token or not device_keys:
        print("ERROR: Invalid token file format", file=sys.stderr)
        return 1
    
    # List pending requests
    if args.list:
        print("\nListing pending device requests...")
        requests = await list_pending_requests(args.url, access_token)
        if requests:
            for req in requests:
                print(f"\n  User Code: {req['user_code']}")
                print(f"  Client ID: {req['client_id']}")
                print(f"  Scopes: {', '.join(req['scopes'])}")
                print(f"  Expires: {req['expires_at']}")
        return 0
    
    # Auto-approve first pending request
    if args.auto:
        print("\nLooking for pending requests...")
        requests = await list_pending_requests(args.url, access_token)
        if requests and len(requests) > 0:
            first_request = requests[0]
            user_code = first_request['user_code']
            print(f"\nFound pending request: {user_code}")
            success = await approve_device_request(
                user_code, args.url, access_token, device_keys, args.token_file
            )
            return 0 if success else 1
        else:
            print("No pending requests to approve")
            return 0
    
    # Approve specific user code
    if args.user_code:
        success = await approve_device_request(
            args.user_code, args.url, access_token, device_keys
        )
        return 0 if success else 1
    
    # Auto-detect from QR login page or saved file
    if args.detect:
        print("\nDetecting active device authorization...")
        
        # First try to read from saved file
        saved_device_data = await fetch_user_code_from_file()
        if saved_device_data:
            user_code = saved_device_data['user_code']
            print("\nUsing saved device authorization from ~/.p8fs/auth/device_code/code.json")
        else:
            print("\nNo saved device code found, checking device verification page...")
            # Use explicit port if provided, otherwise let function extract from URL
            user_code = await fetch_user_code_from_qr_page(args.url, args.port)
        
        if user_code:
            print("\nApproving detected device authorization...")
            success = await approve_device_request(
                user_code, args.url, access_token, device_keys, args.token_file
            )
            return 0 if success else 1
        else:
            print("\nNo active device authorization found.")
            print("Make sure:")
            print("1. The API server is running")
            print("2. Someone has initiated a device flow (e.g., via Claude MCP)")
            print("3. The QR login page is accessible or code.json file exists")
            return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))