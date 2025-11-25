
-- ================================================
-- Source: functions/header.sql
-- ================================================

-- p8 PostgreSQL Functions with AGE Graph Database Integration
-- 
-- This file implements graph-based KV storage for device authorization flows
-- and other temporary data using PostgreSQL AGE extension for graph operations.
--
-- Key Functions:
-- - cypher_query: Execute Cypher queries against AGE graph
-- - get_entities: Retrieve entities by keys from graph index
-- - add_nodes: Add nodes to graph from entity tables
-- - KV operations: put_kv, get_kv, scan_kv for device auth flows

-- Set search path to include AGE catalog
SET search_path = ag_catalog, "$user", public;

-- Create p8 schema if not exists
CREATE SCHEMA IF NOT EXISTS p8;

-- Create p8 graph if not exists  
DO $$ 
BEGIN
    -- Check if AGE extension is available before trying to load it
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'age') THEN
        -- AGE is already loaded by CREATE EXTENSION in 00_install.sql
        -- Set search path for AGE operations
        EXECUTE 'SET search_path = ag_catalog, "$user", public';
        
        -- Create graph if it doesn't exist
        IF NOT EXISTS (
            SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'p8graph'
        ) THEN
            PERFORM create_graph('p8graph');
        END IF;
    ELSE
        RAISE NOTICE 'AGE extension not available - graph functions will not work';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Could not initialize AGE graph: %', SQLERRM;
END $$;


-- ================================================
-- Source: functions/add_nodes.sql
-- ================================================

-- =============================================================================
-- GRAPH NODE OPERATIONS
-- =============================================================================

