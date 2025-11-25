"""Resource affinity algorithms for building knowledge graphs through semantic similarity.

This module provides algorithms to discover relationships between resources and build
graph connections through two modes:

1. Basic Mode: Semantic search by splicing text segments
2. LLM Mode: Intelligent relationship assessment with meaningful edges
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from opentelemetry import trace
from p8fs_cluster.logging import get_logger
from p8fs.models.p8 import Resources
from p8fs.providers.base import BaseSQLProvider
from p8fs.services.llm import MemoryProxy
from p8fs.utils.otel_utils import get_tracer, add_span_event, mark_span_as_error

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


class ResourceAffinityBuilder:
    """Build affinity relationships between resources through semantic search."""

    def __init__(self, provider: BaseSQLProvider, tenant_id: str):
        self.provider = provider
        self.tenant_id = tenant_id
        self.memory_proxy = MemoryProxy()

        # Detect database dialect for appropriate query building
        self.dialect = getattr(provider, 'dialect', 'postgresql')
        logger.info(f"ResourceAffinityBuilder initialized with dialect: {self.dialect}")

    def _extract_text_segments(
        self, content: str, num_segments: int = 3, segment_length: int = 100
    ) -> list[str]:
        """Extract random text segments from content for semantic search.

        Args:
            content: Source content to extract from
            num_segments: Number of segments to extract
            segment_length: Character length of each segment

        Returns:
            List of text segments
        """
        if not content or len(content) < segment_length:
            return [content] if content else []

        segments = []
        words = content.split()

        if len(words) < 10:
            return [content]

        for _ in range(num_segments):
            start_idx = random.randint(0, max(0, len(words) - 20))
            segment_words = words[start_idx : start_idx + 20]
            segment = " ".join(segment_words)

            if len(segment) > segment_length:
                segment = segment[:segment_length]

            segments.append(segment.strip())

        return segments

    def _merge_graph_paths(
        self, existing_paths: list[str], new_paths: list[str]
    ) -> list[str]:
        """DEPRECATED: Merge graph paths (string-based).

        This method is deprecated. Use _merge_edges for InlineEdge objects.

        Args:
            existing_paths: Current graph paths (strings)
            new_paths: New paths to merge (strings)

        Returns:
            Merged list of unique paths
        """
        existing_set = set(existing_paths or [])
        new_set = set(new_paths or [])
        merged = existing_set.union(new_set)
        return list(merged)

    def _merge_edges(
        self, existing_edges: list, new_edges: list
    ) -> list:
        """Merge edges without duplicating (dst, rel_type) pairs.

        If an edge with the same (dst, rel_type) exists, keep the one with higher weight.

        Args:
            existing_edges: Current edges (list of InlineEdge or dicts)
            new_edges: New edges to merge (list of InlineEdge)

        Returns:
            Merged list of unique edges
        """
        from p8fs.models.p8 import InlineEdge

        # Convert to dict for easy deduplication
        edges_map = {}

        # Add existing edges
        for edge in existing_edges or []:
            if isinstance(edge, InlineEdge):
                edge_dict = edge.model_dump()
            elif isinstance(edge, dict):
                edge_dict = edge
            else:
                continue

            key = (edge_dict["dst"], edge_dict["rel_type"])
            edges_map[key] = edge_dict

        # Add new edges (replacing if weight is higher)
        for edge in new_edges or []:
            if isinstance(edge, InlineEdge):
                edge_dict = edge.model_dump()
            elif isinstance(edge, dict):
                edge_dict = edge
            else:
                continue

            key = (edge_dict["dst"], edge_dict["rel_type"])

            if key not in edges_map or edge_dict["weight"] > edges_map[key]["weight"]:
                edges_map[key] = edge_dict

        # Return as list of dicts (will be serialized to JSON)
        return list(edges_map.values())

    def _build_vector_search_query(self, embedding: list[float], source_resource_id: str, limit: int) -> tuple[str, tuple]:
        """Build vector search query based on database dialect.

        Args:
            embedding: Query embedding vector
            source_resource_id: ID of source resource to exclude
            limit: Maximum results to return

        Returns:
            Tuple of (query_string, parameters)
        """
        if self.dialect == 'tidb':
            # TiDB uses VEC_COSINE_DISTANCE function with JSON format
            import json
            embedding_json = json.dumps(embedding)

            query = """
                SELECT
                    r.id,
                    r.name,
                    r.content,
                    r.category,
                    r.graph_paths,
                    VEC_COSINE_DISTANCE(e.embedding_vector, VEC_FROM_TEXT(%s)) as distance
                FROM resources r
                JOIN embeddings.resources_embeddings e ON r.id = e.entity_id
                WHERE r.tenant_id = %s
                  AND r.id != %s
                  AND e.field_name = 'content'
                ORDER BY VEC_COSINE_DISTANCE(e.embedding_vector, VEC_FROM_TEXT(%s))
                LIMIT %s
            """
            params = (embedding_json, self.tenant_id, source_resource_id, embedding_json, limit)

        else:
            # PostgreSQL uses <-> operator with vector type
            query = """
                SELECT
                    r.id,
                    r.name,
                    r.content,
                    r.category,
                    r.graph_paths,
                    e.embedding_vector <-> %s::vector as distance
                FROM resources r
                JOIN embeddings.resources_embeddings e ON r.id = e.entity_id
                WHERE r.tenant_id = %s
                  AND r.id != %s
                  AND e.field_name = 'content'
                ORDER BY e.embedding_vector <-> %s::vector
                LIMIT %s
            """
            params = (embedding, self.tenant_id, source_resource_id, embedding, limit)

        return query, params

    def _build_graph_paths_update_query(self, graph_paths: list[dict], resource_id: str) -> tuple[str, tuple]:
        """Build graph paths update query based on database dialect.

        Note: graph_paths now stores InlineEdge objects as JSONB (list of dicts), not strings.

        Args:
            graph_paths: List of InlineEdge dicts to set
            resource_id: Resource ID to update

        Returns:
            Tuple of (query_string, parameters)
        """
        import json
        graph_paths_json = json.dumps(graph_paths)

        if self.dialect == 'tidb':
            # TiDB uses JSON type (no casting needed)
            query = """
                UPDATE resources
                SET graph_paths = %s, updated_at = NOW()
                WHERE id = %s
            """
            params = (graph_paths_json, resource_id)
        else:
            # PostgreSQL uses jsonb type with casting
            query = """
                UPDATE resources
                SET graph_paths = %s::jsonb, updated_at = NOW()
                WHERE id = %s
            """
            params = (graph_paths_json, resource_id)

        return query, params

    async def find_similar_resources_basic(
        self,
        source_resource: Resources,
        limit: int = 5,
        similarity_threshold: float = -0.5,
    ) -> list[dict]:
        """Find similar resources using basic semantic search.

        Extracts text segments from source resource and searches for semantically
        similar resources.

        Args:
            source_resource: Source resource to find similarities for
            limit: Maximum number of similar resources to return
            similarity_threshold: Minimum similarity score

        Returns:
            List of similar resources with similarity scores
        """
        with tracer.start_as_current_span("resource_affinity.find_similar_basic") as span:
            span.set_attribute("tenant.id", self.tenant_id)
            span.set_attribute("resource.id", source_resource.id)
            span.set_attribute("resource.name", source_resource.name)
            span.set_attribute("mode", "basic")
            span.set_attribute("limit", limit)
            span.set_attribute("similarity_threshold", similarity_threshold)

            logger.info(
                f"Finding similar resources for: {source_resource.name} (Basic Mode)"
            )

            if not source_resource.content:
                logger.warning(f"No content in resource: {source_resource.name}")
                span.set_attribute("result.count", 0)
                span.set_attribute("status", "no_content")
                return []

            segments = self._extract_text_segments(source_resource.content)
            span.set_attribute("segments.count", len(segments))

            logger.info(
                f"Extracted {len(segments)} text segments for semantic search"
            )

            all_similar = []

            for i, segment in enumerate(segments):
                add_span_event(span, f"processing_segment_{i}", {"segment_preview": segment[:50]})

                embeddings = self.provider.generate_embeddings_batch([segment])
                embedding = embeddings[0]

                # Build database-agnostic vector search query
                query, params = self._build_vector_search_query(
                    embedding, source_resource.id, limit
                )

                similar = self.provider.execute(query, params)

                for result in similar:
                    similarity_score = 1.0 - float(result["distance"])
                    if similarity_score >= similarity_threshold:
                        result["similarity_score"] = similarity_score
                        result["search_segment"] = segment[:50] + "..."
                        all_similar.append(result)

            unique_results = {}
            for result in all_similar:
                resource_id = result["id"]
                if resource_id not in unique_results:
                    unique_results[resource_id] = result
                else:
                    existing_score = unique_results[resource_id]["similarity_score"]
                    new_score = result["similarity_score"]
                    if new_score > existing_score:
                        unique_results[resource_id] = result

            sorted_results = sorted(
                unique_results.values(),
                key=lambda x: x["similarity_score"],
                reverse=True,
            )[:limit]

            span.set_attribute("result.count", len(sorted_results))
            span.set_attribute("status", "success")

            logger.info(
                f"Found {len(sorted_results)} unique similar resources (Basic Mode)"
            )

            return sorted_results

    async def build_graph_edges_basic(
        self,
        source_resource: Resources,
        similar_resources: list[dict],
    ) -> dict:
        """Build graph edges from source to similar resources.

        Creates InlineEdge objects with human-readable keys.

        Args:
            source_resource: Source resource
            similar_resources: List of similar resources from find_similar_resources_basic

        Returns:
            Updated edges for the source resource
        """
        from p8fs.models.p8 import InlineEdge

        with tracer.start_as_current_span("resource_affinity.build_edges_basic") as span:
            span.set_attribute("tenant.id", self.tenant_id)
            span.set_attribute("resource.id", source_resource.id)
            span.set_attribute("similar_resources.count", len(similar_resources))

            new_edges = []

            for similar in similar_resources:
                target_id = similar["id"]
                target_name = similar["name"]
                target_category = similar.get("category", "unknown")
                similarity_score = similar["similarity_score"]

                # Generate human-readable key from target name
                dst_key = target_name.lower().replace(" ", "-").replace("_", "-")

                # Map similarity score to weight (0.0-1.0)
                # High similarity = high weight
                weight = min(1.0, max(0.3, similarity_score))

                # Create InlineEdge with semantic similarity relationship
                edge = InlineEdge(
                    dst=dst_key,
                    rel_type="semantic_similar",
                    weight=weight,
                    properties={
                        "dst_name": target_name,
                        "dst_id": target_id,
                        "dst_entity_type": f"document/{target_category}" if target_category else "document",
                        "match_type": "semantic-basic",
                        "similarity_score": similarity_score,
                        "confidence": similarity_score,
                    }
                )

                new_edges.append(edge)

                logger.info(
                    f"  → {target_name} (similarity: {similarity_score:.3f}, weight: {weight:.2f})"
                )

            # Merge with existing edges (deduplicate by dst + rel_type)
            merged_edges = self._merge_edges(
                source_resource.graph_paths or [], new_edges
            )

            span.set_attribute("new_edges.count", len(new_edges))
            span.set_attribute("total_edges.count", len(merged_edges))

            logger.info(
                f"Added {len(new_edges)} new edges (total: {len(merged_edges)})"
            )

            return {
                "graph_paths": merged_edges,
                "new_paths_count": len(new_edges),
                "total_paths_count": len(merged_edges),
            }

    async def find_similar_resources_llm(
        self,
        source_resource: Resources,
        limit: int = 5,
    ) -> list[dict]:
        """Find similar resources using LLM-enhanced assessment.

        Uses semantic search to find candidates, then LLM to assess relationships.

        Args:
            source_resource: Source resource to find similarities for
            limit: Maximum number of similar resources to return

        Returns:
            List of similar resources with LLM-assessed relationships
        """
        with tracer.start_as_current_span("resource_affinity.find_similar_llm") as span:
            span.set_attribute("tenant.id", self.tenant_id)
            span.set_attribute("resource.id", source_resource.id)
            span.set_attribute("resource.name", source_resource.name)
            span.set_attribute("mode", "llm")
            span.set_attribute("limit", limit)

            logger.info(
                f"Finding similar resources for: {source_resource.name} (LLM Mode)"
            )

            basic_similar = await self.find_similar_resources_basic(
                source_resource, limit=limit * 2
            )

            if not basic_similar:
                span.set_attribute("result.count", 0)
                span.set_attribute("status", "no_candidates")
                return []

            span.set_attribute("candidates.count", len(basic_similar))
            assessed_resources = []

            for candidate in basic_similar[:limit]:
                prompt = f"""Analyze the relationship between these two resources:

