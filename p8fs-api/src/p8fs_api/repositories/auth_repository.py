"""Auth repository implementation using p8fs SystemRepository with Tenant model only."""

from typing import Any

from p8fs_auth.models.repository import AbstractRepository, Tenant
from p8fs_cluster.logging.setup import get_logger
from p8fs.models.p8 import Tenant as CoreTenant
from p8fs.repository.SystemRepository import SystemRepository

logger = get_logger(__name__)


class P8FSAuthRepository(AbstractRepository):
    """Simple tenant-based repository using only p8fs SystemRepository."""
    
    def __init__(self):
        """Initialize with p8fs SystemRepository for Tenant operations only."""
        # Use SystemRepository for cross-tenant auth operations (bypasses tenant scoping)
        self.tenant_repo = SystemRepository(CoreTenant)
        
        # Get KV provider for temporary storage
        from p8fs.providers import get_provider
        self._provider = get_provider()
        self._kv = self._provider.kv if hasattr(self._provider, 'kv') else None
        
        # Fallback in-memory storage if KV not available
        self._device_authorizations: dict[str, dict[str, Any]] = {}
        
    async def get_tenant_by_id(self, tenant_id: str) -> Tenant | None:
        """Get tenant by tenant_id using SystemRepository."""
        try:
            # Use select method with tenant_id filter (tenant_id is not the database primary key)
            results = await self.tenant_repo.select(filters={"tenant_id": tenant_id}, limit=1)
            
            if results:
                core_tenant = results[0]
                return Tenant(
                    tenant_id=core_tenant.tenant_id,
                    email=core_tenant.email,
                    public_key=core_tenant.public_key,
                    created_at=core_tenant.created_at,
                    metadata=core_tenant.metadata
                )
            return None
        except Exception as e:
            logger.error(f"Database error getting tenant by id {tenant_id}: {e}", exc_info=True)
            # Don't return None for database errors - let them propagate
            # This helps distinguish between "not found" and "database down"
            raise RuntimeError(f"Database error retrieving tenant: {e}") from e
    
    async def get_tenant_by_email(self, email: str) -> Tenant | None:
        """Get tenant by email using SystemRepository."""
        try:
            # Use select method with filters dict
            results = await self.tenant_repo.select(filters={"email": email}, limit=1)
            
            if results:
                core_tenant = results[0]
                return Tenant(
                    tenant_id=core_tenant.tenant_id,
                    email=core_tenant.email,
                    public_key=core_tenant.public_key,
                    created_at=core_tenant.created_at,
                    metadata=core_tenant.metadata
                )
            return None
        except Exception as e:
            logger.error(f"Database error getting tenant by email {email}: {e}", exc_info=True)
            # Don't return None for database errors - let them propagate
            # This helps distinguish between "not found" and "database down"
            raise RuntimeError(f"Database error retrieving tenant: {e}") from e
    
    async def create_tenant(self, tenant: Tenant) -> Tenant:
        """Create tenant using SystemRepository and initialize with sample data."""
        try:
            # Convert to core tenant model
            # Generate UUID for id field from tenant identifier
            from p8fs.utils import make_uuid
            tenant_uuid = make_uuid(tenant.tenant_id)

            core_tenant = CoreTenant(
                id=tenant_uuid,
                tenant_id=tenant.tenant_id,
                email=tenant.email,
                public_key=tenant.public_key,
                device_ids=[],
                metadata=tenant.metadata,
                active=True
            )

            # Save using p8fs upsert
            result = await self.tenant_repo.upsert(core_tenant)
            if not result.get("success"):
                raise ValueError("Failed to create tenant")

            # Initialize sample data for new tenant (async, non-blocking)
            try:
                from p8fs.utils.sample_data import initialize_tenant_sample_data
                sample_result = await initialize_tenant_sample_data(tenant.tenant_id)

                if sample_result.get("success"):
                    logger.info(
                        f"Sample data initialized for new tenant {tenant.tenant_id}: "
                        f"{sample_result.get('moments_created', 0)} moments, "
                        f"{sample_result.get('sessions_created', 0)} sessions"
                    )
                else:
                    logger.warning(
                        f"Failed to initialize sample data for tenant {tenant.tenant_id}: "
                        f"{sample_result.get('error', 'unknown error')}"
                    )
            except Exception as sample_error:
                # Don't fail tenant creation if sample data fails
                logger.warning(
                    f"Sample data initialization failed for tenant {tenant.tenant_id}: {sample_error}"
                )

            return tenant
        except Exception as e:
            logger.error(f"Error creating tenant: {e}")
            raise
    
    async def update_tenant(self, tenant: Tenant) -> Tenant:
        """Update tenant using SystemRepository."""
        try:
            # Need to get the existing tenant to preserve the ID
            existing_results = await self.tenant_repo.select(filters={"tenant_id": tenant.tenant_id}, limit=1)
            if not existing_results:
                raise ValueError(f"Tenant not found: {tenant.tenant_id}")
            
            existing_tenant = existing_results[0]
            
            # Convert to core tenant for update
            # Generate UUID for id field from tenant identifier
            from p8fs.utils import make_uuid
            tenant_uuid = make_uuid(tenant.tenant_id)
            
            core_tenant = CoreTenant(
                id=tenant_uuid,
                tenant_id=tenant.tenant_id,
                email=tenant.email,
                public_key=tenant.public_key,
                device_ids=existing_tenant.device_ids or [],
                metadata=tenant.metadata,
                active=True
            )
            
            # Save updates using upsert
            result = await self.tenant_repo.upsert(core_tenant)
            if not result.get("success"):
                raise ValueError("Failed to update tenant")
            
            return tenant
        except Exception as e:
            logger.error(f"Error updating tenant: {e}")
            raise

    # Device operations implemented via tenant metadata
    async def create_device(self, device) -> None:
        """Store device in tenant metadata."""
        try:
            # Get or create tenant for this email
            tenant = await self.get_tenant_by_email(device.email)
            if not tenant:
                # Create new tenant for this email
                import hashlib
                email_hash = hashlib.sha256(device.email.encode()).hexdigest()[:16]
                tenant_id = f"tenant-{email_hash}"
                
                tenant = Tenant(
                    tenant_id=tenant_id,
                    email=device.email,
                    public_key=device.public_key,
                    metadata={"devices": {}}
                )
            
            # Store device info in tenant metadata
            devices = tenant.metadata.get("devices", {})
            devices[device.device_id] = {
                "device_id": device.device_id,
                "public_key": device.public_key,
                "email": device.email,
                "device_name": device.device_name,
                "trust_level": device.trust_level.value if hasattr(device.trust_level, 'value') else str(device.trust_level),
                "challenge_data": device.challenge_data,
                "created_at": device.created_at.isoformat() if device.created_at else None,
                "last_used_at": device.last_used_at.isoformat() if device.last_used_at else None
            }
            
            tenant.metadata["devices"] = devices
            await self.update_tenant(tenant)
            
        except Exception as e:
            logger.error(f"Error creating device: {e}")
            raise
    
    async def get_device(self, device_id: str, tenant_id: str = None):
        """Get device from specific tenant's metadata by device_id."""
        try:
            if not tenant_id:
                # Legacy call without tenant_id - this shouldn't happen in production
                logger.warning(f"get_device called without tenant_id for device {device_id}")
                return None
            
            # Get the specific tenant
            tenant = await self.get_tenant_by_id(tenant_id)
            if not tenant:
                logger.warning(f"Tenant not found: {tenant_id}")
                return None
            
            # Check if this tenant has the device in metadata
            devices = tenant.metadata.get("devices", {})
            if device_id not in devices:
                logger.debug(f"Device {device_id} not found in tenant {tenant_id}")
                return None
            
            device_data = devices[device_id]
            
            # Convert back to Device object
            from p8fs_auth.models.auth import Device, DeviceTrustLevel
            from datetime import datetime
            
            # Parse trust level
            trust_level_str = device_data.get("trust_level", "unverified")
            try:
                trust_level = DeviceTrustLevel(trust_level_str)
            except (KeyError, ValueError):
                trust_level = DeviceTrustLevel.UNVERIFIED
            
            # Parse timestamps
            created_at = None
            if device_data.get("created_at"):
                created_at = datetime.fromisoformat(device_data["created_at"])
            
            last_used_at = None 
            if device_data.get("last_used_at"):
                last_used_at = datetime.fromisoformat(device_data["last_used_at"])
            
            return Device(
                device_id=device_data["device_id"],
                tenant_id=tenant.tenant_id,
                email=device_data["email"],
                device_name=device_data["device_name"],
                public_key=device_data["public_key"],
                trust_level=trust_level,
                challenge_data=device_data.get("challenge_data"),
                created_at=created_at,
                last_seen=last_used_at
            )
            
        except Exception as e:
            logger.error(f"Database error getting device {device_id}: {e}", exc_info=True)
            # Don't return None for database errors - let them propagate  
            raise RuntimeError(f"Database error retrieving device: {e}") from e
    
    async def update_device(self, device) -> None:
        """Update device in tenant metadata."""
        try:
            # Get tenant by email
            tenant = await self.get_tenant_by_email(device.email)
            if not tenant:
                logger.warning(f"No tenant found for device email: {device.email}")
                return
            
            # Update device in metadata
            devices = tenant.metadata.get("devices", {})
            if device.device_id in devices:
                devices[device.device_id].update({
                    "trust_level": device.trust_level.value if hasattr(device.trust_level, 'value') else str(device.trust_level),
                    "challenge_data": device.challenge_data,
                    "last_used_at": device.last_used_at.isoformat() if device.last_used_at else None
                })
                tenant.metadata["devices"] = devices
                await self.update_tenant(tenant)
            else:
                logger.warning(f"Device not found in tenant metadata: {device.device_id}")
                
        except Exception as e:
            logger.error(f"Error updating device: {e}")
            raise

    # AbstractRepository interface - use KV storage for temporary data
    async def store(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> bool:
        """Store temporary data in KV storage."""
        if self._kv:
            try:
                return await self._kv.put(key, value, ttl_seconds)
            except Exception as e:
                logger.error(f"Error storing in KV: {e}")
                return False
        else:
            # Fallback to in-memory storage
            self._device_authorizations[key] = value
            return True
    
    # Add KV-compatible methods for device_auth module
    async def put(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> bool:
        """KV-compatible put method that delegates to store."""
        return await self.store(key, value, ttl_seconds)
    
    async def get(self, key: str) -> dict[str, Any] | None:
        """KV-compatible get method that delegates to retrieve."""
        # Special handling for user_code lookups
        if key.startswith("user_code:"):
            user_code = key[10:]  # Remove "user_code:" prefix
            
            # Try as-is first
            result = await self.retrieve(key)
            if result:
                return result
                
            # If not found and user code doesn't have a dash, try adding one
            if "-" not in user_code and len(user_code) == 8:
                # Try common format XXXX-YYYY
                formatted_key = f"user_code:{user_code[:4]}-{user_code[4:]}"
                result = await self.retrieve(formatted_key)
                if result:
                    return result
        
        # For all other keys, just retrieve normally
        return await self.retrieve(key)
    
    async def retrieve(self, key: str) -> dict[str, Any] | None:
        """Retrieve temporary data from KV storage."""
        if self._kv:
            try:
                return await self._kv.get(key)
            except Exception as e:
                logger.error(f"Error retrieving from KV: {e}")
                return None
        else:
            # Fallback to in-memory storage
            return self._device_authorizations.get(key)
    
    async def delete(self, key: str) -> bool:
        """Delete temporary data from KV storage."""
        if self._kv:
            try:
                return await self._kv.delete(key)
            except Exception as e:
                logger.error(f"Error deleting from KV: {e}")
                return False
        else:
            # Fallback to in-memory storage
            if key in self._device_authorizations:
                del self._device_authorizations[key]
                return True
            return False
    
    async def query(self, prefix: str, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Query temporary data from KV storage."""
        if self._kv:
            try:
                results = await self._kv.scan(prefix, limit)
                # Apply filters if provided
                if filters:
                    filtered = []
                    for item in results:
                        value = item.get("value", {})
                        match = all(value.get(k) == v for k, v in filters.items())
                        if match:
                            filtered.append(value)
                    return filtered
                return [item.get("value", {}) for item in results]
            except Exception as e:
                logger.error(f"Error querying KV: {e}")
                return []
        else:
            # Fallback to in-memory storage
            results = []
            for key, value in self._device_authorizations.items():
                if key.startswith(prefix):
                    if filters:
                        match = all(value.get(k) == v for k, v in filters.items())
                        if match:
                            results.append(value)
                    else:
                        results.append(value)
                    if len(results) >= limit:
                        break
            return results
    
    async def update(self, key: str, updates: dict[str, Any]) -> bool:
        """Update temporary data in KV storage."""
        # Retrieve, update, and store back
        value = await self.retrieve(key)
        if value:
            value.update(updates)
            return await self.store(key, value)
        return False
    
    # Device authorization methods using KV storage
    async def store_device_authorization(self, user_code: str, device_auth: dict[str, Any]) -> bool:
        """Store device authorization request in KV storage."""
        # Use the same storage method as p8fs.models.device_auth
        from p8fs.models.device_auth import PendingDeviceRequest, store_pending_request
        from datetime import datetime
        
        # Parse datetime strings if present
        created_at = device_auth.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        expires_at = device_auth.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        
        # Create PendingDeviceRequest from dict
        pending_request = PendingDeviceRequest(
            device_code=device_auth.get("device_code"),
            user_code=device_auth.get("user_code"),
            client_id=device_auth.get("client_id"),
            scope=device_auth.get("scope", ["read", "write"]),
            status=device_auth.get("status", "pending"),
            created_at=created_at,
            expires_at=expires_at,
            client_info=device_auth.get("client_info", {})
        )
        
        # Store using the proper method which handles both keys
        success = await store_pending_request(self, pending_request, ttl_seconds=600)
        if success:
            logger.info(f"Stored device authorization for user code: {user_code} in KV storage")
        return success
    
    async def get_device_authorization(self, user_code: str) -> dict[str, Any] | None:
        """Get device authorization by user code from KV storage."""
        # Use the same lookup method as p8fs.models.device_auth
        from p8fs.models.device_auth import get_pending_request_by_user_code
        
        # Try with the user code as-is first
        pending_request = await get_pending_request_by_user_code(self, user_code)
        
        # If not found and user code doesn't have a dash, try adding one
        if not pending_request and "-" not in user_code and len(user_code) == 8:
            # Try common format XXXX-YYYY
            formatted_code = f"{user_code[:4]}-{user_code[4:]}"
            pending_request = await get_pending_request_by_user_code(self, formatted_code)
        
        if pending_request:
            logger.info(f"Found device authorization for user code: {user_code} in KV storage")
            return pending_request.model_dump()
        else:
            logger.warning(f"No device authorization found for user code: {user_code} in KV storage")
            return None
    
    async def update_device_authorization(self, user_code: str, updates: dict[str, Any]) -> bool:
        """Update device authorization request in KV storage."""
        # Use the same update method as p8fs.models.device_auth
        from p8fs.models.device_auth import get_pending_request_by_user_code, update_pending_request
        
        # Get existing request - try as-is first
        pending_request = await get_pending_request_by_user_code(self, user_code)
        
        # If not found and user code doesn't have a dash, try adding one
        if not pending_request and "-" not in user_code and len(user_code) == 8:
            formatted_code = f"{user_code[:4]}-{user_code[4:]}"
            pending_request = await get_pending_request_by_user_code(self, formatted_code)
        
        if pending_request:
            # Update fields
            for key, value in updates.items():
                if hasattr(pending_request, key):
                    setattr(pending_request, key, value)
            
            # Store back using proper method
            success = await update_pending_request(self, pending_request, ttl_seconds=600)
            if success:
                logger.info(f"Updated device authorization for user code: {user_code} in KV storage")
            return success
        logger.warning(f"Cannot update - no device authorization found for user code: {user_code}")
        return False
    
    async def delete_device_authorization(self, user_code: str) -> bool:
        """Delete device authorization request from KV storage."""
        # Get the pending request to find device_code
        from p8fs.models.device_auth import get_pending_request_by_user_code
        
        # Try as-is first
        pending_request = await get_pending_request_by_user_code(self, user_code)
        
        # If not found and user code doesn't have a dash, try adding one
        if not pending_request and "-" not in user_code and len(user_code) == 8:
            formatted_code = f"{user_code[:4]}-{user_code[4:]}"
            pending_request = await get_pending_request_by_user_code(self, formatted_code)
        
        if pending_request:
            # Delete both keys
            device_key = pending_request.get_storage_key()
            user_key = pending_request.get_user_code_key()
            
            # Delete device code key
            device_deleted = await self.delete(device_key)
            # Delete user code mapping
            user_deleted = await self.delete(user_key)
            
            success = device_deleted and user_deleted
            if success:
                logger.info(f"Deleted device authorization for user code: {user_code} from KV storage")
            return success
        
        logger.warning(f"Cannot delete - no device authorization found for user code: {user_code}")
        return False

    # Token repository methods (for AuthenticationService compatibility)
    async def create_auth_token(self, auth_token) -> None:
        """Store auth token (currently no-op as we use stateless JWTs)."""
        # For stateless JWT tokens, we don't need to store them in the repository
        # The token contains all necessary information and is validated via signature
        logger.debug(f"Auth token created (stateless JWT): {getattr(auth_token, 'token_id', 'unknown')}")
        pass

    async def get_auth_token_by_value(self, token_value: str):
        """Get auth token by value (currently no-op as we use stateless JWTs)."""
        # For stateless JWT tokens, we don't store them in the repository
        # Token validation is done via signature verification, not database lookup
        logger.debug(f"Auth token lookup requested (stateless JWT): {token_value[:20]}...")
        return None

    async def get_device_token_by_user_code(self, user_code: str):
        """Get device authorization by user code.
        
        This method is for compatibility with the device service which expects
        to find device authorizations by user code.
        """
        # Just return the device authorization data
        # The device service will handle it appropriately
        return await self.get_device_authorization(user_code)

    async def create_login_event(self, login_event) -> None:
        """Store login event (currently no-op for development)."""
        # In production, this would store login events for auditing
        # For now, just log the event
        logger.info(f"Login event: user={getattr(login_event, 'user_id', 'unknown')}, "
                   f"device={getattr(login_event, 'device_id', 'unknown')}, "
                   f"success={getattr(login_event, 'success', False)}")
        pass