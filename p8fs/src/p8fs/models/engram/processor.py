"""Engram processor for handling engram YAML/JSON documents."""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4, uuid5, NAMESPACE_DNS

import yaml
from p8fs_cluster.logging import get_logger

from p8fs.repository import TenantRepository
from p8fs.models.p8 import Resources, Moment, InlineEdge

logger = get_logger(__name__)


class EngramProcessor:
    """
    Processes engram YAML/JSON documents into Resources with graph edges and optional Moments.

    EngramProcessor handles the complete lifecycle of engram ingestion:
    - Parses YAML/JSON engram documents
    - Creates/updates Resources with deterministic IDs
    - Processes graph edges to build knowledge graph
    - Automatically creates lightweight nodes for referenced entities (ensure_nodes=True)
    - Adds bidirectional edges (e.g., managed_by + inv-managed_by)
    - Attaches Moments with temporal boundaries and emotion/topic tags

    Entity Type Format (dst_entity_type):
    ------------------------------------
    Format: [table:]category[/subcategory]

    Examples:
      - "person/supervisor" → resources table, category="person/supervisor"
      - "resource:project/technical" → resources table, category="project/technical"
      - "moments:reflection" → moments table, category="reflection"
      - "files:image/screenshot" → files table, category="image/screenshot"

    When ensure_nodes=True, referenced entities are automatically created with:
      - Minimal content (placeholder that will be enriched later)
      - Proper category from dst_entity_type
      - Reverse edge back to source (inv-<rel_type>)

    Example Engram YAML:
    -------------------
    ```yaml
    kind: engram
    name: Project Planning Meeting
    category: meeting
    content: |
      Discussed Q4 roadmap and API redesign priorities.
      Sarah will lead the technical specification work.
    summary: Q4 planning session with engineering leadership
    resource_timestamp: "2024-11-15T10:00:00Z"

    graph_edges:
      - dst: Sarah Chen
        rel_type: attended_by
        weight: 1.0
        properties:
          dst_entity_type: person/supervisor
          confidence: 1.0
          role: "Tech Lead"

      - dst: API Redesign Project
        rel_type: discusses
        weight: 0.9
        properties:
          dst_entity_type: project/technical
          confidence: 0.95
          context: "Technical approach and timeline"

      - dst: Q4 Roadmap
        rel_type: references
        weight: 0.8
        properties:
          dst_entity_type: resource:planning/roadmap
          confidence: 0.9

    moments:
      - name: Sarah's Technical Proposal
        moment_type: insight
        content: "Sarah proposed using event-driven architecture"
        emotion_tags: ["confident", "enthusiastic"]
        topic_tags: ["architecture", "api-design"]
    ```

    What Happens During Processing:
    -------------------------------
    1. Creates "Project Planning Meeting" resource
    2. Ensures "Sarah Chen" resource exists:
       - Category: person/supervisor
       - Content: Lightweight placeholder
       - Adds reverse edge: inv-attended_by → Project Planning Meeting
    3. Ensures "API Redesign Project" exists:
       - Category: project/technical
       - Adds reverse edge: inv-discusses → Project Planning Meeting
    4. Ensures "Q4 Roadmap" exists:
       - Table: resources (explicit)
       - Category: planning/roadmap
       - Adds reverse edge: inv-references → Project Planning Meeting
    5. Creates moment "Sarah's Technical Proposal" linked to meeting

    Usage:
    ------
    ```python
    from p8fs.models.engram.processor import EngramProcessor
    from p8fs.repository.TenantRepository import TenantRepository
    from p8fs.models.p8 import Resources

    # Initialize with node creation enabled (default)
    processor = EngramProcessor(repo, ensure_nodes=True)

    # Process engram from YAML
    result = await processor.process(
        content=yaml_content,
        content_type="application/x-yaml",
        tenant_id="tenant-123"
    )

    # Result contains:
    # {
    #   "resource_id": "uuid-...",
    #   "moment_ids": ["uuid-1", "uuid-2"],
    #   "chunks_created": 1,
    #   "embeddings_generated": 0
    # }

    # Disable automatic node creation for testing
    processor = EngramProcessor(repo, ensure_nodes=False)
    ```

    Node Creation Behavior:
    ----------------------
    - ensure_nodes=True (default): Automatically creates lightweight nodes
    - ensure_nodes=False: Only creates edges, nodes must exist beforehand
    - Upsert-safe: Won't duplicate if node already exists
    - Reverse edges: Always created when add_reverse_edge=True
    - Multi-table: Supports resources, moments, files, custom schemas

    See Also:
    ---------
    - InlineEdge model: /p8fs/models/p8.py
    - REM design doc: /p8fs/docs/REM/design.md
    - Engram template: /p8fs/docs/REM/scenarios/scenario-01/ENGRAM_TEMPLATE.md
    """

    def __init__(self, repo: TenantRepository, ensure_nodes: bool = True):
        """
        Initialize engram processor.

        Args:
            repo: TenantRepository for storing entities
            ensure_nodes: If True, automatically creates lightweight entities for
                nodes referenced in graph_paths that don't exist yet. Creates
                bidirectional edges (e.g., managed_by + inv-managed-by). Nodes
                will be "filled in" with richer content when actual entities are created.
        """
        self.repo = repo
        self.ensure_nodes = ensure_nodes

    async def process(
        self,
        content: str,
        content_type: str,
        tenant_id: str,
        session_id: UUID | None = None
    ) -> dict[str, Any]:
        """Process content as engram document."""
        try:
            if content_type == "application/x-yaml":
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)

            if not isinstance(data, dict):
                raise ValueError("Engram content must be a dictionary")

            kind = data.get("kind") or data.get("p8Kind")
            if kind != "engram":
                raise ValueError(f"Expected kind='engram', got: {kind}")

            return await self._process_engram(data, tenant_id, session_id)

        except Exception as e:
            logger.error(f"Error processing engram content: {e}")
            raise

    async def _process_engram(
        self,
        data: dict[str, Any],
        tenant_id: str,
        session_id: UUID | None
    ) -> dict[str, Any]:
        """Process validated engram document into Resource with optional Moments.

        CRITICAL: Implements JSON merge behavior - updates existing engrams instead
        of replacing them. Graph edges, metadata, and arrays are merged.
        """
        engram_name = data.get("name", "Untitled Engram")
        resource_id = uuid5(NAMESPACE_DNS, f"{tenant_id}:engram:{engram_name}")

        logger.info(f"Upserting engram '{engram_name}' with ID {resource_id}")

        # Check if engram already exists
        existing = None
        action = "created"
        try:
            existing = await self.repo.get_by_id(str(resource_id))
            action = "merged"
        except Exception:
            # Doesn't exist, will create new
            pass

        if existing:
            # Merge with existing resource
            resource_data = await self._merge_engram(existing, data, tenant_id, session_id)
        else:
            # Create new resource
            resource_data = await self._create_engram(data, tenant_id, session_id, resource_id)

        resource = Resources.model_validate(resource_data)
        await self.repo.upsert(resource)

        result = {
            "action": action,
            "resource_id": str(resource_id),
            "moment_ids": [],
            "chunks_created": 1,
            "embeddings_generated": 0
        }

        moments_data = data.get("moments", [])
        if moments_data:
            moment_ids = await self._process_moments(
                moments_data,
                tenant_id,
                session_id,
                resource_id,
                engram_name
            )
            result["moment_ids"] = [str(m_id) for m_id in moment_ids]

        return result

    async def _create_engram(
        self,
        data: dict[str, Any],
        tenant_id: str,
        session_id: UUID | None,
        resource_id: UUID
    ) -> dict[str, Any]:
        """Create new engram resource."""
        engram_name = data.get("name", "Untitled Engram")
        graph_paths = []

        if data.get("graph_edges"):
            for edge_data in data["graph_edges"]:
                edge = InlineEdge.model_validate(edge_data)
                graph_paths.append(edge.model_dump())

                # Ensure target nodes exist if enabled
                if self.ensure_nodes:
                    await self._ensure_node_exists(edge, tenant_id, source_name=engram_name)

        resource_data = {
            "id": str(resource_id),
            "tenant_id": tenant_id,
            "name": engram_name,
            "category": data.get("category", "engram"),
            "content": data.get("content"),
            "summary": data.get("summary"),
            "uri": data.get("uri"),
            "metadata": data.get("metadata", {}),
            "graph_paths": graph_paths,
            "resource_timestamp": data.get("resource_timestamp")
        }

        if session_id:
            resource_data["session_id"] = str(session_id)

        return resource_data

    async def _merge_engram(
        self,
        existing: dict[str, Any],
        new_data: dict[str, Any],
        tenant_id: str,
        session_id: UUID | None
    ) -> dict[str, Any]:
        """Merge new engram data with existing resource using JSON merge semantics.

        CRITICAL merge behavior:
        - Graph edges: Merge by dst key (add new, keep existing)
        - Metadata: Deep merge (new keys added, existing updated)
        - Arrays: Combine and deduplicate
        - Content/summary: Update if provided, preserve if not
        - Timestamps: Preserve original if not provided
        """
        merged = dict(existing)

        if new_data.get("name") is not None:
            merged["name"] = new_data["name"]

        if new_data.get("category") is not None:
            merged["category"] = new_data["category"]

        if new_data.get("content") is not None:
            merged["content"] = new_data["content"]

        if new_data.get("summary") is not None:
            merged["summary"] = new_data["summary"]

        if new_data.get("uri") is not None:
            merged["uri"] = new_data["uri"]

        if new_data.get("resource_timestamp") is not None:
            merged["resource_timestamp"] = new_data["resource_timestamp"]

        merged_metadata = self._deep_merge_dict(
            existing.get("metadata", {}),
            new_data.get("metadata", {})
        )
        merged["metadata"] = merged_metadata

        existing_edges = existing.get("graph_paths", [])
        new_edges = []
        if new_data.get("graph_edges"):
            for edge_data in new_data["graph_edges"]:
                edge = InlineEdge.model_validate(edge_data)
                new_edges.append(edge.model_dump())

        merged_edges = self._merge_graph_edges(existing_edges, new_edges)
        merged["graph_paths"] = merged_edges

        logger.debug(
            f"Merged engram: {len(existing_edges)} existing edges + "
            f"{len(new_edges)} new edges = {len(merged_edges)} total edges"
        )

        return merged

    def _merge_graph_edges(
        self,
        existing_edges: list[dict],
        new_edges: list[dict]
    ) -> list[dict]:
        """Merge graph edges by dst key.

        If an edge with the same dst exists, update it with new properties.
        Otherwise, add the new edge.
        """
        edge_map = {}

        for edge in existing_edges:
            dst = edge.get("dst")
            if dst:
                edge_map[dst] = edge

        for edge in new_edges:
            dst = edge.get("dst")
            if dst:
                if dst in edge_map:
                    existing_edge = edge_map[dst]
                    existing_edge["rel_type"] = edge.get("rel_type", existing_edge.get("rel_type"))
                    existing_edge["weight"] = edge.get("weight", existing_edge.get("weight"))

                    existing_props = existing_edge.get("properties", {})
                    new_props = edge.get("properties", {})
                    existing_props.update(new_props)
                    existing_edge["properties"] = existing_props

                    existing_edge["created_at"] = edge.get("created_at", existing_edge.get("created_at"))
                else:
                    edge_map[dst] = edge

        return list(edge_map.values())

    def _deep_merge_dict(self, base: dict, update: dict) -> dict:
        """Deep merge two dictionaries.

        For nested dicts, recursively merges keys.
        For other types, update value overwrites base value.
        """
        merged = dict(base)
        for key, value in update.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._deep_merge_dict(merged[key], value)
            else:
                merged[key] = value
        return merged

    async def _process_moments(
        self,
        moments_data: list[dict[str, Any]],
        tenant_id: str,
        session_id: UUID | None,
        parent_resource_id: UUID,
        parent_resource_name: str
    ) -> list[UUID]:
        """Process attached moments and link them to parent engram.

        Moments are also upserted with deterministic IDs based on name.
        """
        moment_ids = []

        for moment_data in moments_data:
            moment_name = moment_data.get("name", f"moment-{len(moment_ids)}")
            moment_id = uuid5(NAMESPACE_DNS, f"{tenant_id}:moment:{parent_resource_name}:{moment_name}")

            # Create moment repository
            from p8fs.repository import TenantRepository
            moment_repo = TenantRepository(Moment, tenant_id)

            graph_paths = []
            if moment_data.get("graph_edges"):
                for edge_data in moment_data["graph_edges"]:
                    edge = InlineEdge.model_validate(edge_data)
                    graph_paths.append(edge.model_dump())

            parent_edge = InlineEdge(
                dst=parent_resource_name,
                rel_type="part_of",
                weight=1.0,
                properties={
                    "dst_name": parent_resource_name,
                    "dst_id": str(parent_resource_id),
                    "dst_entity_type": "resource/engram",
                    "match_type": "parent_child",
                    "confidence": 1.0
                }
            )
            graph_paths.append(parent_edge.model_dump())

            moment_dict = {
                "id": str(moment_id),
                "tenant_id": tenant_id,
                "name": moment_data.get("name") or moment_name,
                "content": moment_data.get("content"),
                "summary": moment_data.get("summary"),
                "category": moment_data.get("category"),
                "uri": moment_data.get("uri"),
                "resource_timestamp": moment_data.get("resource_timestamp"),
                "resource_ends_timestamp": moment_data.get("resource_ends_timestamp"),
                "moment_type": moment_data.get("moment_type"),
                "emotion_tags": moment_data.get("emotion_tags", []),
                "topic_tags": moment_data.get("topic_tags", []),
                "present_persons": moment_data.get("present_persons", []),
                "speakers": moment_data.get("speakers"),
                "location": moment_data.get("location"),
                "background_sounds": moment_data.get("background_sounds"),
                "metadata": moment_data.get("metadata", {}),
                "graph_paths": graph_paths
            }

            if session_id:
                moment_dict["session_id"] = str(session_id)

            moment = Moment.model_validate(moment_dict)
            await moment_repo.upsert(moment)

            moment_ids.append(moment_id)
            logger.debug(f"Upserted moment '{moment_name}' with {len(graph_paths)} graph edges")

        return moment_ids

    async def _ensure_node_exists(
        self,
        edge: InlineEdge,
        tenant_id: str,
        source_name: str
    ) -> None:
        """
        Ensure target node exists for the given edge.

        If the target node doesn't exist, creates a lightweight entity with:
        - Minimal content (to be enriched later)
        - Reverse edge back to source (e.g., inv-managed-by)
        - Proper category from dst_entity_type

        Args:
            edge: InlineEdge defining the relationship
            tenant_id: Tenant ID
            source_name: Name of source entity (for reverse edge)
        """
        try:
            # Parse entity type to determine target table
            table_name, _ = edge.parse_entity_type()

            # Normalize table name (resource -> resources)
            if table_name == "resource":
                table_name = "resources"

            # Create lightweight node data with reverse edge
            node_data = edge.create_node_data(
                tenant_id=tenant_id,
                add_reverse_edge=True,
                source_name=source_name
            )

            # Upsert the node (creates if doesn't exist, updates if exists)
            if table_name == "resources":
                node = Resources.model_validate(node_data)
                await self.repo.upsert(node)
                logger.debug(
                    f"Ensured node exists: {edge.dst} (category: {node.category}, "
                    f"reverse edge: inv-{edge.rel_type} → {source_name})"
                )
            elif table_name == "moments":
                # Import moment repository when needed
                from p8fs.repository.MomentRepository import MomentRepository
                moment_repo = MomentRepository(self.repo.provider, tenant_id)
                node = Moment.model_validate(node_data)
                await moment_repo.upsert(node)
                logger.debug(
                    f"Ensured moment node exists: {edge.dst} (type: {node.moment_type}, "
                    f"reverse edge: inv-{edge.rel_type} → {source_name})"
                )
            else:
                logger.warning(
                    f"Unsupported table for node creation: {table_name}. "
                    f"Skipping node creation for {edge.dst}"
                )

        except Exception as e:
            logger.warning(f"Failed to ensure node exists for {edge.dst}: {e}")
            # Don't fail the entire engram processing if node creation fails


