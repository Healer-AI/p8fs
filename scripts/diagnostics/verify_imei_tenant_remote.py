#!/usr/bin/env python3
"""Verify IMEI-based deterministic tenant ID generation (REMOTE).

This script tests that device registration with the same IMEI
produces the same tenant ID on a remote server using the production
OAuth device flow with email verification.

Usage:
    # Step 1: Register devices (sends verification emails)
    uv run python scripts/diagnostics/verify_imei_tenant_remote.py register \\
        --server https://p8fs.eepis.ai \\
        --email your@email.com

    # Step 2: Verify devices with codes from email
    uv run python scripts/diagnostics/verify_imei_tenant_remote.py verify \\
        CODE1 CODE2 CODE3

Environment Variables:
    REMOTE_SERVER: Remote server URL (default: https://p8fs.eepis.ai)
    USER_EMAIL: Email address for verification (required for register)

Notes:
    - Requires access to email for verification codes
    - Uses production OAuth device registration flow
    - State is saved to /tmp/imei_test_state.json between steps
"""

import argparse
import asyncio
import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Install with: pip install httpx")
    sys.exit(1)


STATE_FILE = "/tmp/imei_test_state.json"


async def register_devices(server_url: str, email: str, test_imei: str = None):
    """Register 3 test devices and save state.

    Args:
        server_url: Remote server URL
        email: Email address for verification
        test_imei: IMEI to use for testing (default: generates unique)
    """

    # Use provided IMEI or generate unique one for this test
    if not test_imei:
        import time
        test_imei = str(int(time.time() * 1000))[-15:]  # Last 15 digits of timestamp

    expected_hash = hashlib.sha256(test_imei.encode()).hexdigest()[:16]
    expected_tenant_id = f"tenant-{expected_hash}"

    print("=" * 70)
    print(f"🌐 Registering Devices on: {server_url}")
    print("=" * 70)
    print(f"Email: {email}")
    print(f"Test IMEI: {test_imei}")
    print(f"Expected tenant_id: {expected_tenant_id}")
    print()

    devices = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Device 1: with IMEI
        print("📱 Registering Device 1 (with IMEI)")
        private_key1 = ed25519.Ed25519PrivateKey.generate()
        public_key1_b64 = base64.b64encode(
            private_key1.public_key().public_bytes_raw()
        ).decode('utf-8')

        response = await client.post(
            f"{server_url}/api/v1/oauth/device/register",
            json={
                "email": email,
                "public_key": public_key1_b64,
                "device_info": {
                    "platform": "iOS",
                    "model": "iPhone 15",
                    "imei": test_imei,
                    "device_name": "Test Device 1"
                }
            }
        )

        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Registration ID: {result['registration_id']}")
            devices.append({
                "name": "Device 1 (with IMEI)",
                "registration_id": result['registration_id'],
                "has_imei": True
            })
        else:
            print(f"   ❌ Failed: {response.text}")
            return False

        # Device 2: with SAME IMEI
        print("📱 Registering Device 2 (with SAME IMEI)")
        private_key2 = ed25519.Ed25519PrivateKey.generate()
        public_key2_b64 = base64.b64encode(
            private_key2.public_key().public_bytes_raw()
        ).decode('utf-8')

        response = await client.post(
            f"{server_url}/api/v1/oauth/device/register",
            json={
                "email": email,
                "public_key": public_key2_b64,
                "device_info": {
                    "platform": "Android",
                    "model": "Pixel 8",
                    "imei": test_imei,  # SAME IMEI
                    "device_name": "Test Device 2"
                }
            }
        )

        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Registration ID: {result['registration_id']}")
            devices.append({
                "name": "Device 2 (with SAME IMEI)",
                "registration_id": result['registration_id'],
                "has_imei": True
            })
        else:
            print(f"   ❌ Failed: {response.text}")
            return False

        # Device 3: without IMEI
        print("📱 Registering Device 3 (without IMEI)")
        private_key3 = ed25519.Ed25519PrivateKey.generate()
        public_key3_b64 = base64.b64encode(
            private_key3.public_key().public_bytes_raw()
        ).decode('utf-8')

        response = await client.post(
            f"{server_url}/api/v1/oauth/device/register",
            json={
                "email": email,
                "public_key": public_key3_b64,
                "device_info": {
                    "platform": "iOS",
                    "model": "iPad Pro",
                    "device_name": "Test Device 3"
                }
            }
        )

        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Registration ID: {result['registration_id']}")
            devices.append({
                "name": "Device 3 (without IMEI)",
                "registration_id": result['registration_id'],
                "has_imei": False
            })
        else:
            print(f"   ❌ Failed: {response.text}")
            return False

    # Save state
    state = {
        "server_url": server_url,
        "email": email,
        "test_imei": test_imei,
        "expected_tenant_id": expected_tenant_id,
        "devices": devices
    }

    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

    print()
    print("=" * 70)
    print(f"📧 CHECK YOUR EMAIL: {email}")
    print("=" * 70)
    print("You should have received 3 verification codes.")
    print()
    print("Next step:")
    print(f"  uv run python {sys.argv[0]} verify CODE1 CODE2 CODE3")
    print()

    return True


