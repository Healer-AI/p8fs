# OpenTelemetry Instrumentation Summary

## What's Been Implemented

### 1. OpenTelemetry Collector

Running in the cluster at `otel-collector.observability.svc.cluster.local:4317`

Check status:
```bash
kubectl get pods -n observability
kubectl get svc -n observability
```

Health check:
```bash
kubectl exec -n observability deploy/otel-collector -- curl http://localhost:13133
```

### 2. Centralized Configuration

All OTEL settings are in `p8fs-cluster/src/p8fs_cluster/config/settings.py`:

```python
# Tracing
tracing_enabled: bool = True
otel_exporter_otlp_endpoint: str = "otel-collector.observability.svc.cluster.local:4317"

# Service identification
otel_service_name: str = "p8fs-api"
otel_service_version: str = "0.1.0"
otel_service_namespace: str = "p8fs"

# Environment
deployment_environment: str = "kubernetes"

# Export settings
otel_trace_export_interval: int = 5000  # milliseconds
otel_insecure: bool = True  # for internal cluster communication
```

Override via environment variables:
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317
export OTEL_SERVICE_NAME=my-service
export P8FS_TRACING_ENABLED=true
```

### 3. Auto-Instrumentation

Automatically traces:

**FastAPI Endpoints**
- All HTTP requests (method, route, status code, duration)
- Automatic span creation for each endpoint
- Exception tracking

**HTTPX Client**
- All outbound HTTP requests
- Target URL, method, status code, duration

**MCP Server**
- All MCP tool calls (via FastAPI)
- Tool name, parameters, execution time

**Logging**
- Log entries correlated with traces
- Trace/span IDs available for log context

### 4. Manual Instrumentation Decorators

#### Agent Tracing

```python
from p8fs_api.observability import trace_agent

class MyAgent:
    @trace_agent()
    async def analyze(self, content: str) -> dict:
        result = await self.process_content(content)
        return result

    @trace_agent("CustomAnalyzer")
    def process_sync(self, data: str) -> str:
        return processed_data
```

Creates spans: `agent.MyAgent.analyze`, `agent.CustomAnalyzer.process_sync`

#### LLM Call Tracing

```python
from p8fs_api.observability import trace_llm_call

@trace_llm_call(model="gpt-4o", provider="openai", temperature=0.7)
async def generate_response(prompt: str) -> str:
    response = await openai_client.generate(prompt)
    return response
```

Creates spans: `llm.openai.gpt-4o` with model metadata

#### Custom Operation Tracing

```python
from p8fs_api.observability import trace_operation

async def generate_embeddings(text: str):
    with trace_operation("embedding_generation",
                        model="text-embedding-3-small",
                        input_length=len(text)):
        embeddings = await embedding_service.embed(text)
        return embeddings
```

Creates spans: `operation.embedding_generation` with custom attributes

### 5. Log Correlation

```python
from p8fs_api.observability import get_current_trace_id, get_current_span_id

trace_id = get_current_trace_id()  # Returns hex string or None
span_id = get_current_span_id()    # Returns hex string or None

logger.info("Processing request", trace_id=trace_id, span_id=span_id)
```

## Local Development Setup

### Default Behavior

OpenTelemetry is **disabled by default** in local development to avoid errors when the collector is not accessible.

### Enable for Testing

1. Port forward the collector:
```bash
kubectl port-forward -n observability svc/otel-collector 4317:4317
```

2. Set environment variable:
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317
```

3. Start the API:
```bash
cd p8fs-api
uv run uvicorn src.p8fs_api.main:app --reload --port 8001
```

4. Check logs for:
```
OpenTelemetry initialized
  service=p8fs-api
  version=1.1.37
  namespace=p8fs
  otlp_endpoint=localhost:4317
```

### Disable Tracing

```bash
export P8FS_TRACING_ENABLED=false
```

Or in code:
```python
# In p8fs-cluster config
tracing_enabled: bool = False
```

## Production Deployment

In Kubernetes, OpenTelemetry is automatically enabled:

1. Collector is accessible via cluster DNS
2. No environment variables needed
3. Traces automatically exported
4. Insecure connection used for internal cluster communication

## Testing Instrumentation

### Test Auto-Instrumentation

