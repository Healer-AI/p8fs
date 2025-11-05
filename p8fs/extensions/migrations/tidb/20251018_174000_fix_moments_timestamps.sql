-- Fix moments table timestamp columns
-- Migration: 20251018_174000_fix_moments_timestamps.sql
-- TiDB version

USE public;

-- Fix created_at: change from nullable TIMESTAMP to TIMESTAMP with DEFAULT
ALTER TABLE moments
  MODIFY created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Fix updated_at: change from TEXT to TIMESTAMP with auto-update
ALTER TABLE moments
  MODIFY updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- Update existing NULL timestamps to current time
UPDATE moments
SET created_at = CURRENT_TIMESTAMP
WHERE created_at IS NULL;

UPDATE moments
SET updated_at = CURRENT_TIMESTAMP
WHERE updated_at IS NULL OR updated_at = '';
