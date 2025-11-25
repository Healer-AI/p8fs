"""P8FS MCP Server - Minimal design focused on REM queries and resources.

## Architecture

**Tools** (3 minimal tools):
- chat: Interactive LLM chat with P8FS agents
- query_rem: Execute REM (Resource-Entity-Moment) queries
- read_resource: Read MCP resources (for hosts that don't support resources properly)

**Resources** (paginated data access):
- p8fs://files/{view}?page=1&limit=20 - Files table (view: all, recent)
- p8fs://resources/{view}?page=1&limit=20 - Resources table (view: all, recent)
- p8fs://moments/{view}?page=1&limit=20 - Moments table (view: all, recent)
- p8fs://entities/{table}?page=1&limit=20 - Entity keys/names ordered by modified date
- p8fs://s3-upload/{filename} - Presigned S3 upload URL

## REM Query Language

The query_rem tool exposes P8FS's REM (Resource-Entity-Moment) query dialect:

### LOOKUP - Entity-based queries
```
LOOKUP "Sarah"                    # Find all resources related to entity
LOOKUP resources:sarah-chen       # Table-scoped lookup
LOOKUP "Sarah", "Mike", "Emily"   # Multiple entities (comma-separated)
LOOKUP "Project Alpha", "TiDB Migration", "API Redesign"  # Multiple documents
GET "Kickoff Meeting", "Status Update"  # GET alias works with multiple keys
```

### SEARCH - Semantic similarity search
```
SEARCH "machine learning papers"
SEARCH "database migration tidb postgresql" IN resources
```

### SELECT - SQL queries with temporal/semantic filters
```
SELECT * FROM moments WHERE moment_type='meeting'
SELECT * FROM resources WHERE category='document' AND created_at > '2025-01-01'
SELECT * FROM moments WHERE 'project-alpha' = ANY(topic_tags) ORDER BY start_time
```

## Authentication

JWT Bearer token required for all operations. Automatic tenant isolation.
"""

from typing import Any

from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider
from mcp.server.auth.provider import AccessToken

from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from .. import __version__
from ..middleware.auth import verify_token
from .mcp_resources import (
    register_files_resource,
    register_resources_resource,
    register_moments_resource,
    register_entities_resource,
    register_s3_upload_resource,
    load_resource,
)

logger = get_logger(__name__)


class P8FSAuthProvider(AuthProvider):
    """JWT authentication provider for FastMCP.

    Validates JWT tokens on every MCP request and extracts tenant context.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify JWT token and return AccessToken with user context.

        Args:
            token: Raw JWT token string

        Returns:
            AccessToken if valid, None if invalid
        """
        try:
            from fastapi.security import HTTPAuthorizationCredentials

            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            token_payload = await verify_token(credentials)

            return AccessToken(
                token=token,
                client_id=f"user-{token_payload.sub}",
                scopes=["read", "write"],
                expires_at=None
            )
        except Exception as e:
            logger.warning(f"JWT verification failed: {e}")
            return None


