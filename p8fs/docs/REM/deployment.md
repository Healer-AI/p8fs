# REM Deployment

## Local Development

### Database Setup

**PostgreSQL** (default for local development):
```bash
cd p8fs
docker-compose up postgres -d
```

Connection: `postgresql://postgres:postgres@localhost:5438/app`

**TiDB** (for cluster testing):
```bash
cd p8fs
docker-compose up tidb -d
```

Connection: `mysql://root@localhost:4000/test`

### Environment Configuration

```bash
# Storage provider
export P8FS_STORAGE_PROVIDER=postgresql  # or tidb

# Embedding provider for local testing
export P8FS_DEFAULT_EMBEDDING_PROVIDER=text-embedding-3-small

# API keys
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...

# LLM settings
export P8FS_LLM_PROVIDER=openai
export P8FS_DEFAULT_MODEL=gpt-4.1
```

### Running Dreaming Workers Locally

```bash
# Direct execution (synchronous)
python -m p8fs.cli dreaming \
  --tenant-id demo-tenant-001 \
  --mode moments \
  --execution-mode direct \
  --lookback-hours 168

python -m p8fs.cli dreaming \
  --tenant-id demo-tenant-001 \
  --mode affinity \
  --execution-mode direct \
  --lookback-hours 168
```

## Cluster Deployment

### Kubernetes Configuration

**Namespace**: `p8fs-workers`

**ConfigMap** (`p8fs-dreaming-config`):
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: p8fs-dreaming-config
  namespace: p8fs-workers
data:
  P8FS_STORAGE_PROVIDER: "tidb"
  P8FS_TIDB_HOST: "tidb-cluster.tidb.svc.cluster.local"
  P8FS_TIDB_PORT: "4000"
  P8FS_TIDB_DATABASE: "production"
  P8FS_DEFAULT_EMBEDDING_PROVIDER: "all-MiniLM-L6-v2"
  P8FS_NATS_URL: "nats://nats-server.nats.svc.cluster.local:4222"
  P8FS_LLM_PROVIDER: "openai"
  P8FS_DEFAULT_MODEL: "gpt-4.1"
```

**Secrets** (`p8fs-api-keys`):
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: p8fs-api-keys
  namespace: p8fs-workers
type: Opaque
stringData:
  OPENAI_API_KEY: "sk-..."
  ANTHROPIC_API_KEY: "sk-ant-..."
```

### Scheduled Jobs

**First-Order Dreaming** (every 6 hours):
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: p8fs-dreaming-moments
  namespace: p8fs-workers
spec:
  schedule: "0 */6 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: dreaming-worker
            image: p8fs:latest
            command:
            - python
            - -m
            - p8fs.cli
            - dreaming
            args:
            - --tenant-id=system
            - --mode=moments
            - --execution-mode=batch
            - --lookback-hours=24
            envFrom:
            - configMapRef:
                name: p8fs-dreaming-config
            - secretRef:
                name: p8fs-api-keys
            resources:
              requests:
                memory: "512Mi"
                cpu: "250m"
              limits:
                memory: "2Gi"
                cpu: "1000m"
          restartPolicy: OnFailure
```

**Second-Order Dreaming** (daily at 2 AM):
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: p8fs-dreaming-affinity
  namespace: p8fs-workers
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: dreaming-worker
            image: p8fs:latest
            command:
            - python
            - -m
            - p8fs.cli
            - dreaming
            args:
            - --tenant-id=system
            - --mode=affinity
            - --execution-mode=batch
            - --lookback-hours=168
            envFrom:
            - configMapRef:
                name: p8fs-dreaming-config
            - secretRef:
                name: p8fs-api-keys
            resources:
              requests:
                memory: "1Gi"
                cpu: "500m"
              limits:
                memory: "4Gi"
                cpu: "2000m"
          restartPolicy: OnFailure
```

### NATS Workers (Event-Driven)

**Worker Deployment**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: p8fs-dreaming-worker
  namespace: p8fs-workers
