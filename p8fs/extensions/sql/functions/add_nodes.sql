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