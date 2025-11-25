# Dreaming Worker - Cluster Testing Guide

Quick reference for running parameterized dreaming jobs on Kubernetes cluster.

## Prerequisites

```bash
# 1. Ensure ConfigMap and Secret exist
kubectl get configmap p8fs-dreaming-config -n p8fs-workers
kubectl get secret p8fs-api-keys -n p8fs-workers

# 2. Verify cluster access
kubectl cluster-info
```

## Critical Configuration

### Embedding Provider

**IMPORTANT**: Set the embedding provider to match your database vector dimensions.

```bash
# For PostgreSQL/TiDB with 1536 dimensions (production default)
export P8FS_DEFAULT_EMBEDDING_PROVIDER=text-embedding-3-small

# For local testing with FastEmbed (384 dimensions)
export P8FS_DEFAULT_EMBEDDING_PROVIDER=all-MiniLM-L6-v2
```

**Why this matters**: The embedding provider determines vector dimensions for all generated embeddings. Your database schema must match the provider's dimensions, or you'll get "expected X dimensions, not Y" errors.

### Environment Variables Checklist

```bash
# Required
P8FS_STORAGE_PROVIDER=tidb          # or postgresql
P8FS_DEFAULT_EMBEDDING_PROVIDER=text-embedding-3-small
OPENAI_API_KEY=sk-...               # For embeddings and LLM

# Optional (for email notifications)
P8FS_SMTP_HOST=smtp.gmail.com
P8FS_SMTP_PORT=587
P8FS_SMTP_USERNAME=your-email@gmail.com
P8FS_SMTP_PASSWORD=your-app-password
```

## Ad-hoc Testing (One-off Jobs)

Run dreaming tasks immediately without waiting for cron schedule:

### Basic Syntax

```bash
# Run a one-off job from existing CronJob
kubectl create job <job-name> \
  --from=cronjob/<cronjob-name> \
  -n p8fs-workers

# Or run a custom pod directly
kubectl run <pod-name> \
  --image=p8fs:latest \
  --restart=Never \
  --rm -it \
  --env="<ENV_VAR>=<value>" \
  -n p8fs-workers \
  -- python -m p8fs.cli dreaming <args>
```

### Example: Test Moments Processing

```bash
# Quick test with specific tenant (limit 50 resources)
kubectl run test-moments-$(date +%s) \
  --image=p8fs:latest \
  --restart=Never \
  --rm -it \
  -n p8fs-workers \
  --env="P8FS_STORAGE_PROVIDER=tidb" \
  -- python -m p8fs.cli dreaming \
    --task=moments \
    --tenant-id=tenant-test \
    --lookback-hours=24 \
    --limit=50

# From existing CronJob (uses all configured env vars)
kubectl create job test-moments-adhoc \
  --from=cronjob/p8fs-dreaming-moments \
  -n p8fs-workers

# Watch logs
kubectl logs -f job/test-moments-adhoc -n p8fs-workers
```

### Example: Test Resource Affinity (Fast Semantic)

```bash
# Fast semantic similarity mode
kubectl run test-affinity-fast-$(date +%s) \
  --image=p8fs:latest \
  --restart=Never \
  --rm -it \
  -n p8fs-workers \
  --env="P8FS_STORAGE_PROVIDER=tidb" \
  -- python -m p8fs.cli dreaming \
    --task=affinity \
    --tenant-id=tenant-test \
    --lookback-hours=168 \
    --limit=100

# Process all active tenants
kubectl run test-affinity-all-$(date +%s) \
  --image=p8fs:latest \
  --restart=Never \
  --rm -it \
  -n p8fs-workers \
  --env="P8FS_STORAGE_PROVIDER=tidb" \
  -- python -m p8fs.cli dreaming \
    --task=affinity \
    --lookback-hours=48
```

### Example: Test Resource Affinity (LLM Mode)

```bash
# WARNING: Expensive! Use small limits for testing
kubectl run test-affinity-llm-$(date +%s) \
  --image=p8fs:latest \
  --restart=Never \
  --rm -it \
  -n p8fs-workers \
  --env="P8FS_STORAGE_PROVIDER=tidb" \
  --env="OPENAI_API_KEY=${OPENAI_API_KEY}" \
  -- python -m p8fs.cli dreaming \
    --task=affinity \
    --use-llm \
    --tenant-id=tenant-test \
    --lookback-hours=168 \
    --limit=20

# Note: For production LLM runs, use --limit carefully!
# Each resource pair evaluated by LLM = API cost
```

