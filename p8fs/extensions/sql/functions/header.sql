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