SOURCE RESOURCE:
Name: {source_resource.name}
Category: {source_resource.category}
Content: {source_resource.content[:500]}...

TARGET RESOURCE:
Name: {candidate['name']}
Category: {candidate.get('category')}
Content: {candidate['content'][:500]}...

Assess:
1. What is the semantic relationship? (e.g., similar_topic, contrasting_view, complementary, related_domain)
2. What specific entities or concepts connect them? (e.g., people, projects, topics)
3. What is the relationship strength? (weak, moderate, strong)
4. What are 1-3 meaningful graph edge labels that describe the relationship?

Respond in this format:
Relationship Type: <type>
Connecting Entities: <entity1>, <entity2>, <entity3>
Strength: <weak|moderate|strong>
Edge Labels: <label1>, <label2>, <label3>
Explanation: <brief explanation>
"""

                try:
                    response = await self.memory_proxy.query(
                        model=None,
                        request={"prompt": prompt},
                        prompt=prompt,
                        system_prompt="You are an expert at analyzing semantic relationships between content.",
                    )

                    response_text = (
                        response if isinstance(response, str) else str(response)
                    )

                    assessed = {
                        **candidate,
                        "llm_assessment": response_text,
                        "relationship_type": self._extract_field(
                            response_text, "Relationship Type"
                        ),
                        "connecting_entities": self._extract_field(
                            response_text, "Connecting Entities"
                        ),
                        "strength": self._extract_field(response_text, "Strength"),
                        "edge_labels": self._extract_field(
                            response_text, "Edge Labels"
                        ),
                    }

                    assessed_resources.append(assessed)

                    logger.info(
                        f"  → {candidate['name']} ({assessed.get('relationship_type', 'unknown')} - {assessed.get('strength', 'unknown')})"
                    )

                except Exception as e:
                    logger.error(f"LLM assessment failed for {candidate['name']}: {e}")
                    assessed_resources.append(candidate)

            span.set_attribute("result.count", len(assessed_resources))
            span.set_attribute("status", "success")

            return assessed_resources

    def _extract_field(self, text: str, field_name: str) -> str:
        """Extract field value from LLM response text."""
        try:
            lines = text.split("\n")
            for line in lines:
                if line.startswith(field_name + ":"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return "unknown"

    async def build_graph_edges_llm(
        self,
        source_resource: Resources,
        assessed_resources: list[dict],
    ) -> dict:
        """Build graph edges using LLM-assessed relationships.

        Creates InlineEdge objects with rich LLM-derived metadata.

        Args:
            source_resource: Source resource
            assessed_resources: List of resources from find_similar_resources_llm

        Returns:
            Updated edges for the source resource
        """
        from p8fs.models.p8 import InlineEdge

        with tracer.start_as_current_span("resource_affinity.build_edges_llm") as span:
            span.set_attribute("tenant.id", self.tenant_id)
            span.set_attribute("resource.id", source_resource.id)
            span.set_attribute("assessed_resources.count", len(assessed_resources))

            new_edges = []

            for assessed in assessed_resources:
                target_id = assessed["id"]
                target_name = assessed["name"]
                target_category = assessed.get("category", "unknown")

                relationship_type = assessed.get("relationship_type", "related_to")
                strength = assessed.get("strength", "moderate")
                edge_labels = assessed.get("edge_labels", "")
                connecting_entities = assessed.get("connecting_entities", "")
                llm_assessment = assessed.get("llm_assessment", "")

                # Generate human-readable key from target name
                dst_key = target_name.lower().replace(" ", "-").replace("_", "-")

                # Map LLM strength to weight (0.0-1.0)
                strength_map = {
                    "strong": 0.9,
                    "moderate": 0.6,
                    "weak": 0.4,
                }
                weight = strength_map.get(strength.lower(), 0.5)

                # Use LLM-assessed relationship type or default
                rel_type = relationship_type.lower().replace(" ", "_")

                # Create InlineEdge with LLM-enriched properties
                edge = InlineEdge(
                    dst=dst_key,
                    rel_type=rel_type,
                    weight=weight,
                    properties={
                        "dst_name": target_name,
                        "dst_id": target_id,
                        "dst_entity_type": f"document/{target_category}" if target_category else "document",
                        "match_type": "llm-assessed",
                        "llm_assessed": True,
                        "strength": strength,
                        "edge_labels": edge_labels,
                        "connecting_entities": connecting_entities,
                        "reasoning": llm_assessment[:200] if llm_assessment else None,
                    }
                )

                new_edges.append(edge)

                logger.info(
                    f"  → {target_name} ({rel_type}, {strength}, weight: {weight:.2f})"
                )

            # Merge with existing edges (deduplicate by dst + rel_type)
            merged_edges = self._merge_edges(
                source_resource.graph_paths or [], new_edges
            )

            span.set_attribute("new_edges.count", len(new_edges))
            span.set_attribute("total_edges.count", len(merged_edges))

            logger.info(
                f"Added {len(new_edges)} new edges (total: {len(merged_edges)})"
            )

            return {
                "graph_paths": merged_edges,
                "new_paths_count": len(new_edges),
                "total_paths_count": len(merged_edges),
            }

    async def process_resource_batch(
        self,
        lookback_hours: int = 24,
        batch_size: int = 10,
        mode: str = "basic",
    ) -> dict:
        """Process a batch of resources to build affinity graph.

        Selects random resources from the lookback window and iteratively
        finds similar resources, building graph connections.

        Args:
            lookback_hours: Hours to look back for source resources
            batch_size: Number of resources to process
            mode: "basic" or "llm"

        Returns:
            Processing statistics
        """
        with tracer.start_as_current_span("resource_affinity.process_batch") as span:
            span.set_attribute("tenant.id", self.tenant_id)
            span.set_attribute("mode", mode)
            span.set_attribute("lookback_hours", lookback_hours)
            span.set_attribute("batch_size", batch_size)

            logger.info(f"Processing resource batch (mode={mode}, lookback={lookback_hours}h)")

            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

            random_func = "RAND()" if self.dialect == "tidb" else "RANDOM()"
            resources = self.provider.execute(
                f"""
                SELECT id, name, content, category, graph_paths, resource_timestamp
                FROM resources
                WHERE tenant_id = %s
                  AND resource_timestamp >= %s
                  AND content IS NOT NULL
                ORDER BY {random_func}
                LIMIT %s
                """,
                (self.tenant_id, cutoff_time, batch_size),
            )

            if not resources:
                logger.warning("No resources found in lookback window")
                span.set_attribute("resources.found", 0)
                span.set_attribute("status", "no_resources")
                return {"processed": 0, "updated": 0, "total_edges_added": 0}

            span.set_attribute("resources.found", len(resources))
            logger.info(f"Selected {len(resources)} random resources to process")

            stats = {
                "processed": 0,
                "updated": 0,
                "total_edges_added": 0,
                "mode": mode,
            }

            for resource_data in resources:
                resource = Resources(**resource_data)

                logger.info(f"\nProcessing: {resource.name}")
                add_span_event(span, "processing_resource", {
                    "resource.id": resource.id,
                    "resource.name": resource.name,
                    "resource.category": resource.category or "unknown"
                })

                try:
                    if mode == "llm":
                        similar = await self.find_similar_resources_llm(resource, limit=3)
                        if similar:
                            update_data = await self.build_graph_edges_llm(resource, similar)
                        else:
                            update_data = None
                    else:
                        similar = await self.find_similar_resources_basic(resource, limit=3)
                        if similar:
                            update_data = await self.build_graph_edges_basic(resource, similar)
                        else:
                            update_data = None

                    stats["processed"] += 1

                    if update_data and update_data["new_paths_count"] > 0:
                        # Build database-agnostic update query (graph_paths stores InlineEdge objects as JSONB)
                        query, params = self._build_graph_paths_update_query(
                            update_data["graph_paths"], resource.id
                        )
                        self.provider.execute(query, params)

                        stats["updated"] += 1
                        stats["total_edges_added"] += update_data["new_paths_count"]

                        logger.info(
                            f"✓ Updated {resource.name} with {update_data['new_paths_count']} new edges"
                        )
                        add_span_event(span, "resource_updated", {
                            "resource.id": resource.id,
                            "new_paths": update_data["new_paths_count"],
                            "total_paths": update_data["total_paths_count"]
                        })
                except Exception as e:
                    logger.error(f"Error processing {resource.name}: {e}")
                    mark_span_as_error(span, str(e))
                    add_span_event(span, "resource_failed", {
                        "resource.id": resource.id,
                        "error": str(e)
                    })

            span.set_attribute("stats.processed", stats["processed"])
            span.set_attribute("stats.updated", stats["updated"])
            span.set_attribute("stats.total_edges_added", stats["total_edges_added"])
            span.set_attribute("status", "success")

            logger.info(f"\n{'=' * 80}")
            logger.info(f"BATCH PROCESSING COMPLETE ({mode.upper()} MODE)")
            logger.info(f"{'=' * 80}")
            logger.info(f"Processed: {stats['processed']} resources")
            logger.info(f"Updated: {stats['updated']} resources")
            logger.info(f"Total edges added: {stats['total_edges_added']}")
            logger.info(f"{'=' * 80}\n")

            return stats