### Example: Test Both Tasks

```bash
# Process both moments and affinity
kubectl run test-both-$(date +%s) \
  --image=p8fs:latest \
  --restart=Never \
  --rm -it \
  -n p8fs-workers \
  --env="P8FS_STORAGE_PROVIDER=tidb" \
  -- python -m p8fs.cli dreaming \
    --task=both \
    --tenant-id=tenant-test \
    --lookback-hours=72 \
    --limit=200
```

### Example: Test with Email Notifications

```bash
# Moments with email digest
kubectl run test-moments-email-$(date +%s) \
  --image=p8fs:latest \
  --restart=Never \
  --rm -it \
  -n p8fs-workers \
  --env="P8FS_STORAGE_PROVIDER=tidb" \
  -- python -m p8fs.cli dreaming \
    --task=moments \
    --tenant-id=tenant-test \
    --lookback-hours=24 \
    --recipient-email=test@example.com \
    --limit=100
```

## Triggering Manual Jobs from CronJob

**IMPORTANT**: Always create manual jobs from the existing `p8fs-dreaming-worker` CronJob. This ensures:
- ArgoCD shows the job as a child resource
- Jobs inherit all configuration from the managed CronJob
- No configuration drift between manual and scheduled runs

### Quick Manual Run

```bash
# Create job from existing cronjob
kubectl create job -n p8fs dreaming-manual-$(date +%s) --from=cronjob/p8fs-dreaming-worker

# Watch job status
kubectl get jobs -n p8fs -w

# Get pod name and follow logs
POD_NAME=$(kubectl get pods -n p8fs -l job-name=dreaming-manual-TIMESTAMP -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n p8fs -f $POD_NAME
```

### Example: Run Dreaming Worker Now

```bash
# Trigger immediate dreaming job (processes all active tenants)
JOB_NAME="dreaming-manual-$(date +%s)"
kubectl create job -n p8fs $JOB_NAME --from=cronjob/p8fs-dreaming-worker

# Follow logs
kubectl logs -n p8fs -f -l job-name=$JOB_NAME

# Cleanup when done
kubectl delete job -n p8fs $JOB_NAME
```

### Why Use --from=cronjob?

Using `kubectl create job --from=cronjob` instead of standalone Job manifests:
- ✅ Inherits all cronjob configuration (env vars, secrets, resources)
- ✅ Shows as child resource in ArgoCD UI
- ✅ Matches production cronjob configuration exactly
- ✅ No need to maintain separate Job manifests
- ✅ Easier to trigger on-demand testing

### Customizing Manual Jobs

If you need to override parameters (like email recipient), modify the cronjob args temporarily or create a separate parameterized cronjob template.

## Parameter Reference

### Required (one of):
- `--task`: Task type
  - `moments` - Extract temporal activities, classify into moment segments, generate embeddings, and send email digest
  - `affinity` - Build resource relationship graph using semantic similarity or LLM
  - `both` - **Insights workflow**: Run moments + affinity together (recommended for daily cron)
  - `dreams` - Extract goals/fears/dreams using DreamModel (psychological analysis)

### Optional:
- `--tenant-id=<id>` - Process specific tenant (default: all active tenants)
- `--lookback-hours=<hours>` - How far back to look for resources (default: 24)
- `--limit=<number>` - Max resources to process (default: no limit)
- `--use-llm` - Enable LLM mode for affinity (intelligent but expensive)
- `--recipient-email=<email>` - Send moment digest to this email (defaults to tenant email from database)
- `--model=<model>` - LLM model to use (default: from config)
- `--mode=<mode>` - Processing mode: direct, batch, completion (default: direct)
- `--polling` - Enable continuous polling mode (default: False)
- `--poll-interval=<seconds>` - Polling interval in seconds (default: 300)

## Monitoring Running Jobs

