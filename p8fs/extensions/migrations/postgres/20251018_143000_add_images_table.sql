-- Add images table for visual content with CLIP embeddings
-- Migration: 20251018_143000_add_images_table.sql

CREATE TABLE IF NOT EXISTS public.images (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    uri TEXT NOT NULL,
    caption TEXT,
    source TEXT,
    source_id TEXT,
    width BIGINT,
    height BIGINT,
    mime_type TEXT,
    file_size BIGINT,
    tags JSONB,
    metadata JSONB,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_images_source ON images (source);
CREATE INDEX IF NOT EXISTS idx_images_source_id ON images (source_id);
CREATE INDEX IF NOT EXISTS idx_images_uri ON images (uri);
CREATE INDEX IF NOT EXISTS idx_images_tags_gin ON images USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_images_metadata_gin ON images USING GIN (metadata);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('images', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_images_updated_at ON public.images;
CREATE TRIGGER update_images_updated_at
    BEFORE UPDATE ON public.images
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.images_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(512),
    tenant_id TEXT NOT NULL,
    vector_dimension INTEGER DEFAULT 512,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.images(id) ON DELETE CASCADE,
    UNIQUE(entity_id, field_name, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_images_embeddings_vector_cosine ON embeddings.images_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_images_embeddings_vector_l2 ON embeddings.images_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_images_embeddings_vector_ip ON embeddings.images_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_images_embeddings_entity_field ON embeddings.images_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_images_embeddings_provider ON embeddings.images_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_images_embeddings_field_provider ON embeddings.images_embeddings (field_name, embedding_provider);
