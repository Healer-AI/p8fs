-- Migration: Fix tenant_id column length
-- Date: 2025-11-17
-- Description: Update tenant_id from VARCHAR(36) to VARCHAR(255) to support random tenant IDs (45 chars)
--
-- Context: Random tenant IDs are 45 characters (tenant-{32-char-uuid})
--          IMEI-based tenant IDs are 24 characters (tenant-{16-char-hash})
--          Original VARCHAR(36) was too short for random IDs

USE `public`;

-- Main tables
ALTER TABLE agents MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE api_proxies MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE errors MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE files MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE functions MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE language_model_apis MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE projects MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE resources MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE moments MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE sessions MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE tasks MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE token_usage MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE users MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE kv_storage MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;

-- Embedding tables
ALTER TABLE embeddings.agents_embeddings MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE embeddings.functions_embeddings MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE embeddings.projects_embeddings MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE embeddings.resources_embeddings MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE embeddings.moments_embeddings MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE embeddings.sessions_embeddings MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE embeddings.tasks_embeddings MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
ALTER TABLE embeddings.users_embeddings MODIFY COLUMN tenant_id VARCHAR(255) NOT NULL;