spec:
  replicas: 2
  selector:
    matchLabels:
      app: p8fs-dreaming-worker
  template:
    metadata:
      labels:
        app: p8fs-dreaming-worker
    spec:
      containers:
      - name: worker
        image: p8fs:latest
        command:
        - python
        - -m
        - p8fs.workers.dreaming
        - --mode=subscribe
        env:
        - name: WORKER_TYPE
          value: "dreaming_worker"
        - name: P8FS_NATS_URL
          valueFrom:
            configMapKeyRef:
              name: p8fs-dreaming-config
              key: P8FS_NATS_URL
        envFrom:
        - configMapRef:
            name: p8fs-dreaming-config
        - secretRef:
            name: p8fs-api-keys
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
```

**KEDA ScaledObject** (auto-scaling based on queue depth):
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: p8fs-dreaming-worker-scaler
  namespace: p8fs-workers
spec:
  scaleTargetRef:
    name: p8fs-dreaming-worker
  minReplicaCount: 1
  maxReplicaCount: 10
  triggers:
  - type: nats-jetstream
    metadata:
      natsServerMonitoringEndpoint: "nats-server.nats.svc.cluster.local:8222"
      stream: "dreaming_jobs"
      consumer: "dreaming_worker"
      lagThreshold: "10"
```

## Monitoring

### Metrics

**Moment Extraction**:
- Moments created per hour
- Average processing time per resource
- Failed extractions (LLM errors)

**Affinity Calculation**:
- Graph edges created per hour
- Vector search latency
- Failed similarity calculations

**Resource Coverage**:
- Resources with moments: target 60%+
- Resources with affinity edges: target 70%+
- Average graph degree: target 2-3

### Logging

```bash
# View scheduled job logs
kubectl logs -n p8fs-workers job/p8fs-dreaming-moments-<timestamp>

# View worker logs
kubectl logs -n p8fs-workers deployment/p8fs-dreaming-worker -f

# Check NATS queue status
kubectl exec -n nats nats-server-0 -- nats stream info dreaming_jobs
```

### Alerts

**Critical alerts**:
- Dreaming job failed 3 consecutive runs
- Resource coverage dropped below 50%
- Graph connectivity degraded (avg degree < 1.5)

**Warning alerts**:
- Processing latency > 10s per resource
- Queue depth > 1000 jobs
- Worker pod restarts

## Troubleshooting

### Common Issues

**Embedding dimension mismatch**:
```
Error: expected 1536 dimensions, not 384
```
Fix: Set `P8FS_DEFAULT_EMBEDDING_PROVIDER=text-embedding-3-small` for OpenAI or recreate database schema for FastEmbed (384 dims).

**LLM API rate limiting**:
```
Error: Rate limit exceeded
```
Fix: Reduce batch size, increase delay between requests, or upgrade API tier.

**Worker OOM killed**:
```
Container killed: OOMKilled
```
Fix: Increase memory limits in deployment or reduce batch processing size.

**NATS connection timeout**:
```
Error: Failed to connect to NATS
```
Fix: Check NATS service is running, verify URL in config, check network policies.

### Database Verification

**PostgreSQL**:
```bash
docker exec percolate psql -U postgres -d app -c "
  SELECT COUNT(*) as moments FROM moments WHERE tenant_id = 'demo-tenant-001';
  SELECT COUNT(*) as resources_with_edges
  FROM resources
  WHERE tenant_id = 'demo-tenant-001' AND array_length(graph_paths, 1) > 0;
"
```

**TiDB**:
```bash
mysql -h localhost -P 4000 -u root test -e "
  SELECT COUNT(*) as moments FROM moments WHERE tenant_id = 'demo-tenant-001';
  SELECT COUNT(*) as resources_with_edges
  FROM resources
  WHERE tenant_id = 'demo-tenant-001' AND JSON_LENGTH(graph_paths) > 0;
"
```

## Performance Tuning

### Batch Sizes

**Moment extraction**:
- Local: 10-50 resources per batch
- Cluster: 50-100 resources per batch

**Affinity calculation**:
- Local: 20-50 resources per batch
- Cluster: 100-200 resources per batch

### Worker Scaling

**KEDA scaling targets**:
- Lag threshold: 10 jobs
- Min replicas: 1
- Max replicas: 10
- Scale up: queue depth > 10
- Scale down: queue empty for 5 minutes

### Database Connections

**Connection pooling**:
- Min connections: 2 per worker
- Max connections: 10 per worker
- Idle timeout: 300 seconds
- Max lifetime: 3600 seconds
