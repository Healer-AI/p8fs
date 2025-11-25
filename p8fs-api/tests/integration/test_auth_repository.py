"""Integration test for auth repository with tenant operations."""

from datetime import datetime

import pytest

# Import only what we need directly
from p8fs_api.repositories.auth_repository import P8FSAuthRepository


# Define Tenant locally to avoid import issues
class Tenant:
    def __init__(self, tenant_id: str, email: str, public_key: str, **kwargs):
        self.tenant_id = tenant_id
        self.email = email
        self.public_key = public_key
        self.created_at = kwargs.get('created_at', datetime.utcnow())
        self.metadata = kwargs.get('metadata', {})


@pytest.fixture
async def auth_repository():
    """Create auth repository for testing."""
    repo = P8FSAuthRepository()
    return repo


@pytest.mark.asyncio
async def test_tenant_create_and_retrieve(auth_repository):
    """Test creating and retrieving a tenant."""
    # Create test tenant
    tenant = Tenant(
        tenant_id="test_tenant_123",
        email="test@example.com",
        public_key="ed25519_public_key_base64_encoded_here",
        metadata={"test": True, "source": "integration_test"}
    )
    
    # Save tenant
    saved_tenant = await auth_repository.create_tenant(tenant)
    assert saved_tenant.tenant_id == tenant.tenant_id
    assert saved_tenant.email == tenant.email
    assert saved_tenant.public_key == tenant.public_key
    assert saved_tenant.created_at is not None
    
    # Retrieve by ID
    retrieved = await auth_repository.get_tenant_by_id("test_tenant_123")
    assert retrieved is not None
    assert retrieved.tenant_id == tenant.tenant_id
    assert retrieved.email == tenant.email
    assert retrieved.public_key == tenant.public_key
    
    # Retrieve by email
    retrieved_by_email = await auth_repository.get_tenant_by_email("test@example.com")
    assert retrieved_by_email is not None
    assert retrieved_by_email.tenant_id == tenant.tenant_id
    assert retrieved_by_email.email == tenant.email


@pytest.mark.asyncio
async def test_tenant_update(auth_repository):
    """Test updating a tenant."""
    # Create test tenant
    tenant = Tenant(
        tenant_id="test_update_tenant",
        email="update@example.com",
        public_key="original_public_key",
        metadata={"version": 1}
    )
    
    # Save tenant
    saved = await auth_repository.create_tenant(tenant)
    
    # Update tenant
    saved.public_key = "updated_public_key"
    saved.metadata = {"version": 2, "updated": True}
    
    updated = await auth_repository.update_tenant(saved)
    assert updated.public_key == "updated_public_key"
    assert updated.metadata["version"] == 2
    assert updated.metadata["updated"] is True
    
    # Verify update persisted
    retrieved = await auth_repository.get_tenant_by_id("test_update_tenant")
    assert retrieved.public_key == "updated_public_key"
    assert retrieved.metadata["version"] == 2


@pytest.mark.asyncio
async def test_generic_storage_operations(auth_repository):
    """Test generic key-value storage operations."""
    # Test store and retrieve
    test_data = {
        "type": "device_token",
        "device_code": "ABC123",
        "user_code": "WXYZ-1234",
        "expires_at": datetime.utcnow().isoformat()
    }
    
    key = "device_token:ABC123"
    
    # Store data
    success = await auth_repository.store(key, test_data)
    assert success is True
    
    # Retrieve data
    retrieved = await auth_repository.retrieve(key)
    assert retrieved is not None
    assert retrieved["device_code"] == "ABC123"
    assert retrieved["user_code"] == "WXYZ-1234"
    
    # Update data
    updates = {"approved": True, "user_id": "user_123"}
    success = await auth_repository.update(key, updates)
    assert success is True
    
    # Verify update
    retrieved = await auth_repository.retrieve(key)
    assert retrieved["approved"] is True
    assert retrieved["user_id"] == "user_123"
    
    # P8FS is append-only - no delete operations
    # Data should persist after updates


@pytest.mark.asyncio
async def test_query_operations(auth_repository):
    """Test query operations with prefix scanning."""
    # Store multiple items with same prefix
    prefix = "auth_token:"
    
    for i in range(5):
        key = f"{prefix}token_{i}"
        data = {
            "token_id": f"token_{i}",
            "user_id": f"user_{i % 2}",  # Alternate between user_0 and user_1
            "scope": ["read", "write"] if i % 2 == 0 else ["read"]
        }
        await auth_repository.store(key, data)
    
    # Query all with prefix
    results = await auth_repository.query(prefix)
    assert len(results) >= 5
    
    # Query with filter
    filtered = await auth_repository.query(prefix, filters={"user_id": "user_0"})
    assert len(filtered) >= 2
    assert all(item["user_id"] == "user_0" for item in filtered)
    
    # Cleanup
    for i in range(5):
        await auth_repository.delete(f"{prefix}token_{i}")


@pytest.mark.asyncio
async def test_tenant_not_found(auth_repository):
    """Test handling of non-existent tenants."""
    # Try to get non-existent tenant by ID
    tenant = await auth_repository.get_tenant_by_id("non_existent_id")
    assert tenant is None
    
    # Try to get non-existent tenant by email
    tenant = await auth_repository.get_tenant_by_email("nonexistent@example.com")
    assert tenant is None
    
    # Try to update non-existent tenant
    fake_tenant = Tenant(
        tenant_id="fake_tenant",
        email="fake@example.com",
        public_key="fake_key"
    )
    
    with pytest.raises(ValueError, match="not found"):
        await auth_repository.update_tenant(fake_tenant)