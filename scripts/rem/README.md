# REM Testing Scripts

Comprehensive testing suite for REM (Resource-Entity-Moment) functionality with TiDB provider.

## Overview

These scripts test the complete REM system including:

- **KV Operations**: Key-value storage for entity lookups
- **Resource Management**: Creating resources with related entities
- **Moment Generation**: Temporal narratives from resources
- **LOOKUP Queries**: Entity-based retrieval using KV storage
- **SEARCH Queries**: Semantic search using embeddings
- **TRAVERSE Queries**: Graph navigation using InlineEdge objects
- **Dreaming Workers**: Moments and affinity generation
- **Data Quality**: Validation metrics

## Quick Start

### Run Inside Kubernetes Pod

The easiest way to run tests is using the helper script:

```bash
# Run all tests in the API pod
./scripts/rem/run_in_pod.sh

# Run specific test category
CATEGORY=kv ./scripts/rem/run_in_pod.sh
CATEGORY=resources ./scripts/rem/run_in_pod.sh
CATEGORY=dreaming ./scripts/rem/run_in_pod.sh

# Use specific pod
POD_NAME=p8fs-api-64c9fd96b5-lrw9c ./scripts/rem/run_in_pod.sh

# Use different namespace
NAMESPACE=default ./scripts/rem/run_in_pod.sh
```

### Run Directly in Pod

```bash
# Get pod name
POD_NAME=$(kubectl get pods -n p8fs -l app=p8fs-api -o jsonpath='{.items[0].metadata.name}')

# Run all tests
kubectl exec -n p8fs $POD_NAME -- \
  python scripts/rem/test_tidb_rem_comprehensive.py

# Run specific category
kubectl exec -n p8fs $POD_NAME -- \
  python scripts/rem/test_tidb_rem_comprehensive.py --category kv
```

### Run Locally (Development)

```bash
# Ensure TiDB provider is configured
export P8FS_STORAGE_PROVIDER=tidb
export P8FS_TIDB_HOST=fresh-cluster-tidb.tikv-cluster.svc.cluster.local
export P8FS_TIDB_PORT=4000

# Run tests
cd /path/to/p8fs-modules
python scripts/rem/test_tidb_rem_comprehensive.py
```

## Test Categories

### `kv` - KV Storage Operations

Tests basic key-value storage functionality:

- Write and read simple values
- Array-based entity mapping (REM pattern)
- Scan by prefix
- Delete operations

### `resources` - Resource Creation

Tests creating resources with related entities:

- Resource creation with entities
- KV population for entity lookups
- Resource verification
- Entity extraction

### `moments` - Moment Creation

Tests creating temporal moments:

- Moment creation with temporal boundaries
- Present persons and speakers
- Emotion and topic tags
- Moment verification

### `queries` - REM Query Testing

Tests all REM query types:

- **LOOKUP**: Entity-based retrieval using KV
- **SEARCH**: Semantic search using embeddings
- **TRAVERSE**: Graph navigation using InlineEdge

### `dreaming` - Dreaming Worker Operations

Tests dreaming workflows:

- **Moment Generation**: Extract temporal narratives
- **Affinity Building**: Create knowledge graph edges
- Validation of dreaming output

### `all` - Complete Test Suite

Runs all test categories plus data quality validation.

## Test Data

The script creates test data based on **Sample 01** from the REM documentation:

- **Tenant**: `test-tenant`
- **People**: sarah-chen, mike-johnson, emily-santos
- **Project**: project-alpha
- **Technologies**: tidb, postgresql, redis
- **Concepts**: database-migration, api-performance

## Expected Results

### Stage 1: Resources Seeded (40% Answerable)

After resource creation:

- ✓ LOOKUP queries work (entity-based)
- ✓ KV storage populated
- ✗ No moments yet
- ✗ No graph edges yet

### Stage 2: Moments Generated (70% Answerable)

After moment dreaming:

- ✓ LOOKUP queries work
- ✓ Temporal queries work (moments table)
- ✗ No graph edges yet

### Stage 3: Affinity Built (100% Answerable)

After affinity dreaming:

- ✓ LOOKUP queries work
- ✓ SEARCH queries work (semantic)
- ✓ TRAVERSE queries work (graph edges)

## Troubleshooting

### No Pod Found

```bash
# List available pods
kubectl get pods -n p8fs

# Use specific pod
POD_NAME=p8fs-api-xxx ./scripts/rem/run_in_pod.sh
```

### TiDB Connection Issues

```bash
# Check TiDB pods
kubectl get pods -n tikv-cluster

# Verify TiDB service
kubectl get svc -n tikv-cluster fresh-cluster-tidb

# Test connection from pod
kubectl exec -n p8fs $POD_NAME -- \
  python -c "from p8fs.providers import get_provider; p = get_provider(); p.connect_sync(); print('Connected!')"
```

### Missing Dependencies

The script assumes the pod has:

- p8fs package installed
- p8fs-cluster package installed
- Access to TiDB cluster
- OpenAI API key (for embeddings and LLM)

### Embedding Generation Failures

If semantic search tests fail:

```bash
# Check embedding provider config
kubectl exec -n p8fs $POD_NAME -- \
  python -c "from p8fs_cluster.config.settings import config; print(config.embedding_provider)"

# Verify OpenAI API key
kubectl exec -n p8fs $POD_NAME -- \
  python -c "from p8fs_cluster.config.settings import config; print('Key set:', bool(config.openai_api_key))"
```

## Exit Codes

- `0`: All tests passed
- `1`: One or more tests failed

## Integration with CI/CD

Add to your CI pipeline:

```yaml
test-rem:
  stage: test
  script:
    - kubectl config use-context $K8S_CONTEXT
    - ./scripts/rem/run_in_pod.sh
  only:
    - main
    - develop
```

## Related Documentation

- [REM Design](/p8fs/docs/REM/design.md)
- [REM Testing Philosophy](/p8fs/docs/REM/testing.md)
- [Sample 01 Example](/p8fs/docs/REM/examples/sample-01.md)
- [Dreaming Worker](/p8fs/src/p8fs/workers/dreaming.py)

## Support

For issues or questions:

1. Check the [REM documentation](/p8fs/docs/REM/)
2. Review test output for specific error messages
3. Verify TiDB cluster connectivity
4. Check pod logs: `kubectl logs -n p8fs $POD_NAME`
