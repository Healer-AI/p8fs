"""Abstract repository interface for auth module."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class Tenant:
    """Tenant model for auth operations."""
    def __init__(self, tenant_id: str, email: str, public_key: str, **kwargs):
        self.tenant_id = tenant_id
        self.email = email
        self.public_key = public_key
        self.created_at = kwargs.get('created_at', datetime.utcnow())
        self.metadata = kwargs.get('metadata', {})


class AbstractRepository(ABC):
    """Repository interface for auth module - wraps p8fs repository."""
    
    # Tenant operations
    @abstractmethod
    async def get_tenant_by_id(self, tenant_id: str) -> Tenant | None:
        """Get tenant by ID."""
        pass
    
    @abstractmethod
    async def get_tenant_by_email(self, email: str) -> Tenant | None:
        """Get tenant by email."""
        pass
    
    @abstractmethod
    async def create_tenant(self, tenant: Tenant) -> Tenant:
        """Create a new tenant."""
        pass
    
    @abstractmethod
    async def update_tenant(self, tenant: Tenant) -> Tenant:
        """Update tenant information."""
        pass

    # Generic storage operations for auth entities
    @abstractmethod
    async def store(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> bool:
        """Store a value with optional TTL."""
        pass
    
    @abstractmethod
    async def retrieve(self, key: str) -> dict[str, Any] | None:
        """Retrieve a value by key."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a value by key."""
        pass
    
    @abstractmethod
    async def query(self, prefix: str, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Query values by key prefix with optional filters."""
        pass
    
    @abstractmethod
    async def update(self, key: str, updates: dict[str, Any]) -> bool:
        """Update specific fields of a stored value."""
        pass


# Global repository instance holder
_repository_instance: AbstractRepository | None = None


def set_repository(repository: AbstractRepository) -> None:
    """Set the global repository instance."""
    global _repository_instance
    _repository_instance = repository


def get_repository() -> AbstractRepository:
    """Get the global repository instance."""
    if _repository_instance is None:
        raise RuntimeError("Repository not initialized. Call set_repository() first.")
    return _repository_instance


# For compatibility with existing code
def get_oauth_repository() -> AbstractRepository:
    """Get repository (compatibility wrapper)."""
    return get_repository()


def get_token_repository() -> AbstractRepository:
    """Get repository (compatibility wrapper)."""
    return get_repository()


def get_auth_repository() -> AbstractRepository:
    """Get repository (compatibility wrapper)."""
    return get_repository()


def get_login_event_repository() -> AbstractRepository:
    """Get repository (compatibility wrapper)."""
    return get_repository()