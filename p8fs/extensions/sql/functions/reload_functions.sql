-- Reload all P8FS graph functions with fixed AGE integration
-- Run this after fixing cypher() calls to properly reload functions

-- First, ensure AGE extension is loaded
CREATE EXTENSION IF NOT EXISTS age;

-- Set proper search path
SET search_path = ag_catalog, "$user", public;

-- Create p8graph if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'p8graph'
    ) THEN
        PERFORM ag_catalog.create_graph('p8graph');
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Could not create graph p8graph: %', SQLERRM;
END $$;

-- Load all function files in order
-- NOTE: Use compiled 03_functions.sql instead of individual files
-- The compile_migrations.py script combines all function files into one
-- This avoids path issues with \i commands
-- To reload functions, run: psql -f /path/to/extensions/sql/03_functions.sql

-- Test basic functionality
DO $$
BEGIN
    RAISE NOTICE 'Testing AGE graph functionality...';
    
    -- Test if we can execute a simple cypher query
    PERFORM * FROM ag_catalog.cypher('p8graph', $$
        MATCH (n)
        RETURN count(n) as node_count
    $$) AS (node_count agtype);
    
    RAISE NOTICE 'AGE graph functions loaded successfully!';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'AGE graph test failed: %', SQLERRM;
END $$;