```bash
# List all jobs
kubectl get jobs -n p8fs-workers

# Watch job status
kubectl get jobs -n p8fs-workers -w

# View job logs (follow)
kubectl logs -f job/<job-name> -n p8fs-workers

# View pod logs if job failed
kubectl get pods -n p8fs-workers | grep <job-name>
kubectl logs <pod-name> -n p8fs-workers

# Describe job for troubleshooting
kubectl describe job/<job-name> -n p8fs-workers

# Delete completed job
kubectl delete job/<job-name> -n p8fs-workers
```

## Verify Results in Database

### PostgreSQL

```bash
# Connect to PostgreSQL
kubectl exec -it <postgres-pod> -n p8fs-workers -- psql -U postgres -d app

# Check moments created (basic count)
SELECT tenant_id, COUNT(*) as moment_count, MAX(created_at) as latest
FROM moments
GROUP BY tenant_id;

# Verify moments WITH embeddings (comprehensive check)
SELECT
  m.id,
  m.name,
  m.moment_type,
  m.created_at,
  e.embedding_provider,
  e.vector_dimension
FROM moments m
LEFT JOIN embeddings.moments_embeddings e ON m.id = e.entity_id
WHERE m.tenant_id = 'tenant-test'
  AND m.created_at > NOW() - INTERVAL '24 hours'
ORDER BY m.created_at DESC
LIMIT 10;

# Check for moments WITHOUT embeddings (should be empty)
SELECT m.id, m.name, m.created_at
FROM moments m
LEFT JOIN embeddings.moments_embeddings e ON m.id = e.entity_id
WHERE m.tenant_id = 'tenant-test'
  AND e.entity_id IS NULL
  AND m.created_at > NOW() - INTERVAL '24 hours';

# Check affinity edges
SELECT tenant_id, COUNT(*) as resource_count,
       SUM(array_length(graph_paths, 1)) as total_edges
FROM resources
WHERE array_length(graph_paths, 1) > 0
GROUP BY tenant_id;
```

### TiDB

```bash
# Connect to TiDB
kubectl exec -it <tidb-pod> -n tidb -- mysql -u root -P 4000 production

# Check moments created (basic count)
SELECT tenant_id, COUNT(*) as moment_count, MAX(created_at) as latest
FROM moments
GROUP BY tenant_id;

# Verify moments WITH embeddings (comprehensive check)
SELECT
  m.id,
  m.name,
  m.moment_type,
  m.created_at,
  e.embedding_provider,
  e.vector_dimension
FROM moments m
LEFT JOIN moments_embeddings e ON m.id = e.entity_id
WHERE m.tenant_id = 'tenant-test'
  AND m.created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY m.created_at DESC
LIMIT 10;

# Check for moments WITHOUT embeddings (should be empty)
SELECT m.id, m.name, m.created_at
FROM moments m
LEFT JOIN moments_embeddings e ON m.id = e.entity_id
WHERE m.tenant_id = 'tenant-test'
  AND e.entity_id IS NULL
  AND m.created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR);

# Check affinity edges
SELECT tenant_id, COUNT(*) as resource_count,
       SUM(JSON_LENGTH(graph_paths)) as total_edges
FROM resources
WHERE JSON_LENGTH(graph_paths) > 0
GROUP BY tenant_id;
```

### Verify Email Sending

```bash
# Check job logs for email confirmation
kubectl logs job/<job-name> -n p8fs-workers | grep -i "email"

# Expected output for successful email:
# INFO | Preparing to send moments email to user@example.com
# INFO | Email sent successfully to user@example.com
# INFO | Successfully sent moments email to user@example.com

# If email not sent, check:
# 1. SMTP environment variables are set
kubectl get secret p8fs-api-keys -n p8fs-workers -o jsonpath='{.data}' | base64 -d

# 2. Recipient email was provided or found in tenant profile
kubectl logs job/<job-name> -n p8fs-workers | grep "recipient_email"

# 3. Moments were actually generated
kubectl logs job/<job-name> -n p8fs-workers | grep "Successfully saved"
```

## Performance Tips

### For Testing

- Use `--limit=50` for quick smoke tests
- Use `--limit=100-200` for reasonable feature tests
- Use specific `--tenant-id` to avoid processing all tenants
- Avoid `--use-llm` unless specifically testing LLM mode

### For LLM Mode

- **Always** use `--limit` with LLM mode to control costs
- Start with `--limit=20` for initial testing
- Each resource pair = 1 LLM API call
- 100 resources = potentially thousands of API calls
- Monitor costs in your LLM provider dashboard

