"""
Centralized REM Query Service - Single source of truth for REM query execution.

This service provides a unified interface for executing REM (Resource-Entity-Moment) queries
across all modules (API, MCP, Agents). It handles provider selection, query parsing, and execution.

REM Query Examples (tested with OpenAI gpt-4o-mini on PostgreSQL):

1. SEARCH - Semantic vector search:
   Natural: "find documentation about databases"
   REM: SEARCH "documentation about databases" IN resources
   Result: ✅ Success (0 results - no matching docs in test DB)

2. SEARCH/SELECT - Content discovery:
   Natural: "show me diary entries"
   REM: SELECT * FROM resources WHERE category = 'diary'
   Result: ✅ Success (AI chose SQL over SEARCH - valid optimization)

3. SELECT - Temporal query:
   Natural: "get files from the last 3 days"
   REM: SELECT * FROM resources WHERE created_at > NOW() - INTERVAL '3 days'
   Result: ✅ Success (2 resources returned)

4. SELECT - Category filter:
   Natural: "list all documentation files"
   REM: SELECT * FROM resources WHERE category = 'docs'
   Result: ✅ Success

5. SELECT - Sort by timestamp:
   Natural: "show files sorted by last update"
   REM: SELECT * FROM resources ORDER BY updated_at DESC
   Result: ✅ Success (2 resources sorted)

6. SELECT - Include graph edges:
   Natural: "get all resources with their relationships"
   REM: SELECT id, name, graph_edges FROM resources
   Result: ✅ Success (2 resources with graph_edges)

7. SELECT - JSONB containment:
   Natural: "find files tagged with database"
   REM: SELECT * FROM resources WHERE tags @> '["database"]'::jsonb
   Result: ❌ Error (column "tags" doesn't exist - query valid, schema issue)

8. SELECT - Combined filters:
   Natural: "recent documentation from this week"
   REM: SELECT * FROM resources WHERE category = 'docs' AND created_at > NOW() - INTERVAL '7 days'
   Result: ✅ Success

9. LOOKUP - Direct KV access:
   Natural: "get resource abc-123"
   REM: LOOKUP abc-123
   Result: ✅ Success (0 results - key not in KV)

10. TRAVERSE/SEARCH - Graph query:
    Natural: "find all resources connected to project X"
    REM: SEARCH "project X" IN resources
    Result: ✅ Success (AI chose SEARCH over TRAVERSE)

Usage:
    from p8fs.services.rem_query_service import REMQueryService

    service = REMQueryService(tenant_id="tenant-123")
    result = service.execute_query("SELECT * FROM resources LIMIT 5")
"""

from typing import Any

from p8fs.query.rem_parser import REMQueryParser
from p8fs.providers import PostgreSQLProvider, TiDBProvider
from p8fs.providers.rem_query import REMQueryProvider
from p8fs.providers.rem_query_tidb import TiDBREMQueryProvider
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class REMQueryService:
    """Centralized service for executing REM queries across all modules."""

    def __init__(self, tenant_id: str, provider: str | None = None):
        """
        Initialize REM query service.

        Args:
            tenant_id: Tenant ID for multi-tenant isolation
            provider: Database provider override (default: from config.storage_provider)
        """
        self.tenant_id = tenant_id
        self.provider_type = provider or config.storage_provider
        self.parser = REMQueryParser(default_table="resources", tenant_id=tenant_id)

    def _get_rem_provider(self):
        """Get appropriate REM provider based on configuration."""
        if self.provider_type == "tidb":
            db_provider = TiDBProvider()
            return TiDBREMQueryProvider(db_provider, tenant_id=self.tenant_id)
        else:
            db_provider = PostgreSQLProvider()
            return REMQueryProvider(db_provider, tenant_id=self.tenant_id)

    def execute_query(self, query: str) -> dict[str, Any]:
        """
        Execute REM query and return results.

        Args:
            query: REM query string (SEARCH, SELECT, LOOKUP, TRAVERSE)

        Returns:
            Dictionary containing:
            - success: Whether query succeeded
            - results: List of matching entities
            - count: Number of results
            - query: The executed query
            - error: Error message if failed
        """
        logger.info(f"Executing REM query for tenant {self.tenant_id}: {query[:100]}...")

        try:
            rem_provider = self._get_rem_provider()
            query_plan = self.parser.parse(query)
            results = rem_provider.execute(query_plan)

            return {
                "success": True,
                "results": results,
                "count": len(results),
                "query": query,
                "error": None,
            }

        except Exception as e:
            logger.error(f"REM query failed: {e}", exc_info=True)
            return {
                "success": False,
                "results": [],
                "count": 0,
                "query": query,
                "error": str(e),
            }

    @staticmethod
    def get_dialect_hints(provider: str | None = None) -> str:
        """
        Get SQL dialect hints for the configured provider.

        Args:
            provider: Provider type override (default: from config)

        Returns:
            Dialect-specific hints for REM query generation
        """
        provider_type = provider or config.storage_provider

        if provider_type == "tidb":
            return TiDBREMQueryProvider.get_dialect_hints()
        else:
            return REMQueryProvider.get_dialect_hints()
