"""System-level repository that bypasses tenant scoping for system operations."""

from typing import Any, TypeVar

from p8fs_cluster.logging import get_logger

from p8fs.models import AbstractModel
from p8fs.repository.BaseRepository import BaseRepository

T = TypeVar("T", bound=AbstractModel)

logger = get_logger(__name__)


class SystemRepository(BaseRepository):
    """
    System repository that bypasses tenant scoping for system-level operations.
    
    This repository provides the same CRUD operations as BaseRepository but
    is intended for system operations like authentication, user management, etc.
    
    Use this for:
    - Authentication operations (login, user lookup)
    - System administration  
    - Cross-tenant operations
    
    The underlying tables are the same - this just removes tenant isolation.
    """

    def __init__(self, model_class: type[T], provider_name: str | None = None):
        """
        Initialize system repository without tenant scoping.
        
        Args:
            model_class: The AbstractModel class this repository manages
            provider_name: Optional database provider override
        """
        super().__init__(model_class, tenant_id=None, provider_name=provider_name)
        logger.debug(f"Initialized SystemRepository for {model_class.__name__} without tenant scoping")

    def _build_filters(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Build filters without tenant scoping - just return filters as-is.
        """
        return filters or {}

    def _prepare_entity_data(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        """
        Prepare entity data without injecting tenant_id - preserve any existing tenant_id.
        """
        return entity_data.copy()

    def _get_tenant_id_for_embedding(self, entity_data: dict[str, Any]) -> str | None:
        """
        Return the tenant_id from entity data if it exists, or None for system-level entities.
        """
        return entity_data.get('tenant_id')