-- =============================================================================
-- UTILITY AND MAINTENANCE FUNCTIONS  
-- =============================================================================

DROP FUNCTION IF EXISTS p8.cleanup_expired_kv;
CREATE OR REPLACE FUNCTION p8.cleanup_expired_kv()
RETURNS integer
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    deleted_count integer := 0;
    cleanup_result jsonb;
BEGIN
    /*
    Clean up expired KV entries from the graph.
    Should be run periodically to maintain performance.
    
    Example:
    SELECT p8.cleanup_expired_kv();
    */
    
    SET search_path = ag_catalog, "$user", public;
    
    -- Delete expired nodes
    SELECT result INTO cleanup_result
    FROM p8.cypher_query(
        'MATCH (n:KVStorage) 
         WHERE n.expires_at IS NOT NULL 
         AND n.expires_at < "' || to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') || '"
         DELETE n 
         RETURN COUNT(*) as deleted',
        'deleted agtype'
    ) LIMIT 1;
    
    IF cleanup_result IS NOT NULL THEN
        deleted_count := (cleanup_result->>'deleted')::integer;
    END IF;
    
    RETURN deleted_count;
END;
$BODY$;