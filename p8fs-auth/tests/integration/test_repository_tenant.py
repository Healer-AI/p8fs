"""Integration test for repository with tenant operations."""

import pytest

from p8fs_auth.models.repository import Tenant, set_repository


# Mock repository for testing
class MockRepository:
    """Simple mock repository for testing."""
    
    def __init__(self):
        self.storage = {}
        self.tenants = {}
    
    async def get_tenant_by_id(self, tenant_id: str) -> Tenant:
        return self.tenants.get(tenant_id)
    
    async def get_tenant_by_email(self, email: str) -> Tenant:
        for tenant in self.tenants.values():
            if tenant.email == email:
                return tenant
        return None
    
    async def create_tenant(self, tenant: Tenant) -> Tenant:
        self.tenants[tenant.tenant_id] = tenant
        return tenant
    
    async def update_tenant(self, tenant: Tenant) -> Tenant:
        if tenant.tenant_id in self.tenants:
            self.tenants[tenant.tenant_id] = tenant
        return tenant
    
    async def store(self, key: str, value: dict, ttl_seconds: int = None) -> bool:
        self.storage[key] = value
        return True
    
    async def retrieve(self, key: str) -> dict:
        return self.storage.get(key)
    
    async def delete(self, key: str) -> bool:
        if key in self.storage:
            del self.storage[key]
            return True
        return False
    
    async def query(self, prefix: str, filters: dict = None, limit: int = 100) -> list:
        results = []
        for key, value in self.storage.items():
            if key.startswith(prefix):
                if filters:
                    match = all(value.get(k) == v for k, v in filters.items())
                    if match:
                        results.append(value)
                else:
                    results.append(value)
        return results[:limit]
    
    async def update(self, key: str, updates: dict) -> bool:
        if key in self.storage:
            self.storage[key].update(updates)
            return True
        return False


@pytest.fixture
def mock_repository():
    """Set up mock repository."""
    repo = MockRepository()
    set_repository(repo)
    return repo


@pytest.mark.asyncio
async def test_tenant_operations(mock_repository):
    """Test basic tenant operations."""
    # Create tenant
    tenant = Tenant(
        tenant_id="test123",
        email="test@example.com",
        public_key="test_public_key_base64"
    )
    
    saved = await mock_repository.create_tenant(tenant)
    assert saved.tenant_id == "test123"
    assert saved.email == "test@example.com"
    
    # Get by ID
    retrieved = await mock_repository.get_tenant_by_id("test123")
    assert retrieved.tenant_id == "test123"
    assert retrieved.email == "test@example.com"
    
    # Get by email
    by_email = await mock_repository.get_tenant_by_email("test@example.com")
    assert by_email.tenant_id == "test123"


@pytest.mark.asyncio
async def test_storage_operations(mock_repository):
    """Test generic storage operations."""
    # Store and retrieve
    data = {"type": "test", "value": 42}
    success = await mock_repository.store("test:key1", data)
    assert success
    
    retrieved = await mock_repository.retrieve("test:key1")
    assert retrieved == data
    
    # Update
    await mock_repository.update("test:key1", {"value": 100})
    retrieved = await mock_repository.retrieve("test:key1")
    assert retrieved["value"] == 100
    
    # Delete
    success = await mock_repository.delete("test:key1")
    assert success
    retrieved = await mock_repository.retrieve("test:key1")
    assert retrieved is None