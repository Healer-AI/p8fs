-- P8FS Full Postgres Migration Script
-- Generated on 2025-09-06T16:12:07.552081
-- All P8FS core models with embedding support

-- Agent Model
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    name TEXT NOT NULL,
    category TEXT,
    description TEXT NOT NULL,
    spec TEXT NOT NULL,
    functions JSONB,
    metadata JSONB,
    tenant_id UUID NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agents_functions_gin ON agents USING GIN (functions);
CREATE INDEX IF NOT EXISTS idx_agents_metadata_gin ON agents USING GIN (metadata);;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.agents_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id UUID NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.agents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_agents_embeddings_vector_cosine ON embeddings.agents_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_agents_embeddings_vector_l2 ON embeddings.agents_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_agents_embeddings_vector_ip ON embeddings.agents_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_agents_embeddings_entity_field ON embeddings.agents_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_agents_embeddings_provider ON embeddings.agents_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_agents_embeddings_field_provider ON embeddings.agents_embeddings (field_name, embedding_provider);;

-- ApiProxy Model
CREATE TABLE IF NOT EXISTS api_proxies (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    name TEXT,
    proxy_uri TEXT NOT NULL,
    token TEXT,
    tenant_id UUID NOT NULL
);;

-- Error Model
CREATE TABLE IF NOT EXISTS errors (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    date TIMESTAMPTZ,
    process TEXT,
    message TEXT NOT NULL,
    stack_trace TEXT,
    level TEXT,
    metadata JSONB,
    userid TEXT,
    tenant_id UUID NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_errors_metadata_gin ON errors USING GIN (metadata);;

-- Files Model
CREATE TABLE IF NOT EXISTS files (
    uri TEXT PRIMARY KEY NOT NULL,
    file_size BIGINT,
    mime_type TEXT,
    content_hash TEXT,
    upload_timestamp TIMESTAMPTZ,
    metadata JSONB,
    tenant_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_files_metadata_gin ON files USING GIN (metadata);;

-- Function Model
CREATE TABLE IF NOT EXISTS functions (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    key TEXT,
    name TEXT NOT NULL,
    verb TEXT,
    endpoint TEXT,
    description TEXT,
    function_spec JSONB,
    proxy_uri TEXT,
    tenant_id UUID NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_functions_function_spec_gin ON functions USING GIN (function_spec);;

-- Job Model
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    job_type TEXT NOT NULL,
    status TEXT,
    priority BIGINT,
    payload JSONB,
    max_retries BIGINT,
    retry_count BIGINT,
    timeout BIGINT,
    is_batch BOOLEAN,
    batch_size BIGINT,
    items_processed BIGINT,
    result JSONB,
    error TEXT,
    callback_url TEXT,
    callback_headers JSONB,
    queued_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    openai_batch_id TEXT,
    openai_batch_status TEXT,
    tenant_id UUID NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_payload_gin ON jobs USING GIN (payload);
CREATE INDEX IF NOT EXISTS idx_jobs_result_gin ON jobs USING GIN (result);
CREATE INDEX IF NOT EXISTS idx_jobs_callback_headers_gin ON jobs USING GIN (callback_headers);;

-- LanguageModelApi Model
CREATE TABLE IF NOT EXISTS language_model_apis (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    name TEXT NOT NULL,
    model TEXT,
    scheme TEXT,
    completions_uri TEXT NOT NULL,
    token_env_key TEXT,
    token TEXT,
    tenant_id UUID NOT NULL
);;

-- Project Model
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    target_date TIMESTAMPTZ,
    collaborator_ids JSONB,
    status TEXT,
    priority BIGINT,
    tenant_id UUID NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_collaborator_ids_gin ON projects USING GIN (collaborator_ids);;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.projects_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id UUID NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_projects_embeddings_vector_cosine ON embeddings.projects_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_projects_embeddings_vector_l2 ON embeddings.projects_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_projects_embeddings_vector_ip ON embeddings.projects_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_projects_embeddings_entity_field ON embeddings.projects_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_projects_embeddings_provider ON embeddings.projects_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_projects_embeddings_field_provider ON embeddings.projects_embeddings (field_name, embedding_provider);;

-- Resources Model
CREATE TABLE IF NOT EXISTS resources (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    name TEXT NOT NULL,
    category TEXT,
    content TEXT NOT NULL,
    summary TEXT NOT NULL,
    ordinal BIGINT,
    uri TEXT,
    metadata JSONB,
    graph_paths JSONB,
    resource_timestamp TIMESTAMPTZ,
    userid TEXT,
    tenant_id UUID NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_resources_metadata_gin ON resources USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_resources_graph_paths_gin ON resources USING GIN (graph_paths);;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.resources_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id UUID NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.resources(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_resources_embeddings_vector_cosine ON embeddings.resources_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_resources_embeddings_vector_l2 ON embeddings.resources_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_resources_embeddings_vector_ip ON embeddings.resources_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_resources_embeddings_entity_field ON embeddings.resources_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_resources_embeddings_provider ON embeddings.resources_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_resources_embeddings_field_provider ON embeddings.resources_embeddings (field_name, embedding_provider);;

-- Session Model
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    name TEXT,
    query TEXT NOT NULL,
    user_rating BIGINT,
    agent TEXT,
    parent_session_id TEXT,
    thread_id TEXT,
    channel_id TEXT,
    channel_type TEXT,
    session_type TEXT,
    metadata JSONB,
    session_completed_at TIMESTAMPTZ,
    graph_paths JSONB,
    userid TEXT,
    tenant_id UUID NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_metadata_gin ON sessions USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_sessions_graph_paths_gin ON sessions USING GIN (graph_paths);;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.sessions_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id UUID NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_vector_cosine ON embeddings.sessions_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_vector_l2 ON embeddings.sessions_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_vector_ip ON embeddings.sessions_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_entity_field ON embeddings.sessions_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_provider ON embeddings.sessions_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_field_provider ON embeddings.sessions_embeddings (field_name, embedding_provider);;

-- Task Model
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    target_date TIMESTAMPTZ,
    collaborator_ids JSONB,
    status TEXT,
    priority BIGINT,
    project_name TEXT,
    estimated_effort BIGINT,
    progress DOUBLE PRECISION,
    tenant_id UUID NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_collaborator_ids_gin ON tasks USING GIN (collaborator_ids);;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.tasks_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id UUID NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_vector_cosine ON embeddings.tasks_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_vector_l2 ON embeddings.tasks_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_vector_ip ON embeddings.tasks_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_entity_field ON embeddings.tasks_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_provider ON embeddings.tasks_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_field_provider ON embeddings.tasks_embeddings (field_name, embedding_provider);;

-- TokenUsage Model
CREATE TABLE IF NOT EXISTS token_usage (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    model_name TEXT NOT NULL,
    tokens BIGINT,
    tokens_in BIGINT,
    tokens_out BIGINT,
    tokens_other BIGINT,
    session_id TEXT,
    tenant_id UUID NOT NULL
);;

-- User Model
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    name TEXT,
    email TEXT,
    slack_id TEXT,
    linkedin TEXT,
    twitter TEXT,
    description TEXT NOT NULL,
    recent_threads JSONB,
    last_ai_response TEXT,
    interesting_entity_keys JSONB,
    token TEXT,
    token_expiry TIMESTAMPTZ,
    session_id TEXT,
    last_session_at TIMESTAMPTZ,
    roles JSONB,
    role_level BIGINT,
    groups JSONB,
    graph_paths JSONB,
    metadata JSONB,
    email_subscription_active BOOLEAN,
    userid TEXT,
    tenant_id UUID NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_recent_threads_gin ON users USING GIN (recent_threads);
CREATE INDEX IF NOT EXISTS idx_users_interesting_entity_keys_gin ON users USING GIN (interesting_entity_keys);
CREATE INDEX IF NOT EXISTS idx_users_roles_gin ON users USING GIN (roles);
CREATE INDEX IF NOT EXISTS idx_users_groups_gin ON users USING GIN (groups);
CREATE INDEX IF NOT EXISTS idx_users_graph_paths_gin ON users USING GIN (graph_paths);
CREATE INDEX IF NOT EXISTS idx_users_metadata_gin ON users USING GIN (metadata);;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.users_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id UUID NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_users_embeddings_vector_cosine ON embeddings.users_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_users_embeddings_vector_l2 ON embeddings.users_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_users_embeddings_vector_ip ON embeddings.users_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_users_embeddings_entity_field ON embeddings.users_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_users_embeddings_provider ON embeddings.users_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_users_embeddings_field_provider ON embeddings.users_embeddings (field_name, embedding_provider);;
