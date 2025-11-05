-- Add example language model configs, agents and resources

-- Language Model API Configurations
-- Using p8.json_to_uuid for deterministic IDs that match Python make_uuid function

-- OpenAI Models
INSERT INTO language_model_apis (id, name, scheme, completions_uri, token_env_key, tenant_id, created_at, updated_at)
VALUES 
    (p8.json_to_uuid('"gpt-5"'::jsonb), 'gpt-5', 'openai', 'https://api.openai.com/v1/chat/completions', 'OPENAI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"gpt-5-mini"'::jsonb), 'gpt-5-mini', 'openai', 'https://api.openai.com/v1/chat/completions', 'OPENAI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"gpt-5-2025-08-07"'::jsonb), 'gpt-5-2025-08-07', 'openai', 'https://api.openai.com/v1/chat/completions', 'OPENAI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"gpt-4o-2024-08-06"'::jsonb), 'gpt-4o-2024-08-06', 'openai', 'https://api.openai.com/v1/chat/completions', 'OPENAI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"gpt-4o-mini"'::jsonb), 'gpt-4o-mini', 'openai', 'https://api.openai.com/v1/chat/completions', 'OPENAI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"gpt-4.1"'::jsonb), 'gpt-4.1', 'openai', 'https://api.openai.com/v1/chat/completions', 'OPENAI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"gpt-4.1-mini"'::jsonb), 'gpt-4.1-mini', 'openai', 'https://api.openai.com/v1/chat/completions', 'OPENAI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"gpt-4.1-nano"'::jsonb), 'gpt-4.1-nano', 'openai', 'https://api.openai.com/v1/chat/completions', 'OPENAI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"gpt-4.1-2025-04-14"'::jsonb), 'gpt-4.1-2025-04-14', 'openai', 'https://api.openai.com/v1/chat/completions', 'OPENAI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW())
ON CONFLICT (name, tenant_id) DO UPDATE SET
    scheme = EXCLUDED.scheme,
    completions_uri = EXCLUDED.completions_uri,
    token_env_key = EXCLUDED.token_env_key,
    updated_at = NOW();

