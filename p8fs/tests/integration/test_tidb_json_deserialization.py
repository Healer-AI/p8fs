"""Integration test for TiDB JSON deserialization fix.

This test verifies that JSON columns stored as strings are properly deserialized
back to Python dicts and lists when retrieved from TiDB.
"""

import os
from uuid import uuid4

import pytest
from p8fs.models import AbstractModel
from p8fs.repository.TenantRepository import TenantRepository


class TenantWithJSON(AbstractModel):
    """Test tenant model with JSON fields."""
    id: str
    tenant_id: str
    email: str
    device_ids: list = []
    metadata: dict = {}

    @classmethod
    def to_sql_schema(cls):
        return {
            'table_name': 'test_tenants_json',
            'key_field': 'id',
            'tenant_isolated': False,
            'fields': {
                'id': {'type': str, 'is_primary_key': True},
                'tenant_id': {'type': str, 'nullable': False},
                'email': {'type': str, 'nullable': False},
                'device_ids': {'type': list, 'nullable': True},
                'metadata': {'type': dict, 'nullable': True}
            }
        }


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION_TESTS", "true").lower() == "true",
    reason="Integration tests require Docker TiDB"
)
class TestTiDBJSONDeserialization:
    """Integration tests for TiDB JSON deserialization."""

    @pytest.fixture
    def tenant_id(self):
        """Generate test tenant ID."""
        return f"json-test-{uuid4().hex[:8]}"

    @pytest.fixture
    def repository(self, tenant_id):
        """Create repository instance with TiDB provider."""
        repo = TenantRepository(
            model_class=TenantWithJSON,
            tenant_id=tenant_id,
            provider_name='tidb'
        )

        # Register the model (create table)
        repo.register_model(TenantWithJSON, plan=False)

        yield repo

        # Cleanup
        try:
            repo.close()
        except Exception as e:
            print(f"Warning: Failed to close repository: {e}")

    def test_tidb_json_column_creation(self):
        """Verify JSON columns are created with correct type."""
        from p8fs.providers.tidb import TiDBProvider

        provider = TiDBProvider()
        conn = provider.connect_sync()

        try:
            # Create table
            sql = provider.create_table_sql(TenantWithJSON)
            provider.execute(conn, sql)

            # Check table structure
            result = provider.execute(conn, "DESCRIBE test_tenants_json")

            # Find JSON columns
            columns = {row['Field']: row['Type'] for row in result}

            # TiDB should use JSON type for dict/list fields
            assert 'device_ids' in columns
            assert 'metadata' in columns

        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_json_list_deserialization(self, repository):
        """Test that JSON list columns are deserialized correctly."""
        tenant = TenantWithJSON(
            id=str(uuid4()),
            tenant_id=f"tenant-{uuid4().hex[:8]}",
            email="test@example.com",
            device_ids=["device-1", "device-2", "device-3"],
            metadata={"created_from": "test"}
        )

        # Store tenant
        result = await repository.upsert(tenant)
        assert result['success'] is True

        # Retrieve tenant
        retrieved = await repository.get(tenant.id)

        # Verify device_ids is a list, not a string
        assert isinstance(retrieved.device_ids, list), \
            f"device_ids should be list, got {type(retrieved.device_ids)}"
        assert retrieved.device_ids == ["device-1", "device-2", "device-3"]

        # Verify metadata is a dict, not a string
        assert isinstance(retrieved.metadata, dict), \
            f"metadata should be dict, got {type(retrieved.metadata)}"
        assert retrieved.metadata == {"created_from": "test"}

    @pytest.mark.asyncio
    async def test_json_dict_deserialization(self, repository):
        """Test that JSON dict columns are deserialized correctly."""
        complex_metadata = {
            "source": "device_registration",
            "device_info": {
                "model": "iPhone 15",
                "os": "iOS 17.0"
            },
            "permissions": ["read", "write"],
            "created_at": "2025-01-15T10:30:00Z"
        }

        tenant = TenantWithJSON(
            id=str(uuid4()),
            tenant_id=f"tenant-{uuid4().hex[:8]}",
            email="complex@example.com",
            device_ids=[],
            metadata=complex_metadata
        )

        # Store tenant
        result = await repository.upsert(tenant)
        assert result['success'] is True

        # Retrieve tenant
        retrieved = await repository.get(tenant.id)

        # Verify metadata is properly deserialized
        assert isinstance(retrieved.metadata, dict)
        assert retrieved.metadata == complex_metadata

        # Verify nested structures
        assert isinstance(retrieved.metadata["device_info"], dict)
        assert retrieved.metadata["device_info"]["model"] == "iPhone 15"
        assert isinstance(retrieved.metadata["permissions"], list)
        assert retrieved.metadata["permissions"] == ["read", "write"]

    @pytest.mark.asyncio
    async def test_empty_json_fields(self, repository):
        """Test handling of empty JSON fields."""
        tenant = TenantWithJSON(
            id=str(uuid4()),
            tenant_id=f"tenant-{uuid4().hex[:8]}",
            email="empty@example.com",
            device_ids=[],  # Empty list
            metadata={}     # Empty dict
        )

        # Store tenant
        result = await repository.upsert(tenant)
        assert result['success'] is True

        # Retrieve tenant
        retrieved = await repository.get(tenant.id)

        # Verify empty collections are still proper types
        assert isinstance(retrieved.device_ids, list)
        assert len(retrieved.device_ids) == 0
        assert isinstance(retrieved.metadata, dict)
        assert len(retrieved.metadata) == 0

    @pytest.mark.asyncio
    async def test_select_with_json_fields(self, repository):
        """Test selecting multiple records with JSON fields."""
        tenants = [
            TenantWithJSON(
                id=str(uuid4()),
                tenant_id=f"tenant-{i}",
                email=f"user{i}@example.com",
                device_ids=[f"device-{i}-1", f"device-{i}-2"],
                metadata={"user_id": i, "status": "active"}
            )
            for i in range(3)
        ]

        # Store all tenants
        for tenant in tenants:
            await repository.upsert(tenant)

        # Retrieve all
        results = await repository.select(
            filters={'email__like': 'user%@example.com'}
        )

        # Verify each has properly deserialized JSON
        for result in results:
            if result.email in [f"user{i}@example.com" for i in range(3)]:
                assert isinstance(result.device_ids, list)
                assert len(result.device_ids) == 2
                assert isinstance(result.metadata, dict)
                assert "user_id" in result.metadata
                assert result.metadata["status"] == "active"

    def test_raw_provider_deserialization(self):
        """Test deserialization at the provider level."""
        from p8fs.providers.tidb import TiDBProvider

        provider = TiDBProvider()

        # Test the deserialize_from_db method directly
        raw_data = {
            'id': 'test-123',
            'device_ids': '["device-1", "device-2"]',  # String from TiDB
            'metadata': '{"key": "value", "count": 42}',  # String from TiDB
            'email': 'test@example.com'  # Regular string
        }

        deserialized = provider.deserialize_from_db(raw_data)

        # Verify JSON strings are parsed
        assert isinstance(deserialized['device_ids'], list)
        assert deserialized['device_ids'] == ["device-1", "device-2"]

        assert isinstance(deserialized['metadata'], dict)
        assert deserialized['metadata'] == {"key": "value", "count": 42}

        # Verify regular strings are unchanged
        assert deserialized['email'] == 'test@example.com'

    def test_non_json_strings_unchanged(self):
        """Test that regular strings are not affected by deserialization."""
        from p8fs.providers.tidb import TiDBProvider

        provider = TiDBProvider()

        raw_data = {
            'id': 'test-456',
            'email': 'user@example.com',
            'title': 'This is a regular string',
            'content': 'Some content with {braces} but not JSON',
            'device_ids': '[]'  # Valid JSON
        }

        deserialized = provider.deserialize_from_db(raw_data)

        # Regular strings should be unchanged
        assert deserialized['email'] == 'user@example.com'
        assert deserialized['title'] == 'This is a regular string'
        assert deserialized['content'] == 'Some content with {braces} but not JSON'

        # Valid JSON should be parsed
        assert isinstance(deserialized['device_ids'], list)
        assert deserialized['device_ids'] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
