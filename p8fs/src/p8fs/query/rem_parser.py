"""REM Query Parser - Parse REM query strings into query plans."""

import re
from typing import Tuple, Optional
from p8fs.providers.rem_query import (
    QueryType,
    LookupParameters,
    SearchParameters,
    SQLParameters,
    TraverseParameters,
    REMQueryPlan,
)
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class REMQueryParser:
    """Parse REM query strings into executable query plans."""

    def __init__(self, default_table: str = "resources", tenant_id: str = "tenant-test"):
        self.default_table = default_table
        self.tenant_id = tenant_id

    def parse(self, query: str) -> REMQueryPlan:
        """
        Parse a REM query string into a query plan.

        Supported formats:
        - LOOKUP key                          -> Type-agnostic key lookup
        - LOOKUP table:key                    -> Key lookup with table hint
        - SEARCH "query text" IN table        -> Semantic search (SQL-like)
        - SEARCH "query text"                 -> Semantic search (default table)
        - SELECT ... FROM table WHERE ...     -> Standard SQL query
        - TRAVERSE [edge-type] WITH LOOKUP/SEARCH ... [DEPTH n] [PLAN]

        Examples:
            LOOKUP test-resource-1
            LOOKUP resources:test-resource-1
            SEARCH "what did I do today?" IN resources
            SEARCH "morning run"
            SEARCH "morning \"run\"" IN resources
            SELECT * FROM resources WHERE category='diary'
            TRAVERSE WITH LOOKUP sally
            TRAVERSE reports-to WITH LOOKUP sally DEPTH 2
            TRAVERSE PLAN WITH SEARCH "database team"
        """
        query = query.strip()

        # TRAVERSE: Multi-hop graph traversal
        if query.upper().startswith("TRAVERSE "):
            return self._parse_traverse(query)

        # LOOKUP: "LOOKUP key" or "LOOKUP table:key" (type-agnostic)
        elif query.upper().startswith(("LOOKUP ", "GET ")):
            return self._parse_lookup(query)

        # SEARCH: "SEARCH table: query text"
        elif query.upper().startswith("SEARCH "):
            return self._parse_search(query)

        # SQL: "SELECT ... FROM ..." (standard SQL dialect)
        elif query.upper().startswith("SELECT "):
            return self._parse_sql_select(query)

        # Default: treat as search query
        else:
            return self._parse_implicit_search(query)

    def _parse_lookup(self, query: str) -> REMQueryPlan:
        """
        Parse LOOKUP/GET query.

        Type-agnostic lookup - finds entity by key regardless of table:
        - LOOKUP key              -> Scans all tables via KV reverse lookup
        - LOOKUP table:key        -> Uses table as fallback hint if KV empty
        - LOOKUP key1, key2, key3 -> Multiple keys (comma-separated)
        - LOOKUP table:key1, key2 -> Multiple keys with table hint
        """
        # Remove LOOKUP/GET prefix
        query = re.sub(r"^(LOOKUP|GET)\s+", "", query, flags=re.IGNORECASE).strip()

        # Parse "table:key" format
        table = None
        if ":" in query and not query.count(","):
            # Only treat as table:key if there's a colon and no commas
            # (to avoid treating "key1, key2:value" as table format)
            parts = query.split(":", 1)
            if " " not in parts[0]:  # table name shouldn't have spaces
                table = parts[0].strip()
                query = parts[1].strip()

        if not table:
            # No table specified - truly type-agnostic lookup
            # table_name is only used as fallback hint if KV is empty
            table = self.default_table if self.default_table else None

        # Check for comma-separated keys
        if "," in query:
            # Multiple keys - split by comma and clean each one
            raw_keys = [k.strip() for k in query.split(",")]
            keys = []
            for raw_key in raw_keys:
                # Strip matching surrounding quotes from each key using regex
                # Handles: "...", '...', `...`, ```...```, """...""", '''...'''
                clean_key = re.sub(r'^(```|"""|\'\'\'|"|\'|`)(.+)\1$', r'\2', raw_key.strip())
                if clean_key:  # Only add non-empty keys
                    keys.append(clean_key)

            # Use list if multiple keys, single string if only one
            key = keys if len(keys) > 1 else (keys[0] if keys else "")
        else:
            # Single key - strip quotes
            key = query.strip()
            key = re.sub(r'^(```|"""|\'\'\'|"|\'|`)(.+)\1$', r'\2', key)

        logger.debug(f"Parsed LOOKUP: table={table}, key={key} (type-agnostic: {table is None}, multiple: {isinstance(key, list)})")

        params = LookupParameters(
            table_name=table,
            key=key,
            tenant_id=self.tenant_id,
        )

        return REMQueryPlan(query_type=QueryType.LOOKUP, parameters=params)

    def _parse_search(self, query: str) -> REMQueryPlan:
        """
        Parse SEARCH query.

        Supports SQL-like syntax with quoted strings:
        - SEARCH "query text" IN table
        - SEARCH "query text"
        - SEARCH 'query text' IN table

        Handles escaped quotes: SEARCH "morning \"run\"" IN resources
        """
        # Remove SEARCH prefix
        query = re.sub(r"^SEARCH\s+", "", query, flags=re.IGNORECASE).strip()

        # Try to match quoted string format: SEARCH "query" IN table or SEARCH "query"
        # Match both single and double quotes, handling escaped quotes
        quoted_match = re.match(r'''["'](.+?)["']\s*(?:IN\s+(\w+))?$''', query, re.IGNORECASE | re.DOTALL)

        if quoted_match:
            # Extract search text and optional table
            search_text = quoted_match.group(1)
            table = quoted_match.group(2) if quoted_match.group(2) else self.default_table

            # Handle escaped quotes in search text
            search_text = search_text.replace('\\"', '"').replace("\\'", "'")

        else:
            # Fallback: Legacy "table: query text" format for backward compatibility
            if ":" in query:
                parts = query.split(":", 1)
                table = parts[0].strip()
                search_text = parts[1].strip()
            else:
                # No table specified, use default
                table = self.default_table
                search_text = query

        logger.debug(f"Parsed SEARCH: table={table}, query='{search_text[:50]}...'")

        params = SearchParameters(
            table_name=table,
            query_text=search_text,
            tenant_id=self.tenant_id,
            limit=10,
            threshold=0.7,
        )

        return REMQueryPlan(query_type=QueryType.SEARCH, parameters=params)

    def _parse_sql_select(self, query: str) -> REMQueryPlan:
        """Parse full SQL SELECT query."""
        # Extract table name from SELECT statement
        from_match = re.search(r"FROM\s+(\w+)", query, re.IGNORECASE)
        table = from_match.group(1) if from_match else self.default_table

        # Extract WHERE clause if present
        where_match = re.search(r"WHERE\s+(.+?)(?:ORDER BY|LIMIT|$)", query, re.IGNORECASE | re.DOTALL)
        where_clause = where_match.group(1).strip() if where_match else None

        # Extract LIMIT if present
        limit_match = re.search(r"LIMIT\s+(\d+)", query, re.IGNORECASE)
        limit = int(limit_match.group(1)) if limit_match else None

        # Extract ORDER BY if present
        order_match = re.search(r"ORDER BY\s+(.+?)(?:LIMIT|$)", query, re.IGNORECASE | re.DOTALL)
        order_by = [o.strip() for o in order_match.group(1).split(",")] if order_match else None

        logger.debug(f"Parsed SQL: table={table}, where={where_clause}, limit={limit}")

        params = SQLParameters(
            table_name=table,
            where_clause=where_clause,
            order_by=order_by,
            limit=limit,
            tenant_id=self.tenant_id,
        )

        return REMQueryPlan(query_type=QueryType.SQL, parameters=params)

    def _parse_implicit_search(self, query: str) -> REMQueryPlan:
        """Parse implicit search (plain text -> search on default table)."""
        logger.debug(f"Parsed implicit SEARCH: table={self.default_table}, query='{query[:50]}...'")

        params = SearchParameters(
            table_name=self.default_table,
            query_text=query,
            tenant_id=self.tenant_id,
            limit=10,
            threshold=0.7,
        )

        return REMQueryPlan(query_type=QueryType.SEARCH, parameters=params)

    def _parse_traverse(self, query: str) -> REMQueryPlan:
        """
        Parse TRAVERSE query.

        Supported syntax:
        - TRAVERSE WITH LOOKUP key [DEPTH n] [IN table]
        - TRAVERSE WITH SEARCH "text" [DEPTH n] [IN table]
        - TRAVERSE edge-type WITH LOOKUP key [DEPTH n]
        - TRAVERSE edge-type1,edge-type2 WITH LOOKUP key [DEPTH n]
        - TRAVERSE PLAN WITH LOOKUP key

        Examples:
            TRAVERSE WITH LOOKUP sally
            TRAVERSE WITH SEARCH "database team"
            TRAVERSE reports-to WITH LOOKUP sally DEPTH 2
            TRAVERSE reports-to,manages WITH LOOKUP sally DEPTH 3
            TRAVERSE PLAN WITH LOOKUP sally
            TRAVERSE WITH LOOKUP sally IN resources
        """
        # Remove TRAVERSE prefix
        query = re.sub(r"^TRAVERSE\s+", "", query, flags=re.IGNORECASE).strip()

        # Parse PLAN mode
        plan_mode = False
        if query.upper().startswith("PLAN "):
            plan_mode = True
            query = re.sub(r"^PLAN\s+", "", query, flags=re.IGNORECASE).strip()

        # Parse edge types (optional, before WITH)
        edge_types = None
        with_match = re.search(r"\bWITH\b", query, re.IGNORECASE)
        if with_match:
            before_with = query[:with_match.start()].strip()
            if before_with:
                # Parse comma-separated edge types
                edge_types = [et.strip() for et in before_with.split(",")]
            query = query[with_match.end():].strip()

        # Parse WITH LOOKUP or WITH SEARCH
        initial_query_type = None
        initial_query = None
        table = self.default_table

        if query.upper().startswith("LOOKUP "):
            initial_query_type = "lookup"
            query_part = re.sub(r"^LOOKUP\s+", "", query, flags=re.IGNORECASE).strip()

            # Extract key (stop at DEPTH or IN)
            depth_match = re.search(r"\s+DEPTH\s+", query_part, re.IGNORECASE)
            in_match = re.search(r"\s+IN\s+", query_part, re.IGNORECASE)

            end_pos = len(query_part)
            if depth_match and in_match:
                end_pos = min(depth_match.start(), in_match.start())
            elif depth_match:
                end_pos = depth_match.start()
            elif in_match:
                end_pos = in_match.start()

            initial_query = query_part[:end_pos].strip()
            # Strip outer quotes (but preserve inner quotes)
            # e.g., "My 'great' idea" -> My 'great' idea
            initial_query = re.sub(r'^(```|"""|\'\'\'|"|\'|`)(.+)\1$', r'\2', initial_query)
            query = query_part[end_pos:].strip()

        elif query.upper().startswith("SEARCH "):
            initial_query_type = "search"
            query_part = re.sub(r"^SEARCH\s+", "", query, flags=re.IGNORECASE).strip()

            # Extract quoted search text
            quoted_match = re.match(r'''["'](.+?)["']''', query_part, re.DOTALL)
            if quoted_match:
                initial_query = quoted_match.group(1)
                # Handle escaped quotes
                initial_query = initial_query.replace('\\"', '"').replace("\\'", "'")
                query = query_part[quoted_match.end():].strip()
            else:
                raise ValueError("TRAVERSE SEARCH requires quoted text: TRAVERSE WITH SEARCH \"text\"")

        else:
            raise ValueError("TRAVERSE requires WITH LOOKUP or WITH SEARCH")

        # Parse DEPTH (optional)
        max_depth = 1  # Default depth
        depth_match = re.search(r"DEPTH\s+(\d+)", query, re.IGNORECASE)
        if depth_match:
            max_depth = int(depth_match.group(1))
            query = query[:depth_match.start()].strip() + query[depth_match.end():].strip()

        # Parse IN table (optional)
        in_match = re.search(r"IN\s+(\w+)", query, re.IGNORECASE)
        if in_match:
            table = in_match.group(1)

        logger.debug(
            f"Parsed TRAVERSE: initial_query_type={initial_query_type}, "
            f"initial_query={initial_query}, edge_types={edge_types}, "
            f"max_depth={max_depth}, plan_mode={plan_mode}, table={table}"
        )

        params = TraverseParameters(
            initial_query_type=initial_query_type,
            initial_query=initial_query,
            edge_types=edge_types,
            max_depth=max_depth,
            plan_mode=plan_mode,
            table_name=table,
            tenant_id=self.tenant_id,
        )

        return REMQueryPlan(query_type=QueryType.TRAVERSE, parameters=params)
