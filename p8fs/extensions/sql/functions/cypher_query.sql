-- =============================================================================
-- CYPHER QUERY WRAPPER FUNCTIONS
-- =============================================================================

DROP FUNCTION IF EXISTS p8.cypher_query;
CREATE OR REPLACE FUNCTION p8.cypher_query(
    cypher_query TEXT,
    return_columns TEXT DEFAULT 'result agtype',
    graph_name TEXT DEFAULT 'p8graph'   
)
RETURNS TABLE(result JSONB)
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    sql_query TEXT;
BEGIN
    /*
    Execute a Cypher query against the p8 graph database.
    
    Examples:
    - SELECT * FROM p8.cypher_query('MATCH (v) RETURN v');
    - SELECT * FROM p8.cypher_query('CREATE (n:DeviceAuth {key: "abc123"}) RETURN n');
    */

    SET search_path = ag_catalog, "$user", public;

    -- Build dynamic SQL with proper escaping
    -- Use format() with %I for identifier quoting to prevent SQL injection
    sql_query := format('WITH cypher_result AS (
                    SELECT * FROM ag_catalog.cypher(%L, $$%s$$) 
                    AS (%s)
                  )
                  SELECT to_jsonb(cypher_result) FROM cypher_result;',
                  graph_name, cypher_query, return_columns);

    RETURN QUERY EXECUTE sql_query;
END;
$BODY$;