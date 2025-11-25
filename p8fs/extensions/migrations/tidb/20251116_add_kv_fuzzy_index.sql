-- Add FULLTEXT index to kv_entity_mapping.entity_name for fuzzy searching
-- This enables fuzzy LOOKUP queries on the reverse key mapping using FTS_MATCH_WORD

-- Add FULLTEXT index for full-text search on entity_name field
ALTER TABLE kv_entity_mapping 
ADD FULLTEXT INDEX idx_entity_name_fts (entity_name) 
WITH PARSER MULTILINGUAL;

-- Performance note:
-- The FULLTEXT index allows fuzzy matching using:
--   - FTS_MATCH_WORD('search_term', entity_name)
--   - Returns BM25 relevance scores
--   - Supports multilingual text (EN, CN, JP, KR)
--
-- Example usage:
--   SELECT * FROM kv_entity_mapping
--   WHERE tenant_id = 'tenant-test'
--   AND FTS_MATCH_WORD('david', entity_name) > 0
--   ORDER BY FTS_MATCH_WORD('david', entity_name) DESC;
--
-- Fallback (if FULLTEXT not available):
--   SELECT * FROM kv_entity_mapping
--   WHERE tenant_id = 'tenant-test'
--   AND entity_name LIKE '%david%'
--   ORDER BY entity_name;
