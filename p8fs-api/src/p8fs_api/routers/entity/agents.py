"""Agent entity router with custom extensions."""

from fastapi import Depends
from pydantic import BaseModel

from ...middleware import User, get_current_user
from .base import create_entity_router
from .entity_controller import EntityController

# Create base router for agents
router = create_entity_router("agent", tags=["Agents"])


# Add custom endpoints for agents

class AgentActivationRequest(BaseModel):
    """Request to activate/deactivate an agent."""
    active: bool
    reason: str | None = None


@router.post("/{agent_id}/activate")
async def toggle_agent_activation(
    agent_id: str,
    request: AgentActivationRequest,
    current_user: User = Depends(get_current_user)
):
    """Activate or deactivate an agent."""
    controller = EntityController("agent", current_user.tenant_id)
    
    # Get the agent
    agent = await controller.get_by_id(agent_id)
    
    # Update metadata
    metadata = agent.get("metadata", {})
    metadata["active"] = request.active
    if request.reason:
        metadata["status_reason"] = request.reason
    metadata["last_status_change"] = "2025-01-11T00:00:00Z"
    
    # Update agent
    agent["metadata"] = metadata
    updated = await controller.create_or_update(agent)
    
    return {
        "agent_id": agent_id,
        "active": request.active,
        "message": f"Agent {'activated' if request.active else 'deactivated'} successfully"
    }


@router.get("/{agent_id}/functions")
async def get_agent_functions(
    agent_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get available functions for an agent."""
    controller = EntityController("agent", current_user.tenant_id)
    agent = await controller.get_by_id(agent_id)
    
    return {
        "agent_id": agent_id,
        "functions": agent.get("functions", []),
        "function_count": len(agent.get("functions", []))
    }