### For Production

- Use scheduled CronJobs instead of ad-hoc runs
- Set appropriate memory/CPU limits in CronJob specs
- Enable `--use-llm` only for daily deep analysis
- Use fast semantic mode for frequent updates (every 2-6 hours)

## Troubleshooting

### Job Stuck in Pending

```bash
kubectl describe job/<job-name> -n p8fs-workers
# Check: Resource limits, image pull status, node availability
```

### Pod Crashed (OOMKilled)

```bash
kubectl get pods -n p8fs-workers | grep <job-name>
kubectl describe pod/<pod-name> -n p8fs-workers
# Increase memory limits in CronJob spec
```

### No Results Generated

```bash
# Check logs for errors
kubectl logs job/<job-name> -n p8fs-workers | grep -i error

# Verify database connectivity
kubectl run test-db-$(date +%s) \
  --image=p8fs:latest \
  --restart=Never \
  --rm -it \
  -n p8fs-workers \
  --env="P8FS_STORAGE_PROVIDER=tidb" \
  -- python -c "from p8fs.providers import get_provider; p = get_provider(); print('DB OK')"
```

### Moments Generated But Not Saved

**Symptom**: Logs show "Successfully saved N moments" but database has 0 rows

**Root Cause**: UUID serialization error in batch operations (fixed in v1.1.57)

**Diagnosis**:
```bash
# Check for UUID serialization errors
kubectl logs job/<job-name> -n p8fs-workers | grep -i "can't adapt type"
kubectl logs job/<job-name> -n p8fs-workers | grep -i "UUID"

# Verify actual database saves
kubectl logs job/<job-name> -n p8fs-workers | grep "affected_rows"
```

**Solution**: Upgrade to p8fs v1.1.57+ which includes proper UUID to string conversion

### Embedding Dimension Mismatch

**Symptom**: `expected 1536 dimensions, not 384` or similar error

**Root Cause**: Embedding provider doesn't match database schema

**Diagnosis**:
```bash
# Check current embedding provider
kubectl logs job/<job-name> -n p8fs-workers | grep "embedding_provider"

# Check database schema dimensions
# PostgreSQL:
psql -c "SELECT vector_dimension FROM embeddings.moments_embeddings LIMIT 1;"

# TiDB:
mysql -e "SELECT vector_dimension FROM moments_embeddings LIMIT 1;"
```

**Solution**:
```bash
# Set correct embedding provider in ConfigMap/Secret
# For 1536 dims: text-embedding-3-small
# For 384 dims: all-MiniLM-L6-v2
kubectl set env cronjob/p8fs-dreaming-moments \
  P8FS_DEFAULT_EMBEDDING_PROVIDER=text-embedding-3-small \
  -n p8fs-workers
```

### OpenAI Rate Limit (TPM)

**Symptom**: `Request too large for gpt-4o: Limit 30000, Requested 31935`

**Root Cause**: Content exceeds tokens-per-minute rate limit (fixed in v1.1.57)

**Diagnosis**:
```bash
kubectl logs job/<job-name> -n p8fs-workers | grep "rate_limit_exceeded"
kubectl logs job/<job-name> -n p8fs-workers | grep "TPM"
```

**Solution**: Upgrade to p8fs v1.1.57+ which caps chunk size at 25K tokens to respect TPM limits

### Email Not Sent

**Symptom**: Moments generated successfully but no email received

**Root Cause**: Missing recipient_email or SMTP configuration

**Diagnosis**:
```bash
# Check if recipient email was found
kubectl logs job/<job-name> -n p8fs-workers | grep "recipient_email"

# Check SMTP configuration
kubectl get secret p8fs-api-keys -n p8fs-workers -o jsonpath='{.data.P8FS_SMTP_HOST}' | base64 -d

# Check for email sending errors
kubectl logs job/<job-name> -n p8fs-workers | grep -i "smtp\|email"
```

**Solution**:
```bash
# Option 1: Pass email explicitly
kubectl run test-moments-$(date +%s) ... \
  --recipient-email=user@example.com

# Option 2: Set in tenant database profile
# Option 3: Configure SMTP environment variables
```

### JSONB vs Array Type Errors

