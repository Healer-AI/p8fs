"""Fast memory saving for agent observations with minimal latency.

This module provides a lightweight save_memory function for agents to record
user comments, corrections, or observed preferences. Designed for speed using
gpt-4.1-nano model and terse descriptions to minimize token generation latency.

USAGE GUIDANCE:
- Use sparingly to avoid latency issues
- Record only significant observations (user corrections, strong preferences)
- Keep descriptions to one sentence maximum
- Limit to 2 observations per interaction to maintain speed
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.models.p8 import InlineEdge, Resources, KVStorage
from p8fs.repository import SystemRepository
from p8fs.services.llm import MemoryProxy

logger = get_logger(__name__)


async def save_memory(
    observation: str,
    category: str = "agent_observation",
    source_id: Optional[str] = None,
    mode: str = "kv",
    tenant_id: Optional[str] = None,
    related_to: Optional[str] = None,
    rel_type: str = "observed_from"
) -> dict:
    """
    Save agent observations to memory with minimal latency.

    Records user comments, corrections, or observed preferences as either
    resources or KV entries with graph edges. Uses gpt-4.1-nano for speed
    and generates terse one-sentence descriptions.

    **When to Use:**
    - User explicitly corrects the agent ("No, I meant X not Y")
    - User expresses strong preference ("I always prefer X")
    - User provides clarifying context ("That's for project ABC")
    - Agent observes consistent behavioral pattern

    **When NOT to Use:**
    - Every user message (too chatty, causes latency)
    - Routine information already in memory
    - General conversation without new information

    **Modes:**

    1. **KV Mode** (default, fastest):
       - Stores in key-value storage with TTL (30 days)
       - Reads existing entry first to merge graph edges
       - Best for: Temporary observations, session context, recent corrections

    2. **Resource Mode** (persistent):
       - Creates/updates a Resource entity with graph edges
       - Requires source_id if updating existing resource
       - Best for: Permanent preferences, user profile data, long-term corrections

    **Graph Edges:**
    - Automatically creates InlineEdge connecting observation to related entity
    - Supports semantic relationships (observed_from, corrects, prefers, relates_to)
    - Merges with existing edges if entity already has them

    Args:
        observation: The observation to save (e.g., "User prefers PostgreSQL over MySQL")
        category: Category for organization (default: "agent_observation")
        source_id: Resource ID to update (Resource mode) or KV key (KV mode)
        mode: Storage mode - "kv" (temporary) or "resource" (persistent)
        tenant_id: Tenant identifier (default: from config)
        related_to: Human-readable key of related entity (for graph edge)
        rel_type: Relationship type for graph edge (default: "observed_from")

    Returns:
        dict with keys:
        - success: bool
        - mode: str ("kv" or "resource")
        - key: str (KV key or resource ID)
        - description: str (generated one-sentence summary)
        - edges_added: int
        - error: str (if failed)

    Examples:
        # User correction during conversation
        >>> await save_memory(
        ...     observation="User corrected: prefers TiDB for production deployments",
        ...     category="user_preference",
        ...     mode="kv",
        ...     related_to="tidb-migration-spec",
        ...     rel_type="prefers"
        ... )

        # Update existing resource with new observation
        >>> await save_memory(
        ...     observation="User noted: always uses UV for Python dependency management",
        ...     category="user_preference",
        ...     mode="resource",
        ...     source_id="user-profile-123",
        ...     related_to="uv-tool",
        ...     rel_type="prefers"
        ... )

        # Session context (temporary)
        >>> await save_memory(
        ...     observation="User is currently debugging NATS connection issues",
        ...     category="current_context",
        ...     mode="kv",
        ...     related_to="nats-troubleshooting",
        ...     rel_type="currently_working_on"
        ... )
    """
    tenant_id = tenant_id or config.default_tenant_id

    try:
        # Generate terse one-sentence description using fast model
        from p8fs.services.llm.models import CallingContext

        memory_proxy = MemoryProxy()

        summary_prompt = f"""Summarize this observation in ONE short sentence (max 10 words):

{observation}

