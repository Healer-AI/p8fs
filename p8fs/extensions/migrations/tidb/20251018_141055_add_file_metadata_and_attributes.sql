-- Migration: Add parsing_metadata and derived_attributes to Files table (TiDB)
-- Created: 2025-10-18 14:10:55
-- Description: Adds optional JSON columns for parser metadata and ML-derived attributes to the files table,
--              and creates a new file_attributes table for flexible attribute storage from any model.

-- Use the public database
USE `public`;

-- Add new columns to files table
-- Note: TiDB uses JSON type instead of JSONB, and TEXT type for JSON storage
ALTER TABLE files
    ADD COLUMN IF NOT EXISTS parsing_metadata TEXT COMMENT 'Custom parser metadata (e.g., PDF parser uncertainty about pages, actual page count parsed, parsing warnings)',
    ADD COLUMN IF NOT EXISTS derived_attributes TEXT COMMENT 'Machine learning model-derived attributes (e.g., background noise detection in WAV files, arbitrary ML-inferred properties)';

-- Create file_attributes table for flexible ML model attribute storage
CREATE TABLE IF NOT EXISTS file_attributes (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    file_id VARCHAR(255) NOT NULL COMMENT 'File entity ID (deterministic hash from uri + tenant_id)',
    model VARCHAR(255) NOT NULL COMMENT 'Model or processor name that generated these attributes',
    attributes TEXT NOT NULL COMMENT 'JSON attributes from the model/processor',
    tenant_id VARCHAR(36) NOT NULL,
    INDEX idx_file_attributes_file_id (file_id),
    INDEX idx_file_attributes_model (model),
    INDEX idx_file_attributes_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
COMMENT='Flexible attribute storage for files from ML models and processors';