**Symptom**: `column "emotion_tags" is of type jsonb but expression is of type text[]`

**Root Cause**: Incorrect type serialization (fixed in v1.1.57)

**Diagnosis**:
```bash
kubectl logs job/<job-name> -n p8fs-workers | grep "is of type jsonb"
```

**Solution**: Upgrade to p8fs v1.1.57+ which properly handles JSONB fields

### API Key Issues

```bash
# Verify secret exists
kubectl get secret p8fs-api-keys -n p8fs-workers -o yaml

# Check if keys are set in pod
kubectl run test-keys-$(date +%s) \
  --image=p8fs:latest \
  --restart=Never \
  --rm -it \
  -n p8fs-workers \
  --env="P8FS_STORAGE_PROVIDER=tidb" \
  --env-from=secret/p8fs-api-keys \
  -- env | grep -i key
```

## Common Cron Job Patterns

### Daily Insights (Recommended)

Run moments + affinity every 24 hours at 3 AM:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: p8fs-dreaming-daily-insights
  namespace: p8fs-workers
spec:
  schedule: "0 3 * * *"  # 3 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: dreaming
            image: p8fs:latest
            command:
            - python
            - -m
            - p8fs.cli
            - dreaming
            - --task=both
            - --lookback-hours=24
            env:
            - name: P8FS_STORAGE_PROVIDER
              value: tidb
            - name: P8FS_DEFAULT_EMBEDDING_PROVIDER
              value: text-embedding-3-small
            envFrom:
            - secretRef:
                name: p8fs-api-keys
          restartPolicy: OnFailure
```

### Frequent Affinity Updates

Build resource graph every 6 hours using fast semantic mode:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: p8fs-dreaming-affinity-frequent
  namespace: p8fs-workers
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: dreaming
            image: p8fs:latest
            command:
            - python
            - -m
            - p8fs.cli
            - dreaming
            - --task=affinity
            - --lookback-hours=6
            env:
            - name: P8FS_STORAGE_PROVIDER
              value: tidb
            envFrom:
            - secretRef:
                name: p8fs-api-keys
          restartPolicy: OnFailure
```

### Weekly Deep Analysis

Weekly LLM-powered affinity analysis every Sunday at 2 AM:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: p8fs-dreaming-weekly-llm
  namespace: p8fs-workers
spec:
  schedule: "0 2 * * 0"  # Sunday 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: dreaming
            image: p8fs:latest
            command:
            - python
            - -m
            - p8fs.cli
            - dreaming
            - --task=affinity
            - --use-llm
            - --lookback-hours=168
            - --limit=500
            env:
            - name: P8FS_STORAGE_PROVIDER
              value: tidb
            - name: P8FS_DEFAULT_EMBEDDING_PROVIDER
              value: text-embedding-3-small
            envFrom:
            - secretRef:
                name: p8fs-api-keys
          restartPolicy: OnFailure
```

### Tenant-Specific Moments with Email

Daily moments for specific high-value tenant with email:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: p8fs-dreaming-vip-tenant
  namespace: p8fs-workers
spec:
  schedule: "0 8 * * *"  # 8 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: dreaming
            image: p8fs:latest
            command:
            - python
            - -m
            - p8fs.cli
            - dreaming
            - --task=moments
            - --tenant-id=vip-tenant-123
            - --lookback-hours=24
            - --recipient-email=vip@example.com
            env:
            - name: P8FS_STORAGE_PROVIDER
              value: tidb
            - name: P8FS_DEFAULT_EMBEDDING_PROVIDER
              value: text-embedding-3-small
            envFrom:
            - secretRef:
                name: p8fs-api-keys
          restartPolicy: OnFailure
```

## Cost Management

### Estimate LLM Costs

For `--task=affinity --use-llm`:
- Each resource evaluated against N other resources
- Approximate: `(limit * limit) / 2` LLM API calls
- With `--limit=100`: ~5,000 API calls
- With `--limit=500`: ~125,000 API calls

**Always start small when testing LLM mode!**

### Cost-Effective Strategies

1. Use semantic mode (no `--use-llm`) for frequent updates
2. Use LLM mode with small `--limit` for targeted deep analysis
3. Run LLM mode daily at off-peak hours
4. Use batch mode for large workloads to avoid timeouts