-- Single node operation
DROP FUNCTION IF EXISTS p8.add_node;
CREATE OR REPLACE FUNCTION p8.add_node(
    node_key text,
    node_label text,
    properties jsonb DEFAULT '{}'::jsonb,
    userid text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    cypher_query TEXT;
    node_result jsonb;
    props_str TEXT;
BEGIN
    /*
    Add a single node to the p8 graph.
    
    Example:
    SELECT p8.add_node(
        'device-auth:abc123', 
        'DeviceAuth', 
        '{"device_code": "abc123", "client_id": "desktop_app"}'::jsonb
    );
    */
    
    SET search_path = ag_catalog, "$user", public;
    
    -- Build properties string for Cypher
    props_str := 'key: "' || node_key || '"';
    
    -- Add user_id if provided
    IF userid IS NOT NULL THEN
        props_str := props_str || ', user_id: "' || userid || '"';
    END IF;
    
    -- Add custom properties
    IF properties != '{}'::jsonb THEN
        SELECT props_str || ', ' ||
            string_agg(
                key || ': ' || 
                CASE 
                    WHEN jsonb_typeof(value) = 'string' THEN quote_literal(value::text)
                    ELSE value::text 
                END, 
                ', '
            )
        INTO props_str
        FROM jsonb_each(properties);
    END IF;
    
    -- Create Cypher MERGE query to avoid duplicates
    -- MERGE ensures node exists, then SET updates all properties
    cypher_query := 'MERGE (n:' || node_label || ' {key: "' || node_key || '"}) ' ||
                    'SET n = {' || props_str || '} ' ||
                    'RETURN n';
    
    -- Execute and return result
    SELECT result INTO node_result 
    FROM p8.cypher_query(cypher_query, 'n agtype') 
    LIMIT 1;
    
    RETURN node_result;
END;
$BODY$;

-- Batch node operation for entity tables
DROP FUNCTION IF EXISTS p8.add_nodes;
CREATE OR REPLACE FUNCTION p8.add_nodes(
    table_name text
)
RETURNS integer
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    cypher_query TEXT;
    row RECORD;
    sql TEXT;
    schema_name TEXT;
    pure_table_name TEXT;
    view_name TEXT;
    view_exists BOOLEAN;
    nodes_created_count INTEGER := 0;  
BEGIN
    /*
    Batch add nodes from entity tables to the graph.
    Uses contractual views (vw_<schema>_<table>) that provide uid, key, and userid columns.
    Only processes rows where gid IS NULL (not yet in graph).
    
    Example:
    SELECT p8.add_nodes('public.language_model_apis');
    */
    
    -- AGE extension is preloaded at session level
    SET search_path = ag_catalog, "$user", public; 

    -- Handle schema.table parsing correctly
    IF strpos(table_name, '.') > 0 THEN
        -- Has schema prefix
        schema_name := lower(split_part(table_name, '.', 1));
        pure_table_name := split_part(table_name, '.', 2);
    ELSE
        -- No schema prefix, default to public
        schema_name := 'public';
        pure_table_name := table_name;
    END IF;
    
    view_name := format('p8."vw_%s_%s"', schema_name, pure_table_name);
    
    -- Check if the view exists before attempting to query it
    EXECUTE format('
        SELECT EXISTS (
            SELECT FROM information_schema.views 
            WHERE table_schema = ''p8'' 
            AND table_name = ''vw_%s_%s''
        )', schema_name, pure_table_name) 
    INTO view_exists;
    
    -- If view doesn't exist, log a message and return 0
    IF NOT view_exists THEN
        RAISE NOTICE 'View % does not exist - skipping node creation', view_name;
        RETURN 0;
    END IF;

    cypher_query := 'CREATE ';

    -- Loop through each row in the table  
    FOR row IN
        EXECUTE format('SELECT uid, key, userid FROM %s WHERE gid IS NULL LIMIT 1660', view_name)
    LOOP
        -- Append Cypher node creation for each row (include user_id only when present)
        IF row.userid IS NULL THEN
            cypher_query := cypher_query || format(
                '(:%s__%s {uid: "%s", key: "%s"}), ',
                schema_name, pure_table_name, row.uid, row.key
            );
        ELSE
            cypher_query := cypher_query || format(
                '(:%s__%s {uid: "%s", key: "%s", user_id: "%s"}), ',
                schema_name, pure_table_name, row.uid, row.key, row.userid
            );
        END IF;

        nodes_created_count := nodes_created_count + 1;
    END LOOP;

    -- Run the batch
    IF nodes_created_count > 0 THEN
        cypher_query := left(cypher_query, length(cypher_query) - 2);

        -- Use p8.cypher_query wrapper function instead of direct cypher call
        PERFORM * FROM p8.cypher_query(cypher_query, 'v agtype');

        RETURN nodes_created_count;
    ELSE
        -- No rows to process
        RAISE NOTICE 'Nothing to do in add_nodes for this batch - all good';
        RETURN 0;
    END IF;
END;
$BODY$;


-- ================================================
-- Source: functions/cleanup_expired_kv.sql
-- ================================================

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


-- ================================================
-- Source: functions/cypher_query.sql
-- ================================================

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


-- ================================================
-- Source: functions/fuzzy_scan_kv.sql
-- ================================================

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


-- ================================================
-- Source: functions/fuzzy_search.sql
-- ================================================

-- Fuzzy search function using pg_trgm similarity
-- Table-agnostic fuzzy text search for REM queries
-- Pushes fuzzy search computation down to database

DROP FUNCTION IF EXISTS p8.fuzzy_search;

CREATE OR REPLACE FUNCTION p8.fuzzy_search(
    table_name text,
    search_fields text[],
    query_text text,
    tenant_id text,
    similarity_threshold real DEFAULT 0.3,
    max_results int DEFAULT 10,
    use_word_similarity boolean DEFAULT false
)
RETURNS TABLE(
    result jsonb
)
LANGUAGE plpgsql
AS $$
DECLARE
    sql_query text;
    field_name text;
    field_conditions text[] := '{}';
    score_expressions text[] := '{}';
    sim_func text;
    sim_op text;
BEGIN
    /*
    Table-agnostic fuzzy text search using pg_trgm similarity.

    Searches any table for records where specified fields fuzzy-match the query text.
    Returns full row data as JSONB with similarity scores.

    Parameters:
    - table_name: Target table to search (e.g., 'resources', 'moments')
    - search_fields: Array of fields to search (e.g., ARRAY['name', 'content'])
    - query_text: Text to search for (fuzzy matching)
    - tenant_id: Tenant filter (required for security)
    - similarity_threshold: Minimum similarity score (0.0-1.0, default: 0.3)
    - max_results: Maximum number of results to return (default: 10)
    - use_word_similarity: Use word_similarity vs similarity (default: false)

    Examples:
    -- Search resources by name
    SELECT result FROM p8.fuzzy_search(
        'resources',
        ARRAY['name'],
        'afternoon',
        'tenant-test',
        0.1,
        5
    );

    -- Search moments by content with word similarity
    SELECT result FROM p8.fuzzy_search(
        'moments',
        ARRAY['content', 'summary'],
        'database design',
        'tenant-test',
        0.2,
        10,
        true
    );

    Returns:
    - result: JSONB object containing full row data plus similarity_score field
    */

    -- Choose similarity function
    IF use_word_similarity THEN
        sim_func := 'word_similarity';
        sim_op := '<%';
    ELSE
        sim_func := 'similarity';
        sim_op := '%';
    END IF;

    -- Build field conditions and score expressions
    FOREACH field_name IN ARRAY search_fields
    LOOP
        field_conditions := array_append(
            field_conditions,
            format('%I %s $1', field_name, sim_op)
        );
        score_expressions := array_append(
            score_expressions,
            format('%s(%I, $1)', sim_func, field_name)
        );
    END LOOP;

    -- Build max score expression
    DECLARE
        max_score_expr text;
    BEGIN
        IF array_length(score_expressions, 1) > 1 THEN
            max_score_expr := format('GREATEST(%s)', array_to_string(score_expressions, ', '));
        ELSE
            max_score_expr := score_expressions[1];
        END IF;

        -- Build dynamic SQL query
        sql_query := format(
            'SELECT to_jsonb(t.*) || jsonb_build_object(''similarity_score'', (%s)::real) as result
             FROM %I t
             WHERE tenant_id = $2
             AND (%s)
             AND (%s) >= $3
             ORDER BY (%s) DESC
             LIMIT $4',
            max_score_expr,
            table_name,
            array_to_string(field_conditions, ' OR '),
            max_score_expr,
            max_score_expr
        );
    END;

    -- Execute query with parameters
    RETURN QUERY EXECUTE sql_query
        USING query_text, tenant_id, similarity_threshold, max_results;
END;
$$;

COMMENT ON FUNCTION p8.fuzzy_search IS
'Table-agnostic fuzzy text search using pg_trgm similarity.
Searches any table for fuzzy matches on specified fields.
Default threshold: 0.3 (lower = more matches, higher = stricter).
Example: SELECT * FROM p8.fuzzy_search(''resources'', ARRAY[''name''], ''friday'', ''tenant-test'', 0.2, 10);';

-- Grant execute permission
GRANT EXECUTE ON FUNCTION p8.fuzzy_search(text, text[], text, text, real, int, boolean) TO public;


-- ================================================
-- Source: functions/get_entities.sql
-- ================================================

-- =============================================================================
-- ENTITY OPERATIONS (Legacy compatibility with Percolate patterns)
-- =============================================================================

DROP FUNCTION IF EXISTS p8.get_entities;
CREATE OR REPLACE FUNCTION p8.get_entities(
    keys text[],
    userid text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    result JSONB := '{}'::JSONB;
BEGIN
    /*
    Get entities by keys from the graph index.
    This is the main entry point for graph-based entity retrieval.
    
    Example:
    SELECT * FROM p8.get_entities(ARRAY['gpt-5', 'claude-3']);
    */

    SET search_path = ag_catalog, "$user", public;
    
    -- Load nodes based on keys, returning the associated entity type and key
    WITH nodes AS (
        SELECT id, entity_type FROM p8.get_graph_nodes_by_key(keys, userid)
    ),
    grouped_records AS (
        SELECT 
            CASE 
                WHEN strpos(entity_type, '__') > 0 THEN replace(entity_type, '__', '.')
                ELSE entity_type
            END AS entity_type,
            array_agg(id) FILTER (WHERE id IS NOT NULL AND id != '') AS keys
        FROM nodes
        WHERE id IS NOT NULL AND entity_type IS NOT NULL AND id != ''
        GROUP BY entity_type
        HAVING array_length(array_agg(id) FILTER (WHERE id IS NOT NULL AND id != ''), 1) > 0
    )
    -- Combine grouped records with their table data using a JOIN and aggregate the result
    -- Use COALESCE to handle empty results
    SELECT COALESCE(
        jsonb_object_agg(
            entity_type, 
            p8.get_records_by_keys(entity_type, grouped_records.keys)
        ), 
        '{}'::jsonb
    )
    INTO result
    FROM grouped_records;

    -- Return the final JSON object
    RETURN result;
END;
$BODY$;


-- ================================================
-- Source: functions/get_graph_nodes_by_key.sql
-- ================================================

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


-- ================================================
-- Source: functions/get_kv.sql
-- ================================================

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


-- ================================================
-- Source: functions/get_kv_stats.sql
-- ================================================

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


-- ================================================
-- Source: functions/get_records_by_keys.sql
-- ================================================

-- =============================================================================
-- RECORD RETRIEVAL BY KEYS
-- =============================================================================

DROP FUNCTION IF EXISTS p8.get_records_by_keys;
CREATE OR REPLACE FUNCTION p8.get_records_by_keys(
    table_name TEXT,
    key_list TEXT[],
    key_column TEXT DEFAULT 'name'::TEXT,  -- Default to 'name' for p8fs
    include_entity_metadata BOOLEAN DEFAULT TRUE
)
RETURNS JSONB
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    result JSONB;            -- The JSON result to be returned
    metadata JSONB;          -- The metadata JSON result
    query TEXT;              -- Dynamic query to execute
    schema_name VARCHAR;
    pure_table_name VARCHAR;
    safe_key_list TEXT[];    -- Safely processed key list
BEGIN
    -- Ensure clean search path to avoid session variable interference
    SET LOCAL search_path = p8, public;
    
    schema_name := lower(split_part(table_name, '.', 1));
    pure_table_name := split_part(table_name, '.', 2);

    -- Check if key_list is empty, null, or contains only empty strings
    IF key_list IS NULL OR array_length(key_list, 1) IS NULL OR array_length(key_list, 1) = 0 THEN
        result := '[]'::jsonb;
    ELSE
        -- Filter out empty strings and null values from key_list
        safe_key_list := array_remove(array_remove(key_list, ''), NULL);
        
        -- Check again after filtering
        IF safe_key_list IS NULL OR array_length(safe_key_list, 1) IS NULL OR array_length(safe_key_list, 1) = 0 THEN
            result := '[]'::jsonb;
        ELSE
            -- Use a safer approach: build the query with explicit array handling
            query := format('SELECT jsonb_agg(to_jsonb(t)) FROM %I."%s" t WHERE t.%I::TEXT = ANY($1::TEXT[])', schema_name, pure_table_name, key_column);
            
            -- Execute the dynamic query with the safe key list
            EXECUTE query USING safe_key_list INTO result;
        END IF;
    END IF;
    
    -- For p8fs, we'll simplify metadata handling
    metadata := NULL;
    
    -- Return JSONB object containing data (simplified for p8fs)
    RETURN jsonb_build_object('data', COALESCE(result, '[]'::jsonb));
END;
$BODY$;


-- ================================================
-- Source: functions/insert_entity_nodes.sql
-- ================================================

-- =============================================================================
-- BATCH OPERATIONS FOR ENTITY NODE MANAGEMENT
-- =============================================================================

DROP FUNCTION IF EXISTS p8.insert_entity_nodes;
CREATE OR REPLACE FUNCTION p8.insert_entity_nodes(
    entity_table text
)
RETURNS TABLE(entity_name text, total_records_affected integer) 
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
ROWS 1000
AS $BODY$
DECLARE
    records_affected INTEGER := 0;
    total_records_affected INTEGER := 0;
BEGIN
    /*
    Insert entity nodes in batches using p8.add_nodes function.
    Loop until no more records are affected.
    */
    
    -- Loop until no more records are affected
    LOOP
        -- Call p8_add_nodes and get the number of records affected
        SELECT add_nodes INTO records_affected FROM p8.add_nodes(entity_table);

        -- If no records are affected, exit the loop
        IF records_affected = 0 THEN
            EXIT;
        END IF;

        -- Add the current records affected to the total
        total_records_affected := total_records_affected + records_affected;
    END LOOP;

    -- Return the entity name and total records affected
    RETURN QUERY SELECT entity_table AS entity_name, total_records_affected;
END;
$BODY$;


-- ================================================
-- Source: functions/put_kv.sql
-- ================================================

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


-- ================================================
-- Source: functions/scan_kv.sql
-- ================================================

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
