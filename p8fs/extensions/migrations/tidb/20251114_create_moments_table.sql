-- Create moments table for TiDB
-- Date: 2025-11-14
-- Description: Creates moments table with proper schema for present_persons and speakers

USE `public`;

CREATE TABLE IF NOT EXISTS moments (
    id VARCHAR(36) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    name TEXT NOT NULL,
    category TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    ordinal BIGINT,
    uri TEXT,
    metadata TEXT COMMENT 'JSON object with additional metadata',
    graph_paths TEXT COMMENT 'JSON array for graph integration',
    resource_timestamp TIMESTAMP NULL,
    userid TEXT,
    resource_ends_timestamp TIMESTAMP NULL,
    present_persons TEXT COMMENT 'JSON array of person objects: [{"id": "fp_123", "name": "John Doe", "comment": "optional"}]',
    location TEXT,
    background_sounds TEXT,
    moment_type TEXT COMMENT 'Type: conversation, meeting, reflection, planning, etc.',
    emotion_tags TEXT COMMENT 'JSON array of emotion strings',
    topic_tags TEXT COMMENT 'JSON array of topic strings',
    images TEXT COMMENT 'JSON array of image URIs',
    speakers TEXT COMMENT 'JSON array of speaker objects: [{"text": "...", "speaker_identifier": "fp_123", "timestamp": "2025-01-13T10:30:00Z", "emotion": "happy"}]',
    key_emotions TEXT COMMENT 'JSON array of key emotion strings',
    tenant_id VARCHAR(36) NOT NULL,
    INDEX idx_moments_tenant (tenant_id),
    INDEX idx_moments_resource_timestamp (resource_timestamp),
    INDEX idx_moments_moment_type (moment_type(255)),
    INDEX idx_moments_category (category(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Create embeddings table for moments
CREATE TABLE IF NOT EXISTS embeddings.moments_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(384) NOT NULL COMMENT 'Updated to 384 dimensions for all-MiniLM-L6-v2',
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 384,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_entity_field_tenant (entity_id, field_name, tenant_id),
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id),
    VECTOR INDEX idx_vector_cosine (embedding_vector) COMMENT 'Vector index for cosine similarity'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Enable TiFlash replica for analytical queries
ALTER TABLE embeddings.moments_embeddings SET TIFLASH REPLICA 1;

-- Note: TiDB doesn't have GIN indexes like PostgreSQL, so we use regular indexes
-- JSON fields are stored as TEXT and parsed at query time
