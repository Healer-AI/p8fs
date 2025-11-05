-- P8FS Full TiDB Migration Script
-- Generated from Python models with TiDB-specific types
--
-- This migration creates tables in a 'public' database to match PostgreSQL's
-- public schema structure. This makes it easier to compare and switch between
-- PostgreSQL and TiDB deployments.
--
-- Structure:
--   - Main tables: public.agents, public.users, etc.
--   - Embedding tables: embeddings.agents_embeddings, etc.
--
-- Connection string: mysql://root@localhost:4000/public

-- Create public database to match PostgreSQL structure
CREATE DATABASE IF NOT EXISTS `public`;
USE `public`;

-- Create embeddings database (TiDB uses database instead of schema)
CREATE DATABASE IF NOT EXISTS embeddings;

-- Helper function for updated_at trigger (TiDB uses ON UPDATE CURRENT_TIMESTAMP)
-- Note: TiDB automatically handles updated_at with ON UPDATE CURRENT_TIMESTAMP

-- KV Entity Mapping Table for reverse key lookups

CREATE TABLE IF NOT EXISTS kv_entity_mapping (
    entity_name VARCHAR(255),
    entity_type VARCHAR(50),
    entity_key VARCHAR(500),
    tenant_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_lookup (tenant_id, entity_type, entity_name),
    INDEX idx_key_lookup (entity_key)
);

-- Agent Model
CREATE TABLE IF NOT EXISTS agents (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    name VARCHAR(255) NOT NULL,
    category TEXT,
    description TEXT NOT NULL,
    spec TEXT,
    functions TEXT,
    metadata TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS embeddings.agents_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(1536) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 1536,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.agents_embeddings SET TIFLASH REPLICA 1;

-- ApiProxy Model
CREATE TABLE IF NOT EXISTS api_proxies (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    name TEXT,
    proxy_uri VARCHAR(255) NOT NULL,
    token TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Error Model
CREATE TABLE IF NOT EXISTS errors (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    date TIMESTAMP,
    process TEXT,
    message VARCHAR(255) NOT NULL,
    stack_trace TEXT,
    level VARCHAR(255),
    metadata TEXT,
    userid TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Files Model
CREATE TABLE IF NOT EXISTS files (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    uri VARCHAR(255) NOT NULL,
    file_size TEXT,
    mime_type TEXT,
    content_hash TEXT,
    upload_timestamp TEXT,
    metadata TEXT,
    parsing_metadata TEXT,
    derived_attributes TEXT,
    model_pipeline_run_at TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Function Model
CREATE TABLE IF NOT EXISTS functions (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    `key` TEXT,
    name VARCHAR(255) NOT NULL,
    verb TEXT,
    endpoint TEXT,
    description TEXT,
    function_spec TEXT,
    proxy_uri TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Job Model
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    job_type TEXT NOT NULL,
    status TEXT,
    priority BIGINT,
    tenant_id VARCHAR(255) NOT NULL,
    payload TEXT,
    max_retries BIGINT,
    retry_count BIGINT,
    timeout TEXT,
    is_batch TINYINT(1),
    batch_size TEXT,
    items_processed BIGINT,
    result TEXT,
    error TEXT,
    callback_url TEXT,
    callback_headers TEXT,
    queued_at TIMESTAMP,
    started_at TEXT,
    completed_at TEXT,
    openai_batch_id TEXT,
    openai_batch_status TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- LanguageModelApi Model
CREATE TABLE IF NOT EXISTS language_model_apis (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    name VARCHAR(255) NOT NULL,
    model TEXT,
    scheme TEXT,
    completions_uri VARCHAR(255) NOT NULL,
    token_env_key TEXT,
    token TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Project Model
CREATE TABLE IF NOT EXISTS projects (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    target_date TEXT,
    collaborator_ids TEXT,
    status TEXT,
    priority TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS embeddings.projects_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(1536) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 1536,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.projects_embeddings SET TIFLASH REPLICA 1;

-- Resources Model
CREATE TABLE IF NOT EXISTS resources (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    name VARCHAR(255) NOT NULL,
    category TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    ordinal TEXT,
    uri TEXT,
    metadata TEXT,
    graph_paths TEXT,
    resource_timestamp TEXT,
    userid TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS embeddings.resources_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(1536) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 1536,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.resources_embeddings SET TIFLASH REPLICA 1;

-- Session Model
CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    name TEXT,
    query TEXT NOT NULL,
    user_rating TEXT,
    agent TEXT,
    parent_session_id TEXT,
    thread_id TEXT,
    channel_id TEXT,
    channel_type TEXT,
    session_type TEXT,
    metadata TEXT,
    session_completed_at TEXT,
    graph_paths TEXT,
    userid TEXT,
    moment_id TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS embeddings.sessions_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(1536) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 1536,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.sessions_embeddings SET TIFLASH REPLICA 1;

-- Task Model
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    target_date TEXT,
    collaborator_ids TEXT,
    status TEXT,
    priority TEXT,
    project_name TEXT,
    estimated_effort TEXT,
    progress TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS embeddings.tasks_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(1536) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 1536,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.tasks_embeddings SET TIFLASH REPLICA 1;

-- Tenant Model
CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    tenant_id VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    public_key VARCHAR(255) NOT NULL,
    device_ids JSON,
    storage_bucket TEXT,
    metadata JSON,
    active TINYINT(1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- TokenUsage Model
CREATE TABLE IF NOT EXISTS token_usage (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    model_name VARCHAR(255) NOT NULL,
    tokens TEXT,
    tokens_in BIGINT,
    tokens_out BIGINT,
    tokens_other BIGINT,
    session_id TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- User Model
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    name TEXT,
    email TEXT,
    slack_id TEXT,
    linkedin TEXT,
    twitter TEXT,
    description TEXT NOT NULL,
    recent_threads TEXT,
    last_ai_response TEXT,
    interesting_entity_keys TEXT,
    token TEXT,
    token_expiry TEXT,
    session_id TEXT,
    last_session_at TEXT,
    roles TEXT,
    role_level TEXT,
    graph_paths TEXT,
    metadata TEXT,
    email_subscription_active TEXT,
    userid TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS embeddings.users_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR(1536) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    vector_dimension INT DEFAULT 1536,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider),
    INDEX idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE embeddings.users_embeddings SET TIFLASH REPLICA 1;

-- KVStorage Model
CREATE TABLE IF NOT EXISTS kv_storage (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP,
    updated_at TEXT,
    `key` VARCHAR(255) NOT NULL,
    value JSON NOT NULL,
    expires_at TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
