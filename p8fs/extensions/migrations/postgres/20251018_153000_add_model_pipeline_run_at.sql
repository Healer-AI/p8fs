-- Migration: Add model_pipeline_run_at to files table
-- Date: 2025-10-18 15:30:00
-- Description: Adds model_pipeline_run_at timestamp column to track when advanced model processing was completed

-- Add model_pipeline_run_at column to files table
ALTER TABLE files ADD COLUMN IF NOT EXISTS model_pipeline_run_at TIMESTAMP;

-- Add comment for documentation
COMMENT ON COLUMN files.model_pipeline_run_at IS 'Timestamp when advanced model pipeline processing was completed';

-- Create index for efficient querying of processed files
CREATE INDEX IF NOT EXISTS idx_files_model_pipeline_run_at ON files(model_pipeline_run_at) WHERE model_pipeline_run_at IS NOT NULL;
