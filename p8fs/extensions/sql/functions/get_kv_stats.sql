-- =============================================================================
-- UTILITY AND MAINTENANCE FUNCTIONS  
-- =============================================================================

DROP FUNCTION IF EXISTS p8.get_kv_stats;  
CREATE OR REPLACE FUNCTION p8.get_kv_stats()
RETURNS TABLE(
    total_nodes integer,
    expired_nodes integer,
    active_nodes integer,
    device_auth_nodes integer,
    user_code_nodes integer
)
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
BEGIN
    /*
    Get statistics about KV storage usage.
    
    Example:
    SELECT * FROM p8.get_kv_stats();
    */
    
    SET search_path = ag_catalog, "$user", public;
    
    RETURN QUERY
    WITH stats AS (
        SELECT * FROM p8.cypher_query(
            'MATCH (n:KVStorage) 
             RETURN 
               COUNT(*) as total,
               COUNT(CASE WHEN n.expires_at IS NOT NULL AND n.expires_at < "' || 
               to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') || '" THEN 1 END) as expired,
               COUNT(CASE WHEN n.expires_at IS NULL OR n.expires_at >= "' || 
               to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') || '" THEN 1 END) as active,
               COUNT(CASE WHEN n.key STARTS WITH "device-auth:" THEN 1 END) as device_auth,
               COUNT(CASE WHEN n.key STARTS WITH "user-code:" THEN 1 END) as user_code',
            'total agtype, expired agtype, active agtype, device_auth agtype, user_code agtype'
        )
    )
    SELECT 
        (result->>'total')::integer,
        (result->>'expired')::integer, 
        (result->>'active')::integer,
        (result->>'device_auth')::integer,
        (result->>'user_code')::integer
    FROM stats;
END;
$BODY$;