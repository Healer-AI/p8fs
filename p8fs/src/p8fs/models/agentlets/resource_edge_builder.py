"""Resource edge builder for creating semantic links between resources."""

from datetime import datetime, timezone
from typing import Any
from p8fs.services.graph import GraphAssociation, PostgresGraphProvider
from p8fs.providers.rem_query import (
    REMQueryProvider,
    REMQueryPlan,
    QueryType,
    SearchParameters
)
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class ResourceEdgeBuilder:
    """
    Builder for creating semantic edges between resources.

    This component finds semantically related resources using vector search
    and creates explicit graph edges to enable "see also" navigation and
    historical context discovery.

    Edge Type: SEE_ALSO
    - Connects resources with high semantic similarity
    - Includes similarity score in metadata
    - Enables discovery of related content across time
    """

    def __init__(
        self,
        rem_provider: REMQueryProvider,
        graph_provider: PostgresGraphProvider,
        tenant_id: str = "tenant-test"
    ):
        """
        Initialize resource edge builder.

        Args:
            rem_provider: REM query provider for semantic search
            graph_provider: Graph provider for edge creation
            tenant_id: Tenant context
        """
        self.rem_provider = rem_provider
        self.graph_provider = graph_provider
        self.tenant_id = tenant_id

    async def find_related_resources(
        self,
        resource_id: str,
        resource_content: str,
        similarity_threshold: float = 0.7,
        limit: int = 5,
        exclude_self: bool = True
    ) -> list[tuple[str, float]]:
        """
        Find semantically related resources using vector search.

        Args:
            resource_id: Source resource ID
            resource_content: Source resource content for search
            similarity_threshold: Minimum similarity score (0.0-1.0)
            limit: Maximum number of results
            exclude_self: Whether to exclude the source resource

        Returns:
            List of (resource_id, similarity_score) tuples
        """
        try:
            # Execute semantic search via REM provider
            search_plan = REMQueryPlan(
                query_type=QueryType.SEARCH,
                parameters=SearchParameters(
                    table_name="resources",
                    query_text=resource_content[:1000],  # Limit content length
                    limit=limit + (1 if exclude_self else 0),  # Extra for filtering
                    threshold=similarity_threshold,
                    tenant_id=self.tenant_id
                )
            )

            results = self.rem_provider.execute(search_plan)

            # Process results
            related = []
            for result in results:
                related_id = result.get('id')
                similarity = result.get('similarity', 0.0)

                # Skip self-references
                if exclude_self and related_id == resource_id:
                    continue

                # Filter by threshold
                if similarity >= similarity_threshold:
                    related.append((related_id, float(similarity)))

            # Sort by similarity descending and limit
            related.sort(key=lambda x: x[1], reverse=True)
            related = related[:limit]

            logger.info(
                f"Found {len(related)} related resources for {resource_id} "
                f"(threshold: {similarity_threshold})"
            )

            return related

        except Exception as e:
            logger.error(f"Failed to find related resources for {resource_id}: {e}")
            return []

    def create_edges(
        self,
        from_resource_id: str,
        related_resources: list[tuple[str, float]]
    ) -> int:
        """
        Create SEE_ALSO edges to related resources.

        Args:
            from_resource_id: Source resource ID
            related_resources: List of (resource_id, similarity_score) tuples

        Returns:
            Number of edges successfully created
        """
        if not related_resources:
            logger.info(f"No related resources to link for {from_resource_id}")
            return 0

        associations = []
        for related_id, similarity_score in related_resources:
            association = GraphAssociation(
                from_entity_id=from_resource_id,
                to_entity_id=related_id,
                relationship_type="SEE_ALSO",
                from_entity_type="Resource",
                to_entity_type="Resource",
                tenant_id=self.tenant_id,
                metadata={
                    "similarity_score": similarity_score,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    "processing_phase": "second_order_dreaming"
                }
            )
            associations.append(association)

        # Batch create edges
        count = self.graph_provider.create_associations(associations)

        logger.info(
            f"Created {count}/{len(associations)} SEE_ALSO edges from {from_resource_id}"
        )

        return count

    async def process_resource(
        self,
        resource_id: str,
        resource_content: str,
        similarity_threshold: float = 0.7,
        max_edges: int = 5
    ) -> dict[str, Any]:
        """
        Process a single resource: find related resources and create edges.

        Args:
            resource_id: Resource to process
            resource_content: Resource content for search
            similarity_threshold: Minimum similarity for edge creation
            max_edges: Maximum edges to create per resource

        Returns:
            Processing statistics
        """
        # Find related resources
        related = await self.find_related_resources(
            resource_id=resource_id,
            resource_content=resource_content,
            similarity_threshold=similarity_threshold,
            limit=max_edges
        )

        # Create edges
        edges_created = self.create_edges(resource_id, related)

        return {
            "resource_id": resource_id,
            "related_found": len(related),
            "edges_created": edges_created,
            "average_similarity": (
                sum(score for _, score in related) / len(related)
                if related else 0.0
            )
        }

    async def process_batch(
        self,
        resources: list[dict[str, Any]],
        similarity_threshold: float = 0.7,
        max_edges_per_resource: int = 5
    ) -> dict[str, Any]:
        """
        Process a batch of resources to create inter-resource edges.

        Args:
            resources: List of resource dicts with 'id' and 'content'
            similarity_threshold: Minimum similarity for edge creation
            max_edges_per_resource: Maximum edges per resource

        Returns:
            Batch processing statistics
        """
        results = []
        total_edges = 0

        for resource in resources:
            resource_id = resource.get('id')
            resource_content = resource.get('content', '')

            if not resource_id or not resource_content:
                logger.warning(f"Skipping resource with missing id or content")
                continue

            try:
                result = await self.process_resource(
                    resource_id=resource_id,
                    resource_content=resource_content,
                    similarity_threshold=similarity_threshold,
                    max_edges=max_edges_per_resource
                )
                results.append(result)
                total_edges += result['edges_created']

            except Exception as e:
                logger.error(f"Failed to process resource {resource_id}: {e}")
                continue

        return {
            "resources_processed": len(results),
            "total_edges_created": total_edges,
            "average_edges_per_resource": (
                total_edges / len(results) if results else 0.0
            ),
            "results": results
        }
