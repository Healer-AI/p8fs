#!/usr/bin/env python3
"""
Get Development JWT Token for P8FS API

This script generates a complete JWT authentication package for P8FS development:

1. **Generates Ed25519 key pair** - Creates device identity keys for authentication
2. **Calls dev registration endpoint** - Uses P8FS_DEV_TOKEN_SECRET to bypass email verification  
3. **Gets JWT tokens** - Returns access_token + refresh_token for API calls
4. **Saves everything** - Token + private/public keys for device operations

SECURITY: 
- Requires P8FS_DEV_TOKEN_SECRET environment variable (strong dev token)
- testing@percolationlabs.ai gets deterministic tenant (idempotent)
- Other emails get random tenant IDs

FLOW:
- Server validates dev token → creates/reuses tenant → issues JWT → returns tokens
- Client saves: JWT tokens + Ed25519 key pair for signing future requests

Usage:
    python get_dev_jwt.py                           # Use testing@percolationlabs.ai
    python get_dev_jwt.py --email user@example.com  # Use custom email  
    python get_dev_jwt.py -o custom_token.json      # Save to custom location
    python get_dev_jwt.py --url http://localhost:8000  # Use local dev server
"""

import argparse
import asyncio
import base64
import json
import os
import sys
from datetime import datetime
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Configuration
DEFAULT_BASE_URL = "http://localhost:8000"  # Default to local dev server
DEFAULT_EMAIL = "testing@percolationlabs.ai"
DEFAULT_OUTPUT = os.path.expanduser("~/.p8fs/auth/token.json")

async def get_dev_jwt_token(
    email: str, 
    output_file: str, 
    base_url: str = DEFAULT_BASE_URL
) -> dict[str, Any] | None:
    """Get development JWT token via dev endpoint"""
    
    # Get dev token from environment
    dev_token = os.getenv("P8FS_DEV_TOKEN_SECRET")
    if not dev_token:
        print("ERROR: P8FS_DEV_TOKEN_SECRET not set", file=sys.stderr)
        print("For development, use:", file=sys.stderr)
        print("export P8FS_DEV_TOKEN_SECRET='p8fs-dev-dHMZAB_dK8JR6ps-zLBSBTfBeoNdXu2KcpNywjDfD58'", file=sys.stderr)
        return None
    
    # Generate Ed25519 key pair
    print(f"Generating Ed25519 keypair for {email}...")
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Serialize keys
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    public_key_b64 = base64.b64encode(public_key_bytes).decode('utf-8')
    
    # Make request to dev endpoint
    print(f"Requesting dev JWT from {base_url}...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{base_url}/api/v1/auth/dev/register",
                json={
                    "email": email,
                    "public_key": public_key_b64,
                    "device_info": {
                        "device_name": "Dev JWT Generator",
                        "device_type": "desktop",
                        "os_version": "Development",
                        "app_version": "dev-1.0.0",
                        "platform": "dev-script"
                    },
                },
                headers={
                    "X-Dev-Token": dev_token,
                    "X-Dev-Email": email,
                    "X-Dev-Code": "123456",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code != 200:
                print(f"ERROR: Request failed {response.status_code}: {response.text}", file=sys.stderr)
                print(f"URL: {base_url}/api/v1/auth/dev/register", file=sys.stderr)
                return None
                
            token_data = response.json()
            access_token = token_data.get("access_token")
            
            if not access_token:
                print("ERROR: No access token received", file=sys.stderr)
                print(f"Response: {token_data}", file=sys.stderr)
                return None
                
        except httpx.RequestError as e:
            print(f"ERROR: Network error: {e}", file=sys.stderr)
            print("Make sure the P8FS API server is running at:", base_url, file=sys.stderr)
            return None
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return None
    
    # Save token with key pair
    token_info = {
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token"),
        "token_type": "Bearer",
        "expires_in": token_data.get("expires_in", 3600),
        "tenant_id": token_data.get("tenant_id"),
        "created_at": datetime.now().isoformat(),
        "email": email,
        "base_url": base_url,
        "device_keys": {
            "private_key_pem": private_key_pem,
            "public_key_pem": public_key_pem,
            "public_key_b64": public_key_b64
        }
    }
    
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(token_info, f, indent=2)
        print(f"✓ Token saved to {output_file}")
        print(f"✓ Access token: {access_token[:20]}...")
        if token_data.get("tenant_id"):
            print(f"✓ Tenant ID: {token_data['tenant_id']}")
        return token_info
    except Exception as e:
        print(f"ERROR: Failed to save token: {e}", file=sys.stderr)
        return None

def sign_message_with_saved_key(message: str, token_file: str = DEFAULT_OUTPUT) -> str | None:
    """Sign a message with the saved device private key"""
    try:
        with open(token_file) as f:
            token_data = json.load(f)
        
        private_key_pem = token_data["device_keys"]["private_key_pem"]
        private_key = Ed25519PrivateKey.from_private_bytes(
            serialization.load_pem_private_key(
                private_key_pem.encode('utf-8'),
                password=None
            ).private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )
        )
        
        signature = private_key.sign(message.encode('utf-8'))
        return base64.b64encode(signature).decode('utf-8')
    except Exception as e:
        print(f"ERROR: Failed to sign message: {e}", file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(description="Get P8FS development JWT token")
    parser.add_argument(
        "--email", 
        default=DEFAULT_EMAIL,
        help=f"Email to use (default: {DEFAULT_EMAIL})"
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output file (default: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--url", "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of P8FS API (default: {DEFAULT_BASE_URL})"
    )
    parser.add_argument(
        "--test-sign",
        action="store_true",
        help="Test message signing with saved key after getting token"
    )
    
    args = parser.parse_args()
    
    print("P8FS Development JWT Token Generator")
    print("=" * 40)
    
    result = asyncio.run(get_dev_jwt_token(args.email, args.output, args.url))
    
    if not result:
        sys.exit(1)
    
    # Optionally test message signing
    if args.test_sign:
        print("\nTesting message signing...")
        test_message = "Hello, P8FS! This is a test message."
        signature = sign_message_with_saved_key(test_message, args.output)
        if signature:
            print(f"✓ Test signature: {signature[:20]}...")
        else:
            print("✗ Failed to generate test signature")
    
    print("\nTo use this token in API requests:")
    print(f'curl -H "Authorization: Bearer {result["access_token"][:20]}..." {args.url}/health')

if __name__ == "__main__":
    main()