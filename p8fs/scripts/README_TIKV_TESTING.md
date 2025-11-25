# TiKV Save Memory Testing

This directory contains scripts for testing the `save_memory` function with TiDB/TiKV in the K8s cluster.

## Why Cluster Testing?

TiKV uses gRPC clients which behave differently than local PostgreSQL connections. Testing in the actual cluster environment ensures:
- gRPC client compatibility
- Proper TiKV key-value operations
- Network/latency handling
- Cluster-specific configurations

## Test Script

**`test_save_memory_tikv.py`** - Comprehensive integration test that verifies:
1. **Basic KV Mode**: Entity resolver pattern with TiKV
2. **Edge Merging**: Multiple observations to same KV key
3. **Resource Mode**: Direct TiDB table operations
4. **KV TTL**: Proper expiration handling

## Running Tests

### Option 1: Exec into Existing Pod (Recommended)

```bash
# Auto-detect pod and run test
./scripts/run_tikv_test.sh

# Specify pod explicitly
./scripts/run_tikv_test.sh --pod p8fs-worker-abc123

# Use different namespace
./scripts/run_tikv_test.sh --namespace production
```

### Option 2: Run as K8s Job

```bash
./scripts/run_tikv_test.sh --job
```

**Note:** Requires the K8s job YAML to be configured with your cluster details.

### Option 3: Run Locally with Port-Forward

```bash
# Automatically port-forwards to cluster TiDB
./scripts/run_tikv_test.sh --local-tidb
```

**Requirements:**
- TiDB service must be accessible in cluster
- OPENAI_API_KEY set for LLM description generation

## Manual Testing

You can also run the test script directly:

```bash
# In cluster pod
kubectl exec -it <pod-name> -- python3 /app/scripts/test_save_memory_tikv.py

# Locally with port-forward
export P8FS_STORAGE_PROVIDER=tidb
export P8FS_TIDB_HOST=localhost
export P8FS_TIDB_PORT=4000
uv run python scripts/test_save_memory_tikv.py
```

## Test Flow

Each test follows this pattern:

1. **Save**: Call `save_memory()` with observation
2. **Verify KV**: Check TiKV has entity reference
3. **Verify Entity**: Check TiDB has actual resource with graph_paths
4. **Validate**: Ensure data matches expectations

### KV Entity Resolver Pattern

```
save_memory() in KV mode:
  ├─> Create/update resource in TiDB resources table
  │   └─> Includes graph_paths (edges)
  └─> Store reference in TiKV
      └─> {resource_id, entity_type, category}

Retrieval:
  ├─> Get reference from TiKV by key
  └─> Fetch full entity from TiDB by resource_id
```

## Expected Output

```
🚀 Starting TiKV save_memory integration tests
Storage provider: tidb
Tenant ID: tenant-test
TiDB connection: tidb-service:4000

================================================================================
TEST 1: Basic KV Mode with TiKV
================================================================================
Saving observation: User prefers TiDB for production deployments in K8s cluster
Save result: {'success': True, 'mode': 'kv', 'key': 'tenant-test/observation/...', ...}
KV reference retrieved: {'resource_id': '...', 'entity_type': 'resources', ...}
Resource retrieved from TiDB:
  ID: abc-123
  Category: user_preference
  Graph edges: 1
Graph edge: dst=tidb-production, rel_type=prefers, weight=0.7
✅ TEST 1 PASSED: Basic KV mode works with TiKV

...

================================================================================
TEST SUMMARY
================================================================================
✅ PASS: Basic KV Mode
✅ PASS: KV Edge Merging
✅ PASS: Resource Mode
✅ PASS: KV TTL
================================================================================
Results: 4/4 tests passed
🎉 All tests passed!
```

## Troubleshooting

### Test fails with "connection refused"
- Check TiDB service is running: `kubectl get svc -l app=tidb`
- Verify pod can reach TiDB: `kubectl exec <pod> -- nc -zv tidb-service 4000`

### gRPC client errors
- Ensure TiKV provider is properly configured in the pod
- Check TiKV endpoints are accessible from pod network

### LLM description generation fails
- Set OPENAI_API_KEY in pod environment
- Or mock LLM calls in test (set P8FS_MOCK_LLM=true)

### Resource not found after save
- Check tenant_id matches: should be same in save and retrieval
- Verify key format uses forward slashes: `tenant-id/entity/uuid`

## Cleanup

Tests automatically clean up their data. To manually clean:

```bash
kubectl exec <pod> -- python3 -c "
from p8fs.providers import get_provider
provider = get_provider()
provider.execute('DELETE FROM resources WHERE category IN (\"test\", \"user_preference\") AND tenant_id = \"tenant-test\"')
"
```
