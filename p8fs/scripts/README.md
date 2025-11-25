# P8FS Utility Scripts

## check_tenant_activity.sh

Helper script for checking tenant file activity in SeaweedFS filer and reprocessing files.

### Prerequisites

1. Port-forward SeaweedFS S3 service:
   ```bash
   kubectl port-forward -n seaweed svc/seaweedfs-s3 8333:8333
   ```

2. Port-forward NATS (for reprocessing):
   ```bash
   kubectl port-forward -n p8fs svc/nats 4222:4222
   ```

3. AWS CLI installed and configured

### Usage

```bash
./scripts/check_tenant_activity.sh [COMMAND] [OPTIONS]
```

### Commands

#### List all tenant buckets
```bash
./scripts/check_tenant_activity.sh list-tenants
```

#### Count files per tenant (top 10)
```bash
./scripts/check_tenant_activity.sh count-files
```

Output:
```
Tenant                                    File Count
tenant-test                              49
test-corp                                9
tenant-7737c2b1eb7ca1b1c0a0da8a29a836ca  4
```

#### List files in specific tenant
```bash
./scripts/check_tenant_activity.sh list-tenant-files --tenant-id tenant-7737c2b1eb7ca1b1c0a0da8a29a836ca
```

Output:
```
2025-11-14 14:54:29     111017 uploads/2025/11/14/recording_1763132063261.m4a
2025-11-14 18:01:54      93272 uploads/2025/11/14/recording_1763143310114.m4a
2025-11-14 18:06:42      78448 uploads/2025/11/14/recording_1763143598832.m4a
2025-11-14 19:58:22      84873 uploads/2025/11/14/recording_1763150297967.m4a
```

#### Reprocess all files for tenant
```bash
./scripts/check_tenant_activity.sh reprocess-tenant --tenant-id tenant-7737c2b1eb7ca1b1c0a0da8a29a836ca
```

This will:
1. List all files in the tenant bucket
2. For each file, call `p8fs retry` to requeue it for processing
3. Workers will process each file through the full pipeline

### How It Works

The script:
1. Automatically fetches S3 credentials from Kubernetes secret
2. Uses AWS CLI to interact with SeaweedFS S3 API
3. Filters for tenant buckets (prefix: `tenant-*` or `test-corp`)
4. Provides convenient commands for common tenant operations

### Integration with retry command

The script uses the `p8fs retry` command under the hood. You can also use the retry command directly:

```bash
# Single file retry
uv run python -m p8fs.cli retry \
  --uri uploads/2025/11/14/recording_1763132063261.m4a \
  --tenant-id tenant-7737c2b1eb7ca1b1c0a0da8a29a836ca \
  --size 111017

# See full retry help with filer instructions
uv run python -m p8fs.cli retry --help
```

### Troubleshooting

**Port-forward not working:**
- Ensure port 8333 is not already in use
- Check that SeaweedFS pods are running: `kubectl get pods -n seaweed`

**No credentials found:**
- Verify the secret exists: `kubectl get secret -n seaweed seaweedfs-s3-config`
- Check you have read access to the namespace

**Files not processing:**
- Check NATS is accessible: `kubectl port-forward -n p8fs svc/nats 4222:4222`
- Monitor worker logs: `kubectl logs -n p8fs deployment/storage-worker-small -f`
- Verify NATS queue status: `kubectl exec -n p8fs deployment/nats-box -- nats consumer info P8FS_STORAGE_EVENTS_SMALL small-workers`
