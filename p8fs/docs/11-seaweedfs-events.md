# SeaweedFS Event Processing System

## CRITICAL: S3 Content-MD5 Compatibility Warning

**DO NOT use Content-MD5 header with certain SeaweedFS S3 endpoints.**

Some SeaweedFS servers have a bug where the Content-MD5 header causes a 500 Internal Server Error on PUT requests. This is a confirmed issue affecting production deployments.

### Affected Servers
- **s3.eepis.ai**: BROKEN - Returns 500 error with Content-MD5
- Other SeaweedFS instances may also be affected

### Working Servers
- **s3.percolationlabs.ai**: WORKING - Supports Content-MD5
- AWS S3: WORKING - Standard implementation

### Symptoms
```
HTTP 500 Internal Server Error
<Code>InternalError</Code>
<Message>We encountered an internal error, please try again.</Message>
```

The same request works perfectly when Content-MD5 header is removed.

### Solution
The `S3StorageService` class has `use_content_md5=False` by default. **DO NOT change this** unless you have verified your specific SeaweedFS server supports it.

```python
# CORRECT - default configuration
s3 = S3StorageService()  # use_content_md5=False

# WRONG - only enable if tested and confirmed working
s3 = S3StorageService(use_content_md5=True)  # Will fail on s3.eepis.ai!
```

### Data Integrity
File integrity is verified using SHA-256 hashing instead of MD5, providing better security and avoiding the SeaweedFS bug.

### Testing
```bash
# This works (no Content-MD5)
uv run python -m p8fs.cli files upload test.txt --tenant-id tenant-test

# To test if your server supports Content-MD5, use boto3:
python3 -c "
import boto3
from botocore.client import Config
import urllib3
urllib3.disable_warnings()

client = boto3.client('s3',
    endpoint_url='https://s3.eepis.ai',
    aws_access_key_id='your-key',
    aws_secret_access_key='your-secret',
    config=Config(signature_version='s3v4', s3={'addressing_style': 'path'}),
    region_name='us-east-1',
    verify=False
)
# boto3 includes Content-MD5 by default - if this works, your server supports it
client.upload_file('test.txt', 'bucket', 'test.txt')
"
```

See implementation details in:
- `src/p8fs/services/s3_storage.py` (module docstring)
- `src/p8fs/cli.py` (files_command docstring)

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

# Check NATS stream status
kubectl exec -n p8fs deployment/nats-box -- \
  nats stream info P8FS_STORAGE_EVENTS

# Check small worker consumer status
kubectl exec -n p8fs deployment/nats-box -- \
  nats consumer info P8FS_STORAGE_EVENTS_SMALL small-workers

# List all P8FS worker deployments
kubectl get deployments -n p8fs -l component=worker

# Watch pod status
kubectl get pods -n p8fs -l component=worker -w
```

## Overview

The P8FS SeaweedFS event processing system provides real-time file event streaming from SeaweedFS storage into NATS JetStream queues for distributed processing. The system uses gRPC metadata subscription to capture create, update, delete, and rename events with minimal latency.

**Production Status**: ✅ **FULLY OPERATIONAL** in Kubernetes cluster (`p8fs` namespace)

- ✅ SeaweedFS Filer with gRPC port 18888 enabled
- ✅ gRPC subscriber capturing and publishing events to NATS
- ✅ NATS JetStream receiving and persisting events
- ✅ Storage workers (2 small worker replicas) processing files
- ✅ End-to-end file upload → event capture → processing working

**Local Development Note**: The `docker-compose.yaml` provides **limited testing only** for basic S3 operations. It does NOT include gRPC event streaming. For event system development, use the production Kubernetes cluster or set up the full local environment (see Configuration section).

## Architecture

### Current Production Architecture

```
SeaweedFS Filer (gRPC) → gRPC Subscriber → NATS (p8fs.storage.events.small)
    (K8s cluster)            (K8s pod)              (JetStream)
                                                           ↓
                                                    Small Workers (2 pods)
                                                           ↓
                                               Storage Processing
                                            (Files/Resources Creation)
