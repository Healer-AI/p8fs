"""
REM Query Provider - Production implementation with real embeddings.

Implements Resource-Entity-Moment query semantics using existing PostgreSQL provider.
Integrates with real embedding services and existing database infrastructure.
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


# Query Type Definitions
class QueryType(str, Enum):
    """REM query types."""
    LOOKUP = "lookup"
    SEARCH = "search"
    FUZZY = "fuzzy"
    SQL = "sql"
    TRAVERSE = "traverse"


# Query Parameter Models
class QueryParameters(BaseModel):
    """Base class for query parameters."""
    table_name: str = "resources"
    tenant_id: Optional[str] = None


class LookupParameters(QueryParameters):
    """Key-based lookup parameters."""
    key: Union[str, List[str]]
    fields: Optional[List[str]] = None


class SearchParameters(QueryParameters):
    """Semantic search parameters."""
    query_text: str
    embedding_field: Optional[str] = None
    limit: int = 10
    threshold: float = 0.7
    metric: str = "cosine"


class FuzzyParameters(QueryParameters):
    """Fuzzy text search parameters using trigram similarity."""
    query_text: str
    search_fields: List[str] = Field(default_factory=lambda: ["name", "content"])
    limit: int = 10
    threshold: float = 0.3  # Similarity threshold (0-1, where 1 is exact match)
    use_word_similarity: bool = False  # Use word_similarity instead of similarity


class SQLParameters(QueryParameters):
    """SQL SELECT query parameters - read-only queries only."""
    select_fields: List[str] = Field(default_factory=lambda: ["*"])
    where_clause: Optional[str] = None
    order_by: Optional[List[str]] = None
    limit: Optional[int] = None

    def model_post_init(self, __context):
        """Validate that query is read-only (no DELETE, UPDATE, DROP, etc.)."""
        if self.where_clause:
            import re
            dangerous_keywords = ['DELETE', 'UPDATE', 'DROP', 'INSERT', 'TRUNCATE', 'ALTER', 'CREATE']
            upper_clause = self.where_clause.upper()
            for keyword in dangerous_keywords:
                # Match whole words only (not substrings like CREATE in created_at)
                if re.search(r'\b' + keyword + r'\b', upper_clause):
                    raise ValueError(
                        f"REM queries are read-only. '{keyword}' operations are not allowed. "
                        f"Use appropriate repository methods for data modification."
                    )


class TraverseParameters(QueryParameters):
    """
    Graph traversal parameters for multi-hop LOOKUP/SEARCH/SELECT.

    TRAVERSE orchestrates multiple queries:
    1. Execute initial query (LOOKUP, SEARCH, or SELECT) to find entry entities
    2. Examine graph_paths field on results
    3. Filter edges by type if specified
    4. LOOKUP target keys from edges
    5. Optionally repeat for depth > 1

    Examples:
        TRAVERSE reports-to WITH LOOKUP sally DEPTH 2
        TRAVERSE WITH SEARCH "database team"
        TRAVERSE WITH SELECT * FROM resources WHERE category = 'person'
        TRAVERSE WITH LOOKUP sally DEPTH 0  # PLAN mode (analyze edges)
        TRAVERSE WITH LOOKUP sally ORDER BY created_at DESC LIMIT 9
    """
    initial_query_type: str  # "lookup", "search", or "sql"
    initial_query: Union[str, List[str]]  # Key(s) for LOOKUP, text for SEARCH, or WHERE clause for SQL
    edge_types: Optional[List[str]] = None  # Filter edges by type (e.g., ["reports-to"])
    max_depth: int = 1  # Number of hops (0=PLAN mode, 1=single-hop, 2+=multi-hop)
    plan_memo: Optional[str] = None  # Agent scratchpad: terse goal/progress memo (echoed in response)
    plan_mode: bool = False  # Deprecated: use max_depth=0 instead
    direction: str = "outbound"  # "outbound", "inbound", or "both"
    order_by_edge_field: str = "created_at"  # Field to order edges by before following
    order_direction: str = "DESC"  # "ASC" or "DESC" for edge ordering
    result_limit: int = 9  # Maximum number of nodes to return in final result


class REMQueryPlan(BaseModel):
    """REM query execution plan."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    query_type: QueryType
    parameters: QueryParameters
    metadata: Dict[str, Any] = Field(default_factory=dict)