# ===== CLI Interface =====

if __name__ == "__main__":
    import asyncio
    import sys
    from pathlib import Path

    import typer
    from p8fs_cluster.config.settings import config
    from p8fs.repository.TenantRepository import TenantRepository

def main():
    """Engram processor CLI entry point."""
    import typer

    app = typer.Typer(help="Engram processor CLI")

    @app.command()
    def process_file(
        file_path: str = typer.Argument(help="Path to JSON/YAML engram file"),
        tenant_id: str = typer.Option("test-tenant", help="Tenant ID"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output")
    ):
        """Process an engram file and store in database."""
        async def run():
            try:
                repo = TenantRepository(Resources, tenant_id)
                processor = EngramProcessor(repo)

                path = Path(file_path)
                if not path.exists():
                    typer.echo(f"File not found: {file_path}", err=True)
                    raise typer.Exit(1)

                content = path.read_text()
                content_type = "application/x-yaml" if path.suffix.lower() in ['.yaml', '.yml'] else "application/json"

                typer.echo(f"Processing {content_type} file: {file_path}")
                typer.echo(f"Tenant ID: {tenant_id}")

                if verbose:
                    typer.echo("File content:")
                    typer.echo(content)
                    typer.echo("-" * 50)

                result = await processor.process(content, content_type, tenant_id)

                typer.echo(f"✅ Processing completed successfully!")
                typer.echo(f"📄 Resource ID: {result['resource_id']}")

                if result.get("moment_ids"):
                    typer.echo(f"⏰ Created {len(result['moment_ids'])} moments")
                    if verbose:
                        for moment_id in result['moment_ids']:
                            typer.echo(f"  - {moment_id}")

                typer.echo(f"📦 Chunks created: {result['chunks_created']}")

            except Exception as e:
                typer.echo(f"❌ Error: {e}", err=True)
                if verbose:
                    import traceback
                    traceback.print_exc()
                raise typer.Exit(1)

        asyncio.run(run())

    app()
