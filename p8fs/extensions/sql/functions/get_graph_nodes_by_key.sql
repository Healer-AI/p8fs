-- =============================================================================
-- GRAPH NODE RETRIEVAL BY KEY
-- =============================================================================

DROP FUNCTION IF EXISTS p8.get_graph_nodes_by_key;
CREATE OR REPLACE FUNCTION p8.get_graph_nodes_by_key(
    keys text[],
    userid text DEFAULT NULL
)
RETURNS TABLE(id text, entity_type text, node_data text) -- Returning id, entity_type, and full node data
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    sql_query text;
BEGIN
    -- Set search path to include ag_catalog for AGE functions
    SET search_path = ag_catalog, "$user", public;
    
    -- Construct the dynamic SQL with quoted keys and square brackets
    -- Build the dynamic SQL for retrieving graph nodes, optionally filtering by user_id
    -- Start building the Cypher match, filtering by business key
    sql_query := 'WITH nodes AS (
                    SELECT * 
                    FROM cypher(''p8graph'', $$ 
                        MATCH (v)
                        WHERE v.key IN ['
                 || array_to_string(ARRAY(SELECT '"' || replace(replace(k, '\', '\\'), '"', '\"') || '"' FROM unnest(keys) AS k), ', ')
                 || '] 
                        RETURN v, v.key 
                    $$) AS (v agtype, key agtype)
                  ), 
                  records AS (
                    SELECT 
                        key::text AS id, 
                        (v::json)->>''label'' AS entity_type,
                        v::json::text AS node_data
                    FROM nodes
                  )
                  SELECT DISTINCT id, entity_type, node_data
                  FROM records';
    
    -- Execute the dynamic SQL and return the result
    RETURN QUERY EXECUTE sql_query;
END;
$BODY$;