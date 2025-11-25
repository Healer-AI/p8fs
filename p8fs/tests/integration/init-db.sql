-- Initialize test database with pgvector extension
-- This runs automatically when the Docker container starts

-- Create pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create embeddings schema
CREATE SCHEMA IF NOT EXISTS embeddings;

-- Grant permissions
GRANT ALL ON SCHEMA embeddings TO postgres;
GRANT ALL ON SCHEMA public TO postgres;

-- Optional: Create p8 schema for percolate compatibility
CREATE SCHEMA IF NOT EXISTS p8;

-- Optional: User context function stub for testing
CREATE OR REPLACE FUNCTION p8.set_user_context(user_id uuid, tenant_id uuid)
RETURNS text AS $$
BEGIN
    -- In production, this would set row-level security context
    -- For testing, we just return a success message
    RETURN 'User context set: ' || user_id || ' / ' || tenant_id;
END;
$$ LANGUAGE plpgsql;

-- Log successful initialization
DO $$ 
BEGIN 
    RAISE NOTICE 'Test database initialized with pgvector support';
END $$;