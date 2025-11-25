-- Migration: Add model_pipeline_run_at to files table
-- Date: 2025-10-18 15:30:00
-- Description: Adds model_pipeline_run_at timestamp column to track when advanced model processing was completed
-- Database: TiDB

-- Add model_pipeline_run_at column to files table
ALTER TABLE files ADD COLUMN model_pipeline_run_at TIMESTAMP NULL;

-- Create index for efficient querying of processed files
CREATE INDEX idx_files_model_pipeline_run_at ON files(model_pipeline_run_at);
