# P8FS Workers

## Overview

P8FS workers process background jobs including file storage operations, dream analysis, and moment classification. Workers run as Kubernetes deployments that consume messages from NATS JetStream queues with automatic scaling via KEDA.

## Cluster Testing with Self-Test Mode

Test storage workers against a live Kubernetes cluster by running a self-contained test that uploads to SeaweedFS, publishes to NATS, and processes from the queue - all in one command.

### How It Works

The self-test mode uses a dedicated **TEST queue** (`P8FS_STORAGE_EVENTS_TEST`) that operates independently from production queues:

1. **Isolation**: TEST queue is separate from production queues (small/medium/large)
2. **Self-Contained**: Single command uploads→publishes→processes without external dependencies
3. **S3 Download Path**: File is uploaded to SeaweedFS, then downloaded via S3 API (not processed directly from local file)
4. **Full Integration**: Tests complete flow including SeaweedFS, NATS, content providers, and database storage

### Prerequisites

```bash
# Port-forward cluster services to localhost
kubectl port-forward -n p8fs svc/seaweedfs-s3 8333:8333 &
kubectl port-forward -n p8fs svc/nats 4222:4222 &

# Verify services are accessible
curl http://localhost:8333  # SeaweedFS S3
# Expected: 404 (service is running)
```

### Run Self-Test

The `storage-worker` command with `--send-sample` flag performs a complete end-to-end test:

```bash
# Self-test: upload file, publish event, process from queue
uv run python -m p8fs.cli storage-worker \
  --tier small \
  --send-sample p8fs/tests/sample_data/content/Sample.pdf

# What happens:
# 1. Uploads Sample.pdf to SeaweedFS via port-forward (8333)
# 2. Publishes storage event to NATS cluster queue
# 3. Pulls message from queue and processes it
# 4. Extracts content using PDF provider
# 5. Stores resources in cluster PostgreSQL database
```

**Output:**
```
📤 Step 1: Uploading Sample.pdf to SeaweedFS...
✅ Uploaded to: test/Sample.pdf
   Size: 840,059 bytes

📨 Step 2: Publishing test event to NATS...
✅ Published to: p8fs.storage.events.small

⚙️  Step 3: Processing event from queue...
✅ Received message from queue
INFO: Using PDFContentProvider - will extract text and structure
INFO: Created 8 chunks in 0.9s
INFO: Successfully created 8 content resources
✅ Successfully processed Sample.pdf

📊 Verify in database:
   kubectl exec -n tikv-cluster tidb-cluster-tidb-0 -- \
   mysql -u root public -e "SELECT name, category FROM resources WHERE tenant_id = 'tenant-test' LIMIT 5;"
```

### Verify Processing

Check resources were created in the cluster database:

```bash
# For TiDB cluster
kubectl exec -n tikv-cluster tidb-cluster-tidb-0 -- \
  mysql -u root public -e \
  "SELECT name, category, length(content) as size FROM resources \
   WHERE tenant_id = 'tenant-test' ORDER BY created_at DESC LIMIT 5;"

# For PostgreSQL cluster
kubectl exec -n p8fs percolate -- \
  psql -U postgres -d app -c \
  "SELECT name, category, length(content) as size FROM resources \
   WHERE tenant_id = 'tenant-test' ORDER BY created_at DESC LIMIT 5;"
```

**Expected output:**
```
       name        | category      | size
-------------------+---------------+------
Sample_chunk_0     | content_chunk | 1024
Sample_chunk_1     | content_chunk | 1024
Sample_chunk_2     | content_chunk | 1024
```

### Run Worker Continuously

For development/debugging, run the worker without self-test to process queued events:

```bash
# Connect to cluster and process events continuously
kubectl port-forward -n p8fs svc/nats 4222:4222 &

uv run python -m p8fs.cli storage-worker --tier small

# Worker will:
# 1. Connect to NATS via port-forward
# 2. Subscribe to p8fs.storage.events.small queue
# 3. Process messages as they arrive
# 4. Continue running until Ctrl+C
```

### Test Different Tiers

```bash
# Small tier (< 100MB files)
uv run python -m p8fs.cli storage-worker --tier small \
  --send-sample p8fs/tests/sample_data/content/document.pdf

# Medium tier (100MB-1GB files)
uv run python -m p8fs.cli storage-worker --tier medium \
  --send-sample path/to/large-video.mp4

# Large tier (> 1GB files)
uv run python -m p8fs.cli storage-worker --tier large \
  --send-sample path/to/huge-dataset.zip
```

