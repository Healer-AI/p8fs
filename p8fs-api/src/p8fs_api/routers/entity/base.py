"""Base router factory for entity endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ...middleware import User, get_current_user
from ...models.responses import ErrorResponse
from .entity_controller import EntityController


class EntitySearchRequest(BaseModel):
    """Entity search request parameters."""
    query: str | None = Field(None, description="Semantic search query")
    filters: dict[str, Any] | None = Field(None, description="Filter conditions")
    limit: int = Field(20, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class EntitySearchResponse(BaseModel):
    """Entity search response."""
    results: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    entity_type: str


class EntityResponse(BaseModel):
    """Single entity response."""
    data: dict[str, Any]
    entity_type: str


class EntityDeleteResponse(BaseModel):
    """Entity deletion response."""
    message: str
    id: str


def create_entity_router(entity_type: str, tags: list[str] | None = None) -> APIRouter:
    """
    Create a router for a specific entity type.
    
    Args:
        entity_type: Type of entity (e.g., "moment", "resource", "engram-models-Agent")
        tags: Optional tags for the router
    
    Returns:
        Configured FastAPI router for the entity type
    """
    # Determine route prefix
    if "-" in entity_type:
        # Namespaced entity - use full name
        route_prefix = f"/api/entity/{entity_type}"
    else:
        # Public namespace - use simple name
        route_prefix = f"/api/entity/{entity_type}"
    
    # Create router
    router = APIRouter(
        prefix=route_prefix,
        tags=tags or [f"Entity: {entity_type}"],
        dependencies=[Depends(get_current_user)]
    )
    
    # Define endpoints
    
    @router.get("/{entity_id}", response_model=EntityResponse)
    async def get_entity_by_id(
        entity_id: str,
        current_user: User = Depends(get_current_user)
    ):
        """Get entity by ID."""
        controller = EntityController(entity_type, current_user.tenant_id)
        data = await controller.get_by_id(entity_id)
        return EntityResponse(data=data, entity_type=entity_type)
    
    @router.get("/name/{name}", response_model=EntityResponse)
    async def get_entity_by_name(
        name: str,
        current_user: User = Depends(get_current_user)
    ):
        """Get entity by name (for entities with name field)."""
        controller = EntityController(entity_type, current_user.tenant_id)
        data = await controller.get_by_name(name)
        return EntityResponse(data=data, entity_type=entity_type)
    
    @router.post("/search", response_model=EntitySearchResponse)
    async def search_entities(
        request: EntitySearchRequest,
        current_user: User = Depends(get_current_user)
    ):
        """Search entities with optional semantic search."""
        controller = EntityController(entity_type, current_user.tenant_id)
        return await controller.search(
            query=request.query,
            filters=request.filters,
            limit=request.limit,
            offset=request.offset
        )
    
    @router.get("/", response_model=EntitySearchResponse)
    async def list_entities(
        query: str | None = Query(None, description="Semantic search query"),
        limit: int = Query(20, ge=1, le=100, description="Maximum results"),
        offset: int = Query(0, ge=0, description="Offset for pagination"),
        current_user: User = Depends(get_current_user)
    ):
        """List entities with optional search."""
        controller = EntityController(entity_type, current_user.tenant_id)
        return await controller.search(
            query=query,
            filters=None,
            limit=limit,
            offset=offset
        )
    
    @router.put("/", response_model=EntityResponse)
    async def upsert_entity(
        entity_data: dict[str, Any],
        current_user: User = Depends(get_current_user)
    ):
        """Create or update an entity."""
        controller = EntityController(entity_type, current_user.tenant_id)
        data = await controller.create_or_update(entity_data)
        return EntityResponse(data=data, entity_type=entity_type)
    
    @router.delete("/{entity_id}", response_model=EntityDeleteResponse)
    async def delete_entity(
        entity_id: str,
        current_user: User = Depends(get_current_user)
    ):
        """Delete an entity by ID."""
        controller = EntityController(entity_type, current_user.tenant_id)
        return await controller.delete(entity_id)
    
    return router