from fastapi import APIRouter, Depends, Query as QueryParam
from pydantic import BaseModel, Field
from typing import Any

from ..middleware import User, get_current_user
from ..controllers.rem_query_controller import REMQueryController
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/rem", tags=["rem-query"])


class REMQueryRequest(BaseModel):
    query: str = Field(..., description="REM query string or natural language question")
    provider: str | None = Field(None, description="Database provider (postgresql, tidb)")
    ask_ai: bool = Field(False, description="Convert natural language to REM query using AI")
    table: str = Field("resources", description="Default table for query context")
    model: str | None = Field(None, description="LLM model for AI conversion (supports provider:model syntax, e.g., 'openai:gpt-4o')")


class REMQueryResponse(BaseModel):
    success: bool
    results: list[dict[str, Any]]
    count: int
    query: str
    original_query: str | None = None
    error: str | None = None


@router.post("/query", response_model=REMQueryResponse)
async def execute_rem_query_post(
    request: REMQueryRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Execute REM (Resource-Entity-Moment) query.

    **Direct REM Query Mode (ask_ai=false or REM syntax detected):**
    - Executes REM queries directly without LLM processing
    - Supported syntax:
      * SEARCH "text" IN table - Semantic vector search
      * LOOKUP key1, key2 - Direct key-value lookup
      * FUZZY "text" - Fuzzy text matching via pg_trgm similarity
      * SELECT * FROM table WHERE... - SQL queries with filters

    **Natural Language Mode (ask_ai=true + natural language input):**
    - Uses specialized REM query generation agent
    - Converts questions like "show me recent uploads" into optimized REM queries
    - Automatically detects REM syntax - if query is already valid REM, skips LLM
    - Optional: Specify model with provider:model syntax (e.g., "cerebras:qwen-2.5-72b")

    **Examples:**
    ```json
    // Natural language → REM conversion
    {"query": "find documentation about databases", "ask_ai": true}
    → SEARCH "documentation about databases" IN resources

    // Direct REM execution (no LLM)
    {"query": "SELECT * FROM resources WHERE category='docs'", "ask_ai": false}
    → Executes directly

    // Fuzzy text matching
    {"query": "FUZZY afternoon", "ask_ai": false}
    → Matches "Friday Afternoon", "Monday Afternoon", etc.

    // Fast Cerebras Qwen for query planning
    {"query": "show recent files", "ask_ai": true, "model": "cerebras:qwen-2.5-72b"}
    ```
    """
    controller = REMQueryController(tenant_id=current_user.tenant_id)

    result = await controller.execute_query(
        query=request.query, provider=request.provider, ask_ai=request.ask_ai, table=request.table, model=request.model
    )

    return REMQueryResponse(**result)


@router.get("/query", response_model=REMQueryResponse)
async def execute_rem_query_get(
    query: str = QueryParam(..., description="REM query string or natural language question"),
    provider: str | None = QueryParam(None, description="Database provider"),
    ask_ai: bool = QueryParam(False, description="Convert natural language to REM query using AI"),
    table: str = QueryParam("resources", description="Default table for query context"),
    model: str | None = QueryParam(None, description="LLM model for AI conversion (supports provider:model syntax)"),
    current_user: User = Depends(get_current_user),
):
    """Execute REM query via GET request."""
    controller = REMQueryController(tenant_id=current_user.tenant_id)

    result = await controller.execute_query(query=query, provider=provider, ask_ai=ask_ai, table=table, model=model)

    return REMQueryResponse(**result)
