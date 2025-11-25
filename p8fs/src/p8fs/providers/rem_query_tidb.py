"""
REM Query Provider for TiDB - Production implementation with real embeddings.

Implements Resource-Entity-Moment query semantics using existing TiDB provider.
Uses TiDB's native VECTOR type and VEC_* functions for semantic search.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


# Import models from PostgreSQL version (they're provider-agnostic)
from .rem_query import (
    QueryType,
    QueryParameters,
    LookupParameters,
    SearchParameters,
    SQLParameters,
    TraverseParameters,
    REMQueryPlan,
)


class TiDBREMQueryProvider:
    """
    REM query provider using existing TiDB provider.

    Provides unified query interface across:
    - LOOKUP: Key-based retrieval
    - SEARCH: Semantic vector search with TiDB VEC_* functions
    - SQL: Standard SELECT queries
    - TRAVERSE: Graph traversal using recursive CTEs (no native AGE)
    """

    def __init__(self, tidb_provider, tenant_id: str = "tenant-test"):
        """
        Initialize with existing TiDB provider.

        Args:
            tidb_provider: TiDBProvider instance
            tenant_id: Default tenant ID for multi-tenant isolation
        """
        self.provider = tidb_provider
        self.tenant_id = tenant_id

    @staticmethod
    def get_dialect_hints() -> str:
        """Return TiDB-specific dialect hints for REM query generation."""
        return """TiDB Dialect Hints:
- Vector search: Use VEC_COSINE_DISTANCE() function
  Example: ORDER BY VEC_COSINE_DISTANCE(embedding, query_vector) LIMIT 10
- Date queries: Use DATE_SUB() function
  Example: WHERE created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
- JSON tags: Use JSON_CONTAINS() function
  Example: WHERE JSON_CONTAINS(tags, '"database"')

