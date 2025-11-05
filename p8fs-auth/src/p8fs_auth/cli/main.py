"""P8FS Auth CLI tool for development and testing.

This CLI provides utilities for:
- Generating development JWT tokens
- Creating test keypairs
- Validating tokens
- Testing authentication flows

Reference: p8fs-api/src/p8fs_api/scripts/get_dev_jwt.py - Original implementation
"""

import asyncio
import base64
import json
import sys
from datetime import datetime

import click
from p8fs_cluster.config.settings import config
from rich.console import Console
from rich.table import Table

from ..services.jwt_key_manager import JWTKeyManager
from ..services.mobile_service import MobileAuthenticationService

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="p8fs-auth")
def cli():
    """P8FS Authentication CLI for development and testing.
    
    Provides tools for JWT generation, keypair management, and auth testing.
    """
    pass


@cli.command()
@click.option('--user-id', '-u', required=True, help='User ID for the token')
@click.option('--client-id', '-c', default='dev-cli', help='OAuth client ID')
@click.option('--scope', '-s', multiple=True, default=['read', 'write'], help='Token scopes')
@click.option('--expires-in', '-e', default=3600, help='Token lifetime in seconds')
@click.option('--device-id', '-d', help='Optional device ID binding')
@click.option('--output', '-o', type=click.Choice(['token', 'full', 'jwt-io']), default='token')
def generate_token(
    user_id: str,
    client_id: str,
    scope: tuple,
    expires_in: int,
    device_id: str | None,
    output: str
):
    """Generate a development JWT token.
    
    This command creates a signed JWT token for testing API endpoints.
    
    Examples:
        
        # Basic token generation
        p8fs-auth generate-token -u user123
        
        # With custom scopes and expiry
        p8fs-auth generate-token -u user123 -s read -s write -s admin -e 7200
        
        # Full output with claims
        p8fs-auth generate-token -u user123 --output full
    """
    # Initialize JWT manager
    jwt_manager = JWTKeyManager()
    
    # Create token
    token = asyncio.run(jwt_manager.create_access_token(
        user_id=user_id,
        client_id=client_id,
        scope=list(scope),
        device_id=device_id
    ))
    
    if output == 'token':
        # Just output the token
        click.echo(token)
    elif output == 'full':
        # Decode and display full token info
        claims = asyncio.run(jwt_manager.verify_token(token, verify_expiration=False))
        
        console.print("\n[bold green]JWT Token Generated[/bold green]")
        console.print(f"\n[bold]Token:[/bold]\n{token}")
        
        console.print("\n[bold]Claims:[/bold]")
        table = Table(show_header=True)
        table.add_column("Claim", style="cyan")
        table.add_column("Value", style="yellow")
        
        for key, value in claims.items():
            if key in ['exp', 'iat']:
                # Format timestamps
                value = datetime.fromtimestamp(value).isoformat()
            elif isinstance(value, list):
                value = ', '.join(value)
            table.add_row(key, str(value))
        
        console.print(table)
        
        # Show expiration info
        exp = datetime.fromtimestamp(claims['exp'])
        remaining = exp - datetime.utcnow()
        console.print(f"\n[bold]Expires in:[/bold] {remaining}")
        
    elif output == 'jwt-io':
        # Format for jwt.io debugging
        parts = token.split('.')
        header = json.loads(base64.urlsafe_b64decode(parts[0] + '=='))
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
        
        console.print("\n[bold green]JWT.io Debug Format[/bold green]")
        console.print("\n[bold]Header:[/bold]")
        console.print(json.dumps(header, indent=2))
        console.print("\n[bold]Payload:[/bold]")
        console.print(json.dumps(payload, indent=2))
        console.print(f"\n[bold]Token:[/bold]\n{token}")


