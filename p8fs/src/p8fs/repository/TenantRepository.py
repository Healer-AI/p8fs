"""Tenant-aware repository implementation for P8FS models."""

from typing import Any, TypeVar

from p8fs_cluster.logging import get_logger

from p8fs.models import AbstractModel
from p8fs.repository.BaseRepository import BaseRepository

T = TypeVar("T", bound=AbstractModel)

logger = get_logger(__name__)


class TenantRepository(BaseRepository):
    """
    Multi-tenant repository that automatically isolates data by tenant_id.
    
    This repository provides CRUD operations with automatic tenant isolation,
    ensuring that all operations are scoped to a specific tenant.

    Key Features:
    - Automatic tenant isolation on all operations
    - Embedding generation and vector search capabilities (via BaseRepository)
    - Batch operations for high throughput
    - SQL query execution with tenant scoping

    Design Principles:
    - Tenant ID is automatically injected into all operations
    - SQL queries include tenant_id WHERE clauses automatically
    - Embedding tables are also tenant-isolated
    """

    def __init__(
        self, model_class: type[T], tenant_id: str, provider_name: str | None = None
    ):
        """
        Initialize tenant repository bound to a specific model and tenant.

        Args:
            model_class: The AbstractModel class this repository manages
            tenant_id: The tenant ID for automatic data isolation
            provider_name: Optional database provider override
        """
        super().__init__(model_class, tenant_id=tenant_id, provider_name=provider_name)

    def _build_filters(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Build filters with automatic tenant isolation.
        """
        final_filters = filters.copy() if filters else {}
        final_filters["tenant_id"] = self.tenant_id
        return final_filters

    def _prepare_entity_data(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        """
        Prepare entity data with automatic tenant_id injection and ID generation.
        """
        prepared_data = entity_data.copy()
        prepared_data["tenant_id"] = self.tenant_id
        
        # Generate ID if not provided
        if "id" not in prepared_data or prepared_data["id"] is None:
            # Get the key field name and value
            key_field = self.model_class.get_model_key_field()
            key_value = prepared_data.get(key_field)
            
            if key_value:
                # Generate ID from tenant_id + key_field value
                from uuid import NAMESPACE_DNS, uuid5
                id_string = f"{self.tenant_id}:{key_value}"
                prepared_data["id"] = str(uuid5(NAMESPACE_DNS, id_string))
            else:
                # If no key value, generate a random UUID
                from uuid import uuid4
                prepared_data["id"] = str(uuid4())
        
        return prepared_data

    def _get_tenant_id_for_embedding(self, entity_data: dict[str, Any]) -> str | None:
        """
        Return the tenant_id for embedding storage.
        """
        return self.tenant_id

    def _get_tenant_id_for_search(self) -> str | None:
        """
        Return the tenant_id for semantic search filtering.
        Overrides base implementation to provide tenant isolation.
        """
        return self.tenant_id

    async def put(self, entity: T) -> bool:
        """
        Store a single entity and populate KV entries for entity lookups.

        Args:
            entity: Entity to store

        Returns:
            True if successful, False otherwise
        """
        try:
            await self.upsert(entity)
            # Entity indexing happens via p8.add_nodes() and AGE graph
            # LOOKUP queries use p8.get_entities() to query the graph
            # No need for separate KV entity indexing
            return True
        except Exception as e:
            logger.error(f"Database error in put {self.model_class.__name__}: {e}", exc_info=True)
            # Don't return False for database errors - let them propagate
            raise RuntimeError(f"Database error storing {self.model_class.__name__}: {e}") from e

    # Entity indexing removed - now handled by AGE graph via p8.add_nodes()
    # LOOKUP queries use p8.get_entities() to query the graph directly

    # Note: Old complex embedding methods removed. 
    # TenantRepository now inherits clean embedding implementation from BaseRepository:
    # - create_with_embeddings() 
    # - semantic_search()
    # These automatically handle tenant isolation via _get_tenant_id_for_search() override above.