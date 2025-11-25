"""Resources entity router."""

from .base import create_entity_router

# Create router for resources
router = create_entity_router("resources", tags=["Resources"])