```

**Current Status**: The production cluster currently routes all events directly to the `small` queue without size-based routing. The tiered router implementation exists in the codebase but is not yet deployed.

### Planned Full Architecture

```
SeaweedFS Filer (gRPC) → gRPC Subscriber → NATS (P8FS_STORAGE_EVENTS)
                                                       ↓
                                            Tiered Router (not deployed)
                                                       ↓
                              ┌────────────────────────┴───────────────────────┐
                              ↓                        ↓                       ↓
                    p8fs.storage.events.small  p8fs.storage.events.medium  p8fs.storage.events.large
                              ↓                        ↓                       ↓
                        Small Workers            Medium Workers          Large Workers
                              ↓                        ↓                       ↓
                           Storage Processing (Files/Resources Creation)
```

**Future Enhancement**: Deploy the tiered router to enable size-based queue routing for optimized worker resource allocation.

## Components

### 1. SeaweedFS gRPC Subscriber

**Location**: `src/p8fs/workers/queues/seaweedfs_events/grpc_subscriber.py`

The gRPC subscriber is the primary event capture mechanism. It streams metadata events from SeaweedFS Filer using the gRPC protocol.

**Features**:
- Real-time event streaming via gRPC SubscribeMetadata
- Automatic reconnection on connection loss
- Event type detection (create, update, delete, rename)
- Tenant ID extraction from path structure
- Comprehensive metadata extraction (file size, MIME type, attributes)

**Connection**:
- gRPC endpoint: `filer_host:filer_grpc_port` (default: localhost:18888)
- Path prefix: `/buckets/` (monitors all tenant buckets)

**Event Format**:
```json
{
  "type": "create|update|delete|rename",
  "path": "/buckets/tenant-123/path/to/file.pdf",
  "directory": "/buckets/tenant-123/path/to",
  "timestamp": "2024-01-01T12:00:00.000000",
  "timestamp_ns": 1234567890123456789,
  "source": "seaweedfs-grpc",
  "tenant_id": "tenant-123",
  "size": 1048576,
  "mime_type": "application/pdf",
  "is_directory": false,
  "entry": {
    "name": "file.pdf",
    "is_directory": false,
    "chunks": 2,
    "attributes": { /* ... */ }
  }
}
```

### 2. NATS Integration

**Base Class**: `src/p8fs/workers/queues/seaweedfs_events/base.py`

The base event processor provides NATS JetStream integration:

**Stream Creation**:
- Stream Name: `P8FS_STORAGE_EVENTS`
- Subjects: `p8fs.storage.events`
- Description: "P8FS storage events from SeaweedFS"

**Publishing**:
Events are published to `p8fs.storage.events` subject as JSON messages.

### 3. Tiered Storage Router

**Location**: `src/p8fs/workers/queues/tiered_router.py`

The router consumes events from the main `p8fs.storage.events` queue and routes them to size-specific queues based on file size thresholds.

**Size Classification**:
- **Small**: 0 - 100 MB → `p8fs.storage.events.small`
- **Medium**: 100 MB - 1 GB → `p8fs.storage.events.medium`
- **Large**: 1 GB+ → `p8fs.storage.events.large`

**Resilience Patterns**:
1. **Explicit Consumer Cleanup**: Deletes stale consumers before starting
2. **Fail-Hard Design**: Setup failures cause immediate termination
3. **Consecutive Error Handling**: 3 consecutive errors trigger failure
4. **Publish-Then-ACK**: Messages only ACKed after successful routing
5. **Exponential Backoff**: 2x backoff between consecutive errors

**Routing Metadata Added**:
```json
{
  "routing": {
    "original_subject": "p8fs.storage.events",
    "target_subject": "p8fs.storage.events.small",
    "file_size_bytes": 1048576,
    "router_id": "router-1234567890",
    "message_count": 42,
    "routing_timestamp": 1234567890.123
  }
}
```

### 4. Storage Event Workers

**Location**: `src/p8fs/workers/queues/storage_worker.py`

Workers process events from size-specific queues and create Files/Resources entries.

**Worker Types**:
- **Small Worker**: Processes small files (high throughput)
- **Medium Worker**: Processes medium files (balanced)
- **Large Worker**: Processes large files (high memory)

**Processing Flow**:
1. Pull message from size-specific queue
2. Validate and parse storage event
3. Convert to legacy format for existing storage worker
4. Process file (create/update) or handle deletion
5. Update metrics and ACK message

**Integration with Existing Workers**:
```python
from p8fs.workers.storage import StorageWorker

