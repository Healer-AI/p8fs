"""JWT key management service with ES256 signing.

This service handles JWT token generation and validation using:
- ES256 (ECDSA with P-256 curve) for signing
- Automatic key rotation with zero downtime
- Token validation and claims extraction
- Key storage abstraction for distributed systems

Reference: p8fs-auth/docs/authentication-flows.md - JWT Signing Keys (ES256)
Reference: p8fs-api/src/p8fs_api/middleware/auth.py - JWT token verification
"""

import base64
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import jwt
from jwt.exceptions import PyJWTError as JWTError
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging.setup import get_logger

logger = get_logger(__name__)


# Singleton instance
_jwt_key_manager_instance: "JWTKeyManager | None" = None


class JWTKeyManager:
    """JWT key management with ES256 signing.

    Implements JWT management from:
    Reference: p8fs-auth/docs/authentication-flows.md - JWT Signing Keys (ES256)

    Key features:
    - ECDSA with P-256 curve for smaller signatures
    - System-wide signing key with rotation
    - Zero-downtime key rotation
    - Support for distributed key storage
    - Singleton pattern to ensure consistent keys across application

    Why ES256 over RS256:
    - Smaller signatures (64 bytes vs 256 bytes)
    - Faster verification
    - Equivalent security level
    - Better for mobile/embedded devices
    """

    def __new__(cls):
        """Implement singleton pattern to ensure one instance per process."""
        global _jwt_key_manager_instance
        if _jwt_key_manager_instance is None:
            _jwt_key_manager_instance = super().__new__(cls)
        return _jwt_key_manager_instance

    def __init__(self):
        """Initialize JWT key manager.

        In production, keys would be loaded from TiKV
        for distributed consistency.
        """
        # Skip initialization if already initialized (singleton pattern)
        if hasattr(self, '_initialized'):
            return

        # Key rotation settings from config
        # Reference: CLAUDE.md - "All configuration must come from centralized config"
        self.key_rotation_days = getattr(config, 'auth_jwt_rotation_days', 30)
        self.algorithm = "ES256"  # ECDSA with P-256

        # JWT settings
        self.issuer = getattr(config, 'auth_jwt_issuer', "p8fs-auth")
        self.audience = getattr(config, 'auth_jwt_audience', "p8fs-api")

        # In-memory key storage (would be TiKV in production)
        # Structure: {key_id: {private_key, public_key, created_at, retired_at}}
        self._keys: dict[str, dict[str, Any]] = {}
        self._current_key_id: str | None = None

        # Try to load keys in priority order:
        # 1. Environment variables (production)
        # 2. Saved file from script (development persistence)
        # 3. Generate new keys (first-time development use)
        loaded = self._load_from_config()

        if not loaded:
            loaded = self._load_from_file()

        # If no keys loaded, generate new ones (development only)
        if not self._current_key_id:
            logger.info("JWT Keys: GENERATING NEW KEYS (first-time development use)")
            self._ensure_current_key()

        # Mark as initialized
        self._initialized = True
    
    def _load_from_config(self) -> bool:
        """Load JWT keys from configuration.

        Checks for PEM-encoded keys in configuration and loads them.
        In development mode, auto-generates temporary keys if not configured.
        In production mode, raises error if keys are missing.

        Returns:
            True if keys were loaded, False otherwise

        Raises:
            RuntimeError: If no JWT keys are configured in production
        """
        private_pem = getattr(config, 'jwt_private_key_pem', '')
        public_pem = getattr(config, 'jwt_public_key_pem', '')

        if not private_pem or not public_pem:
            # In production, require explicit key configuration
            if config.is_production:
                logger.error(
                    "JWT signing keys not configured in production. "
                    "Set P8FS_JWT_PRIVATE_KEY_PEM and P8FS_JWT_PUBLIC_KEY_PEM environment variables."
                )
                raise RuntimeError(
                    "JWT signing keys required in production. "
                    "P8FS_JWT_PRIVATE_KEY_PEM and P8FS_JWT_PUBLIC_KEY_PEM must be set."
                )

            # In development, will try to load from file or generate new keys
            logger.info(
                "JWT Keys: No environment variables found. "
                "Attempting to load from ~/.p8fs/server/auth/temp_tokens.json or will generate new keys."
            )
            return False  # Signal to try file loading or generation
        
        try:
            # Load private key from PEM
            private_key = serialization.load_pem_private_key(
                private_pem.encode() if isinstance(private_pem, str) else private_pem,
                password=None
            )
            
            # Load public key from PEM
            public_key = serialization.load_pem_public_key(
                public_pem.encode() if isinstance(public_pem, str) else public_pem
            )
            
            # Verify keys are EC keys for ES256
            if not isinstance(private_key, ec.EllipticCurvePrivateKey):
                raise ValueError("Private key must be an EC key for ES256 signing")
                
            # Store loaded keys
            key_id = "config-key"
            self._keys[key_id] = {
                "private_key": private_key,
                "public_key": public_key,
                "created_at": datetime.utcnow(),
                "retired_at": None,
                "public_key_pem": public_pem.encode() if isinstance(public_pem, str) else public_pem,
                "public_key_jwk": self._public_key_to_jwk(public_key, key_id)
            }
            self._current_key_id = key_id
            logger.info("JWT Keys: Loaded from ENVIRONMENT VARIABLES (production mode)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load JWT keys from configuration: {e}")
            raise RuntimeError(
                f"Failed to load JWT signing keys: {e}. "
                "Ensure P8FS_JWT_PRIVATE_KEY_PEM and P8FS_JWT_PUBLIC_KEY_PEM contain valid ES256 keys."
            )

    def _load_from_file(self) -> bool:
        """Load JWT keys from saved file.

        Loads keys from ~/.p8fs/server/auth/temp_tokens.json if it exists.
        This allows persistence of generated keys across server restarts in development.

        Returns:
            True if keys were loaded, False otherwise
        """
        storage_dir = Path.home() / ".p8fs" / "server" / "auth"
        token_file = storage_dir / "temp_tokens.json"

        if not token_file.exists():
            return False

        try:
            with open(token_file) as f:
                token_data = json.load(f)

            private_pem = token_data.get("private_key_pem")
            public_pem = token_data.get("public_key_pem")

            if not private_pem or not public_pem:
                logger.warning(f"JWT key file {token_file} missing required keys")
                return False

            # Load private key from PEM
            private_key = serialization.load_pem_private_key(
                private_pem.encode() if isinstance(private_pem, str) else private_pem,
                password=None
            )

            # Load public key from PEM
            public_key = serialization.load_pem_public_key(
                public_pem.encode() if isinstance(public_pem, str) else public_pem
            )

            # Verify keys are EC keys for ES256
            if not isinstance(private_key, ec.EllipticCurvePrivateKey):
                raise ValueError("Private key must be an EC key for ES256 signing")

            # Store loaded keys
            key_id = "file-key"
            self._keys[key_id] = {
                "private_key": private_key,
                "public_key": public_key,
                "created_at": datetime.utcnow(),
                "retired_at": None,
                "public_key_pem": public_pem.encode() if isinstance(public_pem, str) else public_pem,
                "public_key_jwk": self._public_key_to_jwk(public_key, key_id)
            }
            self._current_key_id = key_id
            logger.info(f"JWT Keys: Loaded from FILE {token_file} (development mode)")
            return True

        except Exception as e:
            logger.warning(f"Failed to load JWT keys from file {token_file}: {e}")
            return False

    def _generate_es256_keypair(self) -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
        """Generate ES256 (P-256) keypair.
        
        Implements key generation from:
        Reference: p8fs-auth/docs/authentication-flows.md - "Algorithm: ECDSA with P-256 curve (ES256)"
        
        Returns:
            Tuple of (private_key, public_key) for ES256
        """
        # Generate P-256 keypair
        # Reference: p8fs-auth/docs/authentication-flows.md - "Algorithm: ECDSA with P-256 curve"
        private_key = ec.generate_private_key(
            ec.SECP256R1(),  # P-256 curve
        )
        public_key = private_key.public_key()
        
        return private_key, public_key
    
    def _ensure_current_key(self) -> None:
        """Ensure we have a current signing key.

        Implements key management from:
        Reference: p8fs-auth/docs/authentication-flows.md - "Automatic rotation with zero downtime"

        This method:
        - Checks if current key exists and is not expired
        - Generates new key if needed
        - Maintains old keys for verification
        - Saves generated keys to file for persistence in development
        """
        # Check if we have a current key
        if self._current_key_id:
            current_key = self._keys.get(self._current_key_id)
            if current_key:
                # Check if key needs rotation
                age = datetime.utcnow() - current_key["created_at"]
                if age.days < self.key_rotation_days:
                    return  # Key is still valid

        # Generate new keypair
        private_key, public_key = self._generate_es256_keypair()

        # Serialize to PEM for storage
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        # Create new key entry
        key_id = str(uuid4())
        key_data = {
            "private_key": private_key,
            "public_key": public_key,
            "created_at": datetime.utcnow(),
            "retired_at": None,
            "public_key_pem": public_pem,
            "public_key_jwk": self._public_key_to_jwk(public_key, key_id)
        }

        # Retire old key but keep for validation
        # Reference: p8fs-auth/docs/authentication-flows.md - "Automatic rotation with zero downtime"
        if self._current_key_id:
            old_key = self._keys.get(self._current_key_id)
            if old_key:
                old_key["retired_at"] = datetime.utcnow()

        # Store new key
        self._keys[key_id] = key_data
        self._current_key_id = key_id

        # In development, save to file for persistence across restarts
        # In production, persist to TiKV
        # Reference: p8fs-auth/docs/authentication-flows.md - "Storage: System-wide key in TiKV"
        if not config.is_production:
            self._save_keys_to_file(private_pem.decode('utf-8'), public_pem.decode('utf-8'))

    def _save_keys_to_file(self, private_pem: str, public_pem: str) -> None:
        """Save generated keys to file for development persistence.

        Args:
            private_pem: Private key in PEM format
            public_pem: Public key in PEM format
        """
        try:
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

            logger.info(f"JWT Keys: SAVED to {token_file} for persistence across restarts")
        except Exception as e:
            logger.warning(f"JWT Keys: Failed to save to file: {e}")
    
    def _public_key_to_jwk(self, public_key: ec.EllipticCurvePublicKey, key_id: str) -> dict[str, str]:
        """Convert EC public key to JWK format.
        
        Required for JWKS endpoint and token validation.
        
        Args:
            public_key: EC public key
            key_id: Key identifier
            
        Returns:
            JWK dictionary
        """
        # Extract public key coordinates
        public_numbers = public_key.public_numbers()
        
        # Convert to base64url-encoded values
        x = self._int_to_base64url(public_numbers.x)
        y = self._int_to_base64url(public_numbers.y)
        
        return {
            "kty": "EC",
            "crv": "P-256",
            "x": x,
            "y": y,
            "use": "sig",
            "kid": key_id,
            "alg": "ES256"
        }
    
    def _int_to_base64url(self, value: int) -> str:
        """Convert integer to base64url encoding.
        
        Used for JWK coordinate encoding.
        """
        # P-256 uses 32-byte coordinates
        value_bytes = value.to_bytes(32, byteorder='big')
        return base64.urlsafe_b64encode(value_bytes).decode('ascii').rstrip('=')
    
    async def create_access_token(
        self,
        user_id: str,
        client_id: str,
        scope: list[str],
        device_id: str | None = None,
        additional_claims: dict[str, Any] | None = None
    ) -> str:
        """Create JWT access token.
        
        Implements token creation from:
        Reference: p8fs-api/src/p8fs_api/middleware/auth.py - JWT token structure
        
        Token includes:
        - Standard JWT claims (iss, aud, exp, iat, jti)
        - User identification (sub, user_id)  
        - Client and scope information
        - Optional device binding
        
        Args:
            user_id: User identifier
            client_id: OAuth client ID
            scope: Token permissions
            device_id: Optional device binding
            additional_claims: Extra claims to include
            
        Returns:
            Signed JWT token string
        """
        # Ensure we have a current key
        self._ensure_current_key()
        
        # Get current signing key
        current_key = self._keys[self._current_key_id]
        private_key = current_key["private_key"]
        
        # Build token claims
        # Reference: p8fs-api/src/p8fs_api/middleware/auth.py - Token payload structure
        now = datetime.utcnow()
        claims = {
            # Standard JWT claims
            "iss": self.issuer,  # Issuer
            "aud": self.audience,  # Audience  
            "exp": now + timedelta(seconds=getattr(config, 'auth_access_token_ttl', 3600)),
            "iat": now,  # Issued at
            "jti": str(uuid4()),  # JWT ID for revocation
            
            # User claims
            "sub": user_id,  # Subject
            "user_id": user_id,  # Explicit user ID
            
            # OAuth claims
            "client_id": client_id,
            "scope": " ".join(scope),
            
            # Optional device binding
            "device_id": device_id,
            
            # Key identifier for rotation
            "kid": self._current_key_id
        }
        
        # Add additional claims if provided
        if additional_claims:
            claims.update(additional_claims)
        
        # Sign token with ES256
        # Reference: p8fs-auth/docs/authentication-flows.md - "Algorithm: ECDSA with P-256 curve (ES256)"
        token = jwt.encode(
            claims,
            private_key,
            algorithm=self.algorithm,
            headers={"kid": self._current_key_id}
        )
        
        return token
    
    async def verify_token(
        self,
        token: str,
        verify_audience: bool = True,
        verify_expiration: bool = True
    ) -> dict[str, Any]:
        """Verify and decode JWT token.
        
        Implements token verification from:
        Reference: p8fs-api/src/p8fs_api/middleware/auth.py - verify_jwt_token
        
        Supports:
        - Multiple keys for zero-downtime rotation
        - Audience and expiration validation
        - Signature verification with ES256
        
        Args:
            token: JWT token string
            verify_audience: Whether to check audience claim
            verify_expiration: Whether to check expiration
            
        Returns:
            Decoded token claims
            
        Raises:
            JWTError: Invalid or expired token
        """
        # Get all valid public keys (current and recently retired)
        # Reference: p8fs-auth/docs/authentication-flows.md - "Automatic rotation with zero downtime"
        valid_keys = {}
        
        for key_id, key_data in self._keys.items():
            # Include current key and keys retired within grace period
            if key_data["retired_at"] is None:
                valid_keys[key_id] = key_data["public_key"]
            else:
                # Allow recently retired keys (1 hour grace period)
                retirement_age = datetime.utcnow() - key_data["retired_at"]
                if retirement_age.total_seconds() < 3600:
                    valid_keys[key_id] = key_data["public_key"]
        
        # Try to decode with each valid key
        last_error = None

        for _, public_key in valid_keys.items():
            try:
                # Build options for PyJWT
                decode_options = {
                    "verify_signature": True,
                    "verify_exp": verify_expiration,
                    "verify_aud": verify_audience,
                    "verify_iss": verify_audience
                }

                # Verify token
                claims = jwt.decode(
                    token,
                    public_key,
                    algorithms=[self.algorithm],
                    issuer=self.issuer if verify_audience else None,
                    audience=self.audience if verify_audience else None,
                    options=decode_options
                )

                return claims

            except JWTError as e:
                last_error = e
                continue

        # No valid key could verify the token
        if last_error:
            raise last_error
        else:
            raise JWTError("No valid key found for token verification")
    
    def get_jwks(self) -> dict[str, Any]:
        """Get JSON Web Key Set for public key distribution.
        
        Implements JWKS endpoint data for:
        - Public key distribution to services
        - Token verification by external systems
        - Key rotation transparency
        
        Returns:
            JWKS dictionary with all active public keys
        """
        # Build JWKS with all non-expired keys
        keys = []
        
        for _, key_data in self._keys.items():
            # Include current and recently retired keys
            if key_data["retired_at"] is None:
                keys.append(key_data["public_key_jwk"])
            else:
                # Include recently retired keys
                retirement_age = datetime.utcnow() - key_data["retired_at"]
                if retirement_age.total_seconds() < 3600:  # 1 hour grace
                    keys.append(key_data["public_key_jwk"])
        
        return {"keys": keys}
    
    async def rotate_keys(self) -> None:
        """Force key rotation.
        
        Implements manual key rotation from:
        Reference: p8fs-auth/docs/authentication-flows.md - "Automatic rotation with zero downtime"
        
        Used for:
        - Scheduled rotation
        - Security incident response
        - Manual rotation triggers
        """
        # Mark current key as retired
        if self._current_key_id:
            current_key = self._keys.get(self._current_key_id)
            if current_key:
                current_key["retired_at"] = datetime.utcnow()
                self._current_key_id = None
        
        # Generate new key
        self._ensure_current_key()
        
        # Clean up old keys (keep for 1 day after retirement)
        cutoff = datetime.utcnow() - timedelta(days=1)
        keys_to_remove = []
        
        for key_id, key_data in self._keys.items():
            if key_data["retired_at"] and key_data["retired_at"] < cutoff:
                keys_to_remove.append(key_id)
        
        for key_id in keys_to_remove:
            del self._keys[key_id]