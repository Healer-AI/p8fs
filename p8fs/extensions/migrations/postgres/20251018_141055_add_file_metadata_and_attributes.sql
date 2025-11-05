-- Migration: Add parsing_metadata and derived_attributes to Files table
-- Created: 2025-10-18 14:10:55
-- Description: Adds optional JSON columns for parser metadata and ML-derived attributes to the files table,
--              and creates a new file_attributes table for flexible attribute storage from any model.

-- Add new columns to files table
ALTER TABLE public.files
    ADD COLUMN IF NOT EXISTS parsing_metadata JSONB,
    ADD COLUMN IF NOT EXISTS derived_attributes JSONB;

-- Add GIN indexes for the new JSONB columns
CREATE INDEX IF NOT EXISTS idx_files_parsing_metadata_gin ON public.files USING GIN (parsing_metadata);
CREATE INDEX IF NOT EXISTS idx_files_derived_attributes_gin ON public.files USING GIN (derived_attributes);

-- Add comments to explain column purposes
COMMENT ON COLUMN public.files.parsing_metadata IS 'Custom parser metadata (e.g., PDF parser uncertainty about pages, actual page count parsed, parsing warnings)';
COMMENT ON COLUMN public.files.derived_attributes IS 'Machine learning model-derived attributes (e.g., background noise detection in WAV files, arbitrary ML-inferred properties)';

-- Create file_attributes table for flexible ML model attribute storage
CREATE TABLE IF NOT EXISTS public.file_attributes (
    id UUID PRIMARY KEY NOT NULL DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    file_id TEXT NOT NULL,
    model TEXT NOT NULL,
    attributes JSONB NOT NULL,
    tenant_id TEXT NOT NULL
);

-- Add GIN index for attributes JSONB column
CREATE INDEX IF NOT EXISTS idx_file_attributes_attributes_gin ON public.file_attributes USING GIN (attributes);

-- Add indexes for common lookup patterns
CREATE INDEX IF NOT EXISTS idx_file_attributes_file_id ON public.file_attributes (file_id);
CREATE INDEX IF NOT EXISTS idx_file_attributes_model ON public.file_attributes (model);
CREATE INDEX IF NOT EXISTS idx_file_attributes_tenant_id ON public.file_attributes (tenant_id);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('file_attributes', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_file_attributes_updated_at ON public.file_attributes;
CREATE TRIGGER update_file_attributes_updated_at
    BEFORE UPDATE ON public.file_attributes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments to file_attributes table and columns
COMMENT ON TABLE public.file_attributes IS 'Flexible attribute storage for files from ML models and processors';
COMMENT ON COLUMN public.file_attributes.file_id IS 'File entity ID (deterministic hash from uri + tenant_id)';
COMMENT ON COLUMN public.file_attributes.model IS 'Model or processor name that generated these attributes';
COMMENT ON COLUMN public.file_attributes.attributes IS 'JSON attributes from the model/processor';