# Queue workers wrap existing storage workers
storage_worker = StorageWorker(tenant_id)
await storage_worker.process_file(file_path, tenant_id, s3_key)
```

## Configuration

### Production Kubernetes Cluster

**Status**: ✅ **FULLY OPERATIONAL**

The production P8FS cluster runs in Kubernetes with complete gRPC event streaming:

**Deployed Components** (namespace: `p8fs`):

1. **SeaweedFS StatefulSets**:
   - `seaweedfs-master` (1 replica) - ports 9333, 19333, 9327
   - `seaweedfs-volume` (1 replica) - ports 8080, 18080, 9327
   - `seaweedfs-filer` (1 replica) - **ports 8888 (HTTP), 18888 (gRPC)**, 9327

2. **Event Processing Deployments**:
   - `seaweedfs-grpc-subscriber` (1 replica) - captures gRPC events → NATS
   - `seaweedfs-metadata-subscriber` (1 replica) - alternative subscriber
   - `seaweedfs-event-poller` (1 replica) - HTTP polling fallback

3. **Storage Workers** (process events from NATS):
   - `storage-worker-small` (2 replicas) - files < 100 MB
   - `storage-worker-medium` (0/1 replicas) - files 100 MB - 1 GB
   - `storage-worker-large` (0 replicas) - files > 1 GB

4. **NATS JetStream**:
   - `nats` StatefulSet (1 replica) - ports 4222, 8222

**Service Configuration**:
```yaml
# seaweedfs-filer service (headless)
ports:
  - name: swfs-filer
    port: 8888        # HTTP API
  - name: swfs-filer-grpc
    port: 18888       # gRPC metadata streaming
  - name: metrics
    port: 9327        # Prometheus metrics
```

**Event Flow Verification**:
```bash
# Check gRPC subscriber status
kubectl logs -n p8fs deployment/seaweedfs-grpc-subscriber --tail=20

# Example successful events:
# Published rename event for /buckets/tenant-test/uploads/... (stream: P8FS_STORAGE_EVENTS, seq: 11)

# Check storage worker processing
kubectl logs -n p8fs deployment/storage-worker-small --tail=20

# Worker subscribes to: p8fs.storage.events.small
# Durable consumer: small-workers
```

**Verified Working Components**:

1. ✅ **SeaweedFS Filer gRPC Port**: Port 18888 exposed and accessible
2. ✅ **gRPC Subscriber**: Successfully connecting and publishing events to NATS
3. ✅ **NATS JetStream**: Stream `P8FS_STORAGE_EVENTS` receiving events
4. ✅ **Storage Workers**: Small workers (2 replicas) processing events from queue
5. ✅ **Event Publishing**: Files uploaded via S3 trigger gRPC events successfully

**Current Deployment Pattern**:
- gRPC Subscriber publishes directly to: `p8fs.storage.events.small`
- Small workers consume from: `p8fs.storage.events.small` (durable: `small-workers`)
- All file sizes currently processed by small workers (tiered router not deployed)

**Known Issues**:
- Initial DNS resolution errors during subscriber startup (resolves after SeaweedFS pods ready)
- Medium/Large workers scaled to 0 (not needed without tiered router)

**Deployment Commands** (for K8s cluster):
```bash
# Check all P8FS deployments
kubectl get deployments -n p8fs

# Check SeaweedFS services
kubectl get services -n p8fs | grep seaweed

# View gRPC subscriber logs (live)
kubectl logs -n p8fs deployment/seaweedfs-grpc-subscriber -f

# View storage worker logs
kubectl logs -n p8fs deployment/storage-worker-small -f

# Check NATS stream status
kubectl exec -n p8fs deployment/nats-box -- \
  nats stream info P8FS_STORAGE_EVENTS

