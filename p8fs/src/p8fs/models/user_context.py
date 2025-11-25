"""User context model for session loading."""

from datetime import datetime
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class UserContext:
    """
    User context information stored as Resource entity.

    Stored as p8fs-user-info Resource that can be loaded via REM LOOKUP.
    Updated by dreaming processes through summarize_user placeholder.
    """

    @staticmethod
    async def load_or_create(tenant_id: str) -> dict:
        """
        Load existing user context from p8fs-user-info Resource.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary with user context information
        """
        from p8fs.models.p8 import Resources
        from p8fs.repository.TenantRepository import TenantRepository

        try:
            # Try to load existing p8fs-user-info resource
            repo = TenantRepository(model_class=Resources, tenant_id=tenant_id)
            resource = await repo.get("p8fs-user-info")

            if resource:
                logger.debug(f"Loaded user context for {tenant_id}")
                return {
                    "tenant_id": tenant_id,
                    "summary": resource.content,
                    "metadata": resource.metadata or {}
                }

            # Create placeholder context
            logger.info(f"No user context found for {tenant_id}, creating placeholder")
            from p8fs.models.p8 import Resources as ResourceModel
            resource = ResourceModel(
                id="p8fs-user-info",
                name="p8fs-user-info",
                category="user_context",
                content="User context not yet summarized. Use summarize_user to generate summary.",
                metadata={
                    "created_at": datetime.now().isoformat(),
                    "total_sessions": 0,
                    "total_tokens": 0
                }
            )

            await repo.upsert(resource)
            return {
                "tenant_id": tenant_id,
                "summary": resource.content,
                "metadata": resource.metadata
            }

        except Exception as e:
            logger.error(f"Failed to load/create user context: {e}")
            return {
                "tenant_id": tenant_id,
                "summary": "User context unavailable",
                "metadata": {}
            }

    @staticmethod
    async def update_summary(tenant_id: str, summary: str, metadata: dict | None = None) -> None:
        """
        Update user summary (called by dreaming/summarize_user processes).

        Args:
            tenant_id: Tenant identifier
            summary: Updated user summary
            metadata: Optional metadata to update
        """
        from p8fs.models.p8 import Resources
        from p8fs.repository.TenantRepository import TenantRepository
        from datetime import datetime

        try:
            repo = TenantRepository(model_class=Resources, tenant_id=tenant_id)
            resource = await repo.get("p8fs-user-info")

            if not resource:
                from p8fs.models.p8 import Resources as ResourceModel
                resource = ResourceModel(
                    id="p8fs-user-info",
                    name="p8fs-user-info",
                    category="user_context",
                    content=summary,
                    metadata=metadata or {}
                )
            else:
                resource.content = summary
                if metadata:
                    resource.metadata.update(metadata)

            resource.metadata["last_updated"] = datetime.now().isoformat()

            await repo.upsert(resource)
            logger.info(f"Updated user context for {tenant_id}")

        except Exception as e:
            logger.error(f"Failed to update user context: {e}")

    @staticmethod
    def to_context_message(user_context: dict) -> dict[str, str]:
        """
        Convert user context to a system message for LLM.

        Args:
            user_context: Dictionary from load_or_create()

        Returns:
            System message dict with user context
        """
        tenant_id = user_context.get("tenant_id", "unknown")
        summary = user_context.get("summary", "No summary available")
        metadata = user_context.get("metadata", {})

        content = f"""User Context (REM LOOKUP p8fs-user-info):
Tenant ID: {tenant_id}

Summary:
{summary}

Session Stats:
- Total sessions: {metadata.get('total_sessions', 0)}
- Total tokens: {metadata.get('total_tokens', 0):,}
- Last updated: {metadata.get('last_updated', 'Never')}
"""

        return {
            "role": "system",
            "content": content
        }
