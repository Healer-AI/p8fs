-- Fix kv_storage.key column to support JWT tokens (>255 chars)
-- Changes VARCHAR(255) to TEXT to match PostgreSQL schema

ALTER TABLE kv_storage MODIFY COLUMN `key` TEXT NOT NULL;
