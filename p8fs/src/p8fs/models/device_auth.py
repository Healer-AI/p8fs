"""Device authorization flow models for temporary storage.

These models handle the device authorization flow where:
1. Desktop app requests device code (creates PendingDeviceRequest)
2. Mobile user approves via QR/user code (updates approved status)
3. Desktop app polls and gets access token (consumes request)

The requests are stored temporarily in KV storage with TTL.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .base import AbstractModel


class DeviceAuthStatus(str, Enum):
    """Status of device authorization request."""
    
    PENDING = "pending"
    APPROVED = "approved" 
    EXPIRED = "expired"
    CONSUMED = "consumed"  # Token retrieved, request cleaned up


class PendingDeviceRequest(AbstractModel):
    """Temporary device authorization request stored in KV storage.
    
    This model represents the temporary state between device code generation
    and device approval in the OAuth device flow.
    """
    
    device_code: str = Field(..., description="Long secure device code for polling")
    user_code: str = Field(..., description="Short human-friendly code for mobile entry")
    client_id: str = Field(..., description="OAuth client requesting authorization")
    scope: List[str] = Field(default_factory=lambda: ["read", "write"], description="Requested OAuth scopes")
    
    # Request metadata
    status: DeviceAuthStatus = Field(default=DeviceAuthStatus.PENDING, description="Current request status")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Request creation time")
    expires_at: datetime = Field(..., description="Request expiration time")
    
    # Approval data (set when mobile user approves)
    approved_at: Optional[datetime] = Field(None, description="Approval timestamp")
    approved_by_tenant: Optional[str] = Field(None, description="Tenant ID that approved this request")
    access_token: Optional[str] = Field(None, description="Generated access token after approval")
    
    # Additional metadata
    client_info: Dict[str, Any] = Field(default_factory=dict, description="Client application metadata")
    approval_metadata: Dict[str, Any] = Field(default_factory=dict, description="Approval context metadata")

    model_config = {
        "table_name": "kv_storage",  # Stored in KV storage, not as regular table
        "description": "Temporary device authorization requests with TTL"
    }
        
    def is_expired(self) -> bool:
        """Check if request has expired."""
        return datetime.utcnow() > self.expires_at
    
    def is_approved(self) -> bool:
        """Check if request has been approved."""
        return self.status == DeviceAuthStatus.APPROVED and self.approved_at is not None
    
    def can_be_consumed(self) -> bool:
        """Check if request can be consumed (approved and has token)."""
        return (
            self.is_approved() 
            and self.access_token is not None 
            and not self.is_expired()
        )
    
    def approve(self, tenant_id: str, access_token: str, metadata: Dict[str, Any] = None) -> None:
        """Mark request as approved by tenant."""
        self.status = DeviceAuthStatus.APPROVED
        self.approved_at = datetime.utcnow()
        self.approved_by_tenant = tenant_id
        self.access_token = access_token
        if metadata:
            self.approval_metadata.update(metadata)
    
    def consume(self) -> str:
        """Mark request as consumed and return access token."""
        if not self.can_be_consumed():
            raise ValueError("Request cannot be consumed")
        
        self.status = DeviceAuthStatus.CONSUMED
        return self.access_token
    
    def get_storage_key(self) -> str:
        """Get KV storage key for this request."""
        return f"device_auth:{self.device_code}"
    
    def get_user_code_key(self) -> str:
        """Get KV storage key for user code lookup."""
        return f"user_code:{self.user_code}"
    
    @classmethod
    def create_pending_request(
        cls,
        device_code: str,
        user_code: str, 
        client_id: str,
        scope: List[str] = None,
        ttl_seconds: int = 600,
        client_info: Dict[str, Any] = None
    ) -> "PendingDeviceRequest":
        """Create a new pending device authorization request.
        
        Args:
            device_code: Secure device code for polling
            user_code: Human-friendly code for mobile approval
            client_id: OAuth client requesting authorization
            scope: Requested OAuth scopes
            ttl_seconds: Time to live in seconds (default 10 minutes)
            client_info: Additional client metadata
            
        Returns:
            New PendingDeviceRequest instance
        """
        from datetime import timedelta
        
        return cls(
            device_code=device_code,
            user_code=user_code,
            client_id=client_id,
            scope=scope or ["read", "write"],
            expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds),
            client_info=client_info or {}
        )


# Utility functions for KV storage operations

async def store_pending_request(kv_provider, request: PendingDeviceRequest, ttl_seconds: int = 600) -> bool:
    """Store pending device request in KV storage."""
    try:
        # Store by device_code (primary lookup)
        success = await kv_provider.put(
            request.get_storage_key(),
            request.model_dump(),
            ttl_seconds=ttl_seconds
        )
        
        if success:
            # Also store user_code -> device_code mapping for mobile lookup
            await kv_provider.put(
                request.get_user_code_key(),
                {"device_code": request.device_code},
                ttl_seconds=ttl_seconds
            )
        
        return success
    except Exception:
        return False


async def get_pending_request_by_device_code(kv_provider, device_code: str) -> Optional[PendingDeviceRequest]:
    """Get pending device request by device code."""
    try:
        data = await kv_provider.get(f"device_auth:{device_code}")
        if data:
            return PendingDeviceRequest(**data)
        return None
    except Exception:
        return None


async def get_pending_request_by_user_code(kv_provider, user_code: str) -> Optional[PendingDeviceRequest]:
    """Get pending device request by user code."""
    try:
        # First get device_code from user_code mapping
        mapping = await kv_provider.get(f"user_code:{user_code}")
        if not mapping:
            return None
        
        # Then get full request by device_code
        return await get_pending_request_by_device_code(kv_provider, mapping["device_code"])
    except Exception:
        return None


async def update_pending_request(kv_provider, request: PendingDeviceRequest, ttl_seconds: int = 600) -> bool:
    """Update pending device request in KV storage."""
    return await store_pending_request(kv_provider, request, ttl_seconds)


# Delete functionality removed - keys expire via TTL