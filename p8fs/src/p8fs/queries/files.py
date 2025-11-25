"""File listing queries with pagination and filtering.

This module provides database-agnostic queries for listing files (resources)
with pagination, filtering by tenant_id, encryption mode, and date ranges.
"""

from typing import Any


def build_list_files_query(
    dialect: str,
    tenant_id: str | None = None,
    encryption_key_owner: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[str, list[Any]]:
    """Build paginated file listing query with row counting.

    Args:
        dialect: SQL dialect ("postgresql" or "mysql")
        tenant_id: Optional tenant ID filter
        encryption_key_owner: Optional encryption mode filter (USER, SYSTEM, NONE)
        start_date: Optional start date filter (ISO format)
        end_date: Optional end date filter (ISO format)
        page: Page number (1-indexed)
        page_size: Number of results per page (max 200)

    Returns:
        Tuple of (query_string, parameters)
    """
    # Validate and cap page_size
    page_size = min(max(1, page_size), 200)
    page = max(1, page)
    offset = (page - 1) * page_size

    # Build WHERE conditions
    conditions = []
    filter_params = []

    # Use %s for postgresql and tidb (both use pymysql-style placeholders)
    param_placeholder = "%s" if dialect in ("postgresql", "tidb") else "?"

    if tenant_id:
        conditions.append(f"tenant_id = {param_placeholder}")
        filter_params.append(tenant_id)

    if encryption_key_owner:
        conditions.append(f"encryption_key_owner = {param_placeholder}")
        filter_params.append(encryption_key_owner)

    if start_date:
        conditions.append(f"created_at >= {param_placeholder}")
        filter_params.append(start_date)

    if end_date:
        conditions.append(f"created_at <= {param_placeholder}")
        filter_params.append(end_date)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Build CTE query with row counting
    if dialect in ("postgresql", "tidb"):
        # PostgreSQL and TiDB support window functions efficiently
        query = f"""
WITH filtered_files AS (
    SELECT
        id,
        uri,
        created_at,
        updated_at,
        tenant_id,
        encryption_key_owner,
        COUNT(*) OVER() AS total_count
    FROM resources
    {where_clause}
    ORDER BY created_at DESC
    LIMIT {param_placeholder} OFFSET {param_placeholder}
)
SELECT
    id,
    uri,
    created_at,
    updated_at,
    tenant_id,
    encryption_key_owner,
    total_count
FROM filtered_files
"""
        # PostgreSQL/TiDB params: filter_params + pagination
        params = filter_params + [page_size, offset]
    else:  # mysql and other dialects
        query = f"""
WITH filtered_files AS (
    SELECT
        id,
        uri,
        created_at,
        updated_at,
        tenant_id,
        encryption_key_owner
    FROM resources
    {where_clause}
    ORDER BY created_at DESC
    LIMIT {param_placeholder} OFFSET {param_placeholder}
)
SELECT
    id,
    uri,
    created_at,
    updated_at,
    tenant_id,
    encryption_key_owner,
    (SELECT COUNT(*) FROM resources {where_clause}) AS total_count
FROM filtered_files
"""
        # MySQL params: filter_params + pagination + filter_params (for COUNT subquery)
        params = filter_params + [page_size, offset] + filter_params

    return query, params