Output only the summary, nothing else."""

        context = CallingContext(
            model="gpt-4o-mini",  # Fast, cheap model for speed
            tenant_id=tenant_id,
            stream=False
        )

        description = await memory_proxy.run(
            question=summary_prompt,
            context=context
        )

        # Ensure it's actually terse
        description = description.strip()[:100]

        logger.info(f"Saving memory: {description[:50]}...")

        # Create graph edge if related entity specified
        edges = []
        if related_to:
            now = datetime.now(timezone.utc)
            edge = InlineEdge(
                dst=related_to,
                rel_type=rel_type,
                weight=0.7,  # Moderate strength for observations
                properties={
                    "dst_name": related_to,
                    "dst_entity_type": "observation/agent",
                    "match_type": "agent-observed",
                    "confidence": 0.8,
                    "context": observation[:200],
                    "observed_at": now.isoformat()
                },
                created_at=now  # Explicitly set timestamp
            )
            edges.append(edge.model_dump())

        if mode == "resource":
            # Resource mode: Update or create persistent resource
            resource_repo = SystemRepository(Resources)

            if source_id:
                # Update existing resource
                result = resource_repo.execute(
                    "SELECT id, graph_paths FROM resources WHERE id = %s AND tenant_id = %s",
                    (source_id, tenant_id)
                )

                if result:
                    existing = result[0]
                    # Merge graph edges
                    from p8fs.algorithms.resource_affinity import ResourceAffinityBuilder
                    builder = ResourceAffinityBuilder(resource_repo.provider, tenant_id)
                    merged_edges = builder._merge_edges(existing.get("graph_paths", []), edges)

                    # Update resource
                    resource_repo.execute(
                        """
                        UPDATE resources
                        SET content = content || '\n\n' || %s,
                            graph_paths = %s::jsonb,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (f"[{datetime.now(timezone.utc).isoformat()}] {observation}",
                         json.dumps(merged_edges),
                         source_id)
                    )

                    return {
                        "success": True,
                        "mode": "resource",
                        "key": source_id,
                        "resource_id": source_id,
                        "description": description,
                        "edges_added": len(edges)
                    }
                else:
                    logger.warning(f"Resource {source_id} not found, creating new")

            # Create new resource
            resource_id = str(uuid4())
            resource_data = {
                "id": resource_id,
                "tenant_id": tenant_id,
                "name": f"{category}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
                "category": category,
                "content": observation,
                "summary": description,
                "graph_paths": edges,
                "metadata": {
                    "source": "agent_observation",
                    "created_by": "save_memory_function"
                }
            }

            resource_repo.upsert_sync(resource_data, create_embeddings=False)

            return {
                "success": True,
                "mode": "resource",
                "key": resource_id,
                "resource_id": resource_id,
                "description": description,
                "edges_added": len(edges)
            }

        else:
            # KV mode: Use KV as entity resolver, store actual data in resources table
            # KV stores reference to resource entity, resource entity has graph_paths
            from p8fs.providers import get_provider

            provider = get_provider()
            kv = provider.kv
            # Use forward slash format for KV keys: tenant_id/entity_type/entity_id
            kv_key = source_id or f"{tenant_id}/observation/{uuid4()}"

            # Check if KV has a reference to an existing resource
            kv_ref = await kv.get(kv_key)
            resource_repo = SystemRepository(Resources)

            if kv_ref and "resource_id" in kv_ref:
                # Found existing resource reference - fetch and update the resource
                resource_id = kv_ref["resource_id"]

                existing = resource_repo.execute(
                    "SELECT id, graph_paths, content FROM resources WHERE id = %s AND tenant_id = %s",
                    (resource_id, tenant_id)
                )

                if existing:
                    existing_resource = existing[0]

                    # Merge graph edges
                    from p8fs.algorithms.resource_affinity import ResourceAffinityBuilder
                    builder = ResourceAffinityBuilder(provider, tenant_id)
                    merged_edges = builder._merge_edges(
                        existing_resource.get("graph_paths", []),
                        edges
                    )

                    # Update resource with merged edges and append observation
                    resource_repo.execute(
                        """
                        UPDATE resources
                        SET content = content || %s,
                            graph_paths = %s::jsonb,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (f"\n[{datetime.now(timezone.utc).isoformat()}] {observation}",
                         json.dumps(merged_edges),
                         resource_id)
                    )

                    return {
                        "success": True,
                        "mode": "kv",
                        "key": kv_key,
                        "resource_id": resource_id,
                        "description": description,
                        "edges_added": len(edges)
                    }

            # No existing resource - create new one
            resource_id = str(uuid4())
            resource_data = {
                "id": resource_id,
                "tenant_id": tenant_id,
                "name": f"{category}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
                "category": category,
                "content": observation,
                "summary": description,
                "graph_paths": edges,
                "metadata": {
                    "source": "agent_observation",
                    "created_by": "save_memory_function",
                    "kv_key": kv_key
                }
            }

            resource_repo.upsert_sync(resource_data, create_embeddings=False)

            # Store entity reference in KV with TTL
            kv_reference = {
                "resource_id": resource_id,
                "entity_type": "resources",
                "category": category,
                "created_at": datetime.now(timezone.utc).isoformat()
            }

            ttl_seconds = 30 * 24 * 60 * 60  # 30 days
            success = await kv.put(kv_key, kv_reference, ttl_seconds=ttl_seconds, tenant_id=tenant_id)

            if not success:
                logger.warning(f"Resource created but KV reference storage failed for key {kv_key}")

            return {
                "success": True,
                "mode": "kv",
                "key": kv_key,
                "resource_id": resource_id,
                "description": description,
                "edges_added": len(edges)
            }

    except Exception as e:
        logger.error(f"Failed to save memory: {e}")
        return {
            "success": False,
            "error": str(e)
        }
