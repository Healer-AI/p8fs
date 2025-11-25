"""P8FS Core Repository layer - Data access and persistence."""

from .BaseRepository import BaseRepository
from .TenantRepository import TenantRepository
from .SystemRepository import SystemRepository

# Alias for backward compatibility
Repository = BaseRepository

__all__ = [
    "BaseRepository", 
    "TenantRepository",
    "SystemRepository",
    "Repository"
]