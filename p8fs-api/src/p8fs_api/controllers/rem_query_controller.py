from typing import Any

from p8fs.services.llm.language_model import LanguageModel
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class REMQueryController:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def _configure_explicit_provider(self, llm: LanguageModel, provider: str, model_name: str):
        """Configure LanguageModel with explicit provider, overriding inference."""
        provider_configs = {
            "openai": {
                "scheme": "openai",
                "model": model_name,
                "completions_uri": "https://api.openai.com/v1/chat/completions",
                "token_env_key": "OPENAI_API_KEY",
            },
            "anthropic": {
                "scheme": "anthropic",
                "model": model_name,
                "completions_uri": "https://api.anthropic.com/v1/messages",
                "token_env_key": "ANTHROPIC_API_KEY",
                "anthropic-version": "2023-06-01",
            },
            "cerebras": {
                "scheme": "openai",
                "model": model_name,
                "completions_uri": "https://api.cerebras.ai/v1/chat/completions",
                "token_env_key": "CEREBRAS_API_KEY",
            },
            "google": {
                "scheme": "google",
                "model": model_name,
                "completions_uri": f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
                "token_env_key": "GOOGLE_API_KEY",
            },
        }

        if provider in provider_configs:
            llm._params = provider_configs[provider]
            llm._add_api_token()
            logger.info(f"Configured {provider} provider for model {model_name}")
        else:
            logger.warning(f"Unknown provider '{provider}', falling back to model inference")

    async def convert_natural_language_to_rem(self, question: str, table: str = "resources", model: str | None = None) -> str:
        logger.info(f"Converting natural language to REM query: {question[:100]}...")

        # Use centralized model spec parsing from config
        explicit_provider, model_name = config.parse_model_spec(model)

        if explicit_provider:
            logger.info(f"Using explicit provider '{explicit_provider}' with model '{model_name}'")
        else:
            logger.info(f"Using model '{model_name}' (provider will be inferred)")

        llm = LanguageModel(model_name=model_name, tenant_id=self.tenant_id)

        # If explicit provider was specified, configure it to override inference
        if explicit_provider:
            self._configure_explicit_provider(llm, explicit_provider, model_name)

        # Get dialect hints for the configured provider
        from p8fs.services.rem_query_service import REMQueryService
        dialect_hints = REMQueryService.get_dialect_hints(provider=config.storage_provider)

        planning_prompt = f"""You are a specialized REM (Resource-Entity-Moment) query generation agent.

Your task: Convert natural language questions into optimized REM queries.

REM DIALECT REFERENCE:

1. SEARCH - Semantic vector search (use for content/meaning queries)
   Syntax: SEARCH "search text" IN table_name
   Example: SEARCH "machine learning algorithms" IN resources

2. LOOKUP - Direct key lookup from KV store (use for specific IDs)
   Syntax: LOOKUP key1, key2, key3
   Example: LOOKUP resource-123, resource-456

3. SQL - Structured queries (use for filters, temporal, tags, aggregations)
   - Temporal: SELECT * FROM {table} WHERE created_at > NOW() - INTERVAL '7 days'
   - Tags: SELECT * FROM {table} WHERE tags @> '["tag_name"]'::jsonb
   - Category: SELECT * FROM {table} WHERE category = 'value'
   - Combined: SELECT * FROM {table} WHERE category = 'docs' AND created_at > NOW() - INTERVAL '1 day'

4. TRAVERSE - Multi-hop graph traversal (use for relationship/connection queries)
   Syntax: TRAVERSE [edge-type] WITH LOOKUP/SEARCH ... [DEPTH n] [PLAN]
   Examples:
   - TRAVERSE WITH LOOKUP sally
   - TRAVERSE WITH SEARCH "database team"
   - TRAVERSE reports-to WITH LOOKUP sally DEPTH 2
   - TRAVERSE PLAN WITH LOOKUP sally
   Use when user asks about: relationships, connections, graph, traversal, paths, links, hierarchy

{dialect_hints}

USER QUESTION: "{question}"
TARGET TABLE: {table}

INSTRUCTIONS:
- Analyze the user's intent carefully
- Choose the most efficient REM query type
- For content/semantic queries → use SEARCH
- For time-based filters → use SQL with WHERE created_at
- For structured attributes → use SQL with appropriate WHERE clauses
- For relationship/graph queries → use TRAVERSE
- Output ONLY the REM query (no explanations, no markdown, no comments)"""

        messages = [{"role": "user", "content": planning_prompt}]

        response = await llm.invoke_raw(messages=messages, temperature=0.0, max_tokens=500)

        if "choices" in response and response["choices"]:
            planned_query = response["choices"][0]["message"]["content"].strip()
            planned_query = planned_query.strip("`").strip()

            if planned_query.startswith("sql") or planned_query.startswith("rem"):
                planned_query = "\n".join(planned_query.split("\n")[1:]).strip()

            logger.info(f"Generated REM query: {planned_query}")
            return planned_query
        else:
            raise ValueError("No response from LLM")

    def _is_rem_query(self, query: str) -> bool:
        """Detect if query is already a REM query vs natural language."""
        query_upper = query.strip().upper()
        return query_upper.startswith(("SELECT", "SEARCH", "LOOKUP", "INSERT", "UPDATE", "DELETE", "WITH"))

    async def execute_query(
        self, query: str, provider: str | None = None, ask_ai: bool = False, table: str = "resources", model: str | None = None
    ) -> dict[str, Any]:
        try:
            original_query = query

            # Only use LLM if ask_ai is true AND query is natural language (not already REM)
            if ask_ai and not self._is_rem_query(query):
                query = await self.convert_natural_language_to_rem(query, table=table, model=model)
            elif ask_ai:
                logger.info(f"Query is already valid REM syntax, skipping LLM conversion")

            logger.info(f"Executing REM query for tenant {self.tenant_id}: {query[:100]}...")

            # Use centralized REMQueryService
            from p8fs.services.rem_query_service import REMQueryService

            service = REMQueryService(tenant_id=self.tenant_id, provider=provider)
            result = service.execute_query(query)

            # Return with original_query field for API response
            result["original_query"] = original_query if ask_ai else None
            return result

        except Exception as e:
            logger.error(f"REM query failed: {e}", exc_info=True)
            return {
                "success": False,
                "results": [],
                "count": 0,
                "query": query,
                "original_query": original_query if ask_ai else None,
                "error": str(e),
            }