# Check consumer status
kubectl exec -n p8fs deployment/nats-box -- \
  nats consumer info P8FS_STORAGE_EVENTS_SMALL small-workers
```

### Local Docker Compose (Limited Testing Only)

**Note**: The local `docker-compose.yaml` provides a **limited deployment for basic file operations testing only**. It does NOT include gRPC event streaming and should not be used for event system development or testing.

```yaml
# Local testing only - no gRPC events
seaweedfs:
  image: chrislusf/seaweedfs:latest
  container_name: p8fs-seaweedfs
  ports:
    - "9333:9333" # Master
    - "8080:8080" # Volume
    - "8888:8888" # Filer HTTP only
  command: server -dir=/data
```

**Limitations**:
- Single-container server mode (not suitable for production patterns)
- gRPC port (18888) not exposed
- No metadata notification streaming
- Useful only for basic S3 API testing

**For event system work**: Use the production Kubernetes cluster or set up proper separated services locally (see below).

### Local Development with Full Event System

To test the complete event system locally, use separated containers:

```yaml
# docker-compose.events.yaml - for local event testing
services:
  seaweedfs-master:
    image: chrislusf/seaweedfs:latest
    command: master -defaultReplication=001
    ports:
      - "9333:9333"

  seaweedfs-volume:
    image: chrislusf/seaweedfs:latest
    command: volume -mserver=seaweedfs-master:9333 -port=8080
    ports:
      - "8080:8080"

  seaweedfs-filer:
    image: chrislusf/seaweedfs:latest
    command: filer -master=seaweedfs-master:9333
    ports:
      - "8888:8888"   # HTTP API
      - "18888:18888" # gRPC for events
    volumes:
      - ./filer.toml:/etc/seaweedfs/filer.toml

  nats:
    image: nats:alpine
    ports:
      - "4222:4222"
      - "8222:8222"
    command: --js --http_port 8222
```

### Environment Configuration

**Centralized Config** (from `p8fs_cluster.config.settings`):

```python
# SeaweedFS connection
seaweedfs_filer_host: str = "localhost"
seaweedfs_filer_grpc_port: int = 18888
seaweedfs_filer_http_port: int = 8888

# NATS connection (for event publishing)
nats_url: str = "nats://localhost:4222"
```

**Environment Variables**:
```bash
# SeaweedFS configuration
export SEAWEEDFS_FILER_HOST=localhost
export SEAWEEDFS_FILER_GRPC_PORT=18888
export SEAWEEDFS_FILER_HTTP_PORT=8888

# NATS configuration
export NATS_URL=nats://localhost:4222

# Path monitoring
export WATCH_PATH_PREFIX=/buckets/
```

## Usage

### Start gRPC Subscriber

```bash
# Via queue management CLI
uv run python -m p8fs.workers.queues.cli seaweedfs-events grpc

# Direct execution
cd src/p8fs/workers/queues/seaweedfs_events
uv run python -m p8fs.workers.queues.seaweedfs_events grpc

# With custom configuration
uv run python -m p8fs.workers.queues.seaweedfs_events grpc \
  --filer-host localhost \
  --filer-port 18888 \
  --path-prefix /buckets/ \
  --client-name my-subscriber
```

### Start Tiered Router

```bash
# Start the router to distribute events to size-specific queues
uv run python -m p8fs.workers.queues.cli router
```

### Start Storage Workers

```bash
# Start all workers (small, medium, large)
uv run python -m p8fs.workers.queues.cli workers --all

# Start specific worker
uv run python -m p8fs.workers.queues.cli workers --size small
```

### Check Configuration

```bash
# Show current configuration values
uv run python -m p8fs.workers.queues.seaweedfs_events config
```

### Event Capture (Debugging)

Capture raw events to disk for debugging:

```bash
uv run python -m p8fs.workers.queues.seaweedfs_events capture \
  --output-dir ./seaweedfs_events \
  --path-prefix /buckets/
```

## Programmatic Usage

### Basic Event Subscriber

```python
from p8fs.workers.queues.seaweedfs_events import SeaweedFSgRPCSubscriber

