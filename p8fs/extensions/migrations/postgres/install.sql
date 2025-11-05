<frozen runpy>:128: RuntimeWarning: 'p8fs.models.p8' found in sys.modules after import of package 'p8fs.models', but prior to execution of 'p8fs.models.p8'; this may result in unpredictable behaviour
CREATE TABLE IF NOT EXISTS public.agents (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    name TEXT NOT NULL,
    category TEXT,
    description TEXT NOT NULL,
    spec TEXT,
    functions JSONB,
    metadata JSONB,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agents_functions_gin ON agents USING GIN (functions);
CREATE INDEX IF NOT EXISTS idx_agents_metadata_gin ON agents USING GIN (metadata);

-- Ensure business key is unique per tenant
ALTER TABLE public.agents DROP CONSTRAINT IF EXISTS agents_name_tenant_id_key;
ALTER TABLE public.agents ADD CONSTRAINT agents_name_tenant_id_key UNIQUE (name, tenant_id);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('agents', 'name', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_agents_updated_at ON public.agents;
CREATE TRIGGER update_agents_updated_at 
    BEFORE UPDATE ON public.agents
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.agents_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id TEXT NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.agents(id) ON DELETE CASCADE,
    UNIQUE(entity_id, field_name, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_agents_embeddings_vector_cosine ON embeddings.agents_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_agents_embeddings_vector_l2 ON embeddings.agents_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_agents_embeddings_vector_ip ON embeddings.agents_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_agents_embeddings_entity_field ON embeddings.agents_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_agents_embeddings_provider ON embeddings.agents_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_agents_embeddings_field_provider ON embeddings.agents_embeddings (field_name, embedding_provider);;

CREATE TABLE IF NOT EXISTS public.api_proxies (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    name TEXT,
    proxy_uri TEXT NOT NULL,
    token TEXT,
    tenant_id TEXT NOT NULL
);

-- Ensure business key is unique per tenant
ALTER TABLE public.api_proxies DROP CONSTRAINT IF EXISTS api_proxies_proxy_uri_tenant_id_key;
ALTER TABLE public.api_proxies ADD CONSTRAINT api_proxies_proxy_uri_tenant_id_key UNIQUE (proxy_uri, tenant_id);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('api_proxies', 'proxy_uri', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_api_proxies_updated_at ON public.api_proxies;
CREATE TRIGGER update_api_proxies_updated_at 
    BEFORE UPDATE ON public.api_proxies
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

CREATE TABLE IF NOT EXISTS public.engrams (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    name TEXT NOT NULL,
    category TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    ordinal BIGINT,
    uri TEXT,
    metadata JSONB,
    graph_paths JSONB,
    resource_timestamp TIMESTAMPTZ,
    userid TEXT,
    processed_at TIMESTAMPTZ,
    operation_count JSONB,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_engrams_metadata_gin ON engrams USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_engrams_graph_paths_gin ON engrams USING GIN (graph_paths);
CREATE INDEX IF NOT EXISTS idx_engrams_operation_count_gin ON engrams USING GIN (operation_count);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('engrams', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_engrams_updated_at ON public.engrams;
CREATE TRIGGER update_engrams_updated_at 
    BEFORE UPDATE ON public.engrams
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.engrams_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id TEXT NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.engrams(id) ON DELETE CASCADE,
    UNIQUE(entity_id, field_name, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_engrams_embeddings_vector_cosine ON embeddings.engrams_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_engrams_embeddings_vector_l2 ON embeddings.engrams_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_engrams_embeddings_vector_ip ON embeddings.engrams_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_engrams_embeddings_entity_field ON embeddings.engrams_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_engrams_embeddings_provider ON embeddings.engrams_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_engrams_embeddings_field_provider ON embeddings.engrams_embeddings (field_name, embedding_provider);;

CREATE TABLE IF NOT EXISTS public.errors (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    date TIMESTAMPTZ,
    process TEXT,
    message TEXT NOT NULL,
    stack_trace TEXT,
    level TEXT,
    metadata JSONB,
    userid TEXT,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_errors_metadata_gin ON errors USING GIN (metadata);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('errors', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_errors_updated_at ON public.errors;
CREATE TRIGGER update_errors_updated_at 
    BEFORE UPDATE ON public.errors
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

CREATE TABLE IF NOT EXISTS public.file_attributes (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    file_id TEXT NOT NULL,
    model TEXT NOT NULL,
    attributes JSONB NOT NULL,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_file_attributes_attributes_gin ON file_attributes USING GIN (attributes);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('file_attributes', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_file_attributes_updated_at ON public.file_attributes;
CREATE TRIGGER update_file_attributes_updated_at 
    BEFORE UPDATE ON public.file_attributes
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

CREATE TABLE IF NOT EXISTS public.files (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    uri TEXT NOT NULL,
    file_size BIGINT,
    mime_type TEXT,
    content_hash TEXT,
    upload_timestamp TIMESTAMPTZ,
    metadata JSONB,
    parsing_metadata JSONB,
    derived_attributes JSONB,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_metadata_gin ON files USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_files_parsing_metadata_gin ON files USING GIN (parsing_metadata);
CREATE INDEX IF NOT EXISTS idx_files_derived_attributes_gin ON files USING GIN (derived_attributes);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('files', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_files_updated_at ON public.files;
CREATE TRIGGER update_files_updated_at 
    BEFORE UPDATE ON public.files
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

CREATE TABLE IF NOT EXISTS public.functions (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    key TEXT,
    name TEXT NOT NULL,
    verb TEXT,
    endpoint TEXT,
    description TEXT,
    function_spec JSONB,
    proxy_uri TEXT,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_functions_function_spec_gin ON functions USING GIN (function_spec);

-- Ensure business key is unique per tenant
ALTER TABLE public.functions DROP CONSTRAINT IF EXISTS functions_key_tenant_id_key;
ALTER TABLE public.functions ADD CONSTRAINT functions_key_tenant_id_key UNIQUE (key, tenant_id);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('functions', 'key', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_functions_updated_at ON public.functions;
CREATE TRIGGER update_functions_updated_at 
    BEFORE UPDATE ON public.functions
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

CREATE TABLE IF NOT EXISTS public.jobs (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    job_type TEXT NOT NULL,
    status TEXT,
    priority BIGINT,
    tenant_id TEXT NOT NULL,
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
    openai_batch_status TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_payload_gin ON jobs USING GIN (payload);
CREATE INDEX IF NOT EXISTS idx_jobs_result_gin ON jobs USING GIN (result);
CREATE INDEX IF NOT EXISTS idx_jobs_callback_headers_gin ON jobs USING GIN (callback_headers);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('jobs', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_jobs_updated_at ON public.jobs;
CREATE TRIGGER update_jobs_updated_at 
    BEFORE UPDATE ON public.jobs
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

CREATE TABLE IF NOT EXISTS public.kv_storage (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    expires_at TIMESTAMPTZ,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kv_storage_value_gin ON kv_storage USING GIN (value);

-- Ensure business key is unique per tenant
ALTER TABLE public.kv_storage DROP CONSTRAINT IF EXISTS kv_storage_key_tenant_id_key;
ALTER TABLE public.kv_storage ADD CONSTRAINT kv_storage_key_tenant_id_key UNIQUE (key, tenant_id);

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_kv_storage_updated_at ON public.kv_storage;
CREATE TRIGGER update_kv_storage_updated_at 
    BEFORE UPDATE ON public.kv_storage
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

CREATE TABLE IF NOT EXISTS public.language_model_apis (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    name TEXT NOT NULL,
    model TEXT,
    scheme TEXT,
    completions_uri TEXT NOT NULL,
    token_env_key TEXT,
    token TEXT,
    tenant_id TEXT NOT NULL
);

-- Ensure business key is unique per tenant
ALTER TABLE public.language_model_apis DROP CONSTRAINT IF EXISTS language_model_apis_name_tenant_id_key;
ALTER TABLE public.language_model_apis ADD CONSTRAINT language_model_apis_name_tenant_id_key UNIQUE (name, tenant_id);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('language_model_apis', 'name', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_language_model_apis_updated_at ON public.language_model_apis;
CREATE TRIGGER update_language_model_apis_updated_at 
    BEFORE UPDATE ON public.language_model_apis
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

CREATE TABLE IF NOT EXISTS public.moments (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    name TEXT NOT NULL,
    category TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    ordinal BIGINT,
    uri TEXT,
    metadata JSONB,
    graph_paths JSONB,
    resource_timestamp TIMESTAMPTZ,
    userid TEXT,
    resource_ends_timestamp TIMESTAMPTZ,
    present_persons JSONB,
    location TEXT,
    background_sounds TEXT,
    moment_type TEXT,
    emotion_tags JSONB,
    topic_tags JSONB,
    images JSONB,
    speakers JSONB,
    key_emotions JSONB,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_moments_metadata_gin ON moments USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_moments_graph_paths_gin ON moments USING GIN (graph_paths);
CREATE INDEX IF NOT EXISTS idx_moments_present_persons_gin ON moments USING GIN (present_persons);
CREATE INDEX IF NOT EXISTS idx_moments_emotion_tags_gin ON moments USING GIN (emotion_tags);
CREATE INDEX IF NOT EXISTS idx_moments_topic_tags_gin ON moments USING GIN (topic_tags);
CREATE INDEX IF NOT EXISTS idx_moments_images_gin ON moments USING GIN (images);
CREATE INDEX IF NOT EXISTS idx_moments_speakers_gin ON moments USING GIN (speakers);
CREATE INDEX IF NOT EXISTS idx_moments_key_emotions_gin ON moments USING GIN (key_emotions);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('moments', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_moments_updated_at ON public.moments;
CREATE TRIGGER update_moments_updated_at 
    BEFORE UPDATE ON public.moments
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.moments_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id TEXT NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.moments(id) ON DELETE CASCADE,
    UNIQUE(entity_id, field_name, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_moments_embeddings_vector_cosine ON embeddings.moments_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_moments_embeddings_vector_l2 ON embeddings.moments_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_moments_embeddings_vector_ip ON embeddings.moments_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_moments_embeddings_entity_field ON embeddings.moments_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_moments_embeddings_provider ON embeddings.moments_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_moments_embeddings_field_provider ON embeddings.moments_embeddings (field_name, embedding_provider);;

CREATE TABLE IF NOT EXISTS public.presentpersons (
    fingerprint_id TEXT NOT NULL,
    user_id TEXT,
    user_label TEXT,
    tenant_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('presentpersons', 'name', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_presentpersons_updated_at ON public.presentpersons;
CREATE TRIGGER update_presentpersons_updated_at 
    BEFORE UPDATE ON public.presentpersons
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

CREATE TABLE IF NOT EXISTS public.projects (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    target_date TIMESTAMPTZ,
    collaborator_ids JSONB,
    status TEXT,
    priority BIGINT,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_collaborator_ids_gin ON projects USING GIN (collaborator_ids);

-- Ensure business key is unique per tenant
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_name_tenant_id_key;
ALTER TABLE public.projects ADD CONSTRAINT projects_name_tenant_id_key UNIQUE (name, tenant_id);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('projects', 'name', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_projects_updated_at ON public.projects;
CREATE TRIGGER update_projects_updated_at 
    BEFORE UPDATE ON public.projects
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.projects_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id TEXT NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.projects(id) ON DELETE CASCADE,
    UNIQUE(entity_id, field_name, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_projects_embeddings_vector_cosine ON embeddings.projects_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_projects_embeddings_vector_l2 ON embeddings.projects_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_projects_embeddings_vector_ip ON embeddings.projects_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_projects_embeddings_entity_field ON embeddings.projects_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_projects_embeddings_provider ON embeddings.projects_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_projects_embeddings_field_provider ON embeddings.projects_embeddings (field_name, embedding_provider);;

CREATE TABLE IF NOT EXISTS public.resources (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    name TEXT NOT NULL,
    category TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    ordinal BIGINT,
    uri TEXT,
    metadata JSONB,
    graph_paths JSONB,
    resource_timestamp TIMESTAMPTZ,
    userid TEXT,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_resources_metadata_gin ON resources USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_resources_graph_paths_gin ON resources USING GIN (graph_paths);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('resources', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_resources_updated_at ON public.resources;
CREATE TRIGGER update_resources_updated_at 
    BEFORE UPDATE ON public.resources
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.resources_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id TEXT NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.resources(id) ON DELETE CASCADE,
    UNIQUE(entity_id, field_name, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_resources_embeddings_vector_cosine ON embeddings.resources_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_resources_embeddings_vector_l2 ON embeddings.resources_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_resources_embeddings_vector_ip ON embeddings.resources_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_resources_embeddings_entity_field ON embeddings.resources_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_resources_embeddings_provider ON embeddings.resources_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_resources_embeddings_field_provider ON embeddings.resources_embeddings (field_name, embedding_provider);;

CREATE TABLE IF NOT EXISTS public.sessions (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
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
    moment_id TEXT,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_metadata_gin ON sessions USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_sessions_graph_paths_gin ON sessions USING GIN (graph_paths);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('sessions', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_sessions_updated_at ON public.sessions;
CREATE TRIGGER update_sessions_updated_at 
    BEFORE UPDATE ON public.sessions
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.sessions_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id TEXT NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.sessions(id) ON DELETE CASCADE,
    UNIQUE(entity_id, field_name, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_vector_cosine ON embeddings.sessions_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_vector_l2 ON embeddings.sessions_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_vector_ip ON embeddings.sessions_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_entity_field ON embeddings.sessions_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_provider ON embeddings.sessions_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_sessions_embeddings_field_provider ON embeddings.sessions_embeddings (field_name, embedding_provider);;

CREATE TABLE IF NOT EXISTS public.tasks (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    target_date TIMESTAMPTZ,
    collaborator_ids JSONB,
    status TEXT,
    priority BIGINT,
    project_name TEXT,
    estimated_effort BIGINT,
    progress DOUBLE PRECISION,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_collaborator_ids_gin ON tasks USING GIN (collaborator_ids);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('tasks', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_tasks_updated_at ON public.tasks;
CREATE TRIGGER update_tasks_updated_at 
    BEFORE UPDATE ON public.tasks
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.tasks_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id TEXT NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.tasks(id) ON DELETE CASCADE,
    UNIQUE(entity_id, field_name, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_vector_cosine ON embeddings.tasks_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_vector_l2 ON embeddings.tasks_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_vector_ip ON embeddings.tasks_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_entity_field ON embeddings.tasks_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_provider ON embeddings.tasks_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_tasks_embeddings_field_provider ON embeddings.tasks_embeddings (field_name, embedding_provider);;

CREATE TABLE IF NOT EXISTS public.tenants (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    tenant_id TEXT NOT NULL,
    email TEXT NOT NULL,
    public_key TEXT NOT NULL,
    device_ids JSONB,
    storage_bucket TEXT,
    metadata JSONB,
    active BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_tenants_device_ids_gin ON tenants USING GIN (device_ids);
CREATE INDEX IF NOT EXISTS idx_tenants_metadata_gin ON tenants USING GIN (metadata);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('tenants', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_tenants_updated_at ON public.tenants;
CREATE TRIGGER update_tenants_updated_at 
    BEFORE UPDATE ON public.tenants
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

CREATE TABLE IF NOT EXISTS public.token_usage (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    model_name TEXT NOT NULL,
    tokens BIGINT,
    tokens_in BIGINT,
    tokens_out BIGINT,
    tokens_other BIGINT,
    session_id TEXT,
    tenant_id TEXT NOT NULL
);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('token_usage', 'id', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_token_usage_updated_at ON public.token_usage;
CREATE TRIGGER update_token_usage_updated_at 
    BEFORE UPDATE ON public.token_usage
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
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
    graph_paths JSONB,
    metadata JSONB,
    email_subscription_active BOOLEAN,
    userid TEXT,
    tenant_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_recent_threads_gin ON users USING GIN (recent_threads);
CREATE INDEX IF NOT EXISTS idx_users_interesting_entity_keys_gin ON users USING GIN (interesting_entity_keys);
CREATE INDEX IF NOT EXISTS idx_users_roles_gin ON users USING GIN (roles);
CREATE INDEX IF NOT EXISTS idx_users_graph_paths_gin ON users USING GIN (graph_paths);
CREATE INDEX IF NOT EXISTS idx_users_metadata_gin ON users USING GIN (metadata);

-- Ensure business key is unique per tenant
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_email_tenant_id_key;
ALTER TABLE public.users ADD CONSTRAINT users_email_tenant_id_key UNIQUE (email, tenant_id);

-- Register entity for graph integration
SELECT * FROM p8.register_entities('users', 'email', false, 'p8graph');

-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_users_updated_at ON public.users;
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON public.users
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();;

-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS embeddings.users_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),
    tenant_id TEXT NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.users(id) ON DELETE CASCADE,
    UNIQUE(entity_id, field_name, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_users_embeddings_vector_cosine ON embeddings.users_embeddings USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_users_embeddings_vector_l2 ON embeddings.users_embeddings USING ivfflat (embedding_vector vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_users_embeddings_vector_ip ON embeddings.users_embeddings USING ivfflat (embedding_vector vector_ip_ops);
CREATE INDEX IF NOT EXISTS idx_users_embeddings_entity_field ON embeddings.users_embeddings (entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_users_embeddings_provider ON embeddings.users_embeddings (embedding_provider);
CREATE INDEX IF NOT EXISTS idx_users_embeddings_field_provider ON embeddings.users_embeddings (field_name, embedding_provider);;
