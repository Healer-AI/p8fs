-- Migration: Add speakers and key_emotions to Moments, add moment_id to Sessions (TiDB)
-- Created: 2025-10-18 14:25:55
-- Description: Adds speaker tracking and key emotions to moments table,
--              and adds moment_id reference to sessions table for contextual linking.
--
-- This is an INCREMENTAL migration for production databases.
-- For new deployments, use the full install.sql script.

-- Use the public database
USE `public`;

-- ============================================================================
-- MOMENTS TABLE UPDATES
-- ============================================================================

-- Add speakers column (JSON text for speaker array)
ALTER TABLE moments
    ADD COLUMN IF NOT EXISTS speakers TEXT COMMENT 'List of speaker entries with format: {text: str, speaker_identifier: str, timestamp: datetime, emotion: str}';

-- Add key_emotions column (JSON text for emotional context tags)
ALTER TABLE moments
    ADD COLUMN IF NOT EXISTS key_emotions TEXT COMMENT 'Key emotional context tags for the entire moment (e.g., collaborative, tense, enthusiastic)';

-- ============================================================================
-- SESSIONS TABLE UPDATES
-- ============================================================================

-- Add moment_id column (optional reference to moments table)
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS moment_id VARCHAR(255) COMMENT 'Optional reference to associated Moment entity ID for contextual linking';

-- Add index for moment_id lookups
CREATE INDEX IF NOT EXISTS idx_sessions_moment_id ON sessions (moment_id);

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Verify moments table structure
-- DESCRIBE moments;

-- Verify sessions table structure
-- DESCRIBE sessions;

-- ============================================================================
-- ROLLBACK INSTRUCTIONS (if needed)
-- ============================================================================

-- IMPORTANT: Only uncomment and run these if you need to rollback the migration
-- DROP INDEX idx_sessions_moment_id ON sessions;
-- ALTER TABLE moments DROP COLUMN IF EXISTS speakers;
-- ALTER TABLE moments DROP COLUMN IF EXISTS key_emotions;
-- ALTER TABLE sessions DROP COLUMN IF EXISTS moment_id;