System Fields (available on all tables):
- created_at, updated_at: Timestamp fields (use in WHERE, ORDER BY)
- graph_paths: JSON array of relationships (SELECT only, not for WHERE predicates)
  Example: SELECT id, name, graph_paths FROM resources WHERE created_at > DATE_SUB(NOW(), INTERVAL 1 DAY)"""

    def execute(self, plan: REMQueryPlan) -> List[Dict[str, Any]]:
        """
        Execute REM query plan.

        Args:
            plan: REM query plan with type and parameters

        Returns:
            List of result dictionaries
        """
        if plan.query_type == QueryType.LOOKUP:
            return self._execute_lookup(plan.parameters)
        elif plan.query_type == QueryType.SEARCH:
            return self._execute_search(plan.parameters)
        elif plan.query_type == QueryType.SQL:
            return self._execute_sql(plan.parameters)
        elif plan.query_type == QueryType.TRAVERSE:
            return self._execute_traverse(plan.parameters)
        else:
            raise ValueError(f"Unsupported query type: {plan.query_type}")

    def _execute_lookup(self, params: LookupParameters) -> List[Dict[str, Any]]:
        """
        Execute schema-agnostic lookup using TiKV reverse mapping.

        CRITICAL: LOOKUP is KV-ONLY. It does NOT use SQL.

        Flow:
        1. Scan TiKV for "{tenant_id}/{entity_name}/{entity_type}" keys
        2. For each KV entry, retrieve stored entity_id (UUID)
        3. Fetch entity from table using stored UUID (or binary key if available)
        4. If not in KV, return empty results (provider must populate KV separately)

        Key Difference from SQL:
        - SQL: SELECT * FROM resources WHERE name='test' (single table, requires table name)
        - LOOKUP: Find ALL entities named 'test' (all tables, no schema knowledge needed)

        Example:
        - resources table has name="my-project" (id=uuid-1)
        - moments table has name="my-project" (id=uuid-2)
        - KV stores: "tenant-a/my-project/resource" -> {entity_id: uuid-1, table_name: "resources"}
        - KV stores: "tenant-a/my-project/moment" -> {entity_id: uuid-2, table_name: "moments"}
        - LOOKUP("my-project") returns BOTH records!
        """
        tenant_id = params.tenant_id or self.tenant_id
        all_results = []

        # Scan for all "{tenant_id}/{entity_name}/{entity_type}" keys to find all entity types
        # Tenant prefix ensures we only scan within tenant's namespace
        name_prefix = f"{tenant_id}/{params.key}/"

        try:
            # Scan TiKV for all name keys matching this prefix
            if hasattr(self.provider, 'tikv_reverse_mapping'):
                # Use TiKV's native scan
                entity_mappings = self.provider.tikv_reverse_mapping.tikv.scan(
                    name_prefix, tenant_id, limit=100
                )

                logger.debug(f"Found {len(entity_mappings)} entity types for '{params.key}'")

                # For each entity type found, fetch using stored entity_id
                for name_key, name_mapping in entity_mappings:
                    if not isinstance(name_mapping, dict):
                        continue

                    entity_type = name_mapping.get('entity_type')
                    table_name = name_mapping.get('table_name')
                    entity_id = name_mapping.get('entity_id')

                    if not entity_type or not table_name or not entity_id:
                        logger.debug(f"Skipping incomplete KV entry: {name_key}")
                        continue

                    # If table-specific lookup, filter by table name
                    if params.table_name and table_name != params.table_name:
                        logger.debug(f"Skipping {table_name} (looking for {params.table_name})")
                        continue

                    entity_data = None

                    # Try direct TiKV binary key access first (O(1)) if available
                    tidb_key = name_mapping.get('tidb_key')
                    if tidb_key:
                        try:
                            if isinstance(tidb_key, str):
                                tidb_key_bytes = bytes.fromhex(tidb_key)
                            else:
                                tidb_key_bytes = tidb_key

                            entity_data = self.provider.get_by_binary_key(tidb_key_bytes)
                            if entity_data:
                                logger.debug(f"Retrieved {entity_type}/{params.key} via binary key (O(1))")
                        except Exception as e:
                            logger.debug(f"Binary key access failed for {entity_type}: {e}")

                    # Fallback to SQL using stored entity_id (UUID)
                    if not entity_data:
                        try:
                            fields = ", ".join(params.fields) if params.fields else "*"
                            # Use stored entity_id (UUID), NOT the human-readable name
                            sql = f"SELECT {fields} FROM {table_name} WHERE id = %s AND tenant_id = %s"
                            results = self.provider.execute(sql, tuple([entity_id, tenant_id]))

                            if results:
                                entity_data = results[0] if len(results) > 0 else None
                        except Exception as e:
                            logger.debug(f"SQL fetch failed for {entity_type}: {e}")

                    if entity_data:
                        # Annotate with entity type for multi-table results
                        entity_data['_entity_type'] = entity_type
                        entity_data['_table_name'] = table_name
                        all_results.append(entity_data)

                        logger.debug(f"Found {entity_type}: {params.key} (id={entity_id})")

                return all_results

        except Exception as e:
            logger.debug(f"Reverse key lookup failed: {e}")

        # LOOKUP is KV-ONLY - no SQL fallback
        # If entity not in KV, provider must populate it separately
        return []

    def _execute_search(self, params: SearchParameters) -> List[Dict[str, Any]]:
        """
        Execute semantic search using TiDB VEC_* functions.

        Uses provider's generate_embeddings_batch for real embedding generation
        and TiDB's native VEC_COSINE_DISTANCE for vector search.
        """
        tenant_id = params.tenant_id or self.tenant_id

        # Generate real embedding using provider's embedding service
        try:
            embeddings = self.provider.generate_embeddings_batch([params.query_text])
            query_embedding = embeddings[0]
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

        # Build semantic search SQL with TiDB native VECTOR type
        embedding_table = f"embeddings.{params.table_name}_embeddings"

        # Convert query embedding to vector string format: "[0.1,0.2,...]"
        query_vector_str = f"[{','.join(map(str, query_embedding))}]"

        # Get distance function based on metric
        if params.metric == "cosine":
            distance_fn = "VEC_COSINE_DISTANCE"
        elif params.metric == "l2":
            distance_fn = "VEC_L2_DISTANCE"
        elif params.metric == "inner_product":
            distance_fn = "VEC_NEGATIVE_INNER_PRODUCT"
        else:
            distance_fn = "VEC_COSINE_DISTANCE"

        where_conditions = []
        sql_params = []

        if params.embedding_field:
            where_conditions.append("e.field_name = %s")
            sql_params.append(params.embedding_field)

        if tenant_id:
            where_conditions.append("m.tenant_id = %s")
            where_conditions.append("e.tenant_id = %s")
            sql_params.extend([tenant_id, tenant_id])

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        # TiDB native VECTOR type - use embedding_vector column directly
        sql = f"""
            SELECT m.*, e.field_name,
                   {distance_fn}(e.embedding_vector, %s) as distance,
                   (1 - {distance_fn}(e.embedding_vector, %s)) as similarity
            FROM {params.table_name} m
            INNER JOIN {embedding_table} e ON m.id = e.entity_id
            WHERE {where_clause}
            ORDER BY {distance_fn}(e.embedding_vector, %s)
            LIMIT %s
        """

        # Build final parameters: query_vector for distance, similarity, order by, then where params, then limit
        final_params = [query_vector_str, query_vector_str] + sql_params + [query_vector_str, params.limit]

        results = self.provider.execute(sql, tuple(final_params))
        return results

    def _execute_sql(self, params: SQLParameters) -> List[Dict[str, Any]]:
        """
        Execute SQL SELECT query.
        """
        fields = ", ".join(params.select_fields)
        sql = f"SELECT {fields} FROM {params.table_name}"

        where_clauses = []
        tenant_id = params.tenant_id or self.tenant_id

        # Add tenant filter
        where_clauses.append(f"tenant_id = '{tenant_id}'")

        # Add custom where clause
        if params.where_clause:
            where_clauses.append(f"({params.where_clause})")

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        # Add ORDER BY
        if params.order_by:
            sql += " ORDER BY " + ", ".join(params.order_by)

        # Add LIMIT
        if params.limit:
            sql += f" LIMIT {params.limit}"

        results = self.provider.execute(sql, None)
        return results

    def _execute_traverse(self, params: TraverseParameters) -> Dict[str, Any]:
        """
        Execute multi-hop graph traversal using LOOKUP/SEARCH/SQL + edge following.

        TRAVERSE orchestrates multiple queries:
        1. Execute initial query (LOOKUP, SEARCH, or SQL) to find entry entities
        2. Examine graph_paths field on results
        3. Filter edges by type if specified
        4. Sort edges by order_by_edge_field and order_direction
        5. LOOKUP target keys from edges
        6. Optionally repeat for depth > 1
        7. Apply result_limit

        Returns enhanced response with stages, edge_summary, and metadata.
        """
        tenant_id = params.tenant_id or self.tenant_id
        all_results = []
        visited_keys = set()
        stages = []
        edge_summary = []
        source_node_keys = []

        logger.info(f"TRAVERSE Stage 1: Executing initial {params.initial_query_type} query")

        # Stage 1: Execute initial query to find entry entities
        if params.initial_query_type == "lookup":
            lookup_params = LookupParameters(
                key=params.initial_query,
                table_name=params.table_name,
                tenant_id=tenant_id
            )
            initial_entities = self._execute_lookup(lookup_params)
        elif params.initial_query_type == "search":
            search_params = SearchParameters(
                query_text=params.initial_query,
                table_name=params.table_name,
                tenant_id=tenant_id,
                limit=100
            )
            initial_entities = self._execute_search(search_params)
        elif params.initial_query_type == "sql":
            sql_params = SQLParameters(
                select_fields=["*"],
                table_name=params.table_name,
                where_clause=params.initial_query if isinstance(params.initial_query, str) else params.initial_query[0],
                tenant_id=tenant_id,
                limit=100
            )
            initial_entities = self._execute_sql(sql_params)
        else:
            raise ValueError(f"Invalid initial_query_type: {params.initial_query_type}")

        if not initial_entities:
            logger.info(f"TRAVERSE: No entities found in initial query")
            return {
                "nodes": [],
                "stages": [{
                    "depth": 0,
                    "executed": f"{params.initial_query_type.upper()} {params.initial_query}",
                    "found": {"nodes": 0, "edges": 0},
                    "plan_memo": params.plan_memo
                }],
                "source_nodes": [],
                "edge_summary": [],
                "metadata": {
                    "total_nodes": 0,
                    "total_nodes_before_limit": 0,
                    "total_edges": 0,
                    "unique_nodes": 0,
                    "node_uniqueness_guaranteed": True,
                    "max_depth_reached": 0,
                    "edge_filter": params.edge_types,
                    "query_plan_memo": params.plan_memo,
                    "result_limit": params.result_limit,
                    "limit_applied": False
                }
            }

        # PLAN mode (depth=0 or plan_mode flag): Return edge analysis without full traversal
        if params.max_depth == 0 or params.plan_mode:
            return self._analyze_edges(initial_entities, params.edge_types)

        # Count initial edges for stage tracking
        initial_edge_count = sum(len(e.get('graph_paths', [])) for e in initial_entities)

        # Add initial entities to results with metadata
        for entity in initial_entities:
            key = entity.get('name') or entity.get('id')
            if key:
                visited_keys.add(key)
                source_node_keys.append(key)
            entity['_traverse_depth'] = 0
            entity['_traverse_path'] = [key]
            all_results.append(entity)

        # Add stage 0 info
        stages.append({
            "depth": 0,
            "executed": f"{params.initial_query_type.upper()} {params.initial_query}",
            "found": {"nodes": len(initial_entities), "edges": initial_edge_count},
            "plan_memo": params.plan_memo
        })

        # Stage 2+: Follow edges for each depth level
        current_entities = initial_entities
        for depth in range(1, params.max_depth + 1):
            logger.info(f"TRAVERSE Stage 2: Following edges at depth {depth}")
            next_keys = set()
            edges_followed = []

            # Examine graph_paths for each entity at current depth
            for entity in current_entities:
                entity_key = entity.get('name') or entity.get('id')
                graph_paths = entity.get('graph_paths', [])

                # Handle JSON string format (TiDB returns JSON as strings)
                if isinstance(graph_paths, str):
                    import json
                    try:
                        graph_paths = json.loads(graph_paths)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse graph_paths: {graph_paths}")
                        continue

                if not graph_paths:
                    continue

                # Collect edges with metadata for sorting
                entity_edges = []
                for edge in graph_paths:
                    if isinstance(edge, dict):
                        edge_type = edge.get('rel_type') or edge.get('type')  # Support both field names
                        target = edge.get('dst')

                        # Filter by edge type if specified
                        if params.edge_types and edge_type not in params.edge_types:
                            continue

                        if target and target not in visited_keys:
                            entity_edges.append({
                                'target': target,
                                'edge_type': edge_type,
                                'created_at': edge.get('created_at'),
                                'weight': edge.get('weight', 1.0),
                                'properties': edge.get('properties', {})
                            })
                    elif isinstance(edge, str):
                        # Simple string edges (just keys)
                        if edge not in visited_keys:
                            entity_edges.append({
                                'target': edge,
                                'edge_type': 'edge',
                                'created_at': None,
                                'weight': 1.0,
                                'properties': {}
                            })

                # Sort edges by specified field and direction
                if entity_edges:
                    order_field = params.order_by_edge_field
                    reverse = (params.order_direction.upper() == "DESC")

                    # Handle None values in sorting (put them last)
                    entity_edges.sort(
                        key=lambda e: (e.get(order_field) is None, e.get(order_field) or ""),
                        reverse=reverse
                    )

                    # Follow sorted edges
                    for edge in entity_edges:
                        target = edge['target']
                        edge_type = edge['edge_type']
                        next_keys.add(target)
                        edges_followed.append((entity_key, edge_type, target))
                        edge_summary.append([entity_key, edge_type, target])

            if not next_keys:
                logger.info(f"TRAVERSE: No new edges found at depth {depth}")
                stages.append({
                    "depth": depth,
                    "executed": "No edges to follow",
                    "found": {"nodes": 0, "edges": 0},
                    "plan_memo": params.plan_memo
                })
                break

            # LOOKUP next level entities
            lookup_params = LookupParameters(
                key=list(next_keys),
                table_name=params.table_name,
                tenant_id=tenant_id
            )
            next_entities = self._execute_lookup(lookup_params)

            # Add depth and path metadata
            for entity in next_entities:
                entity_key = entity.get('name') or entity.get('id')
                if entity_key:
                    visited_keys.add(entity_key)

                entity['_traverse_depth'] = depth
                entity['_traverse_path'] = ['...', entity_key]
                all_results.append(entity)

            # Add stage info for this depth
            edge_types_followed = {}
            for _, edge_type, _ in edges_followed:
                edge_types_followed[edge_type] = edge_types_followed.get(edge_type, 0) + 1

            stages.append({
                "depth": depth,
                "executed": f"LOOKUP {len(next_keys)} targets via {list(edge_types_followed.keys())}",
                "found": {"nodes": len(next_entities), "edges": len(edges_followed)},
                "edge_types": edge_types_followed,
                "plan_memo": params.plan_memo
            })

            current_entities = next_entities

        logger.info(f"TRAVERSE: Completed with {len(all_results)} total entities across {params.max_depth} hops")

        # Apply result limit
        total_nodes_before_limit = len(all_results)
        limited_nodes = all_results[:params.result_limit] if params.result_limit else all_results

        # Return enhanced response structure
        return {
            "nodes": limited_nodes,
            "stages": stages,
            "source_nodes": source_node_keys,
            "edge_summary": edge_summary,
            "metadata": {
                "total_nodes": len(limited_nodes),
                "total_nodes_before_limit": total_nodes_before_limit,
                "total_edges": len(edge_summary),
                "unique_nodes": len(visited_keys),
                "node_uniqueness_guaranteed": True,
                "max_depth_reached": len(stages) - 1,
                "edge_filter": params.edge_types,
                "query_plan_memo": params.plan_memo,
                "result_limit": params.result_limit,
                "limit_applied": total_nodes_before_limit > params.result_limit
            }
        }

    def _analyze_edges(self, entities: List[Dict[str, Any]], edge_type_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Analyze available edges for TRAVERSE PLAN mode.

        Returns edge distribution and sample targets without full traversal.
        Useful for understanding graph structure before executing expensive traversals.
        """
        import json

        edge_analysis = {}

        for entity in entities:
            graph_paths = entity.get('graph_paths', [])

            # Handle JSON string format (TiDB returns JSON as strings)
            if isinstance(graph_paths, str):
                try:
                    graph_paths = json.loads(graph_paths)
                except json.JSONDecodeError:
                    continue

            if not isinstance(graph_paths, list):
                continue

            for edge in graph_paths:
                if isinstance(edge, dict):
                    edge_type = edge.get('type', 'unknown')

                    # Filter by edge type if specified
                    if edge_type_filter and edge_type not in edge_type_filter:
                        continue

                    if edge_type not in edge_analysis:
                        edge_analysis[edge_type] = {
                            'count': 0,
                            'sample_targets': []
                        }

                    edge_analysis[edge_type]['count'] += 1

                    # Collect sample targets (max 5 per type)
                    if len(edge_analysis[edge_type]['sample_targets']) < 5:
                        target = edge.get('dst')
                        if target:
                            edge_analysis[edge_type]['sample_targets'].append(target)

        # Build response
        return [{
            'entity_count': len(entities),
            'edge_types': edge_analysis,
            'entities': [
                {
                    'key': e.get('name') or e.get('id'),
                    'edge_count': len(e.get('graph_paths', []))
                }
                for e in entities[:10]
            ]
        }]

    def get_moments_with_filters(
        self,
        limit: int = 10,
        topic_tags: Optional[List[str]] = None,
        emotion_tags: Optional[List[str]] = None,
        moment_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        person_name: Optional[str] = None,
        sort_by: str = "recent",
        tenant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get moments with structured filters.

        This method handles TiDB-specific SQL generation for moment filtering.
        Uses JSON_CONTAINS for tag filtering instead of PostgreSQL's ARRAY operators.

        Args:
            limit: Maximum number of moments to return
            topic_tags: Filter by topic tags
            emotion_tags: Filter by emotion tags
            moment_type: Filter by moment type
            date_from: Start date in ISO format (YYYY-MM-DD)
            date_to: End date in ISO format (YYYY-MM-DD)
            person_name: Filter moments where this person was present
            sort_by: Sort order - "recent" or "oldest"
            tenant_id: Tenant ID for isolation

        Returns:
            List of matching moments
        """
        tenant_id = tenant_id or self.tenant_id
        conditions = []

        # TiDB JSON syntax
        if topic_tags:
            tags_json = "[" + ", ".join([f'"{tag}"' for tag in topic_tags]) + "]"
            conditions.append(f"JSON_CONTAINS(topic_tags, '{tags_json}')")

        if emotion_tags:
            tags_json = "[" + ", ".join([f'"{tag}"' for tag in emotion_tags]) + "]"
            conditions.append(f"JSON_CONTAINS(emotion_tags, '{tags_json}')")

        if moment_type:
            conditions.append(f"moment_type = '{moment_type}'")

        if date_from:
            conditions.append(f"resource_timestamp >= '{date_from}'")

        if date_to:
            conditions.append(f"resource_timestamp <= '{date_to}'")

        if person_name:
            conditions.append(f"JSON_SEARCH(present_persons, 'one', '%{person_name}%', NULL, '$[*].name') IS NOT NULL")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        order_direction = "DESC" if sort_by == "recent" else "ASC"

        sql = f"SELECT * FROM moments WHERE tenant_id = '{tenant_id}' AND ({where_clause}) ORDER BY resource_timestamp {order_direction} LIMIT {limit}"

        results = self.provider.execute(sql, None)
        return results


def create_tidb_rem_provider(tidb_provider=None, tenant_id: str = "tenant-test"):
    """
    Create TiDB REM query provider.

    Args:
        tidb_provider: TiDBProvider instance (or None to create from config)
        tenant_id: Default tenant ID

    Returns:
        TiDBREMQueryProvider instance
    """
    if tidb_provider is None:
        from . import get_provider
        # Ensure we get TiDB provider
        from p8fs_cluster.config.settings import config
        if config.storage_provider != "tidb":
            raise ValueError("TiDB provider not configured. Set P8FS_STORAGE_PROVIDER=tidb")
        tidb_provider = get_provider()

    return TiDBREMQueryProvider(tidb_provider, tenant_id)