```bash
# Start API with port forwarding
kubectl port-forward -n observability svc/otel-collector 4317:4317 &
export OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317
cd p8fs-api
uv run uvicorn src.p8fs_api.main:app --reload --port 8001

# Make test requests
curl http://localhost:8001/health
curl http://localhost:8001/api/v1/models
```

Check observability backend (Jaeger/Grafana) for traces.

### Test Agent Instrumentation

Add decorator to agent method:

```python
from p8fs_api.observability import trace_agent

@trace_agent("TestAgent")
async def test_method(self, input: str) -> str:
    return f"Processed: {input}"
```

Call the agent through API and check traces.

## Span Hierarchy Example

```
HTTP POST /api/v1/chat/completions [2.5s]
├─ agent.ChatAgent.process [2.4s]
│  ├─ operation.context_retrieval [0.3s]
│  ├─ llm.openai.gpt-4o [1.8s]
│  └─ operation.response_formatting [0.1s]
└─ (response serialization)
```

## Best Practices

### Do Instrument

✅ Agent entry points (analyze, process, execute)
✅ LLM API calls
✅ External service calls
✅ Database queries (future)
✅ Expensive operations (embeddings, large computations)

### Don't Instrument

❌ Simple utility functions
❌ Private helpers (< 1ms execution)
❌ Pure data transformations
❌ Getters/setters

### Use Meaningful Names

```python
# Good
@trace_agent("DreamAnalyzer")
with trace_operation("vector_search", index="resources", limit=100)

# Bad
@trace_agent("agent1")
with trace_operation("op1")
```

### Add Context as Attributes

```python
with trace_operation("embedding_generation",
                    model="text-embedding-3-small",
                    batch_size=32,
                    text_length=len(texts),
                    provider="openai"):
    embeddings = await generate(texts)
```

## Files Added/Modified

### New Files

- `p8fs-api/src/p8fs_api/observability.py` - Core instrumentation module
- `docs/opentelemetry-instrumentation.md` - Detailed documentation
- `p8fs-api/OBSERVABILITY.md` - This summary

### Modified Files

- `p8fs-api/pyproject.toml` - Added OTEL dependencies
- `p8fs-api/src/p8fs_api/main.py` - Integrated OTEL setup
- `p8fs-cluster/src/p8fs_cluster/config/settings.py` - Added OTEL config

### Dependencies Added

```toml
"opentelemetry-api>=1.21.0",
"opentelemetry-sdk>=1.21.0",
"opentelemetry-instrumentation-fastapi>=0.42b0",
"opentelemetry-exporter-otlp-proto-grpc>=1.21.0",
"opentelemetry-instrumentation-httpx>=0.42b0",
"opentelemetry-instrumentation-logging>=0.42b0",
```

## Next Steps

### Install Dependencies

```bash
cd p8fs-api
uv sync
```

### Update Other Services

Apply same pattern to:
- p8fs-node
- p8fs-auth
- Other services

### Add Database Instrumentation

Future enhancement:
```python
# Will auto-trace database queries
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
Psycopg2Instrumentor().instrument()
```

### Configure Observability Backend

Set up:
- Jaeger for trace visualization
- Grafana Tempo for trace storage
- Prometheus for metrics
- Integration with existing monitoring

## Troubleshooting

### No traces appearing

1. Check collector is running:
```bash
kubectl get pods -n observability | grep otel
```

2. Check API startup logs:
```bash
# Should see: "OpenTelemetry initialized"
```

3. Verify port forwarding (local dev):
```bash
lsof -i :4317
```

4. Check collector logs:
```bash
kubectl logs -n observability deploy/otel-collector
```

### High memory usage

Adjust batch processor settings in `observability.py`:
```python
processor = BatchSpanProcessor(
    otlp_exporter,
    max_queue_size=2048,
    max_export_batch_size=512,
    schedule_delay_millis=5000
)
```

### Performance impact

Expected overhead:
- Auto-instrumentation: ~1-2% latency
- Span creation: ~10-50 microseconds
- Network: Batched every 5 seconds
- Memory: ~5-10MB for buffering

## Support

For issues or questions:
1. Check logs for error messages
2. Verify collector connectivity
3. Review documentation: `docs/opentelemetry-instrumentation.md`
4. Check OTEL Python docs: https://opentelemetry.io/docs/python/