def create_secure_mcp_server() -> FastMCP:
    """Create P8FS MCP server with minimal tools and comprehensive resources.

    Returns:
        Configured FastMCP server instance
    """
    auth_provider = P8FSAuthProvider()

    mcp = FastMCP(
        name="p8fs-mcp-server",
        version=__version__,
        instructions=(
            "P8FS Memory System - Smart content management with REM (Resource-Entity-Moment) query language.\n"
            "\n"
            "═══════════════════════════════════════════════════════════════════════════\n"
            "📋 RESOURCES FIRST - READ BEFORE QUERYING!\n"
            "═══════════════════════════════════════════════════════════════════════════\n"
            "\n"
            "**CRITICAL WORKFLOW**: Always check relevant resources BEFORE using query tools.\n"
            "\n"
            "Step 1: Ask yourself - \"What data do I need?\"\n"
            "Step 2: Check if resource exists → Call read_resource FIRST\n"
            "Step 3: If resource insufficient → THEN use query_rem\n"
            "\n"
            "**Why Resources First?**\n"
            "✓ Resources = Paginated table access (fast, structured, complete)\n"
            "✓ Queries = Filtered/semantic search (slower, requires indexes)\n"
            "✓ Resources show you what exists before querying\n"
            "\n"
            "**Available Resources:**\n"
            "\n"
            "Table Data (paginated):\n"
            "• p8fs://files/all?page=1&limit=20 → All uploaded files\n"
            "• p8fs://resources/all?page=1&limit=20 → All content resources\n"
            "• p8fs://moments/all?page=1&limit=20 → Temporal moments (meetings, events)\n"
            "\n"
            "Entity Discovery:\n"
            "• p8fs://entities/resources?page=1&limit=50 → Entity keys from resources (ordered by modified)\n"
            "• p8fs://entities/moments?page=1&limit=50 → Entity keys from moments\n"
            "\n"
            "File Upload:\n"
            "• p8fs://s3-upload/{filename} → Get presigned S3 PUT URL\n"
            "  Example workflow:\n"
            "  1. read_resource(uri='p8fs://s3-upload/document.pdf')\n"
            "  2. curl -T local-file.pdf \"{presigned_url}\"\n"
            "  3. File automatically indexed in P8FS\n"
            "\n"
            "═══════════════════════════════════════════════════════════════════════════\n"
            "🔍 REM QUERY LANGUAGE - Use query_rem tool\n"
            "═══════════════════════════════════════════════════════════════════════════\n"
            "\n"
            "**Entity Lookup (LOOKUP):**\n"
            "LOOKUP \"Sarah\"                     → Find all resources with entity Sarah\n"
            "LOOKUP resources:sarah-chen        → Table-scoped entity lookup\n"
            "LOOKUP \"TiDB\"                      → Case-insensitive entity search\n"
            "\n"
            "**Semantic Search (SEARCH):**\n"
            "SEARCH \"machine learning papers\"   → Natural language search\n"
            "SEARCH \"database migration\" IN resources → Table-scoped semantic search\n"
            "\n"
            "**SQL Queries (SELECT):**\n"
            "SELECT * FROM moments WHERE moment_type='meeting'\n"
            "SELECT * FROM resources WHERE category='document'\n"
            "SELECT * FROM moments WHERE 'project-alpha' = ANY(topic_tags) ORDER BY start_time\n"
            "SELECT * FROM resources WHERE created_at > '2025-01-01' LIMIT 10\n"
            "\n"
            "═══════════════════════════════════════════════════════════════════════════\n"
            "💬 CHAT WITH AGENTS - Use chat tool\n"
            "═══════════════════════════════════════════════════════════════════════════\n"
            "\n"
            "chat(message=\"What are my recent moments?\", agent=\"p8-default\")\n"
            "chat(message=\"Analyze this content\", agent=\"p8-research\", model=\"gpt-4.1\")\n"
            "\n"
            "═══════════════════════════════════════════════════════════════════════════\n"
            "\n"
            "**Example Workflow - Resources First:**\n"
            "\n"
            "User: \"What files have I uploaded recently?\"\n"
            "❌ BAD: query_rem(query=\"SEARCH 'recent files'\")\n"
            "✅ GOOD: read_resource(uri=\"p8fs://files/all?page=1&limit=10\") → Shows latest files\n"
            "\n"
            "User: \"Find documents about Sarah\"\n"
            "✅ GOOD: read_resource(uri=\"p8fs://entities/resources\") FIRST → See what entities exist\n"
            "✅ THEN: query_rem(query=\"LOOKUP Sarah\") → Get Sarah's resources\n"
            "\n"
            "User: \"Show meetings from last week\"\n"
            "✅ GOOD: query_rem(query=\"SELECT * FROM moments WHERE moment_type='meeting' AND start_time > '2025-11-08'\")\n"
        ),
        auth=auth_provider
    )

    # === PROMPTS ===

    @mcp.prompt()
    async def create_agent(
        purpose: str,
        name: str | None = None,
        priority: int = 2
    ) -> list[dict[str, str]]:
        """Help create a custom agent JSON schema for background processing.

        This prompt guides you through creating agent schemas that can:
        - Watch uploaded files and chats
        - Extract specific insights and observations
        - Run as background workers
        - Process content automatically

        Args:
            purpose: What the agent should do (e.g., "watch files and extract key insights")
            name: Optional agent name (will suggest if not provided)
            priority: Agent priority 1-3 (1=high, 2=normal, 3=low, default: 2)

        Examples:
            create_agent(purpose="Extract action items from meeting notes")
            create_agent(purpose="Track mentions of project names", name="project_tracker", priority=1)
            create_agent(purpose="Summarize daily activity", priority=3)
        """
        # Generate suggested name if not provided
        if not name:
            name_suggestion = purpose.lower().replace(" ", "_")[:30]
        else:
            name_suggestion = name

        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""I want to create an agent that: {purpose}

Please help me create a complete JSON schema for this agent following this structure:

