-- Migration: Update embedding dimension from 1536 to 384
-- Date: 2025-11-14
-- Purpose: Change all embedding vectors to use 384 dimensions for small embedding model

-- Backup note: This migration drops and recreates embedding tables
-- Ensure you have backups before running in production

USE embeddings;

-- Drop existing embedding tables (they will be recreated with new dimensions)
DROP TABLE IF EXISTS agents_embeddings;
DROP TABLE IF EXISTS functions_embeddings;
DROP TABLE IF EXISTS projects_embeddings;
DROP TABLE IF EXISTS resources_embeddings;
DROP TABLE IF EXISTS sessions_embeddings;
DROP TABLE IF EXISTS tasks_embeddings;
DROP TABLE IF EXISTS users_embeddings;
DROP TABLE IF EXISTS moments_embeddings;

-- Recreate agents_embeddings with 384 dimensions
CREATE TABLE IF NOT EXISTS agents_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(384) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 384,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.agents_embeddings SET TIFLASH REPLICA 1;

-- Recreate functions_embeddings with 384 dimensions
CREATE TABLE IF NOT EXISTS functions_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(384) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 384,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.functions_embeddings SET TIFLASH REPLICA 1;

-- Recreate projects_embeddings with 384 dimensions
CREATE TABLE IF NOT EXISTS projects_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(384) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 384,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.projects_embeddings SET TIFLASH REPLICA 1;

-- Recreate resources_embeddings with 384 dimensions
CREATE TABLE IF NOT EXISTS resources_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(384) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 384,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.resources_embeddings SET TIFLASH REPLICA 1;

-- Recreate sessions_embeddings with 384 dimensions
CREATE TABLE IF NOT EXISTS sessions_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(384) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 384,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.sessions_embeddings SET TIFLASH REPLICA 1;

-- Recreate users_embeddings with 384 dimensions
CREATE TABLE IF NOT EXISTS users_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(384) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 384,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.users_embeddings SET TIFLASH REPLICA 1;

-- Recreate tasks_embeddings with 384 dimensions
CREATE TABLE IF NOT EXISTS tasks_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(384) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 384,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.tasks_embeddings SET TIFLASH REPLICA 1;

-- Recreate moments_embeddings with 384 dimensions
CREATE TABLE IF NOT EXISTS moments_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(384) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 384,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_entity_field_tenant (entity_id, field_name, tenant_id),
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.moments_embeddings SET TIFLASH REPLICA 1;
