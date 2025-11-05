"""Debug script to test device authorization storage and retrieval."""

import asyncio
import httpx
import json
from p8fs_cluster.config.settings import config

BASE_URL = "http://localhost:8001"


async def debug_device_auth_flow():
    """Debug the device authorization storage and retrieval."""
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        print("\n=== Step 1: Create Device Authorization ===")
        
        # Create device authorization
        device_auth_response = await client.post(
            "/oauth/device_authorization",
            data={
                "client_id": "debug_test_client",
                "scope": "read write"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if device_auth_response.status_code != 200:
            print(f"Failed to create device authorization: {device_auth_response.status_code}")
            print(f"Response: {device_auth_response.text}")
            return
            
        device_auth = device_auth_response.json()
        device_code = device_auth["device_code"]
        user_code = device_auth["user_code"]
        
        print(f"✓ Device code: {device_code}")
        print(f"✓ User code: {user_code}")
        
        # Check if it was saved to file
        import os
        from pathlib import Path
        
        code_file = Path.home() / ".p8fs" / "auth" / "device_code" / "code.json"
        if code_file.exists():
            with open(code_file) as f:
                saved_data = json.load(f)
            print(f"\n✓ Found saved device code in file:")
            print(f"  - User code: {saved_data['user_code']}")
            print(f"  - Device code: {saved_data['device_code']}")
            print(f"  - Status: {saved_data['status']}")
        
        print("\n=== Step 2: Get Dev Token for Approval ===")
        
        # Get a dev token
        if not config.dev_token_secret:
            print("ERROR: No dev token secret configured")
            return
            
        dev_token_response = await client.post(
            "/api/v1/auth/dev/register",
            json={
                "email": "debug@test.com",
                "public_key": "debug_public_key_base64",
                "device_info": {
                    "device_name": "Debug Device",
                    "platform": "debug"
                }
            },
            headers={
                "X-Dev-Token": config.dev_token_secret,
                "X-Dev-Email": "debug@test.com",
                "X-Dev-Code": "DEBUG123"
            }
        )
        
        if dev_token_response.status_code != 200:
            print(f"Failed to get dev token: {dev_token_response.status_code}")
            print(f"Response: {dev_token_response.text}")
            return
            
        dev_token_data = dev_token_response.json()
        access_token = dev_token_data["access_token"]
        print(f"✓ Got access token: {access_token[:50]}...")
        
        print("\n=== Step 3: Attempt Device Approval ===")
        
        # Try to approve with different user code formats
        user_codes_to_try = [
            user_code,  # Original format (e.g., "ABCD-1234")
            user_code.upper(),  # Ensure uppercase
            user_code.replace("-", ""),  # No dash
            user_code.upper().replace("-", "")  # Normalized
        ]
        
        for code_format in user_codes_to_try:
            print(f"\nTrying user code format: {code_format}")
            
            approval_response = await client.post(
                "/oauth/device/approve",
                json={
                    "user_code": code_format,
                    "approved": True,
                    "device_name": "Debug Client"
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
            )
            
            if approval_response.status_code == 200:
                print(f"✓ SUCCESS! Approval worked with format: {code_format}")
                break
            else:
                print(f"✗ Failed with {approval_response.status_code}: {approval_response.text}")
        
        print("\n=== Step 4: Check Repository State ===")
        
        # Try to poll for token to see if it was approved
        print("\nTrying token poll...")
        token_response = await client.post(
            "/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "debug_test_client"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if token_response.status_code == 200:
            print("✓ Token exchange successful! Device was approved.")
            token_data = token_response.json()
            print(f"  Access token: {token_data['access_token'][:50]}...")
        else:
            print(f"✗ Token exchange failed: {token_response.status_code}")
            print(f"  Response: {token_response.text}")


if __name__ == "__main__":
    asyncio.run(debug_device_auth_flow())