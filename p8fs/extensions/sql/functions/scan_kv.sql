-- =============================================================================
-- KV STORAGE OPERATIONS FOR DEVICE AUTHORIZATION
-- =============================================================================

DROP FUNCTION IF EXISTS p8.scan_kv;
CREATE OR REPLACE FUNCTION p8.scan_kv(
    key_prefix text,
    limit_count integer DEFAULT 100,
    userid text DEFAULT NULL
)
RETURNS TABLE(key text, value jsonb, created_at text, expires_at text)
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    sql_query text;
    cypher_query text;
BEGIN
    /*
    Scan for keys matching a prefix pattern.
    Returns key, value, and metadata for matching entries.
    
    Example:
    SELECT * FROM p8.scan_kv('device-auth:', 50);
    SELECT * FROM p8.scan_kv('user-code:', 10);
    */
    
    SET search_path = ag_catalog, "$user", public;
    
    -- Build the Cypher query dynamically
    cypher_query := 'MATCH (n:KVStorage) WHERE n.key STARTS WITH "' || 
                    replace(key_prefix, '"', '\"') || 
                    '" AND (n.expires_at IS NULL OR n.expires_at > "' || 
                    to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') || 
                    '") RETURN n LIMIT ' || 
                    limit_count::text;
                    
    -- Add user filter if provided
    IF userid IS NOT NULL THEN
        cypher_query := replace(cypher_query, 
                               'WHERE n.key STARTS WITH',
                               'WHERE (n.user_id IS NULL OR n.user_id = "' || replace(userid, '"', '\"') || '") AND n.key STARTS WITH');
    END IF;
    
    -- Execute using the cypher_query wrapper
    sql_query := 'WITH nodes AS (
                    SELECT 
                        ((result->>''result'')::jsonb->>''properties'')::jsonb as props
                    FROM p8.cypher_query($1, $2)
                  )
                  SELECT 
                    props->>''key'' as key,
                    (props->>''value'')::jsonb as value,
                    COALESCE(props->>''created_at'', '''') as created_at,
                    COALESCE(props->>''expires_at'', '''') as expires_at
                  FROM nodes
                  WHERE props->>''key'' IS NOT NULL';
    
    RETURN QUERY EXECUTE sql_query USING cypher_query, 'result agtype';
END;
$BODY$;