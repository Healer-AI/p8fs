#!/usr/bin/env python3
"""
Full server diagnostic test.

Tests the complete P8FS API flow:
1. Health check
2. Device registration (dev mode)
3. List moments
4. Create moment
5. Chat completions
6. Chat search by moment

Requirements:
    export P8FS_DEV_TOKEN_SECRET='your-dev-token'

Usage:
    python3 scripts/diagnostics/test_server_full.py [--host https://api.example.com]
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, Optional

import requests


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.YELLOW}→ {text}{Colors.END}")


class ServerDiagnostic:
    """Full server diagnostic test suite."""

    def __init__(self, host: str, dev_token: str):
        self.host = host.rstrip('/')
        self.dev_token = dev_token
        self.access_token: Optional[str] = None
        self.tenant_id: Optional[str] = None
        self.moment_id: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'P8FS-Diagnostic/1.0'
        })

    def test_health(self) -> bool:
        """Test health endpoint."""
        print_header("1. Health Check")
        try:
            response = self.session.get(f"{self.host}/health", timeout=10)
            response.raise_for_status()
            data = response.json()

            print_success(f"Health endpoint accessible: {response.status_code}")
            print_info(f"Status: {data.get('status')}")
            print_info(f"Version: {data.get('version')}")
            return True
        except Exception as e:
            print_error(f"Health check failed: {e}")
            return False

    def test_device_registration(self) -> bool:
        """Test device registration flow (dev mode)."""
        print_header("2. Device Registration (Dev Mode)")
        try:
            # Generate test keypair (simplified - just base64 random data for diagnostic)
            import base64
            import secrets

            test_public_key = base64.b64encode(secrets.token_bytes(32)).decode('utf-8')
            test_email = f"diagnostic-test-{int(time.time())}@example.com"
            test_code = f"{secrets.randbelow(1000000):06d}"

            # Register device using dev endpoint
            headers = {
                'X-Dev-Token': self.dev_token,
                'X-Dev-Email': test_email,
                'X-Dev-Code': test_code,
                'Content-Type': 'application/json'
            }
            payload = {
                "email": test_email,
                "public_key": test_public_key,
                "device_info": {
                    "platform": "diagnostic",
                    "device_name": "Diagnostic Script",
                    "app_version": "1.0.0"
                }
            }
            response = self.session.post(
                f"{self.host}/api/v1/auth/dev/register",
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            self.access_token = data.get('access_token')
            self.tenant_id = test_email

            print_success("Device registered successfully")
            print()
            print(f"  {Colors.BOLD}Registration Response:{Colors.END}")
            # Show truncated token for security
            display_data = data.copy()
            if 'access_token' in display_data and display_data['access_token']:
                display_data['access_token'] = display_data['access_token'][:30] + '...'
            print(f"  {json.dumps(display_data, indent=4)}")
            print()

            return True
        except Exception as e:
            print_error(f"Device registration failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print_error(f"Response: {e.response.text}")
            return False


    def test_moments_list(self) -> bool:
        """Test listing moments."""
        print_header("3. List Moments")
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            response = self.session.get(
                f"{self.host}/api/v1/entity/moments/",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            moments = data.get('results', [])
            print_success(f"Moments endpoint accessible: {len(moments)} moments (total: {data.get('total', 0)})")

            if moments:
                print_info(f"Retrieved {len(moments)} moment(s)")
                print()
                for i, moment in enumerate(moments[:5], 1):  # Show first 5
                    print(f"  {Colors.BOLD}Moment {i}:{Colors.END}")
                    print(f"  {json.dumps(moment, indent=4)}")
                    print()
                self.moment_id = moments[0].get('id')
            else:
                print_info("No moments found (expected for new device)")

            return True
        except Exception as e:
            print_error(f"List moments failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print_error(f"Response: {e.response.text}")
            return False

    def test_create_moment(self) -> bool:
        """Test creating a moment."""
        print_header("4. Create Moment")
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            payload = {
                "name": f"Diagnostic Test Moment {int(time.time())}",
                "description": "Created by diagnostic script",
                "content": "This is a diagnostic test moment created to verify the API is working correctly.",
                "moment_type": "test"
            }
            response = self.session.post(
                f"{self.host}/api/v1/entity/moments/",
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            self.moment_id = data.get('id')
            print_success(f"Moment created successfully")
            print()
            print(f"  {Colors.BOLD}Created Moment:{Colors.END}")
            print(f"  {json.dumps(data, indent=4)}")
            print()

            return True
        except Exception as e:
            print_error(f"Create moment failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print_error(f"Response: {e.response.text}")
            return False

    def test_chat_completion(self) -> bool:
        """Test chat completion with streaming."""
        print_header("5. Chat Completion (Streaming)")
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            if self.moment_id:
                headers['X-Moment-Id'] = self.moment_id

            payload = {
                "model": "gpt-4.1-mini",
                "messages": [
                    {"role": "user", "content": "Write a haiku about debugging code. Keep it short."}
                ],
                "stream": True
            }

            print_info("Sending streaming chat request...")
            print(f"{Colors.YELLOW}→ Assistant: {Colors.END}", end='', flush=True)

            response = self.session.post(
                f"{self.host}/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
                stream=True
            )
            response.raise_for_status()

            # Stream the response
            full_content = ""
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # Remove 'data: ' prefix
                        if data_str.strip() == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get('choices', [{}])[0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                print(content, end='', flush=True)
                                full_content += content
                        except json.JSONDecodeError:
                            pass

            print()  # New line after streaming
            print()
            print_success(f"Chat completion successful ({len(full_content)} characters)")

            return True
        except Exception as e:
            print()
            print_error(f"Chat completion failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print_error(f"Response: {e.response.text}")
            return False

    def test_chat_search(self) -> bool:
        """Test chat search endpoint."""
        print_header("6. Chat Search by Moment")
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            params = {
                'query': 'test',
                'limit': 5
            }
            if self.moment_id:
                params['moment_id'] = self.moment_id

            response = self.session.get(
                f"{self.host}/api/v1/chats/search",
                headers=headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            results = data.get('results', [])
            print_success(f"Chat search successful: {len(results)} results")

            if results:
                print_info(f"First result: {results[0].get('name', 'unnamed')}")

            return True
        except Exception as e:
            print_error(f"Chat search failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print_error(f"Response: {e.response.text}")
            return False

    def run_all(self) -> bool:
        """Run all diagnostic tests."""
        print_header(f"P8FS Server Diagnostic - {self.host}")

        tests = [
            ("Health Check", self.test_health),
            ("Device Registration", self.test_device_registration),
            ("List Moments", self.test_moments_list),
            ("Create Moment", self.test_create_moment),
            ("Chat Completion (Streaming)", self.test_chat_completion),
            ("Chat Search", self.test_chat_search),
        ]

        results = []
        for name, test_func in tests:
            try:
                result = test_func()
                results.append((name, result))
                if not result:
                    print_error(f"Test '{name}' failed, continuing...")
            except Exception as e:
                print_error(f"Test '{name}' crashed: {e}")
                results.append((name, False))

        # Summary
        print_header("Diagnostic Summary")
        passed = sum(1 for _, result in results if result)
        total = len(results)

        for name, result in results:
            status = f"{Colors.GREEN}PASS{Colors.END}" if result else f"{Colors.RED}FAIL{Colors.END}"
            print(f"{status} - {name}")

        print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.END}\n")

        return passed == total


def main():
    parser = argparse.ArgumentParser(
        description="Full P8FS server diagnostic test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Requirements:
  export P8FS_DEV_TOKEN_SECRET='your-dev-token'

Examples:
  # Test remote production API
  python3 scripts/diagnostics/test_server_full.py

  # Test local API server (configure P8FS_STORAGE_PROVIDER for TiDB/PostgreSQL)
  python3 scripts/diagnostics/test_server_full.py --local

  # Test custom host
  python3 scripts/diagnostics/test_server_full.py --host https://staging.example.com

Local Server Testing:
  To test local API with TiDB:
    P8FS_STORAGE_PROVIDER=tidb uvicorn src.p8fs_api.main:app --reload --port 8001
    python3 scripts/diagnostics/test_server_full.py --local

  To test local API with PostgreSQL:
    P8FS_STORAGE_PROVIDER=postgresql uvicorn src.p8fs_api.main:app --reload --port 8001
    python3 scripts/diagnostics/test_server_full.py --local
        """
    )
    parser.add_argument(
        '--host',
        default='https://p8fs.eepis.ai',
        help='API host URL (default: https://p8fs.eepis.ai)'
    )
    parser.add_argument(
        '--local',
        action='store_true',
        help='Test local API server at http://localhost:8001'
    )

    args = parser.parse_args()

    # Check for required environment variable
    dev_token = os.environ.get('P8FS_DEV_TOKEN_SECRET')
    if not dev_token:
        print_error("Environment variable P8FS_DEV_TOKEN_SECRET is required")
        print_info("Set it with: export P8FS_DEV_TOKEN_SECRET='your-token-here'")
        sys.exit(1)

    # Override host if --local flag is set
    host = 'http://localhost:8001' if args.local else args.host

    print_info(f"Testing API: {host}")
    if args.local:
        print_info("Local mode: Server's database provider set by P8FS_STORAGE_PROVIDER")
    print()

    diagnostic = ServerDiagnostic(host, dev_token)
    success = diagnostic.run_all()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