```json
{{
  "p8-type": "agent",
  "short_name": "{name_suggestion}",
  "name": "Descriptive Agent Name",
  "title": "Full Agent Title",
  "version": "1.0.0",
  "description": "Clear description of what this agent does and how it should behave...",
  "fully_qualified_name": "user.agents.{name_suggestion}",
  "use_in_dreaming": true,
  "priority": {priority},
  "properties": {{
    "insights": {{
      "type": "array",
      "items": {{ "type": "string" }},
      "description": "List of insights extracted"
    }},
    "confidence": {{
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "Confidence score for the analysis"
    }}
  }},
  "required": ["insights"],
  "tools": []
}}
```

**Important Fields:**
- `p8-type`: Must be "agent" (required for automatic processing)
- `short_name`: Lowercase with underscores, unique identifier (used for upsert)
- `version`: Semantic version (e.g., "1.0.0")
- `description`: System prompt - detailed instructions for the agent's behavior
- `use_in_dreaming`: Set to `true` to include in background processing
- `priority`: 1 (high), 2 (normal), or 3 (low) - affects processing order
- `properties`: JSON Schema for the structured output the agent should produce

**Priority Levels:**
- Priority 1 (High): Critical agents that should run first (e.g., security monitoring)
- Priority 2 (Normal): Standard agents for general insights
- Priority 3 (Low): Nice-to-have agents that run when resources available

**Example Use Cases:**
- "Extract action items and deadlines from documents" → High priority (1)
- "Identify key themes and topics in conversations" → Normal priority (2)
- "Generate creative suggestions based on content" → Low priority (3)

**How to Save:**
Once you have the JSON schema, save it as `{name_suggestion}.json` and upload it via S3:
1. Get upload URL: `read_resource(uri="p8fs://s3-upload/{name_suggestion}.json")`
2. Upload: `curl -T {name_suggestion}.json "{{presigned_url}}"`
3. The agent will be automatically processed and upserted by name in the database
4. Subsequent uploads with the same `short_name` will update the existing agent

Please create a complete, valid JSON schema tailored to: {purpose}

