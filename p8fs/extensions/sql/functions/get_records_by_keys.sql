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
            -- Use the view which abstracts the key column to 'key' for all tables
            -- Views are created by register_entities and map the actual key column to 'key'
            query := format('SELECT jsonb_agg(to_jsonb(t)) FROM p8.vw_%s_%s t WHERE t.key::TEXT = ANY($1::TEXT[])', schema_name, pure_table_name);
            
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