@cli.command()
@click.option('--output-dir', '-o', default='.', help='Directory to save keypair files')
@click.option('--key-name', '-n', default='dev-keypair', help='Base name for key files')
def generate_keypair(output_dir: str, key_name: str):
    """Generate an Ed25519 keypair for mobile authentication.
    
    Creates a keypair suitable for mobile device authentication.
    
    Examples:
        
        # Generate keypair in current directory
        p8fs-auth generate-keypair
        
        # Custom output location and name
        p8fs-auth generate-keypair -o ./keys -n my-device
    """
    # Initialize mobile service
    mobile_service = MobileAuthenticationService(None, None, None)
    
    # Generate keypair
    private_key_bytes, public_key_bytes = mobile_service.generate_keypair()
    
    # Convert to base64 for storage
    private_key_b64 = base64.b64encode(private_key_bytes).decode('utf-8')
    public_key_b64 = base64.b64encode(public_key_bytes).decode('utf-8')
    
    # Save to files
    import os
    private_key_path = os.path.join(output_dir, f"{key_name}.private.key")
    public_key_path = os.path.join(output_dir, f"{key_name}.public.key")
    
    with open(private_key_path, 'w') as f:
        f.write(private_key_b64)
    
    with open(public_key_path, 'w') as f:
        f.write(public_key_b64)
    
    console.print("\n[bold green]Ed25519 Keypair Generated[/bold green]")
    console.print(f"\n[bold]Private Key:[/bold] {private_key_path}")
    console.print(f"[bold]Public Key:[/bold] {public_key_path}")
    console.print("\n[bold yellow]⚠️  Keep the private key secure![/bold yellow]")
    
    # Display public key for registration
    console.print(f"\n[bold]Public Key (for registration):[/bold]\n{public_key_b64}")


@cli.command()
@click.argument('token')
@click.option('--verify-exp', is_flag=True, help='Verify token expiration')
@click.option('--verify-aud', is_flag=True, help='Verify audience claim')
def verify_token(token: str, verify_exp: bool, verify_aud: bool):
    """Verify and decode a JWT token.
    
    Validates token signature and displays claims.
    
    Examples:
        
        # Basic verification
        p8fs-auth verify-token <token>
        
        # Full verification
        p8fs-auth verify-token <token> --verify-exp --verify-aud
    """
    jwt_manager = JWTKeyManager()
    
    try:
        # Verify token
        claims = asyncio.run(jwt_manager.verify_token(
            token,
            verify_audience=verify_aud,
            verify_expiration=verify_exp
        ))
        
        console.print("\n[bold green]✓ Token is valid[/bold green]")
        
        # Display claims
        console.print("\n[bold]Token Claims:[/bold]")
        table = Table(show_header=True)
        table.add_column("Claim", style="cyan")
        table.add_column("Value", style="yellow")
        
        for key, value in claims.items():
            if key in ['exp', 'iat']:
                # Format timestamps
                timestamp = datetime.fromtimestamp(value)
                value = f"{value} ({timestamp.isoformat()})"
            elif isinstance(value, list):
                value = ', '.join(value)
            table.add_row(key, str(value))
        
        console.print(table)
        
        # Check expiration
        if 'exp' in claims:
            exp = datetime.fromtimestamp(claims['exp'])
            if exp > datetime.utcnow():
                remaining = exp - datetime.utcnow()
                console.print(f"\n[green]Token expires in: {remaining}[/green]")
            else:
                expired_ago = datetime.utcnow() - exp
                console.print(f"\n[red]Token expired {expired_ago} ago[/red]")
        
    except Exception as e:
        console.print("\n[bold red]✗ Token verification failed[/bold red]")
        console.print(f"[red]Error: {str(e)}[/red]")
        sys.exit(1)


@cli.command()
def show_jwks():
    """Display the current JSON Web Key Set.
    
    Shows public keys for token verification.
    """
    jwt_manager = JWTKeyManager()
    jwks = jwt_manager.get_jwks()
    
    console.print("\n[bold green]JSON Web Key Set (JWKS)[/bold green]")
    console.print("\n[bold]Current Keys:[/bold]")
    
    for i, key in enumerate(jwks['keys'], 1):
        console.print(f"\n[bold cyan]Key {i}:[/bold cyan]")
        console.print(json.dumps(key, indent=2))
    
    console.print(f"\n[bold]Total Keys:[/bold] {len(jwks['keys'])}")
    console.print("\n[dim]Use these keys to verify tokens in external services[/dim]")