async def verify_devices(codes: list[str]):
    """Verify devices with provided codes.

    Args:
        codes: List of 3 verification codes from email

    Returns:
        True if all tests pass, False otherwise
    """

    if len(codes) != 3:
        print("❌ Error: Please provide exactly 3 verification codes")
        print(f"Usage: uv run python {sys.argv[0]} verify CODE1 CODE2 CODE3")
        return False

    # Load state
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    except FileNotFoundError:
        print("❌ Error: State file not found. Run 'register' first.")
        return False

    server_url = state['server_url']
    test_imei = state['test_imei']
    expected_tenant_id = state['expected_tenant_id']
    devices = state['devices']

    print("=" * 70)
    print(f"🔐 Verifying Devices on: {server_url}")
    print("=" * 70)
    print(f"Test IMEI: {test_imei}")
    print(f"Expected tenant_id: {expected_tenant_id}")
    print()

    tenant_ids = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, (device, code) in enumerate(zip(devices, codes), 1):
            print(f"🔐 Verifying {device['name']}")
            print(f"   Code: {code}")

            response = await client.post(
                f"{server_url}/api/v1/oauth/device/verify",
                json={
                    "registration_id": device['registration_id'],
                    "verification_code": code,
                    "challenge_signature": ""
                }
            )

            if response.status_code == 200:
                result = response.json()
                tenant_id = result.get('tenant_id')
                tenant_ids.append(tenant_id)

                print(f"   ✅ Verified! Tenant ID: {tenant_id}")

                if device['has_imei']:
                    matches = tenant_id == expected_tenant_id
                    print(f"   {'✅' if matches else '❌'} Matches expected: {matches}")
                else:
                    different = tenant_id != expected_tenant_id
                    print(f"   {'✅' if different else '❌'} Different from IMEI-based: {different}")
                print()
            else:
                print(f"   ❌ Verification failed: {response.text}")
                print()
                return False

    # Final analysis
    print("=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    print(f"Expected (from IMEI {test_imei}): {expected_tenant_id}")
    print()
    print(f"Device 1 (with IMEI):      {tenant_ids[0]}")
    print(f"Device 2 (same IMEI):      {tenant_ids[1]}")
    print(f"Device 3 (without IMEI):   {tenant_ids[2]}")
    print()

    # Check results
    device1_correct = tenant_ids[0] == expected_tenant_id
    device2_correct = tenant_ids[1] == expected_tenant_id
    devices_match = tenant_ids[0] == tenant_ids[1]
    device3_different = tenant_ids[2] != expected_tenant_id

    print("Checks:")
    print(f"  {'✅' if device1_correct else '❌'} Device 1 matches expected tenant ID")
    print(f"  {'✅' if device2_correct else '❌'} Device 2 matches expected tenant ID")
    print(f"  {'✅' if devices_match else '❌'} Device 1 and 2 have same tenant ID")
    print(f"  {'✅' if device3_different else '❌'} Device 3 has different (random) tenant ID")
    print()

    if device1_correct and device2_correct and devices_match and device3_different:
        print(f"🎉 SUCCESS! IMEI-based deterministic tenant IDs are WORKING on {server_url}!")
        return True
    else:
        print("❌ FAILURE! IMEI-based deterministic tenant IDs are NOT working correctly.")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Verify IMEI-based deterministic tenant ID generation on remote server"
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Register command
    register_parser = subparsers.add_parser('register', help='Register test devices')
    register_parser.add_argument('--server', default=os.getenv('REMOTE_SERVER', 'https://p8fs.eepis.ai'),
                                help='Remote server URL')
    register_parser.add_argument('--email', required=True,
                                help='Email address for verification')
    register_parser.add_argument('--imei', help='Custom IMEI to use (default: auto-generated)')

    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify devices with codes')
    verify_parser.add_argument('codes', nargs=3, help='Three verification codes from email')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'register':
        success = asyncio.run(register_devices(args.server, args.email, args.imei))
        sys.exit(0 if success else 1)
    elif args.command == 'verify':
        success = asyncio.run(verify_devices(args.codes))
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