### Tier Routing

Files are automatically routed to appropriate worker tiers based on size:

| Tier | Size Range | Memory Allocation | Subject |
|------|-----------|-------------------|---------|
| Small | 0-100MB | 1.4GB | `p8fs.storage.events.small` |
| Medium | 100MB-1GB | 4GB | `p8fs.storage.events.medium` |
| Large | 1GB+ | 12GB | `p8fs.storage.events.large` |

### Notes

- Self-test mode requires port-forwarding to access cluster services
- Uses the same NATS queues and consumers as production workers
- Content providers (PDF, audio, etc.) require `p8fs-node` package: `uv sync --extra workers`
- SeaweedFS S3 endpoint defaults to `http://localhost:8333` (configurable via `P8FS_SEAWEEDFS_ENDPOINT`)
- NATS endpoint defaults to `nats://localhost:4222` (configurable via `P8FS_NATS_URL`)

## Worker Types

### Storage Workers

Process file uploads with tiered memory allocation based on file size.

| Tier | Memory | File Size Range | Queue Subject | Consumer Name | Min Replicas |
|------|--------|-----------------|---------------|---------------|--------------|
| **Small** | 1.4GB | 0-100MB | p8fs.storage.events.small | small-workers | 2 |
| **Medium** | 4GB | 100MB-1GB | p8fs.storage.events.medium | medium-workers | 0 |
| **Large** | 12GB | 1GB+ | p8fs.storage.events.large | large-workers | 0 |

### Dreaming Worker

Analyzes user sessions and resources to create structured AI summaries using DreamModel.

**Execution Modes**:
- **Direct**: Synchronous processing with immediate results
- **Batch**: Asynchronous processing via OpenAI Batch API
- **Completion**: Checks and processes completed batch jobs

### Moment Worker

Classifies temporal data into structured moment collections using MomentBuilder.

**Features**:
- Processes transcript data with speaker identification
- Extracts emotions, topics, and present persons
- Creates time-bounded activity segments
- Supports batch processing of multiple transcripts

## Architecture

### Consumer Creation Strategy

The tiered storage router creates all NATS consumers during setup:

1. **Router is the single authority** for consumer creation
2. **Workers connect to existing consumers** (never create)
3. **Fail-hard design** - any setup failure causes immediate termination
4. **Explicit cleanup** - router deletes old/broken consumers before creating fresh ones

### Message Flow

```
File Upload → Router → Size-Specific Stream → Consumer → Worker Tier → Process
```

1. Files uploaded to API trigger storage events
2. Router reads from main stream, inspects file size
3. Router publishes to appropriate tier stream (small/medium/large)
4. Workers pull from tier-specific consumers
5. Workers process files with allocated memory resources

## Configuration

### Environment Variables

```bash
# Storage Provider
export P8FS_STORAGE_PROVIDER=tidb  # or postgresql
export P8FS_TIDB_HOST=localhost
export P8FS_TIDB_PORT=4000
export P8FS_TIDB_DATABASE=public
export P8FS_TIDB_USER=root
export P8FS_TIDB_PASSWORD=

# NATS
export P8FS_NATS_URL=nats://nats.p8fs.svc.cluster.local:4222

# SeaweedFS
export P8FS_SEAWEEDFS_FILER=seaweedfs-filer.p8fs.svc.cluster.local:8888

# LLM API Keys
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
```

### PostgreSQL Configuration (Development)

```bash
export P8FS_STORAGE_PROVIDER=postgresql
export P8FS_PG_HOST=localhost
export P8FS_PG_PORT=5438
export P8FS_PG_DATABASE=app
export P8FS_PG_USER=postgres
export P8FS_PG_PASSWORD=postgres
```

## CLI Commands

### Router

Creates NATS streams and consumers for tiered message routing.

```bash
# Local development
uv run python -m p8fs.cli router --worker-id=local-router

# With TiDB
P8FS_STORAGE_PROVIDER=tidb \
P8FS_TIDB_HOST=localhost \
uv run python -m p8fs.cli router
```

**What the router creates**:
- Streams: `P8FS_STORAGE_EVENTS`, `P8FS_STORAGE_EVENTS_SMALL/MEDIUM/LARGE`
- Consumers: `small-workers`, `medium-workers`, `large-workers`

### Dreaming Worker

