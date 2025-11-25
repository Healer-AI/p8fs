"""Agent loader service for loading agent schemas from resources."""

import json
from typing import Optional, Dict, Any, List

from p8fs_cluster.logging import get_logger
from p8fs.repository import TenantRepository
from p8fs.models.p8 import Resources

logger = get_logger(__name__)


class AgentLoader:
    """Service for loading agent schemas from resources table."""

    def __init__(self, tenant_id: str):
        """Initialize agent loader with tenant context.

        Args:
            tenant_id: Tenant ID to scope agent lookups
        """
        self.tenant_id = tenant_id
        self.repo = TenantRepository(Resources, tenant_id=tenant_id)

    async def load_agent_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Load agent schema by name.

        Args:
            name: Agent name (short_name)

        Returns:
            Agent schema as dict, or None if not found
        """
        try:
            # Use raw SQL to avoid Pydantic deserialization issues with JSONB fields
            from p8fs.providers import get_provider
            provider = get_provider()

            rows = provider.execute(
                "SELECT * FROM resources WHERE category = %s AND name = %s AND tenant_id = %s LIMIT 1",
                ("agent", name, self.tenant_id)
            )

            if not rows:
                logger.warning(f"Agent '{name}' not found for tenant {self.tenant_id}")
                return None

            resource = rows[0]

            # Parse the content field which contains the JSON schema
            try:
                content = resource["content"]
                agent_schema = json.loads(content) if isinstance(content, str) else content
                logger.info(f"Loaded agent '{name}' (version {agent_schema.get('version', 'unknown')})")
                return agent_schema
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse agent schema for '{name}': {e}")
                return None

        except Exception as e:
            logger.error(f"Error loading agent '{name}': {e}")
            return None

    async def list_agents(
        self,
        use_in_dreaming: Optional[bool] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List all agent schemas for this tenant.

        Args:
            use_in_dreaming: Filter by use_in_dreaming flag if provided
            limit: Maximum number of agents to return

        Returns:
            List of agent schemas
        """
        try:
            # Use raw SQL to avoid Pydantic deserialization issues
            from p8fs.providers import get_provider
            provider = get_provider()

            rows = provider.execute(
                "SELECT * FROM resources WHERE category = %s AND tenant_id = %s LIMIT %s",
                ("agent", self.tenant_id, limit)
            )

            agents = []
            for resource in rows:
                try:
                    content = resource["content"]
                    agent_schema = json.loads(content) if isinstance(content, str) else content

                    # Apply use_in_dreaming filter if specified
                    if use_in_dreaming is not None:
                        # Check both metadata and schema for use_in_dreaming
                        metadata = resource.get("metadata", {})
                        if isinstance(metadata, str):
                            metadata = json.loads(metadata)

                        agent_use_in_dreaming = (
                            metadata.get("use_in_dreaming", False)
                            or agent_schema.get("use_in_dreaming", False)
                        )
                        if agent_use_in_dreaming != use_in_dreaming:
                            continue

                    agents.append(agent_schema)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse agent schema for resource {resource['id']}: {e}")
                    continue

            logger.info(f"Found {len(agents)} agents for tenant {self.tenant_id}")
            return agents

        except Exception as e:
            logger.error(f"Error listing agents: {e}")
            return []

    async def get_dreaming_agents(self) -> List[Dict[str, Any]]:
        """Get all agents marked for use in dreaming.

        Returns:
            List of agent schemas with use_in_dreaming=True
        """
        return await self.list_agents(use_in_dreaming=True)

    async def delete_agent_by_name(self, name: str) -> bool:
        """Delete agent by name.

        Args:
            name: Agent name to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            # Find the agent first using raw SQL
            from p8fs.providers import get_provider
            provider = get_provider()

            rows = provider.execute(
                "SELECT id FROM resources WHERE category = %s AND name = %s AND tenant_id = %s LIMIT 1",
                ("agent", name, self.tenant_id)
            )

            if not rows:
                logger.warning(f"Agent '{name}' not found for deletion")
                return False

            resource_id = rows[0]["id"]
            await self.repo.delete(resource_id)
            logger.info(f"Deleted agent '{name}' (ID: {resource_id})")
            return True

        except Exception as e:
            logger.error(f"Error deleting agent '{name}': {e}")
            return False


async def load_agent(name: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """Convenience function to load an agent schema.

    Args:
        name: Agent name
        tenant_id: Tenant ID

    Returns:
        Agent schema dict or None
    """
    loader = AgentLoader(tenant_id)
    return await loader.load_agent_by_name(name)


async def list_agents(tenant_id: str, use_in_dreaming: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Convenience function to list agents.

    Args:
        tenant_id: Tenant ID
        use_in_dreaming: Filter by use_in_dreaming flag

    Returns:
        List of agent schemas
    """
    loader = AgentLoader(tenant_id)
    return await loader.list_agents(use_in_dreaming=use_in_dreaming)
