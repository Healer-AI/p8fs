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