# P8FS Embeddings Architecture

## Overview

P8FS uses embeddings to enable semantic search across content. Embeddings are vector representations of text that capture semantic meaning, allowing for similarity-based searches. This document explains how embeddings are generated, stored, and used in the P8FS system.

This example shows the `postgres` provided examples which uses `pg_vector` but the same idea can apply to the `TiDB` for that provider (etc.)

## Schema Design

### Embeddings Storage

Embeddings are stored in a separate schema called `embeddings` with dedicated tables for each entity type that supports embeddings. The naming convention is:

```
embeddings.<entity_table_name>_embeddings
```

For example:
- `embeddings.resources_embeddings` for the `resources` table
- `embeddings.agents_embeddings` for the `agents` table
- `embeddings.sessions_embeddings` for the `sessions` table

### Table Structure

Each embeddings table follows this schema:

```sql
CREATE TABLE IF NOT EXISTS embeddings.<entity>_embeddings (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector(1536),  -- pgvector type, dimension varies by provider
    tenant_id TEXT NOT NULL,
    vector_dimension INTEGER DEFAULT 1536,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.<entity>(id) ON DELETE CASCADE,
    UNIQUE(entity_id, field_name, tenant_id)
);
```

### Key Fields

- **id**: Primary key, generated deterministically (see ID Generation below)
- **entity_id**: Foreign key to the main entity table
- **field_name**: The name of the field that was embedded (e.g., "content", "summary")
- **embedding_provider**: The provider used to generate the embedding (e.g., "openai", "sentence-transformers")
- **embedding_vector**: The actual vector data using pgvector type
- **tenant_id**: For multi-tenant isolation
- **vector_dimension**: The dimension of the vector (typically 1536 for OpenAI)

### Indexes

Three indexes are created for efficient vector similarity search:

1. **Cosine similarity**: `CREATE INDEX ON embeddings.<entity>_embeddings USING ivfflat (embedding_vector vector_cosine_ops);`
2. **L2 distance**: `CREATE INDEX ON embeddings.<entity>_embeddings USING ivfflat (embedding_vector vector_l2_ops);`
3. **Inner product**: `CREATE INDEX ON embeddings.<entity>_embeddings USING ivfflat (embedding_vector vector_ip_ops);`

## ID Generation

The embedding ID is generated deterministically using the `make_uuid` function, which creates a UUID v5 hash from:

```python
embedding_id = make_uuid(f"{entity_id}:{field_name}:{embedding_provider}")
```

This ensures:
1. The same entity/field/provider combination always generates the same ID
2. Embeddings can be updated (upserted) deterministically
3. No duplicate embeddings for the same entity/field/provider

Example:
```python
# For a resource with ID "123", field "content", provider "openai"
embedding_id = make_uuid("123:content:openai")
# Always produces the same UUID: "a1b2c3d4-e5f6-5678-9abc-def012345678"
```

## Multi-Field Embedding Support

Entities can have multiple fields embedded. For example, the Resources model embeds both:
- `content` field - The main content text
- `summary` field - A summarized version

This is configured in the model using a property attribute (see examples e.g. Resources)

## Embedding Generation Process

1. **Entity Creation/Update**: When an entity is created or updated
2. **Text Extraction**: The model's `get_embedding_column_values` method extracts text from embedding fields
3. **Embedding Generation**: The embedding service generates vectors for each text
4. **Record Creation**: The model's `build_embedding_records` method creates embedding records
5. **Storage**: Records are inserted with deterministic IDs using UPSERT logic

## Joins and Queries

### Semantic Search Query Pattern

```sql
SELECT 
    m.*,                                              -- Main entity data
    e.field_name,                                     -- Which field matched
    (e.embedding_vector <=> %s::vector) as distance,  -- Vector distance
    (1 - (e.embedding_vector <=> %s::vector)) as score -- Similarity score
FROM resources m
INNER JOIN embeddings.resources_embeddings e ON m.id = e.entity_id
WHERE 
    m.tenant_id = %s 
    AND e.tenant_id = %s
    AND e.field_name = %s  -- Optional field filter
ORDER BY e.embedding_vector <=> %s::vector  -- Sort by similarity
LIMIT %s;
```

### Vector Operators

PostgreSQL pgvector supports three distance operators:
- `<=>` - Cosine distance (most common for text)
- `<->` - L2/Euclidean distance
- `<#>` - Inner product (negative)

## Example: Creating Resources with Embeddings

```python
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models import Resources

repo = TenantRepository(Resources, tenant_id="tenant-123")

# Create resources - embeddings are generated automatically
resources = [
    {
        "name": "Machine Learning Guide",
        "content": "This guide covers ML fundamentals...",
        "summary": "Introduction to machine learning concepts",
        "category": "education"
    }
]

# This method automatically generates embeddings
resource_ids = repo.create_with_embeddings(resources)

# Semantic search
results = repo.semantic_search(
    query="artificial intelligence tutorials",
    limit=10,
    field_name="content"  # Optional: search specific field
)
```

## Embedding Providers

The system supports multiple embedding providers:

1. **OpenAI** (default)
   - Model: `text-embedding-3-small` or `text-embedding-ada-002`
   - Dimensions: 1536
   - High quality, requires API key

2. **Sentence Transformers** (local)
   - Model: `all-MiniLM-L6-v2` or others
   - Dimensions: 384 (varies by model)
   - Runs locally, no API needed

## Migration and Setup

To create embedding tables for an entity:

```sql
-- Create embeddings schema if not exists
CREATE SCHEMA IF NOT EXISTS embeddings;

-- Create embedding table for resources
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

-- Create indexes for vector search
CREATE INDEX idx_resources_embeddings_vector_cosine 
ON embeddings.resources_embeddings 
USING ivfflat (embedding_vector vector_cosine_ops);
```

## Best Practices

1. **Field Selection**: Only embed fields with meaningful text content
2. **Provider Choice**: Use OpenAI for quality, local models for privacy/speed
3. **Dimension Consistency**: Ensure consistent dimensions per provider
4. **Batch Processing**: Generate embeddings in batches for efficiency
5. **Tenant Isolation**: Always include tenant_id in queries
6. **Index Maintenance**: Periodically rebuild IVFFlat indexes for optimal performance