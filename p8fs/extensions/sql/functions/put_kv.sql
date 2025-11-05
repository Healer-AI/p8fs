-- =============================================================================
-- KV STORAGE OPERATIONS
-- =============================================================================

DROP FUNCTION IF EXISTS p8.put_kv;
CREATE OR REPLACE FUNCTION p8.put_kv(
    kv_key text,
    kv_value jsonb,
    ttl_seconds integer DEFAULT NULL,
    userid text DEFAULT NULL
)
RETURNS boolean
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    expires_at_iso text;
    props jsonb;
    query_result jsonb;
BEGIN
    /*
    Store a key-value pair in the graph with optional TTL.
    Used for device authorization flows and temporary data.
    
    Example:
    SELECT p8.put_kv(
        'device-auth:abc123',
        '{"device_code": "abc123", "user_code": "A1B2", "status": "pending"}'::jsonb,
        600  -- 10 minutes TTL
    );
    */
    
    SET search_path = ag_catalog, "$user", public;
    
    -- Calculate expiration time if TTL provided
    IF ttl_seconds IS NOT NULL THEN
        expires_at_iso := to_char(NOW() + (ttl_seconds || ' seconds')::interval, 'YYYY-MM-DD"T"HH24:MI:SS"Z"');
    END IF;
    
    -- Build properties object
    props := jsonb_build_object(
        'value', kv_value::text,  -- Store as JSON string for AGE compatibility
        'created_at', to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
        'updated_at', to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    );
    
    IF expires_at_iso IS NOT NULL THEN
        props := props || jsonb_build_object('expires_at', expires_at_iso);
    END IF;
    
    -- First try to update existing node
    BEGIN
        SELECT result INTO query_result 
        FROM p8.cypher_query(
            'MATCH (n:KVStorage {key: ' || quote_literal(kv_key) || '}) 
             SET n.value = ' || quote_literal(kv_value::text) || ',
                 n.updated_at = ' || quote_literal(to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS"Z"')) ||
             CASE WHEN expires_at_iso IS NOT NULL THEN 
                ', n.expires_at = ' || quote_literal(expires_at_iso)
             ELSE '' END ||
             ' RETURN n',
            'n agtype'
        ) LIMIT 1;
        
        -- If update worked, return true
        IF query_result IS NOT NULL THEN
            RETURN true;
        END IF;
    EXCEPTION
        WHEN OTHERS THEN
            -- Node doesn't exist, continue to create
            NULL;
    END;
    
    -- Create new node directly with Cypher to avoid complex property handling
    BEGIN
        SELECT result INTO query_result 
        FROM p8.cypher_query(
            'CREATE (n:KVStorage {' ||
                'key: ' || quote_literal(kv_key) || ', ' ||
                'value: ' || quote_literal(kv_value::text) || ', ' ||
                'created_at: ' || quote_literal(to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS"Z"')) || ', ' ||
                'updated_at: ' || quote_literal(to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS"Z"')) ||
                CASE WHEN expires_at_iso IS NOT NULL THEN 
                    ', expires_at: ' || quote_literal(expires_at_iso)
                ELSE '' END ||
                CASE WHEN userid IS NOT NULL THEN
                    ', user_id: ' || quote_literal(userid)
                ELSE '' END ||
            '}) RETURN n',
            'n agtype'
        ) LIMIT 1;
        
        RETURN query_result IS NOT NULL;
    EXCEPTION
        WHEN OTHERS THEN
            RETURN false;
    END;
END;
$BODY$;