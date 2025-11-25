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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    name TEXT NOT NULL,
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

-- ApiProxy Model
CREATE TABLE IF NOT EXISTS api_proxies (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    name TEXT,
    proxy_uri TEXT NOT NULL,
    token TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Error Model
CREATE TABLE IF NOT EXISTS errors (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    date TIMESTAMP,
    process TEXT,
    message TEXT NOT NULL,
    stack_trace TEXT,
    level TEXT,
    metadata TEXT,
    userid TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Files Model
CREATE TABLE IF NOT EXISTS files (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    uri TEXT NOT NULL,
    file_size BIGINT,
    mime_type TEXT,
    content_hash TEXT,
    upload_timestamp TIMESTAMP,
    metadata TEXT,
    parsing_metadata TEXT,
    derived_attributes TEXT,
    model_pipeline_run_at TIMESTAMP,
    encryption_key_owner TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Function Model
CREATE TABLE IF NOT EXISTS functions (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `key` TEXT,
    name TEXT NOT NULL,
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    job_type TEXT NOT NULL,
    status TEXT,
    priority BIGINT,
    tenant_id TEXT NOT NULL,
    payload TEXT,
    max_retries BIGINT,
    retry_count BIGINT,
    timeout BIGINT,
    is_batch BOOLEAN,
    batch_size BIGINT,
    items_processed BIGINT,
    result TEXT,
    error TEXT,
    callback_url TEXT,
    callback_headers TEXT,
    queued_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    openai_batch_id TEXT,
    openai_batch_status TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- LanguageModelApi Model
CREATE TABLE IF NOT EXISTS language_model_apis (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    name TEXT NOT NULL,
    model TEXT,
    scheme TEXT,
    completions_uri TEXT NOT NULL,
    token_env_key TEXT,
    token TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Moment Model
CREATE TABLE IF NOT EXISTS moments (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    name TEXT NOT NULL,
    category TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    ordinal BIGINT,
    uri TEXT,
    metadata TEXT,
    graph_paths TEXT,
    resource_timestamp TIMESTAMP,
    userid TEXT,
    resource_ends_timestamp TIMESTAMP,
    present_persons TEXT,
    location TEXT,
    background_sounds TEXT,
    moment_type TEXT,
    emotion_tags TEXT,
    topic_tags TEXT,
    images TEXT,
    speakers TEXT,
    key_emotions TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS embeddings.moments_embeddings (
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

ALTER TABLE embeddings.moments_embeddings SET TIFLASH REPLICA 1;

-- Project Model
CREATE TABLE IF NOT EXISTS projects (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    target_date TIMESTAMP,
    collaborator_ids TEXT,
    status TEXT,
    priority BIGINT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS embeddings.projects_embeddings (
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

-- Resources Model
CREATE TABLE IF NOT EXISTS resources (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    name TEXT NOT NULL,
    category TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    ordinal BIGINT,
    uri TEXT,
    metadata TEXT,
    graph_paths TEXT,
    resource_timestamp TIMESTAMP,
    userid TEXT,
    tenant_id VARCHAR(36) NOT NULL,
    encryption_key_owner VARCHAR(50)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS embeddings.resources_embeddings (
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

-- Session Model
CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    name TEXT,
    query TEXT NOT NULL,
    user_rating BIGINT,
    agent TEXT,
    parent_session_id TEXT,
    thread_id TEXT,
    channel_id TEXT,
    channel_type TEXT,
    session_type TEXT,
    metadata TEXT,
    session_completed_at TIMESTAMP,
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

-- Task Model
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    target_date TIMESTAMP,
    collaborator_ids TEXT,
    status TEXT,
    priority BIGINT,
    project_name TEXT,
    estimated_effort BIGINT,
    progress DOUBLE PRECISION,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS embeddings.tasks_embeddings (
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

-- Tenant Model
CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    tenant_id TEXT NOT NULL,
    email TEXT NOT NULL,
    public_key TEXT NOT NULL,
    device_ids TEXT,
    storage_bucket TEXT,
    metadata TEXT,
    active BOOLEAN,
    security_policy TEXT,
    encryption_wait_time_days BIGINT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- TokenUsage Model
CREATE TABLE IF NOT EXISTS token_usage (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    model_name TEXT NOT NULL,
    tokens BIGINT,
    tokens_in BIGINT,
    tokens_out BIGINT,
    tokens_other BIGINT,
    session_id TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- User Model
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
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
    token_expiry TIMESTAMP,
    session_id TEXT,
    last_session_at TIMESTAMP,
    roles TEXT,
    role_level BIGINT,
    graph_paths TEXT,
    metadata TEXT,
    email_subscription_active BOOLEAN,
    userid TEXT,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS embeddings.users_embeddings (
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

-- KVStorage Model
CREATE TABLE IF NOT EXISTS kv_storage (
    id VARCHAR(255) PRIMARY KEY NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `key` TEXT NOT NULL,
    value TEXT NOT NULL,
    expires_at TIMESTAMP,
    tenant_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