# Create subscriber
subscriber = SeaweedFSgRPCSubscriber(
    filer_host="localhost",
    filer_grpc_port=18888,
    path_prefix="/buckets/",
    client_name="my-app-subscriber"
)

# Set up and start
await subscriber.setup()
await subscriber.start()

# Stop when done
await subscriber.stop()
```

### Complete Pipeline

```python
from p8fs.services.nats import NATSClient
from p8fs.workers.queues import TieredStorageRouter, WorkerManager
from p8fs.workers.queues.seaweedfs_events import SeaweedFSgRPCSubscriber

# Initialize NATS client
nats_client = NATSClient()
await nats_client.connect()

# Start gRPC subscriber (captures events → NATS)
subscriber = SeaweedFSgRPCSubscriber()
await subscriber.setup()
subscriber_task = asyncio.create_task(subscriber.start())

# Start tiered router (routes events by size)
router = TieredStorageRouter()
await router.setup()
router_task = asyncio.create_task(router.start())

# Start storage workers (processes sized queues)
worker_manager = WorkerManager(nats_client, tenant_id="tenant-123")
await worker_manager.start_all_workers()

# Run until interrupted
await asyncio.gather(subscriber_task, router_task)
```

## Event Processing Flow

### 1. File Upload to SeaweedFS

```bash
# Upload file via S3 API
aws s3 cp file.pdf s3://buckets/tenant-123/documents/file.pdf \
  --endpoint-url http://localhost:8333
```

### 2. gRPC Event Capture

SeaweedFS Filer emits metadata event:
- Event type: `create`
- Path: `/buckets/tenant-123/documents/file.pdf`
- Metadata: size, MIME type, chunks, attributes

### 3. NATS Publishing

gRPC Subscriber publishes to `p8fs.storage.events`:
```json
{
  "type": "create",
  "path": "/buckets/tenant-123/documents/file.pdf",
  "tenant_id": "tenant-123",
  "size": 2097152,
  "mime_type": "application/pdf"
}
```

### 4. Tiered Routing

Router determines size (2 MB < 100 MB) and routes to `p8fs.storage.events.small`

### 5. Worker Processing

Small worker:
1. Pulls message from small queue
2. Creates `Files` entry in database
3. Triggers content processing (text extraction, embeddings)
4. ACKs message

### 6. Result

- File indexed in database
- Content extracted and stored
- Embeddings generated for semantic search
- Ready for querying

## Monitoring

### Stream Status

```python
from p8fs.services.nats import NATSClient

client = NATSClient()
await client.connect()

# Check main stream
info = await client.get_stream_info("P8FS_STORAGE_EVENTS")
print(f"Messages: {info['messages']}")
print(f"Consumers: {info['consumers']}")

# Check size-specific streams
for stream in ["P8FS_STORAGE_EVENTS_SMALL", "P8FS_STORAGE_EVENTS_MEDIUM", "P8FS_STORAGE_EVENTS_LARGE"]:
    info = await client.get_stream_info(stream)
    print(f"{stream}: {info['messages']} messages")
```

### Worker Metrics

```python
# Get worker status
status = await worker_manager.get_status()
print(f"Total messages processed: {status['summary']['total_messages_processed']}")
print(f"Total files processed: {status['summary']['total_files_processed']}")

# Get specific worker health
health = await worker.health_check()
print(f"Healthy: {health['healthy']}")
print(f"NATS connected: {health['checks']['nats_connected']}")
```

## Troubleshooting

### No Events Being Captured

**Symptoms**: gRPC subscriber runs but receives no events

**Possible Causes**:
1. SeaweedFS not configured with gRPC port exposed
2. gRPC port not accessible (check `18888`)
3. Notification not enabled in filer configuration

**Solutions**:
```bash
# Check if gRPC port is accessible
nc -zv localhost 18888

# Check SeaweedFS logs
docker logs p8fs-seaweedfs

# Enable debug logging
uv run python -m p8fs.workers.queues.seaweedfs_events grpc --debug
```

### Router Not Processing Messages

**Symptoms**: Messages in main queue but not routed to size-specific queues

**Possible Causes**:
1. Router not running
2. Consumer conflicts (stale consumers)
3. NATS connection issues

**Solutions**:
```bash
# Check router status
# (router logs show processed/error counts)