```bash
# Direct mode (synchronous)
uv run python -m p8fs.workers.dreaming process \
  --mode direct \
  --tenant-id test-tenant

# Batch mode (asynchronous)
export OPENAI_API_KEY=sk-...
uv run python -m p8fs.workers.dreaming process \
  --mode batch \
  --tenant-id test-tenant

# Check completion
uv run python -m p8fs.workers.dreaming process --completion
```

### Moment Worker (Eval)

Process transcripts to create moment collections.

```bash
# Single transcript
export ANTHROPIC_API_KEY=sk-ant-...
uv run python -m p8fs.cli eval \
  --agent-model agentlets.moments.MomentBuilder \
  --file tests/sample_data/moment_samples/tenant_1/transcript_2025-01-13T09-00-00Z_input.json \
  --model claude-sonnet-4-5 \
  --format yaml

# Output: Collection of moments with timestamps, emotions, topics, present persons
```

**Example Output**:
```yaml
moments:
- name: Morning Standup with Team
  moment_type: meeting
  emotion_tags: [focused, collaborative, energized]
  topic_tags: [standup-meeting, authentication-middleware, rate-limiting]
  resource_timestamp: '2025-01-13T09:00:00Z'
  resource_ends_timestamp: '2025-01-13T09:01:12Z'
  present_persons:
  - fingerprint_id: fp_alex_t1
    user_label: Alex
  - fingerprint_id: fp_jordan_t1
    user_label: Jordan
```

## Data Structures

### DreamModel Output

```python
{
    "user_id": "tenant-id",
    "analysis_id": "uuid",
    "executive_summary": "Analysis summary",
    "key_themes": ["theme1", "theme2"],
    "goals": [{
        "goal": "Learn programming",
        "category": "career",
        "priority": "high"
    }],
    "dreams": [{
        "dream": "Travel to Japan",
        "category": "lifestyle",
        "timeline": "short-term"
    }],
    "fears": [],
    "pending_tasks": [],
    "appointments": [],
    "entity_relationships": [],
    "recommendations": [],
    "metrics": {
        "total_documents_analyzed": 3,
        "confidence_score": 0.8,
        "data_completeness": 0.9
    }
}
```

### MomentBuilder Output

```python
{
    "moments": [{
        "name": "Morning Standup",
        "content": "Team meeting discussing progress...",
        "summary": "Quick standup covering tasks",
        "category": "work",
        "uri": "s3://bucket/recording.wav",
        "resource_timestamp": "2025-01-13T09:00:00Z",
        "resource_ends_timestamp": "2025-01-13T09:10:12Z",
        "moment_type": "meeting",
        "emotion_tags": ["focused", "collaborative"],
        "topic_tags": ["standup-meeting", "authentication"],
        "present_persons": [{
            "fingerprint_id": "fp_alex_t1",
            "user_id": "user_alex_001",
            "user_label": "Alex"
        }],
        "location": "video_conference",
        "background_sounds": "keyboard typing",
        "metadata": {
            "transcript_id": "t1_20250113_090000",
            "duration_seconds": 72
        }
    }],
    "analysis_summary": "Single standup meeting with team coordination",
    "total_moments": 1
}
```

## Database Tables

### Critical Tables

**errors** - Error logging:
```sql
CREATE TABLE errors (
    id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    date DATETIME NOT NULL,
    process VARCHAR(255),
    message TEXT NOT NULL,
    stack_trace TEXT,
    level VARCHAR(50) DEFAULT 'ERROR',
    metadata JSON,
    INDEX idx_tenant (tenant_id)
);
```

**jobs** - Async task tracking:
```sql
CREATE TABLE jobs (
    id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING',
    payload JSON,
    result JSON,
    error TEXT,
    queued_at DATETIME NOT NULL,
    INDEX idx_tenant (tenant_id),
    INDEX idx_status (status)
);
```

**files** - File metadata:
```sql
CREATE TABLE files (
    id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    uri TEXT NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR(255),
    content_hash VARCHAR(255),
    upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tenant (tenant_id)
);
```

## Kubernetes Deployment

### Docker Image

```bash
# Build and push heavy image (includes ML/media dependencies)
cd /Users/sirsh/code/p8fs-modules
docker buildx build --platform linux/amd64,linux/arm64 \
  -t percolationlabs/p8fs-eco:latest \
  --push .
```