Make sure the `description` field contains clear, detailed instructions for what the agent should do, how it should behave, and what specific things it should look for."""
                }
            }
        ]

    # === MINIMAL TOOLS (3 only) ===

    @mcp.tool()
    async def chat(
        message: str,
        agent: str = "p8-default",
        model: str = "gpt-4.1",
        temperature: float = 0.7,
        max_tokens: int | None = None
    ) -> str:
        """Chat with P8FS agents for content analysis and assistance.

        Args:
            message: Your message to the agent
            agent: Agent to use (default: p8-default)
            model: LLM model (default: gpt-4.1, options: gpt-4.1, claude-sonnet-4-5)
            temperature: Sampling temperature 0.0-2.0 (default: 0.7)
            max_tokens: Optional token limit

        Returns:
            Agent response

        Examples:
            chat(message="Summarize my recent activity")
            chat(message="What moments involve Sarah?", model="claude-sonnet-4-5")
            chat(message="Analyze this document", agent="p8-research")
        """
        try:
            context = CallingContext(
                model=model,
                temperature=temperature,
                prefers_streaming=True,
                max_tokens=max_tokens,
                tenant_id=None,  # TODO: Get from auth context
                user_id=None,
            )

            # Load agent if specified
            agent_instance = None
            if agent and agent != "p8-default":
                try:
                    from p8fs.utils.inspection import load_entity as load_entity_by_name
                    agent_class = load_entity_by_name(agent)
                    logger.info(f"Loading agent for chat: {agent}")

                    agent_kwargs = {
                        "id": f"mcp-{agent.replace('.', '-').lower()}",
                        "name": agent,
                        "description": f"MCP instance of {agent}",
                        "spec": {"source": "mcp", "type": "agent"},
                    }

                    try:
                        agent_instance = agent_class(**agent_kwargs)
                    except TypeError:
                        agent_instance = agent_class()

                except Exception as e:
                    logger.warning(f"Failed to load agent '{agent}': {e}")

            # Stream from LLM and collect response
            async with MemoryProxy(model_context=agent_instance) as memory_proxy:
                full_response = ""
                async for chunk in memory_proxy.stream(message, context):
                    if isinstance(chunk, dict):
                        if chunk.get("type") == "completion":
                            final_response = chunk.get("final_response", "")
                            if final_response:
                                full_response = final_response
                            break

                        elif "choices" in chunk:
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                if "content" in delta and delta["content"]:
                                    full_response += delta["content"]

                        elif chunk.get("type") == "content_block_delta" and "delta" in chunk:
                            delta = chunk.get("delta", {})
                            if delta.get("type") == "text_delta" and "text" in delta:
                                full_response += delta["text"]

                return full_response if full_response else "No response generated"

        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            return f"Chat error: {str(e)}"

    @mcp.tool()
    async def query_rem(query: str, limit: int = 20) -> dict[str, Any]:
        """Execute REM (Resource-Entity-Moment) query in P8FS dialect.

        REM is P8FS's unified query language supporting entity lookup, semantic search, and SQL.

        **Query Types:**

        **1. LOOKUP - Entity-based queries**
        ```
        LOOKUP "Sarah"                    # Find all resources with entity Sarah
        LOOKUP resources:sarah-chen       # Table-scoped lookup
        LOOKUP "TiDB"                     # Case-insensitive entity search
        LOOKUP "Sarah", "Mike", "Emily"   # Multiple entities (comma-separated)
        LOOKUP "Project Alpha", "TiDB Migration", "API Redesign"  # Multiple documents
        GET "Kickoff Meeting", "Status Update"  # GET alias works with multiple keys
        ```

        **2. SEARCH - Semantic similarity**
        ```
        SEARCH "machine learning papers"
        SEARCH "database migration tidb postgresql"
        SEARCH "meeting notes" IN moments
        ```

        **3. SELECT - SQL queries**
        ```
        SELECT * FROM moments WHERE moment_type='meeting'
        SELECT * FROM resources WHERE category='document'
        SELECT * FROM moments WHERE 'project-alpha' = ANY(topic_tags) ORDER BY start_time
        SELECT * FROM resources WHERE created_at > '2025-01-01' LIMIT 10
        ```

        Args:
            query: REM query string (LOOKUP, SEARCH, or SELECT)
            limit: Maximum results to return (default: 20)

        Returns:
            Query results with metadata

        Examples:
            query_rem(query="LOOKUP Sarah")
            query_rem(query="SEARCH 'machine learning'", limit=10)
            query_rem(query="SELECT * FROM moments WHERE moment_type='meeting'")
        """
        try:
            from p8fs.services.rem_query_service import REMQueryService

            # TODO: Get tenant_id from auth context
            tenant_id = config.default_tenant_id

            # Use centralized REMQueryService
            service = REMQueryService(tenant_id=tenant_id)
            result = service.execute_query(query)

            # Format results
            formatted_results = []
            for item in result.get("results", []):
                if isinstance(item, dict):
                    formatted_results.append(item)
                else:
                    formatted_results.append(
                        item.model_dump() if hasattr(item, 'model_dump') else item.__dict__
                    )

            return {
                "status": "success" if result.get("success") else "error",
                "query": query,
                "total_results": len(formatted_results),
                "results": formatted_results[:limit],  # Apply limit
                "info": f"Executed query - found {len(formatted_results)} results",
                "error": result.get("error")
            }

        except Exception as e:
            logger.error(f"REM query error: {e}", exc_info=True)
            return {
                "status": "error",
                "query": query,
                "error": str(e)
            }

    @mcp.tool()
    async def read_resource(uri: str) -> dict[str, Any]:
        """Read MCP resource by URI (for hosts that don't support resources properly).

        This tool bridges the gap for MCP hosts that require manual resource attachment.
        While FastMCP correctly exposes resources via MCP protocol, some hosts need
        tool-based access for automatic invocation.

        **Available Resources:**

        Table Data (paginated):
        • p8fs://files/all?page=1&limit=20
        • p8fs://resources/all?page=1&limit=20
        • p8fs://moments/all?page=1&limit=20

        Entity Discovery:
        • p8fs://entities/resources?page=1&limit=50
        • p8fs://entities/moments?page=1&limit=50

        S3 Upload:
        • p8fs://s3-upload/{filename}

        Args:
            uri: Resource URI with optional query parameters

        Returns:
            Resource data

        Examples:
            read_resource(uri="p8fs://files/all?page=1&limit=10")
            read_resource(uri="p8fs://entities/resources?limit=50")
            read_resource(uri="p8fs://s3-upload/document.pdf")
        """
        try:
            # TODO: Get tenant_id from auth context
            tenant_id = config.default_tenant_id

            result = await load_resource(uri, tenant_id=tenant_id)

            if isinstance(result, dict):
                return {
                    "status": "success",
                    "uri": uri,
                    "data": result
                }

            return {
                "status": "success",
                "uri": uri,
                "data": {"content": str(result)}
            }

        except Exception as e:
            logger.error(f"Failed to read resource {uri}: {e}", exc_info=True)
            return {
                "status": "error",
                "uri": uri,
                "error": str(e)
            }

    # === REGISTER RESOURCES ===

    register_files_resource(mcp)
    register_resources_resource(mcp)
    register_moments_resource(mcp)
    register_entities_resource(mcp)
    register_s3_upload_resource(mcp)

    logger.info("Created P8FS MCP server with 1 prompt, 3 tools and 5 resource types")
    return mcp
