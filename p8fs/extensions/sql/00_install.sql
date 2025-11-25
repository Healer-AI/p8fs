-- P8FS Core PostgreSQL Extensions Installation
-- Simple setup for testing - minimal extensions only

---------create app user-----------------
-- Create app user if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app') THEN
        CREATE USER app;
    END IF;
END $$;

-- Grant privileges to app user
GRANT ALL PRIVILEGES ON DATABASE app TO app;
GRANT ALL PRIVILEGES ON SCHEMA public TO app;

---------extensions----------------------
-- Essential extensions for P8FS testing
CREATE EXTENSION IF NOT EXISTS vector;     -- For embedding storage and similarity search
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- For fuzzy text search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; -- For UUID generation
CREATE EXTENSION IF NOT EXISTS age;

-- Create p8 graph if not exists  
DO $$ 
BEGIN
    -- Set search path for AGE operations
    EXECUTE 'SET search_path = ag_catalog, "$user", public';
    
    IF NOT EXISTS (
        SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'p8graph'
    ) THEN
        PERFORM create_graph('p8graph');
    END IF;
END $$;

-- Reset search path to default for table creation (public first, then ag_catalog for functions)
SET search_path = public, ag_catalog;

---------basic utilities----------------
-- Update timestamp trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

------Add p8 schema-------------------
CREATE SCHEMA IF NOT EXISTS p8;
CREATE SCHEMA IF NOT EXISTS models;
CREATE SCHEMA IF NOT EXISTS embeddings;

-- Simple UUID generation from JSON (for deterministic IDs)
CREATE OR REPLACE FUNCTION p8.json_to_uuid(json_data jsonb)
    RETURNS uuid
    LANGUAGE 'plpgsql'
    COST 100
    IMMUTABLE PARALLEL UNSAFE
AS $BODY$
DECLARE
    json_string TEXT;
    hash TEXT;
    uuid_result UUID;
BEGIN
    -- Serialize JSON deterministically
    json_string := jsonb(json_data)::text;
    hash := md5(json_string);
    uuid_result := (
        SUBSTRING(hash FROM 1 FOR 8) || '-' ||
        SUBSTRING(hash FROM 9 FOR 4) || '-' ||
        SUBSTRING(hash FROM 13 FOR 4) || '-' ||
        SUBSTRING(hash FROM 17 FOR 4) || '-' ||
        SUBSTRING(hash FROM 21 FOR 12)
    )::uuid;
    
    RETURN uuid_result;
END;
$BODY$;



-- Set basic configuration for p8fs
ALTER DATABASE app SET p8.tenant_id = '00000000-0000-0000-0000-000000000000';


-- =============================================================================
-- ENTITY REGISTRATION FOR AGE GRAPH
-- =============================================================================

DROP FUNCTION IF EXISTS p8.register_entities;
CREATE OR REPLACE FUNCTION p8.register_entities(
    qualified_table_name text,
    key_name text DEFAULT 'name',
    plan boolean DEFAULT false,
    graph_name text DEFAULT 'p8graph'::text
    )
RETURNS TABLE(load_and_cypher_script text, view_script text) 
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
ROWS 1000
AS $BODY$
DECLARE
    schema_name TEXT;
    table_name TEXT;
    graph_node TEXT;
    view_name TEXT;
    -- dynamically determined business key field for graph nodes
    key_col TEXT;
    -- Local variables to avoid ambiguity
    v_schema_name TEXT;
    v_table_name TEXT;
