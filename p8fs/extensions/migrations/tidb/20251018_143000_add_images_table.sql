-- Add images table for visual content with CLIP embeddings
-- Migration: 20251018_143000_add_images_table.sql
-- TiDB version

USE public;

CREATE TABLE IF NOT EXISTS images (
    id VARCHAR(36) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    uri TEXT NOT NULL,
    caption TEXT,
    source VARCHAR(255),
    source_id VARCHAR(255),
    width BIGINT,
    height BIGINT,
    mime_type VARCHAR(255),
    file_size BIGINT,
    tags JSON,
    metadata JSON,
    tenant_id VARCHAR(255) NOT NULL,
    KEY idx_images_source (source),
    KEY idx_images_source_id (source_id),
    KEY idx_images_tenant (tenant_id)
);

-- TiDB doesn't have built-in vector indexes, embeddings stored in separate schema
USE embeddings;

CREATE TABLE IF NOT EXISTS images_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector JSON NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    vector_dimension INT DEFAULT 512,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_entity_field_tenant (entity_id, field_name, tenant_id),
    KEY idx_images_embeddings_entity (entity_id),
    KEY idx_images_embeddings_provider (embedding_provider),
    KEY idx_images_embeddings_field_provider (field_name, embedding_provider)
);
