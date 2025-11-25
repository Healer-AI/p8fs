-- Add pg_trgm index to kv_storage.key for fuzzy searching entity names
-- This enables fuzzy LOOKUP queries on the reverse key mapping

-- Add GIN trigram index for fuzzy text search on key field
CREATE INDEX IF NOT EXISTS idx_kv_storage_key_trgm 
ON public.kv_storage 
USING GIN (key gin_trgm_ops);

-- Add index on tenant_id for efficient filtering
CREATE INDEX IF NOT EXISTS idx_kv_storage_tenant_key 
ON public.kv_storage (tenant_id, key);

-- Performance note:
-- The gin_trgm_ops index allows fuzzy matching using:
--   - similarity(key, 'search_term')
--   - key % 'search_term' (similarity operator)
--   - word_similarity(key, 'search_term')
--
-- Example usage:
--   SELECT * FROM kv_storage 
--   WHERE tenant_id = 'tenant-test' 
--   AND key % 'david'
--   ORDER BY similarity(key, 'david') DESC;