@cli.command()
@click.option('--format', '-f', type=click.Choice(['curl', 'httpie', 'python']), default='curl')
def auth_example(format: str):
    """Show example authentication requests.
    
    Displays example API calls for common auth operations.
    """
    base_url = config.auth_base_url or "http://localhost:8000"
    
    examples = {
        'curl': {
            'device_flow': f"""# Initiate device flow
            curl -X POST {base_url}/oauth/device/code \\
            -H "Content-Type: application/json" \\
            -d '{{"client_id": "desktop-app", "scope": "read write"}}'

            # Poll for token
            curl -X POST {base_url}/oauth/token \\
            -H "Content-Type: application/x-www-form-urlencoded" \\
            -d "grant_type=urn:ietf:params:oauth:grant-type:device_code&device_code=<code>&client_id=desktop-app"
            """,
                        'register': f"""# Register mobile device
            curl -X POST {base_url}/api/v1/auth/register \\
            -H "Content-Type: application/json" \\
            -d '{{"email": "user@example.com", "public_key": "<base64-public-key>", "device_name": "My Phone"}}'
            """,
                        'token': f"""# Use bearer token
            curl -H "Authorization: Bearer <token>" \\
            {base_url}/api/v1/protected-endpoint
            """
                    },
                    'httpie': {
                        'device_flow': f"""# Initiate device flow
            http POST {base_url}/oauth/device/code \\
            client_id=desktop-app \\
            scope="read write"

            # Poll for token  
            http --form POST {base_url}/oauth/token \\
            grant_type=urn:ietf:params:oauth:grant-type:device_code \\
            device_code=<code> \\
            client_id=desktop-app
            """,
                        'register': f"""# Register mobile device
            http POST {base_url}/api/v1/auth/register \\
            email=user@example.com \\
            public_key=<base64-public-key> \\
            device_name="My Phone"
            """,
                        'token': f"""# Use bearer token
            http GET {base_url}/api/v1/protected-endpoint \\
            Authorization:"Bearer <token>"
            """
                    },
                    'python': {
                        'device_flow': f"""# Initiate device flow
            import requests

            # Start device flow
            response = requests.post(
                "{base_url}/oauth/device/code",
                json={{"client_id": "desktop-app", "scope": "read write"}}
            )
            device_data = response.json()

            # Poll for token
            import time
            while True:
                response = requests.post(
                    "{base_url}/oauth/token",
                    data={{
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "device_code": device_data["device_code"],
                        "client_id": "desktop-app"
                    }}
                )
                if response.status_code == 200:
                    token_data = response.json()
                    break
                time.sleep(device_data["interval"])
            """,
                        'register': f"""# Register mobile device  
            import requests
            import base64
            from cryptography.hazmat.primitives.asymmetric import ed25519

            # Generate keypair
            private_key = ed25519.Ed25519PrivateKey.generate()
            public_key = private_key.public_key()
            public_key_b64 = base64.b64encode(
                public_key.public_bytes_raw()
            ).decode('utf-8')

            # Register device
            response = requests.post(
                "{base_url}/api/v1/auth/register",
                json={{
                    "email": "user@example.com",
                    "public_key": public_key_b64,
                    "device_name": "My Device"
                }}
            )
            """,
                        'token': f"""# Use bearer token
            import requests

            headers = {{"Authorization": f"Bearer {{token}}"}}
            response = requests.get(
                "{base_url}/api/v1/protected-endpoint",
                headers=headers
            )
            """
        }
    }
    
    console.print(f"\n[bold green]Authentication Examples - {format.upper()}[/bold green]")
    
    for operation, code in examples[format].items():
        console.print(f"\n[bold cyan]{operation.replace('_', ' ').title()}:[/bold cyan]")
        console.print(code)


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == '__main__':
    main()