-- Cerebras Models (OpenAI-compatible)
INSERT INTO language_model_apis (id, name, model, scheme, completions_uri, token_env_key, tenant_id, created_at, updated_at)
VALUES 
    (p8.json_to_uuid('"cerebras-llama3.1-8b"'::jsonb), 'cerebras-llama3.1-8b', 'llama3.1-8b', 'openai', 'https://api.cerebras.ai/v1/chat/completions', 'CEREBRAS_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW())
ON CONFLICT (name, tenant_id) DO UPDATE SET
    model = EXCLUDED.model,
    scheme = EXCLUDED.scheme,
    completions_uri = EXCLUDED.completions_uri,
    token_env_key = EXCLUDED.token_env_key,
    updated_at = NOW();

-- Groq Models (OpenAI-compatible)
INSERT INTO language_model_apis (id, name, model, scheme, completions_uri, token_env_key, tenant_id, created_at, updated_at)
VALUES 
    (p8.json_to_uuid('"groq-llama-3.3-70b-versatile"'::jsonb), 'groq-llama-3.3-70b-versatile', 'llama-3.3-70b-versatile', 'openai', 'https://api.groq.com/openai/v1/chat/completions', 'GROQ_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW())
ON CONFLICT (name, tenant_id) DO UPDATE SET
    model = EXCLUDED.model,
    scheme = EXCLUDED.scheme,
    completions_uri = EXCLUDED.completions_uri,
    token_env_key = EXCLUDED.token_env_key,
    updated_at = NOW();

-- Anthropic Models
INSERT INTO language_model_apis (id, name, scheme, completions_uri, token_env_key, tenant_id, created_at, updated_at)
VALUES 
    (p8.json_to_uuid('"claude-3-5-sonnet-20241022"'::jsonb), 'claude-3-5-sonnet-20241022', 'anthropic', 'https://api.anthropic.com/v1/messages', 'ANTHROPIC_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"claude-3-7-sonnet-20250219"'::jsonb), 'claude-3-7-sonnet-20250219', 'anthropic', 'https://api.anthropic.com/v1/messages', 'ANTHROPIC_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW())
ON CONFLICT (name, tenant_id) DO UPDATE SET
    scheme = EXCLUDED.scheme,
    completions_uri = EXCLUDED.completions_uri,
    token_env_key = EXCLUDED.token_env_key,
    updated_at = NOW();

-- Google Models
INSERT INTO language_model_apis (id, name, scheme, completions_uri, token_env_key, tenant_id, created_at, updated_at)
VALUES 
    (p8.json_to_uuid('"gemini-1.5-flash"'::jsonb), 'gemini-1.5-flash', 'google', 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent', 'GEMINI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"gemini-2.0-flash"'::jsonb), 'gemini-2.0-flash', 'google', 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent', 'GEMINI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"gemini-2.0-flash-thinking-exp-01-21"'::jsonb), 'gemini-2.0-flash-thinking-exp-01-21', 'google', 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-thinking-exp-01-21:generateContent', 'GEMINI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW()),
    (p8.json_to_uuid('"gemini-2.0-pro-exp-02-05"'::jsonb), 'gemini-2.0-pro-exp-02-05', 'google', 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-pro-exp-02-05:generateContent', 'GEMINI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW())
ON CONFLICT (name, tenant_id) DO UPDATE SET
    scheme = EXCLUDED.scheme,
    completions_uri = EXCLUDED.completions_uri,
    token_env_key = EXCLUDED.token_env_key,
    updated_at = NOW();

-- DeepSeek Models (OpenAI-compatible)
INSERT INTO language_model_apis (id, name, scheme, completions_uri, token_env_key, tenant_id, created_at, updated_at)
VALUES 
    (p8.json_to_uuid('"deepseek-chat"'::jsonb), 'deepseek-chat', 'openai', 'https://api.deepseek.com/chat/completions', 'DEEPSEEK_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW())
ON CONFLICT (name, tenant_id) DO UPDATE SET
    scheme = EXCLUDED.scheme,
    completions_uri = EXCLUDED.completions_uri,
    token_env_key = EXCLUDED.token_env_key,
    updated_at = NOW();

-- xAI Models (OpenAI-compatible)
INSERT INTO language_model_apis (id, name, scheme, completions_uri, token_env_key, tenant_id, created_at, updated_at)
VALUES 
    (p8.json_to_uuid('"grok-2-latest"'::jsonb), 'grok-2-latest', 'openai', 'https://api.x.ai/v1/chat/completions', 'XAI_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW())
ON CONFLICT (name, tenant_id) DO UPDATE SET
    scheme = EXCLUDED.scheme,
    completions_uri = EXCLUDED.completions_uri,
    token_env_key = EXCLUDED.token_env_key,
    updated_at = NOW();

-- Inception Models (OpenAI-compatible)
INSERT INTO language_model_apis (id, name, scheme, completions_uri, token_env_key, tenant_id, created_at, updated_at)
VALUES 
    (p8.json_to_uuid('"mercury-coder-small"'::jsonb), 'mercury-coder-small', 'openai', 'https://api.inceptionlabs.ai/v1/chat/completions', 'INCEPTION_API_KEY', '00000000-0000-0000-0000-000000000000', NOW(), NOW())
ON CONFLICT (name, tenant_id) DO UPDATE SET
    scheme = EXCLUDED.scheme,
    completions_uri = EXCLUDED.completions_uri,
    token_env_key = EXCLUDED.token_env_key,
    updated_at = NOW();

-- test calling index entities here and then we can use this as a get_entities integration test

-- Register the language_model_apis table for graph indexing
SELECT * FROM p8.register_entities('public.language_model_apis', 'name', false, 'p8graph');

-- Index existing entities in the graph
SELECT p8.insert_entity_nodes('language_model_apis');

-- Test get_entities to verify it works
-- This should retrieve the language model API we just inserted
DO $$
DECLARE
    result JSONB;
    entity_count INTEGER;
BEGIN
    -- Test retrieving by key
    result := p8.get_entities(ARRAY['language_model_api:mercury-coder-small']);
    
    -- Check if we got results
    IF result = '{}'::JSONB THEN
        RAISE NOTICE 'ERROR: get_entities returned empty result';
    ELSE
        RAISE NOTICE 'SUCCESS: get_entities returned: %', jsonb_pretty(result);
        
        -- Count entities returned
        entity_count := jsonb_array_length(result->'language_model_apis');
        RAISE NOTICE 'Found % language_model_api entities', entity_count;
        
        -- Verify the specific entity
        IF result->'language_model_apis'->0->>'name' = 'mercury-coder-small' THEN
            RAISE NOTICE 'SUCCESS: Found mercury-coder-small entity';
        ELSE
            RAISE NOTICE 'ERROR: Could not find mercury-coder-small entity';
        END IF;
    END IF;
    
    -- Test with multiple keys (including non-existent)
    result := p8.get_entities(ARRAY['language_model_api:mercury-coder-small', 'language_model_api:non-existent']);
    RAISE NOTICE 'Multi-key test result: %', jsonb_pretty(result);
    
END $$;