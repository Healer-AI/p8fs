#!/usr/bin/env python3
"""Generate a development token using dev endpoint."""

import json
import httpx
import asyncio
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.backends import default_backend
import base64
import os

async def generate_dev_token():
    """Generate a fresh development token."""
    # Check for dev token secret
    dev_token_secret = os.environ.get("P8FS_DEV_TOKEN_SECRET")
    if not dev_token_secret:
        print("ERROR: P8FS_DEV_TOKEN_SECRET environment variable not set")
        return None
    
    # Generate a new keypair for the device
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Convert to PEM format
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    # Convert public key to base64
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    public_key_b64 = base64.b64encode(public_key_bytes).decode('utf-8')
    
    # Use dev endpoint to register and get token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8001/api/v1/auth/dev/register",
            json={
                "email": "teofilovicdejan892@gmail.com",
                "public_key": public_key_b64,
                "device_info": {
                    "device_name": "Dev Token Generator",
                    "device_type": "script",
                    "platform": "development"
                }
            },
            headers={
                "X-Dev-Token": dev_token_secret,
                "X-Dev-Email": "teofilovicdejan892@gmail.com",
                "X-Dev-Code": "dev-token-gen"
            }
        )
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data["access_token"]
            
            # Save to token.json
            token_file = Path.home() / ".p8fs" / "auth" / "token.json"
            token_file.parent.mkdir(parents=True, exist_ok=True)
            
            token_json = {
                "access_token": access_token,
                "refresh_token": token_data.get("refresh_token"),
                "token_type": "Bearer",
                "expires_in": token_data.get("expires_in", 86400),
                "tenant_id": token_data.get("tenant_id"),
                "created_at": asyncio.get_event_loop().time(),
                "email": "teofilovicdejan892@gmail.com",
                "base_url": "http://localhost:8001",
                "device_keys": {
                    "private_key_pem": private_key_pem,
                    "public_key_pem": public_key_pem,
                    "public_key_b64": public_key_b64
                }
            }
            
            with open(token_file, "w") as f:
                json.dump(token_json, f, indent=2)
            
            print(f"✓ Fresh development token generated and saved to {token_file}")
            print(f"  Access token: {access_token[:50]}...")
            print(f"  Tenant ID: {token_data.get('tenant_id')}")
            print(f"  Expires in: {token_data.get('expires_in', 0)} seconds")
            
            return access_token
        else:
            print(f"ERROR: Failed to generate token: {response.status_code}")
            print(response.text)
            return None

if __name__ == "__main__":
    token = asyncio.run(generate_dev_token())
    if not token:
        exit(1)