# Check for stale consumers
# Router automatically cleans up old consumers on startup

# Verify NATS connection
docker logs p8fs-nats  # if using dockerized NATS
```

### Workers Not Processing Files

**Symptoms**: Messages in size-specific queues but files not created

**Possible Causes**:
1. Workers not running
2. Database connection issues
3. Storage worker errors

**Solutions**:
```bash
# Check worker status
# Workers log processing time and success/failure

# Check database connectivity
docker exec percolate psql -U postgres -d app -c "SELECT 1"

# Enable debug logging for storage workers
export P8FS_LOG_LEVEL=DEBUG
```

## Performance Considerations

### Scaling Workers

KEDA can automatically scale workers based on queue depth:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: storage-worker-small
spec:
  scaleTargetRef:
    name: storage-worker-small
  minReplicaCount: 1
  maxReplicaCount: 10
  triggers:
  - type: nats-jetstream
    metadata:
      natsServerMonitoringEndpoint: "nats://nats:8222"
      account: "$G"
      stream: "P8FS_STORAGE_EVENTS_SMALL"
      consumerName: "small-workers"
      lagThreshold: "10"
```

### Throughput Optimization

**Small Files** (< 100 MB):
- High worker count (10-20 replicas)
- Fast processing (text extraction, embeddings)
- High throughput (100+ files/min per worker)

**Medium Files** (100 MB - 1 GB):
- Medium worker count (5-10 replicas)
- Moderate processing time
- Medium throughput (10-50 files/min per worker)

**Large Files** (> 1 GB):
- Low worker count (1-5 replicas)
- High memory requirements
- Low throughput (1-10 files/min per worker)

### Backpressure Management

Router implements consecutive error handling:
- 3 consecutive errors trigger failure
- Exponential backoff (2x per error)
- Fail-hard design prevents silent failures

## Testing

### Integration Test

```bash
# Start services
docker-compose up postgres nats seaweedfs -d

# Start event processing pipeline
uv run python -m p8fs.workers.queues.seaweedfs_events grpc &
uv run python -m p8fs.workers.queues.cli router &
uv run python -m p8fs.workers.queues.cli workers --all &

# Upload test file
aws s3 cp test.pdf s3://buckets/tenant-test/test.pdf \
  --endpoint-url http://localhost:8333

# Verify processing
psql -h localhost -p 5438 -U postgres -d app \
  -c "SELECT name, category FROM resources WHERE tenant_id='tenant-test'"
```

### Event Capture Test

```bash
# Capture events for analysis
uv run python -m p8fs.workers.queues.seaweedfs_events capture \
  --output-dir ./test_events &

# Upload file
aws s3 cp test.pdf s3://buckets/tenant-test/test.pdf \
  --endpoint-url http://localhost:8333

# Check captured events
ls -la test_events/
cat test_events/event_*.json | jq
```

## Future Enhancements

### Planned Features

1. **HTTP Poller Fallback**: Polling-based event detection when gRPC unavailable
2. **Event Replay**: Replay historical events from timestamp
3. **Dead Letter Queue**: Handle persistently failing messages
4. **Metrics Dashboard**: Real-time visualization of event flow
5. **Multi-Cluster Support**: Federated event processing across clusters

### Known Limitations

1. **No Event History**: Only captures events from subscription time forward
2. **Single Filer**: Subscribes to one filer instance (can run multiple subscribers)
3. **No Deduplication**: Same event may be processed multiple times on reconnection
4. **Path-Based Tenant**: Assumes `/buckets/{tenant_id}/` structure

## References

- **SeaweedFS Documentation**: https://github.com/seaweedfs/seaweedfs/wiki
- **SeaweedFS gRPC API**: https://github.com/seaweedfs/seaweedfs/tree/master/weed/pb
- **NATS JetStream**: https://docs.nats.io/nats-concepts/jetstream
- **KEDA Scaling**: https://keda.sh/docs/latest/scalers/nats-jetstream/
