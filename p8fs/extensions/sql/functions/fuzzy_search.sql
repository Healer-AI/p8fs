-- Fuzzy search function using AGE graph vertices and pg_trgm similarity
-- Graph-based fuzzy text search for REM queries
-- Ensures consistency with get_entities by reading from same AGE graph data

DROP FUNCTION IF EXISTS p8.fuzzy_search;

CREATE OR REPLACE FUNCTION p8.fuzzy_search(
    search_terms TEXT[],
    similarity_threshold REAL DEFAULT 0.5,
    userid TEXT DEFAULT NULL,
    max_matches_per_term INT DEFAULT 5
)
RETURNS JSONB
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    unique_keys TEXT[];
    result JSONB;
BEGIN
    /*
    Graph-based fuzzy search that reads from AGE vertices (same as get_entities).

    This ensures FUZZY and LOOKUP read from the same underlying AGE graph data.

    Flow:
    1. Query AGE graph vertices for fuzzy matches on entity keys
    2. Use similarity() to find keys matching search terms
    3. Call get_entities() with matched keys (same as LOOKUP)
    4. Return entity data with search metadata

    Key Design:
    - Reads from percolate._ag_label_vertex (AGE graph vertices)
    - Uses pg_trgm similarity on vertex properties->>'key'
    - Calls get_entities() for consistent entity retrieval
    - Same data source as LOOKUP queries

    Threshold behavior:
    - 0.3-0.4: Too permissive, includes weak matches
    - 0.5: Good balance (default)
    - 0.6: More restrictive
    - 0.7: Very restrictive, only close matches

    Performance:
    - Single optimized query with CROSS JOIN
    - Limits matches per term (default 5)
    - Deduplicates results before passing to get_entities
    - Uses GIN index on vertex key field

    Parameters:
    - search_terms: Array of strings to search for
    - similarity_threshold: Minimum similarity score (0.0-1.0, default: 0.5)
    - userid: Optional user ID for filtering results
    - max_matches_per_term: Maximum matches per search term (default: 5)

    Example usage:
    -- Search for multiple terms
    SELECT p8.fuzzy_search(ARRAY['customer', 'order', 'product']);

    -- Search with custom threshold
    SELECT p8.fuzzy_search(ARRAY['afternoon', 'meeting'], 0.6);

    -- Search with user filter
    SELECT p8.fuzzy_search(ARRAY['project', 'alpha'], 0.6, 'user123');

    -- Search with all parameters
    SELECT p8.fuzzy_search(ARRAY['database'], 0.7, 'user123', 10);

    Returns:
    {
        "search_metadata": {
            "search_terms": ["afternoon", "meeting"],
            "similarity_threshold": 0.5,
            "max_matches_per_term": 5,
            "matched_keys_count": 4,
            "matched_keys": ["Friday Afternoon", "Monday Morning", ...]
        },
        "entities": {
            "public.resources": {
                "data": [...],
                "count": 2
            },
            "public.moments": {
                "data": [...],
                "count": 1
            }
        }
    }
    */

    -- Ensure pg_trgm extension is available (already loaded in 00_install.sql)
    -- CREATE EXTENSION IF NOT EXISTS pg_trgm;

    -- Get all fuzzy matches from AGE graph vertices in a single optimized query
    WITH all_matches AS (
        SELECT DISTINCT
            json_data->>'key' AS key,
            search_term,
            similarity(json_data->>'key', search_term) AS similarity_score,
            ROW_NUMBER() OVER (
                PARTITION BY search_term
                ORDER BY similarity(json_data->>'key', search_term) DESC
            ) as rank
        FROM (
            SELECT id, properties::json AS json_data
            FROM p8graph._ag_label_vertex
        ) vertices
        CROSS JOIN unnest(search_terms) AS search_term
        WHERE similarity(json_data->>'key', search_term) > similarity_threshold
    ),
    ranked_matches AS (
        SELECT key
        FROM all_matches
        WHERE rank <= max_matches_per_term
    )
    SELECT ARRAY_AGG(DISTINCT key)
    INTO unique_keys
    FROM ranked_matches;

    -- If we have matched keys, get the entities using get_entities()
    -- This ensures FUZZY uses the same retrieval path as LOOKUP
    IF unique_keys IS NOT NULL AND array_length(unique_keys, 1) > 0 THEN
        -- Call get_entities with the matched keys (same as LOOKUP!)
        result := p8.get_entities(unique_keys, userid);
    ELSE
        -- Return empty result if no matches found
        result := '{}'::JSONB;
    END IF;

    -- Add metadata about the search
    result := jsonb_build_object(
        'search_metadata', jsonb_build_object(
            'search_terms', search_terms,
            'similarity_threshold', similarity_threshold,
            'max_matches_per_term', max_matches_per_term,
            'matched_keys_count', COALESCE(array_length(unique_keys, 1), 0),
            'matched_keys', unique_keys
        ),
        'entities', result
    );

    RETURN result;
END;
$BODY$;

-- Grant execute permission to public
GRANT EXECUTE ON FUNCTION p8.fuzzy_search(TEXT[], REAL, TEXT, INT) TO public;

-- Add comment for documentation
COMMENT ON FUNCTION p8.fuzzy_search IS
'Graph-based fuzzy search using AGE vertices and pg_trgm similarity.
Reads from same AGE graph data as get_entities for consistency.
Returns entities matching search terms with similarity above threshold.
Example: SELECT p8.fuzzy_search(ARRAY[''afternoon'', ''meeting''], 0.5);';

-- Performance index (should exist from AGE setup)
-- CREATE INDEX IF NOT EXISTS idx_vertex_key_trgm
--   ON percolate._ag_label_vertex USING gin ((properties::json->>'key') gin_trgm_ops);