BEGIN
    /*
    Register entities for use with AGE graph database.
    Creates views that bridge relational tables with graph nodes.
    
    Example:
    SELECT * FROM p8.register_entities('tenant.resources');
    SELECT * FROM p8.register_entities('tenant.resources', true); -- plan mode
    
    Then use: SELECT p8.insert_entity_nodes('tenant.resources');
    */
    
    -- Split schema and table name
    IF strpos(qualified_table_name, '.') > 0 THEN
        -- Has schema prefix
        schema_name := split_part(qualified_table_name, '.', 1);
        table_name := split_part(qualified_table_name, '.', 2);
    ELSE
        -- No schema prefix, default to public
        schema_name := 'public';
        table_name := qualified_table_name;
    END IF;
    
    graph_node := format('%s__%s', schema_name, table_name);
    view_name := format('vw_%s_%s', schema_name, table_name);
    
    -- Copy to local variables to avoid ambiguity in subqueries
    v_schema_name := schema_name;
    v_table_name := table_name;
    
    -- Determine the business key field for this entity
    -- Use the provided key_name if specified, otherwise auto-detect
    IF key_name IS NOT NULL THEN
        -- Verify the specified column exists
        IF EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE columns.table_schema = v_schema_name 
            AND columns.table_name = v_table_name 
            AND columns.column_name = key_name
        ) THEN
            key_col := key_name;
        ELSE
            RAISE EXCEPTION 'Specified key column % does not exist in table %.%', key_name, v_schema_name, v_table_name;
        END IF;
    ELSE
        -- Auto-detect the key column (default to 'name')
        SELECT COALESCE(
            CASE 
                WHEN EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE columns.table_schema = v_schema_name 
                    AND columns.table_name = v_table_name 
                    AND columns.column_name = 'name'
                ) THEN 'name'
                WHEN EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE columns.table_schema = v_schema_name 
                    AND columns.table_name = v_table_name 
                    AND columns.column_name = 'key'
                ) THEN 'key'
                ELSE 'id'
            END,
            'id'
        )
        INTO key_col;
    END IF;

    -- Create the LOAD and Cypher script
    load_and_cypher_script := format(
        $CY$
        SET search_path = ag_catalog, "$user", public;
        SELECT * 
        FROM cypher('%s', $$
            CREATE (:%s{key:'ref', uid: 'ref'})
        $$) as (v agtype);
        $CY$,
        graph_name, graph_node
    );

    -- Create the VIEW script, using dynamic key_col
    -- the key col defaults to name or key by convention but could be anything
    view_script := format(
        $$
        CREATE OR REPLACE VIEW p8."%s" AS (
            WITH G AS (
                SELECT id AS gid,
                       (properties::json->>'uid')::VARCHAR AS node_uid,
                       (properties::json->>'key')::VARCHAR AS node_key
                FROM %s."%s" g
            )

            SELECT t.%s AS key,
                   t.%s::VARCHAR(50) AS uid,
                   t.updated_at,
                   t.created_at,
                   t.tenant_id AS userid,
                   G.*
            FROM %s."%s" t
            LEFT JOIN G ON t.%s::character varying(50)::text = G.node_uid::character varying(50)::text
        );
        $$,
        view_name,
        graph_name,
        graph_node,
        key_col,
        key_col,
        schema_name,
        table_name,
        key_col
    );

    IF NOT plan THEN
        -- Create the initial reference node in the graph
        EXECUTE load_and_cypher_script;
        -- Create the view for entity-graph bridging
        EXECUTE view_script;
        
        RAISE NOTICE 'Registered entity % with graph label %', qualified_table_name, graph_node;
        RAISE NOTICE 'Created view p8."%"', view_name;
        RAISE NOTICE 'Key column: %', key_col;
        RAISE NOTICE 'Now run: SELECT p8.insert_entity_nodes(''%'');', qualified_table_name;
    END IF;

    RETURN QUERY SELECT load_and_cypher_script, view_script;
END;
$BODY$;

-- =============================================================================
-- GRAPH NODE OPERATIONS
-- =============================================================================

DROP FUNCTION IF EXISTS p8.get_graph_nodes_by_key;
CREATE OR REPLACE FUNCTION p8.get_graph_nodes_by_key(
    keys text[],
    userid text DEFAULT NULL
)
RETURNS TABLE(id text, entity_type text, node_data jsonb)
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    result_row RECORD;
    cypher_query text;
    key_list text;