# REM Response Models (Contract/Documentation)
class TraverseStageInfo(BaseModel):
    """
    Stage execution details for TRAVERSE operations.

    Tracks what was executed at each depth level and what was found.
    Used for multi-turn agentic workflows where the agent maintains context
    across progressive explorations (depth=0 PLAN → depth=1 → depth=2).
    """
    depth: int = Field(..., description="Depth level this stage executed at (0=initial query, 1=first hop, etc)")
    executed: str = Field(..., description="What query was executed (e.g., 'LOOKUP sarah chen', 'LOOKUP 3 targets via reports-to')")
    found: Dict[str, int] = Field(..., description="What was discovered: {'nodes': N, 'edges': M}")
    edge_types: Optional[Dict[str, int]] = Field(None, description="Edge types followed and their counts (only for depth > 0)")
    plan_memo: Optional[str] = Field(None, description="Agent's scratchpad memo echoed back (terse goal/progress tracking)")


class TraverseMetadata(BaseModel):
    """
    Metadata about TRAVERSE execution results.

    Provides statistics and configuration settings for the traversal operation.
    Useful for agents to understand the scope and boundaries of the result set.
    """
    total_nodes: int = Field(..., description="Total number of nodes returned (after LIMIT)")
    total_nodes_before_limit: int = Field(..., description="Total nodes found before applying result_limit")
    total_edges: int = Field(..., description="Total number of edges followed during traversal")
    unique_nodes: int = Field(..., description="Number of unique nodes (same as total_nodes, uniqueness guaranteed)")
    node_uniqueness_guaranteed: bool = Field(True, description="Always True - nodes are deduplicated during traversal")
    max_depth_reached: int = Field(..., description="Maximum depth level reached (0=initial query only)")
    edge_filter: Optional[List[str]] = Field(None, description="Edge types that were filtered (if specified)")
    query_plan_memo: Optional[str] = Field(None, description="Agent's plan memo for this query")
    result_limit: int = Field(..., description="Maximum number of nodes to return (default: 9)")
    limit_applied: bool = Field(..., description="True if result set was limited")


class TraverseResponse(BaseModel):
    """
    Complete TRAVERSE query response structure.

    This model serves as a contract for what TRAVERSE queries return.
    It is NOT used for runtime validation (to avoid overhead) but documents
    the expected response format for API consumers and agents.

    Response includes:
    - nodes: Full entity data for all discovered nodes
    - stages: Execution tracking at each depth level
    - source_nodes: Entry point keys from initial query
    - edge_summary: Compact edge list as (src, rel_type, dst) tuples
    - metadata: Statistics and configuration

    Example:
        {
            "nodes": [
                {"name": "Sarah Chen", "category": "person", "_traverse_depth": 0, ...},
                {"name": "Michael Torres", "category": "person", "_traverse_depth": 1, ...}
            ],
            "stages": [
                {
                    "depth": 0,
                    "executed": "LOOKUP sarah chen",
                    "found": {"nodes": 1, "edges": 2},
                    "plan_memo": "Goal: org chart. Step 1: PLAN"
                },
                {
                    "depth": 1,
                    "executed": "LOOKUP 2 targets via ['reports-to']",
                    "found": {"nodes": 1, "edges": 0},
                    "edge_types": {"reports-to": 2},
                    "plan_memo": "Goal: org chart. Step 1: PLAN"
                }
            ],
            "source_nodes": ["sarah chen"],
            "edge_summary": [
                ["sarah chen", "reports-to", "michael torres"],
                ["sarah chen", "manages", "alice chen"]
            ],
            "metadata": {
                "total_nodes": 2,
                "total_edges": 2,
                "unique_nodes": 2,
                "node_uniqueness_guaranteed": true,
                "max_depth_reached": 1,
                "edge_filter": ["reports-to"],
                "query_plan_memo": "Goal: org chart. Step 1: PLAN"
            }
        }
    """
    model_config = ConfigDict(
        json_schema_extra={
            "description": "TRAVERSE query response - stateless execution with agent scratchpad support"
        }
    )

    nodes: List[Dict[str, Any]] = Field(..., description="Full entity data for all discovered nodes with _traverse_depth annotations")
    stages: List[TraverseStageInfo] = Field(..., description="Execution details for each depth level")
    source_nodes: List[str] = Field(..., description="Keys of entry nodes from initial query")
    edge_summary: List[List[str]] = Field(..., description="Compact edge list as [src, rel_type, dst] tuples")
    metadata: TraverseMetadata = Field(..., description="Statistics and configuration for the traversal")


