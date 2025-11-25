# Experimental: Image Search with CLIP Embeddings

## Overview

P8FS now includes experimental support for visual semantic search using CLIP embeddings. This feature allows storing and searching images based on their visual and textual content.

## Features

- **Image Model**: Store images with metadata (caption, source, dimensions, tags)
- **CLIP Embeddings**: 512-dimensional multimodal embeddings for semantic search
- **Unsplash Integration**: Sample data utility to fetch 100+ themed images
- **PostgreSQL/TiDB Support**: Vector search with pgvector (PostgreSQL) or JSON storage (TiDB)

## Database Schema

### Images Table
- `id`: UUID primary key
- `uri`: Image location (HTTP URL or S3 path)
- `caption`: Text description for CLIP encoding
- `source`: Image source (e.g., 'unsplash', 'user_upload')
- `width`, `height`: Image dimensions
- `tags`: JSON array of semantic tags
- `metadata`: Additional JSON metadata

### CLIP Embeddings Table
- 512-dimensional vectors stored in `embeddings.images_embeddings`
- Foreign key reference to images table
- Supports cosine similarity and L2 distance search

## Usage

### CLI Command

```bash
# Ingest 100 sample images
uv run python -m p8fs.cli ingest-images --count 100

# Specify tenant
uv run python -m p8fs.cli ingest-images --tenant-id my-tenant --count 50

# With Unsplash API key (optional, better quality)
uv run python -m p8fs.cli ingest-images --unsplash-key YOUR_API_KEY
```

### Programmatic Usage

```python
from p8fs.utils.sample_images import ingest_sample_images

result = ingest_sample_images(
    tenant_id="tenant-123",
    count=100,
    unsplash_access_key=None,  # Optional
    generate_embeddings=True
)

print(f"Ingested {result['images_ingested']} images")
print(f"Generated {result['embeddings_generated']} embeddings")
```

### Querying Images

```python
from p8fs.repository import TenantRepository
from p8fs.models.p8 import Image

# Get repository
repo = TenantRepository(Image, tenant_id="tenant-test")

# Search by caption
images = repo.search(query="family goals", limit=10)

# Future: Vector similarity search with CLIP embeddings
# Will be supported when semantic search is extended to images
```

## Implementation Details

### CLIP Provider

Two implementations available:

1. **MockCLIPProvider** (default): Generates random normalized 512-dim vectors for testing
2. **CLIPEmbeddingProvider**: Full CLIP implementation using transformers library

```python
from p8fs.services.llm.clip_provider import get_clip_provider

# Mock provider (lightweight, no dependencies)
provider = get_clip_provider(use_mock=True)
embeddings = provider.encode(["image caption 1", "image caption 2"])

# Real CLIP (requires transformers + torch)
provider = get_clip_provider(use_mock=False)
embeddings = provider.encode(["image caption"])
```

### Dependencies

**API/Light Mode (current)**:
- No additional dependencies
- Uses mock CLIP provider

**Node/Heavy Mode (future)**:
For real CLIP embeddings, p8fs-node will need:
```bash
pip install transformers torch pillow
```

## Sample Data Themes

The sample image ingestion covers life-tracking related themes:
- Life goals and achievement
- Family time and bonding
- Personal growth and self-improvement
- Productivity and planning
- Health, fitness, and wellness
- Work-life balance
- Career development
- Learning and creativity
- Adventure and travel

## Future Enhancements

1. **Real Image Embedding**: Process actual image bytes through CLIP (in p8fs-node)
2. **Semantic Search Integration**: Extend query system to support image search
3. **Multi-modal Search**: Combined text + image queries
4. **Image Upload API**: Direct image upload with automatic embedding generation
5. **Similarity Clustering**: Group similar images automatically

## Architecture Notes

- **p8fs-api**: Light dependencies, uses mock CLIP provider
- **p8fs-node**: Heavy processing dependencies, will host real CLIP model
- Images stored synchronously for reliability
- Embeddings generated after image storage for safety
- Foreign key constraints ensure data consistency

## Testing

Run migrations:
```bash
# PostgreSQL
cat extensions/migrations/postgres/20251018_143000_add_images_table.sql | \
  docker exec -i percolate psql -U postgres -d app

# TiDB
mysql -h localhost -P 4000 -u root test < \
  extensions/migrations/tidb/20251018_143000_add_images_table.sql
```

Verify:
```sql
-- Check images
SELECT COUNT(*) FROM public.images;

-- Check embeddings
SELECT COUNT(*) FROM embeddings.images_embeddings;

-- Check vector dimensions
SELECT vector_dimension, embedding_provider, COUNT(*)
FROM embeddings.images_embeddings
GROUP BY vector_dimension, embedding_provider;
```

## Performance

- Synchronous ingestion: ~100 images in 5-10 seconds
- Mock embedding generation: Instant
- Real CLIP embedding: ~100ms per image (when implemented)
- Vector search: Sub-second for 1000s of images with proper indexes

## Status

**Experimental**: This feature is functional but not production-ready. Use for:
- Testing semantic search concepts
- Prototyping visual memory features
- Development and experimentation

Not recommended for:
- Production deployments without real CLIP
- Large-scale image processing (yet)
- Critical user-facing features
