-- Migration: Add speakers and key_emotions to Moments, add moment_id to Sessions
-- Created: 2025-10-18 14:25:55
-- Description: Adds speaker tracking and key emotions to moments table,
--              and adds moment_id reference to sessions table for contextual linking.
--
-- This is an INCREMENTAL migration for production databases.
-- For new deployments, use the full install.sql script.

-- ============================================================================
-- MOMENTS TABLE UPDATES
-- ============================================================================

-- Add speakers column (JSONB array of speaker dictionaries)
ALTER TABLE public.moments
    ADD COLUMN IF NOT EXISTS speakers JSONB;

-- Add key_emotions column (TEXT array for emotional context tags)
ALTER TABLE public.moments
    ADD COLUMN IF NOT EXISTS key_emotions TEXT[];

-- Add GIN indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_moments_speakers_gin ON public.moments USING GIN (speakers);
CREATE INDEX IF NOT EXISTS idx_moments_key_emotions_gin ON public.moments USING GIN (key_emotions);

-- Add column comments
COMMENT ON COLUMN public.moments.speakers IS 'List of speaker entries with format: {text: str, speaker_identifier: str, timestamp: datetime, emotion: str}';
COMMENT ON COLUMN public.moments.key_emotions IS 'Key emotional context tags for the entire moment (e.g., collaborative, tense, enthusiastic)';

-- ============================================================================
-- SESSIONS TABLE UPDATES
-- ============================================================================

-- Add moment_id column (optional reference to moments table)
ALTER TABLE public.sessions
    ADD COLUMN IF NOT EXISTS moment_id UUID;

-- Add index for moment_id lookups
CREATE INDEX IF NOT EXISTS idx_sessions_moment_id ON public.sessions (moment_id);

-- Add column comment
COMMENT ON COLUMN public.sessions.moment_id IS 'Optional reference to associated Moment entity ID for contextual linking';

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Verify moments table structure
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_schema = 'public' AND table_name = 'moments'
-- ORDER BY ordinal_position;

-- Verify sessions table structure
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_schema = 'public' AND table_name = 'sessions'
-- ORDER BY ordinal_position;

-- ============================================================================
-- ROLLBACK INSTRUCTIONS (if needed)
-- ============================================================================

-- IMPORTANT: Only uncomment and run these if you need to rollback the migration
-- DROP INDEX IF EXISTS public.idx_moments_speakers_gin;
-- DROP INDEX IF EXISTS public.idx_moments_key_emotions_gin;
-- DROP INDEX IF EXISTS public.idx_sessions_moment_id;
-- ALTER TABLE public.moments DROP COLUMN IF EXISTS speakers;
-- ALTER TABLE public.moments DROP COLUMN IF EXISTS key_emotions;
-- ALTER TABLE public.sessions DROP COLUMN IF EXISTS moment_id;