BEGIN
    /*
    Get graph nodes by their business keys.
    Returns the key, entity type (label), and full node data.
    
    Example:
    SELECT * FROM p8.get_graph_nodes_by_key(ARRAY['test - Chunk 1', 'another key']);
    */
    
    SET search_path = ag_catalog, "$user", public;
    
    -- Build properly escaped key list for Cypher
    SELECT string_agg(quote_literal(k), ', ') INTO key_list
    FROM unnest(keys) AS k;
    
    -- Build Cypher query
    cypher_query := 'MATCH (v) WHERE v.key IN [' || key_list || '] RETURN v';
    
    -- Execute query and process results
    FOR result_row IN
        EXECUTE format('SELECT * FROM cypher(''p8graph'', $cypher$ %s $cypher$) AS (v agtype)', cypher_query)
    LOOP
        DECLARE
            node_json jsonb;
            labels_json jsonb;
            label_text text;
        BEGIN
            -- Convert agtype to jsonb
            node_json := to_jsonb(result_row.v::text);
            
            -- Extract label (entity type) - AGE stores it in the node structure
            IF node_json ? 'label' THEN
                label_text := node_json->>'label';
            ELSE
                label_text := 'Unknown';
            END IF;
            
            -- Return the result
            id := COALESCE(node_json->'properties'->>'key', '');
            entity_type := label_text;
            node_data := node_json;
            
            -- Apply user filter if provided
            IF userid IS NOT NULL THEN
                IF node_json->'properties' ? 'user_id' THEN
                    IF node_json->'properties'->>'user_id' != userid THEN
                        CONTINUE;
                    END IF;
                END IF;
            END IF;
            
            RETURN NEXT;
        END;
    END LOOP;
END;
$BODY$;

DROP FUNCTION IF EXISTS p8.get_records_by_keys;
CREATE OR REPLACE FUNCTION p8.get_records_by_keys(
    table_name TEXT,
    key_list TEXT[],
    key_column TEXT DEFAULT 'name'::TEXT,
    include_entity_metadata BOOLEAN DEFAULT TRUE
)
RETURNS JSONB
LANGUAGE 'plpgsql'
COST 100
VOLATILE PARALLEL UNSAFE
AS $BODY$
DECLARE
    result JSONB;
    query TEXT;
    schema_name VARCHAR;
    pure_table_name VARCHAR;
    safe_key_list TEXT[];
BEGIN
    /*
    Get records from a table by keys.
    Now uses 'name' as default key column for p8fs resources.
    */
    
    SET LOCAL search_path = p8, public;
    
    schema_name := lower(split_part(table_name, '.', 1));
    pure_table_name := split_part(table_name, '.', 2);

    -- Handle empty/null key lists
    IF key_list IS NULL OR array_length(key_list, 1) IS NULL OR array_length(key_list, 1) = 0 THEN
        RETURN '[]'::jsonb;
    END IF;

    -- Filter out empty strings and null values
    safe_key_list := array_remove(array_remove(key_list, ''), NULL);
    
    IF safe_key_list IS NULL OR array_length(safe_key_list, 1) IS NULL OR array_length(safe_key_list, 1) = 0 THEN
        RETURN '[]'::jsonb;
    END IF;
    
    -- Build and execute query
    query := format('SELECT COALESCE(jsonb_agg(to_jsonb(t)), ''[]''::jsonb) FROM %I."%s" t WHERE t.%I::TEXT = ANY($1::TEXT[])', 
                    schema_name, pure_table_name, key_column);
    
    EXECUTE query USING safe_key_list INTO result;
    
    -- Return simple data structure for p8
    RETURN jsonb_build_object('data', COALESCE(result, '[]'::jsonb));
END;
$BODY$;

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
    entity_group RECORD;
BEGIN
    /*
    Get entities by keys from the graph index.
    This is the main entry point for graph-based entity retrieval.
    
    Example:
    SELECT * FROM p8.get_entities(ARRAY['test - Chunk 1']);
    */

    SET search_path = ag_catalog, "$user", public;
    
    -- Get nodes from graph and process by entity type
    FOR entity_group IN
        WITH nodes AS (
            SELECT id, entity_type FROM p8.get_graph_nodes_by_key(keys, userid)
            WHERE id IS NOT NULL AND id != ''
        )
        SELECT 
            entity_type,
            array_agg(id) AS entity_keys
        FROM nodes
        WHERE entity_type IS NOT NULL
        GROUP BY entity_type
    LOOP
        -- For each entity type, get records from the corresponding table
        -- Convert label format (e.g., 'public__resources') to table name
        DECLARE
            table_name text;
            entity_data jsonb;
        BEGIN
            -- Convert label to table name (e.g., 'public__resources' -> 'public.resources')
            table_name := replace(entity_group.entity_type, '__', '.');
            
            -- Get records for this entity type
            entity_data := p8.get_records_by_keys(table_name, entity_group.entity_keys);
            
            -- Add to result
            result := result || jsonb_build_object(entity_group.entity_type, entity_data);
        END;
    END LOOP;

    RETURN result;
END;
$BODY$;