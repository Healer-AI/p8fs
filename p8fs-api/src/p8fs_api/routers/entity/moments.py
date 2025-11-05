"""Moments entity router for P8FS API."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from p8fs.models.engram.models import Moment
from p8fs_api.middleware import User, get_current_user
from p8fs_api.models.responses import ErrorResponse

from .entity_controller import EntityController


class MomentCreate(Moment):
    """Request model for creating/updating a moment."""
    
    # Override required fields to make them optional for creation
    id: str | None = None
    tenant_id: str | None = None
    created_at: datetime | None = None


class MomentSearchResponse(BaseModel):
    """Response model for moment search results."""

    results: list[Moment]
    total: int
    limit: int
    offset: int
    entity_type: str = "moment"


# Create router with authentication
router = APIRouter(
    prefix="/api/v1/entity/moments",
    tags=["moments"],
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "Not found"},
        400: {"model": ErrorResponse, "description": "Bad request"},
    },
)


@router.get("/{moment_id}", response_model=Moment)
async def get_moment_by_id(
    moment_id: str,
    current_user: User = Depends(get_current_user),
) -> Moment:
    """Get a specific moment by ID."""
    controller = EntityController(entity_class=Moment, tenant_id=current_user.tenant_id)
    
    # Get moment by ID using the get() method
    moment = await controller.repository.get(moment_id)
    if not moment:
        raise HTTPException(status_code=404, detail="Moment not found")
    
    return moment


@router.get("/name/{name}", response_model=Moment)
async def get_moment_by_name(
    name: str,
    current_user: User = Depends(get_current_user),
) -> Moment:
    """Get a specific moment by name."""
    controller = EntityController(entity_class=Moment, tenant_id=current_user.tenant_id)
    result = await controller.get_by_name(name)
    return Moment(**result)


@router.get("/", response_model=MomentSearchResponse)
async def search_moments(
    query: str | None = Query(None, description="Semantic search query"),
    session_id: str | None = Query(None, description="Filter by session ID"),
    moment_type: str | None = Query(None, description="Filter by moment type"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    sort_by: str = Query("created_at DESC", description="Sort field and direction (e.g. 'created_at DESC', 'name ASC')"),
    current_user: User = Depends(get_current_user),
) -> MomentSearchResponse:
    """
    Search moments with optional filters and semantic search.

    - **query**: Optional semantic search query
    - **session_id**: Filter by session ID
    - **moment_type**: Filter by moment type
    - **limit**: Maximum number of results (1-100)
    - **offset**: Number of results to skip for pagination
    - **sort_by**: Sort field and direction (default: created_at DESC)
    """
    controller = EntityController(entity_class=Moment, tenant_id=current_user.tenant_id)

    # Build filters
    filters = {}
    if session_id:
        filters["session_id"] = session_id
    if moment_type:
        filters["moment_type"] = moment_type

    # Parse sort_by into order_by list
    order_by = [sort_by] if sort_by else None

    result = await controller.search(
        query=query,
        filters=filters if filters else None,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )

    # Results are already Moment objects or dicts
    results = result["results"]
    if results and isinstance(results[0], dict):
        moments = [Moment(**moment_dict) for moment_dict in results]
    else:
        moments = results  # Already Moment objects
    
    return MomentSearchResponse(
        results=moments,
        total=result["total"],
        limit=result["limit"],
        offset=result["offset"],
        entity_type=result["entity_type"]
    )


@router.put("/", response_model=Moment)
async def create_or_update_moment(
    moment_data: MomentCreate,
    current_user: User = Depends(get_current_user),
) -> Moment:
    """Create or update a moment."""
    controller = EntityController(entity_class=Moment, tenant_id=current_user.tenant_id)

    # Convert pydantic model to dict and add tenant_id
    data = moment_data.model_dump(exclude_unset=True)
    data["tenant_id"] = current_user.tenant_id
    
    # Generate ID if not provided
    if "id" not in data or data["id"] is None:
        import uuid
        data["id"] = str(uuid.uuid4())

    # Create/update in database
    await controller.create_or_update(data)

    # Fetch the created moment from database to get all fields including defaults
    created_moment = await controller.repository.get(data["id"])
    if not created_moment:
        # Fallback to input data if fetch fails
        if "created_at" not in data:
            data["created_at"] = datetime.now()
        return Moment(**data)

    return created_moment


@router.post("/", response_model=Moment)
async def create_moment(
    moment_data: MomentCreate,
    current_user: User = Depends(get_current_user),
) -> Moment:
    """Create a new moment (alias for PUT)."""
    return await create_or_update_moment(moment_data, current_user)


@router.put("/{moment_id}", response_model=Moment)
async def update_moment(
    moment_id: str,
    moment_data: MomentCreate,
    current_user: User = Depends(get_current_user),
) -> Moment:
    """Update an existing moment."""
    controller = EntityController(entity_class=Moment, tenant_id=current_user.tenant_id)
    
    # Check if moment exists first
    existing_moment = await controller.repository.get(moment_id)
    if not existing_moment:
        raise HTTPException(status_code=404, detail="Moment not found")
    
    # Prepare update data, preserving existing values for unset fields
    data = moment_data.model_dump(exclude_unset=True)
    data["id"] = moment_id
    data["tenant_id"] = current_user.tenant_id
    
    # Ensure moment_type is preserved if not explicitly updated
    if "moment_type" not in data:
        data["moment_type"] = existing_moment.moment_type
    
    await controller.create_or_update(data)
    
    # Fetch and return the updated moment
    updated_moment = await controller.repository.get(moment_id)
    return updated_moment


@router.delete("/{moment_id}")
async def delete_moment(
    moment_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Delete a moment."""
    controller = EntityController(entity_class=Moment, tenant_id=current_user.tenant_id)
    
    # Delete the moment (returns False if not found)
    success = await controller.repository.delete(moment_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Moment not found")
    
    return {"message": "Moment deleted successfully"}


# TODO Todays moments feed and continuous scroll tooling
