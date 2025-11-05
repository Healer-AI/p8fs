-- =============================================================================
-- KV RETRIEVAL OPERATIONS
-- =============================================================================

DROP FUNCTION IF EXISTS p8.get_kv;
CREATE OR REPLACE FUNCTION p8.get_kv(
    kv_key text,
    userid text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    result_row RECORD;
    check_time timestamp;
    cypher_query text;
    node_props jsonb;
    stored_value text;
    expires_at_str text;
BEGIN
    /*
    Retrieve a value by key from graph KV storage.
    Returns NULL if key doesn't exist or has expired.
    
    Example:
    SELECT p8.get_kv('device-auth:abc123');
    */
    
    SET search_path = ag_catalog, "$user", public;
    check_time := NOW();
    
    -- Build the cypher query to return properties directly
    cypher_query := 'MATCH (n:KVStorage {key: ' || quote_literal(kv_key) || '}) RETURN n.value, n.expires_at';
    
    -- Execute the query
    FOR result_row IN
        EXECUTE format('SELECT * FROM cypher(''p8graph'', $$%s$$) AS (value agtype, expires_at agtype)', cypher_query)
    LOOP
        -- Extract the value and expiration directly from the result
        BEGIN
            -- Get the value as text (AGE returns it as agtype)
            stored_value := result_row.value::text;
            
            -- Remove quotes if they exist (AGE adds quotes around strings)
            IF stored_value LIKE '"%' AND stored_value LIKE '%"' THEN
                stored_value := substring(stored_value FROM 2 FOR length(stored_value) - 2);
            END IF;
            
            -- Check expiration if exists
            IF result_row.expires_at IS NOT NULL AND result_row.expires_at::text != 'null' THEN
                expires_at_str := result_row.expires_at::text;
                -- Remove quotes from timestamp too
                IF expires_at_str LIKE '"%' AND expires_at_str LIKE '%"' THEN
                    expires_at_str := substring(expires_at_str FROM 2 FOR length(expires_at_str) - 2);
                END IF;
                
                -- Check if expired
                IF check_time > expires_at_str::timestamp THEN
                    -- Expired, delete node and return NULL
                    PERFORM * FROM cypher('p8graph', 
                        'MATCH (n:KVStorage {key: ' || quote_literal(kv_key) || '}) DELETE n'
                    ) AS (result agtype);
                    RETURN NULL;
                END IF;
            END IF;
            
            -- Return the stored value as JSONB
            BEGIN
                RETURN stored_value::jsonb;
            EXCEPTION
                WHEN OTHERS THEN
                    -- If not valid JSON, return as JSON string
                    RETURN to_jsonb(stored_value);
            END;
        EXCEPTION
            WHEN OTHERS THEN
                -- If any error in processing, continue to next row
                NULL;
        END;
    END LOOP;
    
    -- No node found
    RETURN NULL;
END;
$BODY$;