### Deploy Router

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tiered-storage-router
  namespace: p8fs
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: router
        image: percolationlabs/p8fs-eco:latest
        command: ["python", "-m", "p8fs.cli", "router"]
        env:
        - name: P8FS_NATS_URL
          value: "nats://nats.p8fs.svc.cluster.local:4222"
        - name: P8FS_STORAGE_PROVIDER
          value: "tidb"
        - name: P8FS_TIDB_HOST
          value: "tidb-cluster-tidb.tikv-cluster.svc.cluster.local"
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
```

```bash
kubectl apply -f k8s/workers/tiered-storage-router.yaml
kubectl wait --for=condition=Ready pod -l app=tiered-storage-router -n p8fs
```

### Deploy Storage Workers

**Small Workers** (always-on):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: storage-worker-small
  namespace: p8fs
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: worker
        image: percolationlabs/p8fs-eco:latest
        command: ["python", "-m", "p8fs.workers.queues.storage_worker"]
        env:
        - name: NATS_SUBJECT
          value: "p8fs.storage.events.small"
        - name: NATS_DURABLE_NAME
          value: "small-workers"
        - name: WORKER_TIER
          value: "small"
        resources:
          limits:
            memory: "1400Mi"
```

**Medium/Large Workers** (scale-to-zero):
```yaml
spec:
  replicas: 0  # KEDA scales from zero
  template:
    spec:
      containers:
      - name: worker
        env:
        - name: NATS_SUBJECT
          value: "p8fs.storage.events.medium"  # or .large
        - name: WORKER_TIER
          value: "medium"  # or large
        resources:
          limits:
            memory: "4Gi"  # or 12Gi for large
```

```bash
kubectl apply -f k8s/workers/storage-worker-small.yaml
kubectl apply -f k8s/workers/storage-worker-medium.yaml
kubectl apply -f k8s/workers/storage-worker-large.yaml
```

### KEDA Autoscaling

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: storage-worker-small-scaler
  namespace: p8fs
spec:
  scaleTargetRef:
    name: storage-worker-small
  minReplicaCount: 2
  maxReplicaCount: 20
  triggers:
  - type: nats-jetstream
    metadata:
      natsServerMonitoringEndpoint: "nats.p8fs.svc.cluster.local:8222"
      stream: "P8FS_STORAGE_EVENTS_SMALL"
      consumer: "small-workers"
      lagThreshold: "5"
```

```bash
kubectl apply -f k8s/workers/keda-scalers.yaml
kubectl get scaledobjects -n p8fs
```

## Testing

### Integration Tests

```bash
# Dreaming worker tests
P8FS_STORAGE_PROVIDER=tidb \
pytest tests/integration/test_dreaming_integration.py -v

# Moment builder tests
export ANTHROPIC_API_KEY=sk-ant-...
pytest tests/integration/test_moment_builder.py -v
```

### Manual Testing

**Test Storage Worker**:
```bash
# Publish test event
kubectl exec -n p8fs nats-0 -- nats pub p8fs.storage.events '{
  "event_type": "create",
  "path": "/test/file.txt",
  "size": 1024,
  "mime_type": "text/plain",
  "entry": {"Size": 1024, "Mime": "text/plain"}
}'

# Verify routing
kubectl logs -n p8fs -l app=tiered-storage-router --tail=5

# Verify processing
kubectl logs -n p8fs -l tier=small --tail=10
```

**Test Dreaming Worker**:
```python
import asyncio
from p8fs.workers.dreaming import DreamingWorker

async def test():
    worker = DreamingWorker()
    data = await worker.collect_user_data("test-tenant")
    print(f"Sessions: {len(data.sessions)}")
    print(f"Resources: {len(data.resources)}")

    job = await worker.process_direct("test-tenant")
    print(f"Status: {job.status}")
    print(f"Goals: {len(job.result['goals'])}")

asyncio.run(test())
```

**Test Moment Worker**:
```bash
# Process transcript
export ANTHROPIC_API_KEY=sk-ant-...
uv run python -m p8fs.cli eval \
  --agent-model agentlets.moments.MomentBuilder \
  --file tests/sample_data/moment_samples/tenant_1/transcript_2025-01-13T09-00-00Z_input.json \
  --model claude-sonnet-4-5 \
  --format yaml > /tmp/moments.yaml

# Verify output
cat /tmp/moments.yaml | grep "moment_type:"
cat /tmp/moments.yaml | grep "emotion_tags:"
```

## Monitoring

### Check Worker Status

```bash
# Pod status
kubectl get pods -n p8fs -l component=worker

# Logs
kubectl logs -n p8fs -l component=worker -f --all-containers

# Resource usage
kubectl top pods -n p8fs -l component=worker
```

### Monitor NATS Queues

```bash
# Stream info
kubectl exec -n p8fs nats-0 -- \
  nats stream info P8FS_STORAGE_EVENTS_SMALL