# REM Query Executor
class REMQueryProvider:
    """
    REM query provider using existing PostgreSQL provider.

    Provides unified query interface across:
    - LOOKUP: Key-based retrieval
    - SEARCH: Semantic vector search with real embeddings
    - SQL: Standard SELECT queries
    - TRAVERSE: Graph traversal (requires Apache AGE setup)
    """

    # Configuration constants
    TRAVERSE_INITIAL_LIMIT = 100  # Maximum entities from initial traverse query
    EDGE_SAMPLE_LIMIT = 5  # Number of sample edges to include in analysis

    def __init__(self, pg_provider, tenant_id: str = "tenant-test"):
        """
        Initialize with existing PostgreSQL provider.

        Args:
            pg_provider: PostgreSQLProvider instance
            tenant_id: Default tenant ID for multi-tenant isolation
        """
        self.provider = pg_provider
        self.tenant_id = tenant_id

    @staticmethod
    def _parse_graph_paths(graph_paths: Union[str, List, None]) -> List[Dict[str, Any]]:
        """
        Parse graph_paths from string or list format.

        Args:
            graph_paths: Graph paths in string (JSON) or list format

        Returns:
            List of graph path dictionaries, or empty list if parsing fails
        """
        if not graph_paths:
            return []

        if isinstance(graph_paths, str):
            import json
            try:
                return json.loads(graph_paths)
            except json.JSONDecodeError:
                return []

        return graph_paths if isinstance(graph_paths, list) else []

    @staticmethod
    def get_dialect_hints() -> str:
        """Return PostgreSQL-specific dialect hints for REM query generation."""
        return """PostgreSQL Dialect Hints:
- Vector search: Use <-> operator for L2 distance, <#> for inner product
  Example: WHERE embedding <-> query_vector < 0.5
- Fuzzy search: Use % operator for trigram similarity (pg_trgm extension)
  Example: WHERE name % 'searchterm' (matches similar text, threshold ~0.3)
  Functions: similarity(field, 'text'), word_similarity(field, 'text')
- Date queries: Use INTERVAL syntax
  Example: WHERE created_at > NOW() - INTERVAL '7 days'
- JSONB tags: Use @> containment operator
  Example: WHERE tags @> '["database"]'::jsonb

System Fields (available on all tables):
- created_at, updated_at: Timestamp fields (use in WHERE, ORDER BY)
- graph_paths: JSONB array of relationships (SELECT only, not for WHERE predicates)
  Example: SELECT id, name, graph_paths FROM resources WHERE created_at > NOW() - INTERVAL '1 day'

Query Types:
- LOOKUP: Key-based retrieval (exact match on name/id)
- SEARCH: Semantic vector search (requires embeddings)
- FUZZY: Fuzzy text matching using trigram similarity
- SQL: Standard SELECT queries with WHERE clauses
- TRAVERSE: Graph traversal with edge following"""

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
        elif plan.query_type == QueryType.FUZZY:
            return self._execute_fuzzy(plan.parameters)
        elif plan.query_type == QueryType.SQL:
            return self._execute_sql(plan.parameters)
        elif plan.query_type == QueryType.TRAVERSE:
            return self._execute_traverse(plan.parameters)
        else:
            raise ValueError(f"Unsupported query type: {plan.query_type}")

    def _execute_lookup(self, params: LookupParameters) -> List[Dict[str, Any]]:
        """
        Execute schema-agnostic lookup using graph-based entity retrieval.

        CRITICAL: LOOKUP uses GRAPH via get_entities(). It is O(1) and does NOT scan.

        Flow:
        1. Call p8.get_entities() with entity name(s) for O(1) graph lookup
        2. Graph returns all entities with that name across all registered tables
        3. Filter by tenant_id for multi-tenant isolation

        Key Difference from SQL:
        - SQL: SELECT * FROM resources WHERE name='test' (single table, requires table name)
        - LOOKUP: Find ALL entities named 'test' (all tables, no schema knowledge needed)

        Example:
        - resources table has name="my-project" (id=uuid-1)
        - moments table has name="my-project" (id=uuid-2)
        - Graph stores: public__resources node with key="my-project"
        - Graph stores: public__moments node with key="my-project"
        - LOOKUP("my-project") returns BOTH records via O(1) graph lookup!

        Supports multiple keys:
        - LOOKUP(["key1", "key2"]) returns results for both keys
        - Single key is treated as list with one element
        """
        tenant_id = params.tenant_id or self.tenant_id
        all_results = []

        # Normalize key to list (single key is just a special case)
        keys = params.key if isinstance(params.key, list) else [params.key]

        logger.info(f"LOOKUP: Processing {len(keys)} key(s) via graph")

        try:
            # Call p8.get_entities() for O(1) graph-based lookup
            conn = self.provider.connect_sync()
            cursor = conn.cursor()

            # Execute get_entities with array of keys
            cursor.execute("""
                SELECT p8.get_entities(%s::text[])
            """, (keys,))

            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if not result or not result[0]:
                logger.info(f"LOOKUP: No entities found for keys: {keys}")
                return []

            entities_by_type = result[0]

            # Process results from each entity type
            for entity_type, entity_data in entities_by_type.items():
                if not isinstance(entity_data, dict) or 'data' not in entity_data:
                    continue

                records = entity_data['data']
                if not isinstance(records, list):
                    continue

                # Filter by tenant_id and annotate with entity metadata
                for record in records:
                    if not isinstance(record, dict):
                        continue

                    # Filter by tenant (multi-tenant isolation)
                    record_tenant = record.get('tenant_id')
                    if record_tenant and record_tenant != tenant_id:
                        continue

                    # Extract table name from entity type (e.g., "public.resources" -> "resources")
                    table_name = entity_type.split('.')[-1] if '.' in entity_type else entity_type

                    # Annotate with metadata
                    record['_entity_type'] = entity_type
                    record['_table_name'] = table_name

                    all_results.append(record)

            logger.info(f"LOOKUP: Found {len(all_results)} total results for {len(keys)} key(s) via graph")

        except Exception as e:
            logger.error(f"LOOKUP: Graph query failed: {e}", exc_info=True)
            return []

        return all_results

    def _execute_search(self, params: SearchParameters) -> List[Dict[str, Any]]:
        """
        Execute semantic search using real embeddings.

        Uses provider's generate_embeddings_batch for real embedding generation
        and custom SQL for pgvector search (to handle column name flexibility).
        """
        tenant_id = params.tenant_id or self.tenant_id

        # Generate real embedding using provider's embedding service
        try:
            embeddings = self.provider.generate_embeddings_batch([params.query_text])
            query_embedding = embeddings[0]
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

        # Build semantic search SQL with correct column name (embedding, not embedding_vector)
        embedding_table = f"embeddings.{params.table_name}_embeddings"
        operator = self.provider.get_vector_operator(params.metric)
        query_vector_str = f"[{','.join(map(str, query_embedding))}]"

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

        sql = f"""
            SELECT m.*, e.field_name,
                   (e.embedding_vector {operator} %s::vector) as distance,
                   (1 - (e.embedding_vector {operator} %s::vector)) as similarity
            FROM public.{params.table_name} m
            INNER JOIN {embedding_table} e ON m.id = e.entity_id
            WHERE {where_clause}
            ORDER BY e.embedding_vector {operator} %s::vector
            LIMIT %s
        """

        # Build final parameters: query_vector for SELECT, score, ORDER BY, then where params, then limit
        final_params = [query_vector_str, query_vector_str] + sql_params + [query_vector_str, params.limit]

        results = self.provider.execute(sql, tuple(final_params))
        return results

    def _execute_fuzzy(self, params: FuzzyParameters) -> List[Dict[str, Any]]:
        """
        Execute fuzzy text search using AGE graph vertices (same as get_entities).

        This ensures FUZZY and LOOKUP read from the same underlying AGE graph data.

        Flow:
        1. Query AGE graph vertices for fuzzy matches on entity keys
        2. Use similarity() to find keys matching search terms
        3. Call get_entities() with matched keys (same as LOOKUP)

        Args:
            params: Fuzzy search parameters

        Returns:
            List of matching entity records from graph
        """
        tenant_id = params.tenant_id or self.tenant_id

        # Get provider dialect to determine which implementation to use
        dialect = self.provider.get_dialect_name()

        if dialect == "postgresql":
            # Use graph-based fuzzy search with AGE vertices
            sql, sql_params = self._fuzzy_search_postgresql(params, tenant_id)
            results = self.provider.execute(sql, sql_params)

            # Extract entities from the result
            if results and len(results) > 0:
                result_data = results[0].get('fuzzy_search') if isinstance(results[0], dict) else results[0]

                # Result has format: {search_metadata: {...}, entities: {...}}
                if isinstance(result_data, dict) and 'entities' in result_data:
                    entities_by_type = result_data['entities']

                    # Unwrap nested structure (same as LOOKUP)
                    all_results = []
                    for entity_type, entity_data in entities_by_type.items():
                        if isinstance(entity_data, dict) and 'data' in entity_data:
                            records = entity_data['data']
                            if isinstance(records, list):
                                for record in records:
                                    if isinstance(record, dict):
                                        # Annotate with metadata
                                        table_name = entity_type.split('.')[-1] if '.' in entity_type else entity_type
                                        record['_entity_type'] = entity_type
                                        record['_table_name'] = table_name
                                        all_results.append(record)

                    return all_results

            return []
        elif dialect == "tidb":
            # TiDB: Use legacy table-based fuzzy search for now
            # TODO: Implement TiDB graph-based fuzzy search
            sql, sql_params = self._fuzzy_search_tidb(params, tenant_id)
            results = self.provider.execute(sql, sql_params)
            return results
        else:
            raise ValueError(f"Fuzzy search not supported for dialect: {dialect}")

    def _fuzzy_search_postgresql(self, params: FuzzyParameters, tenant_id: str) -> tuple[str, tuple]:
        """
        Call PostgreSQL graph-based fuzzy search function.

        Uses p8.fuzzy_search() which reads from AGE graph vertices and calls get_entities().
        This ensures FUZZY uses the same data source as LOOKUP.

        New signature:
        p8.fuzzy_search(search_terms TEXT[], similarity_threshold REAL, userid TEXT, max_matches_per_term INT)
        """
        # Convert query_text to array of search terms (can be extended for multiple terms)
        search_terms = [params.query_text]

        sql = """
            SELECT p8.fuzzy_search(
                %s::text[],    -- search_terms array
                %s::real,      -- similarity_threshold
                %s::text,      -- userid (tenant_id)
                %s::int        -- max_matches_per_term
            ) as fuzzy_search
        """

        query_params = (
            search_terms,  # psycopg2 will convert list to array
            params.threshold,
            tenant_id,
            params.limit  # max_matches_per_term
        )

        return sql.strip(), query_params

    def _fuzzy_search_tidb(self, params: FuzzyParameters, tenant_id: str) -> tuple[str, tuple]:
        """
        Generate TiDB fuzzy search SQL using FTS_MATCH_WORD or LIKE fallback.

        Two modes:
        1. Full-text search mode (if use_word_similarity=True): Uses FTS_MATCH_WORD()
           - Requires: FULLTEXT INDEX on search fields
           - Returns: BM25 relevance scores

        2. LIKE fallback mode (default): Pattern matching
           - No index required
           - Simple substring matching

        To enable FTS mode, create indexes:
          ALTER TABLE resources ADD FULLTEXT INDEX idx_name_fts (name) WITH PARSER MULTILINGUAL;
          ALTER TABLE resources ADD FULLTEXT INDEX idx_content_fts (content) WITH PARSER MULTILINGUAL;
        """

        # Mode 1: Full-text search with FTS_MATCH_WORD (if enabled)
        if params.use_word_similarity:
            # Build FTS_MATCH_WORD conditions for each field
            fts_conditions = []
            score_expressions = []

            for field in params.search_fields:
                fts_conditions.append(f"FTS_MATCH_WORD(%s, {field}) > 0")
                score_expressions.append(f"FTS_MATCH_WORD(%s, {field})")

            where_clause = " OR ".join(fts_conditions)

            # Use GREATEST to get max relevance across fields
            if len(score_expressions) > 1:
                relevance_expr = f"GREATEST({', '.join(score_expressions)})"
            else:
                relevance_expr = score_expressions[0]

            sql = f"""
                SELECT *, {relevance_expr} as similarity_score
                FROM {params.table_name}
                WHERE tenant_id = %s
                AND ({where_clause})
                ORDER BY {relevance_expr} DESC
                LIMIT %s
            """

            # Build params: query_text for each score expression + tenant_id + query_text for conditions + limit
            query_params = []
            query_params.extend([params.query_text] * len(params.search_fields))  # SELECT relevance
            query_params.append(tenant_id)  # tenant filter
            query_params.extend([params.query_text] * len(params.search_fields))  # WHERE FTS conditions
            query_params.append(params.limit)  # result limit

            return sql.strip(), tuple(query_params)

        # Mode 2: LIKE-based fuzzy matching (fallback)
        # TiDB LIKE is case-sensitive, use LOWER() for case-insensitive matching
        like_pattern = f"%{params.query_text.lower()}%"
        field_conditions = []
        for field in params.search_fields:
            field_conditions.append(f"LOWER({field}) LIKE %s")

        where_clause = " OR ".join(field_conditions)

        sql = f"""
            SELECT *
            FROM {params.table_name}
            WHERE tenant_id = %s
            AND ({where_clause})
            ORDER BY
                CASE
                    WHEN LOWER({params.search_fields[0]}) = %s THEN 1
                    WHEN LOWER({params.search_fields[0]}) LIKE %s THEN 2
                    ELSE 3
                END,
                {params.search_fields[0]}
            LIMIT %s
        """

        # Build params: tenant_id + LIKE patterns + exact match + starts-with pattern + limit
        query_params = [tenant_id]
        query_params.extend([like_pattern] * len(params.search_fields))  # LIKE conditions
        query_params.append(params.query_text.lower())  # exact match check
        query_params.append(f"{params.query_text.lower()}%")  # starts-with pattern
        query_params.append(params.limit)

        return sql.strip(), tuple(query_params)

    def _execute_sql(self, params: SQLParameters) -> List[Dict[str, Any]]:
        """
        Execute SQL SELECT query with parameterized tenant filter.

        REM queries are read-only. Validation in SQLParameters prevents
        dangerous operations (DELETE, UPDATE, DROP, etc.).
        """
        # Defense-in-depth: Verify this is a SELECT-only context
        # (SQLParameters validation already caught this, but double-check)
        if params.where_clause:
            import re
            dangerous_keywords = ['DELETE', 'UPDATE', 'DROP', 'INSERT', 'TRUNCATE', 'ALTER', 'CREATE']
            upper_clause = params.where_clause.upper()
            for keyword in dangerous_keywords:
                # Match whole words only (not substrings like CREATE in created_at)
                if re.search(r'\b' + keyword + r'\b', upper_clause):
                    raise ValueError(
                        f"REM queries are read-only. '{keyword}' operations are not allowed."
                    )

        fields = ", ".join(params.select_fields)
        sql = f"SELECT {fields} FROM public.{params.table_name}"

        where_clauses = []
        sql_params = []
        tenant_id = params.tenant_id or self.tenant_id

        # Add tenant filter with parameterized query
        where_clauses.append("tenant_id = %s")
        sql_params.append(tenant_id)

        # Add custom where clause (validated above)
        if params.where_clause:
            where_clauses.append(f"({params.where_clause})")

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        # Add ORDER BY (field names, not user input)
        if params.order_by:
            sql += " ORDER BY " + ", ".join(params.order_by)

        # Add LIMIT
        if params.limit:
            sql += f" LIMIT {params.limit}"

        results = self.provider.execute(sql, tuple(sql_params))
        return results

    def _execute_traverse(self, params: TraverseParameters) -> Dict[str, Any]:
        """
        Execute multi-hop graph traversal using LOOKUP/SEARCH + edge following.

        Flow:
        1. Execute initial query (LOOKUP or SEARCH) to get entry entities
        2. Examine graph_paths field on each entity
        3. Filter edges by type if specified
        4. Extract target keys from edges
        5. LOOKUP those keys to get connected entities
        6. Optionally repeat for depth > 1

        PLAN mode returns edge analysis instead of full traversal.

        Returns:
            Dict with keys: nodes, stages, source_nodes, edge_summary, metadata
        """
        tenant_id = params.tenant_id or self.tenant_id
        all_results = []
        visited_keys = set()
        stages = []  # Track execution at each depth
        edge_summary = []  # (src, rel_type, dst) tuples
        source_node_keys = []  # Entry nodes

        # Stage 1: Execute initial query
        logger.info(f"TRAVERSE Stage 1: Executing initial {params.initial_query_type} query")

        if params.initial_query_type == "lookup":
            # Use existing LOOKUP logic
            lookup_params = LookupParameters(
                key=params.initial_query,
                table_name=params.table_name,
                tenant_id=tenant_id
            )
            initial_entities = self._execute_lookup(lookup_params)
        elif params.initial_query_type == "search":
            # Use existing SEARCH logic
            search_params = SearchParameters(
                query_text=params.initial_query if isinstance(params.initial_query, str) else params.initial_query[0],
                table_name=params.table_name,
                tenant_id=tenant_id,
                limit=self.TRAVERSE_INITIAL_LIMIT
            )
            initial_entities = self._execute_search(search_params)
        elif params.initial_query_type == "sql":
            # Use existing SQL logic
            sql_params = SQLParameters(
                select_fields=["*"],
                table_name=params.table_name,
                where_clause=params.initial_query if isinstance(params.initial_query, str) else params.initial_query[0],
                tenant_id=tenant_id,
                limit=self.TRAVERSE_INITIAL_LIMIT
            )
            initial_entities = self._execute_sql(sql_params)
        else:
            raise ValueError(f"Unsupported initial query type: {params.initial_query_type}")

        if not initial_entities:
            logger.info("TRAVERSE: No entities found in initial query")
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
                "metadata": {"total_nodes": 0, "max_depth_reached": 0}
            }

        # Mark initial entities as visited and track as source nodes
        for entity in initial_entities:
            entity_key = entity.get('name') or entity.get('id')
            if entity_key:
                visited_keys.add(entity_key)
                if entity_key not in source_node_keys:
                    source_node_keys.append(entity_key)

        # Count edges in initial entities
        initial_edge_count = sum(len(e.get('graph_paths', [])) for e in initial_entities)

        # PLAN mode: Return edge analysis (triggered by depth=0 or plan_mode=True)
        if params.max_depth == 0 or params.plan_mode:
            analysis = self._analyze_edges(initial_entities, params.edge_types)
            # Wrap in enhanced structure
            return {
                "analysis": analysis,  # Original edge analysis
                "stages": [{
                    "depth": 0,
                    "executed": f"{params.initial_query_type.upper()} {params.initial_query}",
                    "found": {"nodes": len(initial_entities), "edges": initial_edge_count},
                    "plan_memo": params.plan_memo
                }],
                "source_nodes": source_node_keys,
                "metadata": {
                    "mode": "PLAN",
                    "total_nodes": len(initial_entities),
                    "total_edges": initial_edge_count
                }
            }

        # Add stage 0: Initial query results
        stages.append({
            "depth": 0,
            "executed": f"{params.initial_query_type.upper()} {params.initial_query}",
            "found": {"nodes": len(initial_entities), "edges": initial_edge_count},
            "plan_memo": params.plan_memo
        })

        # Add initial entities to results
        for entity in initial_entities:
            entity['_traverse_depth'] = 0
            entity['_traverse_path'] = [entity.get('name') or entity.get('id')]
            all_results.append(entity)

        # Stage 2+: Follow edges for each depth level
        current_entities = initial_entities
        for depth in range(1, params.max_depth + 1):
            logger.info(f"TRAVERSE Stage {depth + 1}: Following edges at depth {depth}")

            next_keys = set()
            edges_followed = []  # Track which edges we follow

            # Examine graph_paths for each entity at current depth
            for entity in current_entities:
                entity_key = entity.get('name') or entity.get('id')
                graph_paths = self._parse_graph_paths(entity.get('graph_paths'))

                if not graph_paths:
                    continue

                # Collect edges with metadata for sorting
                entity_edges = []
                for edge in graph_paths:
                    # Support both dict and string formats
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
                # Add stage for this depth even if no edges found
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
                # TODO: Track full path through parent references
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

        Returns edge type distribution and sample targets.
        """
        edge_analysis = {}

        for entity in entities:
            entity_key = entity.get('name') or entity.get('id')
            graph_paths = self._parse_graph_paths(entity.get('graph_paths'))

            for edge in graph_paths:
                if isinstance(edge, dict):
                    edge_type = edge.get('rel_type') or edge.get('type', 'unknown')  # Support both field names
                    target = edge.get('dst')

                    if edge_type_filter and edge_type not in edge_type_filter:
                        continue

                    if edge_type not in edge_analysis:
                        edge_analysis[edge_type] = {
                            'count': 0,
                            'sample_targets': []
                        }

                    edge_analysis[edge_type]['count'] += 1
                    if len(edge_analysis[edge_type]['sample_targets']) < self.EDGE_SAMPLE_LIMIT:
                        edge_analysis[edge_type]['sample_targets'].append(target)

        return [{
            'entity_count': len(entities),
            'edge_types': edge_analysis,
            'entities': [{'key': e.get('name') or e.get('id'), 'edge_count': len(e.get('graph_paths', []))} for e in entities[:10]]
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
        Get moments with structured filters using parameterized queries.

        This method handles PostgreSQL-specific SQL generation for moment filtering.
        Supports filtering by topics, emotions, moment type, date ranges, and people present.

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
        params = []

        # PostgreSQL ARRAY syntax with parameterized queries
        if topic_tags:
            conditions.append("topic_tags @> %s::text[]")
            params.append(topic_tags)

        if emotion_tags:
            conditions.append("emotion_tags @> %s::text[]")
            params.append(emotion_tags)

        if moment_type:
            conditions.append("moment_type = %s")
            params.append(moment_type)

        if date_from:
            conditions.append("resource_timestamp >= %s::timestamp")
            params.append(date_from)

        if date_to:
            conditions.append("resource_timestamp <= %s::timestamp")
            params.append(date_to)

        if person_name:
            conditions.append("EXISTS (SELECT 1 FROM jsonb_array_elements(present_persons) AS person WHERE person->>'name' ILIKE %s)")
            params.append(f"%{person_name}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        order_direction = "DESC" if sort_by == "recent" else "ASC"

        sql = f"SELECT * FROM moments WHERE tenant_id = %s AND ({where_clause}) ORDER BY resource_timestamp {order_direction} LIMIT %s"

        # Add tenant_id and limit to params
        final_params = [tenant_id] + params + [limit]

        results = self.provider.execute(sql, tuple(final_params))
        return results


# Convenience function
def create_rem_provider(pg_provider=None, tenant_id: str = "tenant-test"):
    """
    Create REM query provider.

    Args:
        pg_provider: PostgreSQLProvider instance (or None to create from config)
        tenant_id: Default tenant ID

    Returns:
        REMQueryProvider instance
    """
    if pg_provider is None:
        from . import get_provider
        pg_provider = get_provider()

    return REMQueryProvider(pg_provider, tenant_id)
