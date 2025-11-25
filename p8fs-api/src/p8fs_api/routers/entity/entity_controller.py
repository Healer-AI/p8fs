"""Entity controller for generic CRUD operations on P8FS entities."""

from typing import Any, TypeVar

from fastapi import HTTPException, status
from p8fs.models import AbstractEntityModel
from p8fs.repository import TenantRepository
from p8fs_cluster.logging import get_logger

T = TypeVar("T", bound=AbstractEntityModel)

logger = get_logger(__name__)


class EntityController:
    """Controller for managing entity CRUD operations."""

    def __init__(self, entity_class: type[AbstractEntityModel], tenant_id: str):
        """
        Initialize entity controller.

        Args:
            entity_class: The entity model class
            tenant_id: Tenant ID for data isolation
        """
        self.entity_class = entity_class
        self.tenant_id = tenant_id
        self.entity_type = entity_class.__name__

        # Initialize repository
        self.repository = TenantRepository(
            model_class=self.entity_class, tenant_id=tenant_id
        )


    async def get_by_id(self, entity_id: str) -> dict[str, Any]:
        """Get entity by ID."""
        entity = await self.repository.get(entity_id)
        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.entity_type} with id '{entity_id}' not found",
            )
        return entity

    async def get_by_name(self, name: str) -> dict[str, Any]:
        """Get entity by name (for entities with name field)."""
        # Check if entity has name field in model_fields
        if hasattr(self.entity_class, "model_fields") and "name" not in self.entity_class.model_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{self.entity_type} does not support lookup by name",
            )

        entities = await self.repository.select_where(name=name)
        if not entities:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.entity_type} with name '{name}' not found",
            )

        # Return first match (names should be unique within tenant)
        return entities[0] if entities else None

    async def search(
        self,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search entities with optional semantic search."""
        results = []
        total = 0

        if query:
            # Use semantic search if query provided
            search_results = await self.repository.semantic_search(
                query=query, limit=limit, threshold=0.7
            )
            results = search_results
            # For semantic search, we don't have exact total count
            total = len(results)
        else:
            # Use regular select with filters
            entities = await self.repository.select(
                filters=filters, limit=limit, offset=offset, order_by=order_by
            )
            results = entities

            # Get total count for pagination
            all_entities = await self.repository.select(filters=filters)
            total = len(all_entities)

        return {
            "results": results,
            "total": total,
            "limit": limit,
            "offset": offset,
            "entity_type": self.entity_type,
        }

    async def create_or_update(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        """Create or update an entity."""
        try:
            # Use repository upsert directly with dict
            result = await self.repository.upsert(entity_data)
            
            # Return the result dict from upsert operation
            return result
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid entity data: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Failed to create/update {self.entity_type}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save entity",
            )