# Consumer lag
kubectl exec -n p8fs nats-0 -- \
  nats consumer info P8FS_STORAGE_EVENTS_SMALL small-workers
```

### Monitor Database

```sql
-- Recent dream jobs
SELECT id, tenant_id, status, created_at
FROM jobs
WHERE job_type = 'dream_analysis'
ORDER BY created_at DESC
LIMIT 10;

-- Error counts
SELECT COUNT(*) as count, level, process
FROM errors
GROUP BY level, process
ORDER BY count DESC;

-- Worker activity
SELECT tenant_id, COUNT(*) as file_count
FROM files
WHERE upload_timestamp > NOW() - INTERVAL 1 HOUR
GROUP BY tenant_id;
```

## Troubleshooting

### Workers fail with "Failed to connect to consumer"

**Check consumers exist**:
```bash
kubectl exec -n p8fs nats-0 -- \
  nats consumer ls P8FS_STORAGE_EVENTS_SMALL
```

**Verify router created consumers**:
```bash
kubectl logs -n p8fs -l app=tiered-storage-router | \
  grep "Created/verified consumer"
```

### Error table doesn't exist

**Check table**:
```bash
kubectl exec -n tikv-cluster tidb-cluster-tidb-0 -- \
  mysql -u root -e "USE public; SHOW TABLES LIKE 'errors';"
```

**Create tables**:
```bash
uv run python -m p8fs.models.p8 --provider tidb --plan > /tmp/tidb_models.sql
kubectl exec -n tikv-cluster tidb-cluster-tidb-0 -- \
  mysql -u root public < /tmp/tidb_models.sql
```

### KEDA not scaling workers

**Check KEDA operator**:
```bash
kubectl logs -n keda -l app=keda-operator --tail=50
```

**Check ScaledObject**:
```bash
kubectl describe scaledobject storage-worker-medium-scaler -n p8fs
```

**Verify NATS endpoint**:
```bash
kubectl exec -n p8fs storage-worker-small-xxx -- \
  curl http://nats.p8fs.svc.cluster.local:8222/varz
```

## Performance

### Dreaming Worker

- **Direct Mode**: Real-time analysis, limited by API rate limits
- **Batch Mode**: Bulk processing, cost-effective for large datasets
- **Data Limits**: Default 100 sessions, 1000 resources per analysis

### Moment Worker

- **Token-aware chunking**: Optimizes for model context windows
- **List chunking**: Preserves record boundaries in transcript data
- **Batch processing**: Handles multiple transcripts efficiently
- **Average**: 1-3 moments per 10-minute transcript

### Storage Workers

- **Small tier**: Handles 80% of files, always-on baseline
- **Medium/Large**: Scale-to-zero, activate on demand
- **Tiered memory**: Prevents OOM with appropriate resource allocation

## Quick Reference - Log Commands

```bash
# Check SeaweedFS Filer logs
kubectl logs -n p8fs statefulset/seaweedfs-filer --tail=50 -f

# Check gRPC Event Subscriber logs
kubectl logs -n p8fs deployment/seaweedfs-grpc-subscriber --tail=50 -f

# Check Tiered Router logs (when deployed)
kubectl logs -n p8fs deployment/tiered-storage-router --tail=50 -f

# Check Small Worker logs
kubectl logs -n p8fs deployment/storage-worker-small --tail=50 -f

# Check Medium Worker logs
kubectl logs -n p8fs deployment/storage-worker-medium --tail=50 -f

# Check Large Worker logs
kubectl logs -n p8fs deployment/storage-worker-large --tail=50 -f

# Check all storage workers at once
kubectl logs -n p8fs -l app=storage-worker --tail=20 -f --all-containers

# Check Dreaming Worker logs
kubectl logs -n p8fs deployment/p8fs-dreaming-worker --tail=50 -f

# Check User Insight Worker logs
kubectl logs -n p8fs deployment/user-insight-worker --tail=50 -f

# Check NATS stream status
kubectl exec -n p8fs deployment/nats-box -- \
  nats stream info P8FS_STORAGE_EVENTS

# Check small worker consumer status
kubectl exec -n p8fs deployment/nats-box -- \
  nats consumer info P8FS_STORAGE_EVENTS_SMALL small-workers

# List all P8FS worker deployments
kubectl get deployments -n p8fs -l component=worker

# Watch worker pod status
kubectl get pods -n p8fs -l component=worker -w

# Check worker resource usage
kubectl top pods -n p8fs -l component=worker
```
