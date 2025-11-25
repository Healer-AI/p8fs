-- Fuzzy KV scan function using pg_trgm similarity
-- Based on existing get_fuzzy_entities pattern
-- Returns KV entries where keys fuzzy-match the search term

DROP FUNCTION IF EXISTS p8.fuzzy_scan_kv;

CREATE OR REPLACE FUNCTION p8.fuzzy_scan_kv(
    search_term text,
    tenant_id text DEFAULT NULL,
    similarity_threshold real DEFAULT 0.3,
    max_results int DEFAULT 20
)
RETURNS TABLE(
    key text,
    value jsonb,
    created_at text,
    expires_at text,
    similarity_score real
)
LANGUAGE plpgsql
AS $$
BEGIN
    /*
    Fuzzy search KV entries using pg_trgm similarity matching.
    
    Searches the AGE graph KV vertices for keys that fuzzy-match the search term.
    Useful for finding entities when you don't know the exact name.
    
    Parameters:
    - search_term: Text to search for (fuzzy matching)
    - tenant_id: Optional tenant filter (searches keys starting with "tenant_id/")
    - similarity_threshold: Minimum similarity score (0.0-1.0, default: 0.3)
      - 0.1-0.2: Very permissive, many matches
      - 0.3: Good balance (default)
      - 0.5: More restrictive
      - 0.7: Very strict, near-exact matches only
    - max_results: Maximum number of results to return (default: 20)
    
    Examples:
    -- Search for 'friday' in all KV entries
    SELECT * FROM p8.fuzzy_scan_kv('friday');
    
    -- Search with tenant filter
    SELECT * FROM p8.fuzzy_scan_kv('friday', 'tenant-test');
    
    -- Strict matching (threshold 0.5)
    SELECT * FROM p8.fuzzy_scan_kv('design', 'tenant-test', 0.5, 10);
    
    -- Extract entity names from results
    SELECT 
        split_part(key, '/', 2) as entity_name,
        split_part(key, '/', 3) as entity_type,
        similarity_score
    FROM p8.fuzzy_scan_kv('afternoon', 'tenant-test', 0.2);
    
    Returns:
    - key: Full KV key (format: "tenant_id/entity_name/entity_type")
    - value: JSONB value stored in KV
    - created_at: Creation timestamp
    - expires_at: Expiration timestamp (NULL if no TTL)
    - similarity_score: Similarity score (0.0-1.0, higher = better match)
    */
    
    RETURN QUERY
    WITH kv_storage AS (
        -- Use Cypher to match KVStorage labeled vertices, similar to scan_kv
        SELECT
            ((result->>'result')::jsonb->>'properties')::jsonb as props
        FROM p8.cypher_query(
            'MATCH (n:KVStorage) RETURN n',
            'result agtype'
        )
    ),
    kv_with_names AS (
        SELECT
            props->>'key' as full_key,
            (props->>'value')::jsonb as kv_value,
            COALESCE(props->>'created_at', '') as kv_created_at,
            COALESCE(props->>'expires_at', '') as kv_expires_at,
            -- Extract entity name from key (format: tenant_id/entity_name/entity_type)
            split_part(props->>'key', '/', 2) as entity_name
        FROM kv_storage
        WHERE props->>'key' IS NOT NULL
    )
    SELECT
        full_key as kv_key,
        kv_value,
        kv_created_at,
        kv_expires_at,
        -- Calculate similarity on entity name, not full key
        similarity(entity_name, search_term)::real as sim_score
    FROM kv_with_names
    WHERE
        -- Apply tenant filter if provided
        (tenant_id IS NULL OR full_key LIKE (tenant_id || '/%'))
        -- Fuzzy match on entity name (not full key)
        AND entity_name % search_term
        -- Filter by threshold
        AND similarity(entity_name, search_term) >= similarity_threshold
    ORDER BY sim_score DESC
    LIMIT max_results;
END;
$$;

COMMENT ON FUNCTION p8.fuzzy_scan_kv IS 
'Fuzzy search KV entries using pg_trgm similarity. 
Useful for finding entities when you don''t know the exact name.
Default threshold: 0.3 (lower = more matches, higher = stricter).
Example: SELECT * FROM p8.fuzzy_scan_kv(''friday'', ''tenant-test'', 0.2, 10);';

-- Grant execute permission
GRANT EXECUTE ON FUNCTION p8.fuzzy_scan_kv(text, text, real, int) TO public;

-- PERFORMANCE NOTE:
-- This function uses Cypher queries which may be slow for large datasets.
-- For production, consider materializing KV data to a regular table with GIN index:
-- CREATE INDEX idx_kv_key_trgm ON kv_table USING GIN (key gin_trgm_ops);
--
-- Note: KV storage is meant for direct lookups, not scanning.
-- Fuzzy search contradicts the KV design pattern but may be useful for discovery.
