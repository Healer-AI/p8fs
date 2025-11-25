#!/usr/bin/env python3
"""
Generate JWT ES256 Key Pair for Development

This script generates an ECDSA P-256 key pair for JWT signing in development.
The keys are saved to ~/.p8fs/server/auth/temp_tokens.json and will be
automatically loaded by the API server on startup.

For production, keys are managed by Kubernetes secrets via environment variables:
    P8FS_JWT_PRIVATE_KEY_PEM="..."
    P8FS_JWT_PUBLIC_KEY_PEM="..."
"""

import json
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate_es256_keypair():
    """Generate ES256 (P-256) keypair for JWT signing."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    return private_pem, public_pem


def save_keys_to_file(private_pem: str, public_pem: str, storage_dir: Path | None = None):
    """Save keys to ~/.p8fs/server/auth/temp_tokens.json."""
    if storage_dir is None:
        storage_dir = Path.home() / ".p8fs" / "server" / "auth"

    storage_dir.mkdir(parents=True, exist_ok=True)
    token_file = storage_dir / "temp_tokens.json"

    token_data = {
        "private_key_pem": private_pem,
        "public_key_pem": public_pem,
        "created_at": datetime.utcnow().isoformat(),
        "key_type": "ES256"
    }

    with open(token_file, 'w') as f:
        json.dump(token_data, f, indent=2)

    return token_file


def main():
    print("P8FS JWT ES256 Key Generator")
    print("=" * 40)
    print()

    private_pem, public_pem = generate_es256_keypair()

    token_file = save_keys_to_file(private_pem, public_pem)

    print(f"✓ Keys generated and saved to: {token_file}")
    print()
    print("The API server will automatically load these keys on startup.")
    print()
    print("Alternatively, you can add these to your .env file:")
    print()
    print("P8FS_JWT_PRIVATE_KEY_PEM=\"\"\"")
    print(private_pem.strip())
    print("\"\"\"")
    print()
    print("P8FS_JWT_PUBLIC_KEY_PEM=\"\"\"")
    print(public_pem.strip())
    print("\"\"\"")
    print()
    print("For production, these keys are managed by Kubernetes secrets.")
    print("Never commit these keys to version control!")


if __name__ == "__main__":
    main()