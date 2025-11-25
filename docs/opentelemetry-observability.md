# OpenTelemetry Observability for P8FS

## Overview

Comprehensive OpenTelemetry instrumentation across all P8FS services:
- **FastAPI API** - HTTP endpoint tracing
- **Tiered Router** - Queue routing with distributed tracing
- **Storage Workers** - File processing with end-to-end tracing
- **LLM Agents** - AI agent execution tracing with OpenInference conventions

**Key Feature**: **Distributed tracing across services** - trace a single file upload from API → Router → Queue → Worker → Processing.

**New**: **Agent Tracing** - Full instrumentation of MemoryProxy agent execution following percolate patterns with OpenInference span kinds for Phoenix compatibility.

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────┐      ┌───────────────┐
│   FastAPI   │ ───> │ Tiered Router    │ ───> │ NATS Queue  │ ───> │ Storage Worker│
│   (API)     │      │ (Queue Routing)  │      │             │      │ (Processing)  │
└─────────────┘      └──────────────────┘      └─────────────┘      └───────────────┘
      │                      │                        │                      │
      └──────────────────────┴────────────────────────┴──────────────────────┘
                               Single Trace ID
                          (via trace context propagation)
```

## Configuration

### Environment Variables

```bash
# Enable/disable tracing
export P8FS_TRACING_ENABLED=true

# OTLP gRPC endpoint (cluster)
export OTEL_EXPORTER_OTLP_ENDPOINT=otel-collector.observability.svc.cluster.local:4317

# Local development (with port-forward)
export OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317

# Service metadata
export P8FS_DEPLOYMENT_ENVIRONMENT=production
export OTEL_SERVICE_NAME=p8fs-api
export OTEL_SERVICE_VERSION=1.1.37
export OTEL_SERVICE_NAMESPACE=p8fs
```

### Local Development Setup

```bash
# 1. Port-forward to OTEL collector
kubectl port-forward -n observability svc/otel-collector 4317:4317

# 2. Enable tracing
export P8FS_TRACING_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317

# 3. Start services
uv run uvicorn src.p8fs_api.main:app --reload  # API
uv run python -m p8fs.cli storage-worker --queue-size small  # Worker
```

## FastAPI API Instrumentation

### File: `p8fs-api/src/p8fs_api/observability.py`

### Setup

```python
from p8fs_api.observability import setup_observability, instrument_fastapi

# Initialize tracing
setup_observability(service_name="p8fs-api")

# Instrument FastAPI app
app = FastAPI()
instrument_fastapi(app)
```

### Auto-Instrumentation

FastAPI auto-instrumentation provides:
- HTTP method and route
- Status codes
- Request duration
- Exception details
- Query parameters and headers

### Manual Tracing

#### Agent Operations

```python
from p8fs_api.observability import trace_agent

@trace_agent("DreamAgent")
async def analyze(self, content: str) -> dict:
    # Traced automatically with agent metadata
    return await process(content)
```

**Span attributes**:
- `agent.name` - Agent name
- `agent.method` - Method name
- `agent.status` - "success" or "error"
- `agent.args_count` - Number of arguments

#### LLM Calls

```python
from p8fs_api.observability import trace_llm_call

@trace_llm_call(model="gpt-4", provider="openai", temperature=0.7)
async def generate_response(prompt: str) -> str:
    return await client.chat.completions.create(...)
```

**Span attributes**:
- `llm.model` - Model name
- `llm.provider` - Provider name
- `llm.temperature` - Sampling temperature
- `llm.max_tokens` - Max tokens

#### Custom Operations

```python
from p8fs_api.observability import trace_operation

with trace_operation("embedding_generation", model="text-embedding-3-small"):
    embeddings = await generate_embeddings(text)
```

## Agent Instrumentation

### Files
- `p8fs/src/p8fs/utils/otel_utils.py` - Agent tracing utilities
- `p8fs/src/p8fs/utils/span_kinds.py` - OpenInference span kinds
- `p8fs/src/p8fs/services/llm/memory_proxy.py` - Instrumented agent

### Overview

Agent tracing instruments the `MemoryProxy.stream()` method to capture complete agent execution flows including:
- Agent initialization and context setup
- Agentic loop iterations
- Tool/function calls
- LLM API interactions
- Error handling and completion

The implementation follows percolate patterns with non-intrusive utility functions and OpenInference semantic conventions for Phoenix compatibility.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ agent.stream (AGENT)                                        │
│   trace_id: 4bf92f3577b34da6a3ce929d0e0e4736               │
│   span_id: a3ce929d0e0e4736                                 │
│                                                              │
│   Attributes:                                                │
│   - openinference.span.kind: AGENT                          │
│   - agent.name: SimpleAgent                                 │
│   - agent.type: memory_proxy                                │
│   - user.id: test-user                                      │
│   - session.id: conversation-123                            │
│                                                              │
│   └─> (Agent execution with agentic loop, tool calls, etc) │
└─────────────────────────────────────────────────────────────┘
```

### Utility Functions

#### `p8fs/src/p8fs/utils/otel_utils.py`

Core utilities for agent instrumentation:

```python
from p8fs.utils.otel_utils import (
    get_tracer,
    set_agent_attributes,
    set_llm_attributes,
    set_generation_attributes,
    get_current_span_id_as_hex,
    get_current_trace_id_as_hex,
    mark_span_as_error,
)

# Get tracer
tracer = get_tracer(__name__)

# Set agent metadata
with tracer.start_as_current_span("agent.execute") as span:
    set_agent_attributes(
        span,
        agent_name="WeatherAgent",
        agent_type="tool_calling",
        user_id="user-123",
        session_id="session-456"
    )

    # Capture trace IDs for session correlation
    span_id = get_current_span_id_as_hex()
    trace_id = get_current_trace_id_as_hex()
```

**Key Features**:
- All functions are no-ops if span doesn't exist (safe to call anywhere)
- Follows GenAI semantic conventions (`gen_ai.*` attributes)
- Hex format IDs for session metadata correlation
- Error handling with proper span status

#### `p8fs/src/p8fs/utils/span_kinds.py`

OpenInference span kinds for Phoenix:

```python
from p8fs.utils.span_kinds import OpenInferenceSpanKind, set_span_kind

# Available span kinds
OpenInferenceSpanKind.AGENT      # Agent execution
OpenInferenceSpanKind.LLM        # Language model calls
OpenInferenceSpanKind.TOOL       # Tool/function execution
OpenInferenceSpanKind.CHAIN      # Chain of operations
OpenInferenceSpanKind.RETRIEVER  # RAG retrieval
OpenInferenceSpanKind.EMBEDDING  # Embedding generation

# Set span kind
set_span_kind(span, OpenInferenceSpanKind.AGENT)
```

**Purpose**: Phoenix and other observability tools use these kinds to categorize and visualize AI operations.

### MemoryProxy Instrumentation

The `MemoryProxy.stream()` method is instrumented to capture complete agent execution:

```python
async def stream(self, question: str, context: CallingContext | None = None, ...):
    """Agent execution with tracing."""
    tracer = get_tracer(__name__)

    with tracer.start_as_current_span("agent.stream", kind=SpanKind.CLIENT) as span:
        # Set agent kind for Phoenix
        set_span_kind(span, OpenInferenceSpanKind.AGENT)

        # Set agent attributes
        agent_name = self._model_context.get_model_full_name() if self._model_context else "MemoryProxy"
        set_agent_attributes(
            span,
            agent_name=agent_name,
            agent_type="memory_proxy",
            user_id=getattr(context, 'user_id', None),
            session_id=getattr(context, 'conversation_id', None),
        )

        # Agent execution (agentic loop, tool calls, etc)
        # Span automatically closed on exit
```

**Attributes Captured**:
- `openinference.span.kind` - "AGENT" for Phoenix categorization
- `agent.name` - Agent model name (e.g., "SimpleAgent", "MemoryProxy")
- `agent.type` - Agent type ("memory_proxy")
- `user.id` - User identifier (if available)
- `session.id` - Conversation/session identifier (if available)

**Trace Context**: Span/trace IDs are captured in `context.metadata` for downstream session correlation.

### Testing

Integration test with tool calls:

```python
# File: p8fs/tests/integration/test_agent_tracing.py

@pytest.mark.integration
async def test_agent_with_tool_call_generates_traces():
    """Test agent execution with tool calls generates OTEL traces."""

    # Create agent with tool
    proxy = MemoryProxy(SimpleAgent)

    # Execute with tracing
    context = CallingContext(
        model="gpt-4o-mini",
        tenant_id="test-tenant",
        user_id="test-user"
    )

    async for chunk in proxy.stream("What's the weather?", context):
        # Process streaming response
        if chunk.get("type") == "function_call_complete":
            print(f"Tool called: {chunk.get('function_name')}")

    # Traces exported to collector
    # Check: kubectl logs -n observability deployment/otel-collector
```

**Run Test**:
```bash
# Start port-forward
kubectl port-forward -n observability svc/otel-collector 4317:4317

# Run test
OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317 \
uv run python tests/integration/test_agent_tracing.py
```

**Verification**:
```bash
# Check collector logs for trace exports
kubectl logs -n observability deployment/otel-collector --tail=20 | grep TracesExporter

# Expected output:
# 2025-11-06T18:25:17.750Z info TracesExporter {"resource spans": 1, "spans": 2}
```

### Span Attributes Reference

**Agent Execution Span** (`agent.stream`):
- `span.name` - "agent.stream"
- `span.kind` - CLIENT
- `openinference.span.kind` - "AGENT"
- `agent.name` - Agent model name
- `agent.type` - "memory_proxy"
- `user.id` - User identifier
- `session.id` - Session/conversation ID

**Context Metadata** (for downstream correlation):
- `context.metadata.otel_span_id` - Current span ID (hex)
- `context.metadata.otel_trace_id` - Current trace ID (hex)

### Best Practices

1. **Non-intrusive**: Use utility functions that are no-ops if tracing disabled
2. **Context managers**: Use `with` statements for automatic span lifecycle
3. **Graceful degradation**: Agents work with or without OTEL
4. **Attribute selection**: Avoid high-cardinality values (no unique IDs in span attributes)
5. **Error handling**: Spans marked as errors but don't interfere with agent flow

### Integration with Other Services

Agent traces can be correlated with:
- **API traces**: Via trace context propagation through HTTP headers
- **Session metadata**: Via span/trace IDs stored in context
- **LLM calls**: Via nested LLM spans (future enhancement)
- **Tool executions**: Via tool call spans (future enhancement)

### Future Enhancements

1. **LLM call instrumentation**: Capture individual LLM API calls with token usage
2. **Tool execution spans**: Separate spans for each tool/function call
3. **Prompt/completion capture**: Store prompts and responses in span events
4. **Token usage tracking**: Capture input/output tokens with GenAI conventions
5. **Streaming chunk metrics**: Track streaming performance

## Worker Instrumentation

### File: `p8fs/src/p8fs/workers/observability.py`

### Setup

```python
from p8fs.workers.observability import setup_worker_observability

# Initialize for router
setup_worker_observability("p8fs-tiered-router")

# Initialize for worker
setup_worker_observability("p8fs-storage-worker-small")
```

### Distributed Tracing

The key feature enabling end-to-end tracing across services.

#### Router: Inject Trace Context

```python
from p8fs.workers.observability import inject_trace_context, get_tracer

tracer = get_tracer()

async def route_message(msg):
    with tracer.start_as_current_span("router.route_message") as span:
        # Add attributes
        span.set_attribute("file.name", file_name)
        span.set_attribute("file.size", file_size)

        # CRITICAL: Inject trace context into headers
        headers = inject_trace_context()

        # Publish with trace context
        await nats.publish(subject, data, headers=headers)
```

#### Worker: Continue Trace

```python
from p8fs.workers.observability import continue_trace

async def process_message(msg):
    # Extract trace context from headers
    headers = msg.headers

    # Continue the distributed trace
    with continue_trace(headers, "worker.process") as span:
        # This span is a child of router span
        # Same trace_id, different span_id
        span.set_attribute("processing.duration", duration)
        await process_file(data)
```

### Trace Context Propagation

**How it works**:

1. **Router creates trace**:
   - New span with unique trace_id
   - Inject `traceparent` header: `00-<trace-id>-<span-id>-01`

2. **NATS preserves headers**:
   - Headers travel with message through queue

3. **Worker continues trace**:
   - Extract `traceparent` from headers
   - Create child span with same trace_id
   - New span_id for worker operations

**Result**: Single trace spanning multiple services and queues.

### File Processing Tracing

```python
from p8fs.workers.observability import trace_file_processing

with trace_file_processing(
    file_name="document.pdf",
    file_size=5242880,
    tenant_id="tenant-123",
    queue_name="small"
) as span:
    result = await process_file_content(file)
    span.set_attribute("chunks_created", len(result))
```

## Metrics

### Router Metrics

**Queue Monitoring**:
- `nats.queue.size` - Messages in NATS queue (gauge)
- `router.sends_queue.size` - Pending router sends (gauge)

**Routing Operations**:
- `router.messages.routed` - Total routed messages (counter)
  - Labels: `queue_tier`, `tenant_id`
- `router.errors` - Total routing errors (counter)
  - Labels: `error_type`
- `router.routing.duration` - Routing time (histogram)
  - Labels: `queue_tier`

### Worker Metrics

**Processing Operations**:
- `worker.files.processed` - Total files processed (counter)
  - Labels: `queue`, `tenant_id`, `event_type`
- `worker.processing.errors` - Total processing errors (counter)
  - Labels: `queue`, `error_type`
- `worker.processing.duration` - Processing time (histogram)
  - Labels: `queue`
- `worker.file_size.processed` - File size distribution (histogram)
  - Labels: `queue`

## Span Attributes

### Common Attributes

All spans include:
- `status` - "success" or "error"
- `processing.duration` - Duration in seconds

### File Processing Attributes

- `file.name` - File name
- `file.size` - Size in bytes
- `file.size_mb` - Size in megabytes
- `tenant.id` - Tenant identifier

### Queue Attributes

- `queue.name` - Queue name (small/medium/large)
- `queue.target` - Target NATS subject
- `queue.tier` - Queue tier

### Error Attributes

- `error.type` - Exception class name
- `error.message` - Exception message
- Full exception stack trace via `span.record_exception(e)`

## Implementation Details

### Tiered Router

**File**: `p8fs/src/p8fs/workers/queues/tiered_router.py`

**Key Changes**:

```python
# Initialization
def __init__(self, worker_id: str = None):
    setup_worker_observability(f"p8fs-tiered-router-{self.instance_id}")
    self.tracer = get_tracer()
    self.metrics = RouterMetrics()

# Message processing with tracing
async def _process_single_message(self, msg) -> None:
    with self.tracer.start_as_current_span("router.route_message") as span:
        # Add attributes
        span.set_attribute("file.name", file_name)
        span.set_attribute("file.size", file_size)
        span.set_attribute("queue.target", target_subject)

        # Inject trace context
        headers = inject_trace_context()

        # Publish with headers
        await self.client._js.publish(subject, data, headers=headers)

        # Record metrics
        self.metrics.messages_routed.add(1, {"queue_tier": tier})
        self.metrics.routing_duration.record(duration, {"queue_tier": tier})
```

### Storage Worker

**File**: `p8fs/src/p8fs/workers/queues/storage_worker.py`

**Key Changes**:

```python
# Initialization
def __init__(self, queue_size: QueueSize, ...):
    setup_worker_observability(f"p8fs-storage-worker-{queue_size.value}")
    self.tracer = get_tracer()
    self.otel_metrics = WorkerMetrics()

# Message processing with trace continuation
async def _process_single_message(self, msg) -> None:
    # Extract trace context
    headers = msg.headers if hasattr(msg, 'headers') else None

    # Continue distributed trace
    with continue_trace(headers, f"worker.{self.queue_size.value}.process_message") as span:
        # Parse event
        event = StorageEvent.from_raw_event(data)

        # Add attributes
        span.set_attribute("file.name", event.path)
        span.set_attribute("file.size", event.metadata.file_size)
        span.set_attribute("tenant.id", event.tenant_id)

        # Detailed file processing
        with trace_file_processing(name, size, tenant, queue) as file_span:
            await self.storage_worker.process_file(...)

            # Record metrics
            self.otel_metrics.files_processed.add(1)
            self.otel_metrics.processing_duration.record(duration)
```

## Visualization Example

### End-to-End Trace in Jaeger

```
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
Duration: 2600ms

│
├─ router.route_message (100ms)
│  │ file.name: "document.pdf"
│  │ file.size: 5242880
│  │ queue.target: "p8fs.storage.events.small"
│  │ status: "success"
│  │
│  └─ worker.small.process_message (2500ms)
│     │ file.name: "document.pdf"
│     │ tenant.id: "tenant-123"
│     │ queue.name: "small"
│     │
│     └─ file.process (2450ms)
│        │ operation: "process_file"
│        │ processing.duration: 2.45
│        │ chunks_created: 42
│        │ status: "success"
```

## Query Examples

### Jaeger / Grafana Tempo

**Find slow file processing**:
```
file.name="document.pdf" AND span.duration > 5s
```

**Find all errors**:
```
status="error"
```

**Files from specific tenant**:
```
tenant.id="tenant-123"
```

**Large file processing**:
```
file.size_mb > 100
```

### Prometheus / Grafana

**Queue depth over time**:
```promql
nats_queue_size{queue="main"}
```

**Routing rate (messages/sec)**:
```promql
rate(router_messages_routed_total[5m])
```

**P95 processing duration**:
```promql
histogram_quantile(0.95, rate(worker_processing_duration_bucket[5m]))
```

**Error rate by queue**:
```promql
rate(worker_processing_errors_total[5m])
```

**Files processed by size tier**:
```promql
sum by (queue) (rate(worker_files_processed_total[5m]))
```

## Grafana Dashboard Example

### Worker Performance Dashboard

```yaml
panels:
  - title: "Queue Depth"
    query: nats_queue_size{queue=~".*"}
    type: graph

  - title: "Processing Rate"
    query: rate(worker_files_processed_total[5m])
    type: graph

  - title: "P95 Latency by Queue"
    query: |
      histogram_quantile(0.95,
        rate(worker_processing_duration_bucket[5m])
      )
    type: graph

  - title: "Error Rate"
    query: rate(worker_processing_errors_total[5m])
    type: graph

  - title: "File Size Distribution"
    query: |
      histogram_quantile(0.50,
        rate(worker_file_size_processed_bucket[5m])
      )
    type: graph
```

## Use Cases

### Debugging Failed File Upload

**Scenario**: File upload failed, need to find why.

**Steps**:
1. Search Jaeger for filename: `file.name="problem.pdf"`
2. Filter by error: `status="error"`
3. View trace timeline to see where it failed
4. Check span attributes for error details
5. Review exception stack trace

**Result**: Identify exact failure point (router, queue, or worker) with full context.

### Performance Optimization

**Scenario**: Files taking too long to process.

**Steps**:
1. Query P99 latency: `histogram_quantile(0.99, processing_duration)`
2. Filter by queue tier to identify bottleneck
3. Find slowest traces in Jaeger
4. Analyze span timings to identify slow operations
5. Check if issue is I/O, CPU, or external dependency

**Result**: Pinpoint slow operations for optimization.

### Capacity Planning

**Scenario**: Plan scaling for increased load.

**Steps**:
1. Monitor queue depths over time
2. Track processing rates per queue tier
3. Analyze file size distributions
4. Calculate throughput vs. latency trade-offs
5. Identify queue saturation points

**Result**: Data-driven scaling decisions.

## Best Practices

### Adding New Tracing

1. **Use context managers** for automatic cleanup:
   ```python
   with trace_operation("my_operation") as span:
       result = await do_work()
       span.set_attribute("result_count", len(result))
   ```

2. **Add meaningful attributes**:
   ```python
   span.set_attribute("chunks_created", 42)
   span.set_attribute("model", "text-embedding-3-small")
   ```

3. **Record exceptions properly**:
   ```python
   except Exception as e:
       span.set_attribute("error.type", type(e).__name__)
       span.record_exception(e)
       raise
   ```

4. **Avoid high-cardinality labels**:
   ```python
   # ✅ Good
   span.set_attribute("queue.tier", "small")

   # ❌ Bad - too many unique values
   span.set_attribute("file.hash", sha256_hash)
   ```

### Performance Considerations

- **Sampling**: Use head-based sampling for high traffic
- **Batch export**: Spans batched every 5s (configurable)
- **Minimal overhead**: ~1-2ms per span
- **Async export**: No blocking on trace export

## Troubleshooting

### Traces Not Appearing

1. **Check OTEL collector connectivity**:
   ```bash
   telnet otel-collector.observability.svc.cluster.local 4317
   ```

2. **Verify tracing enabled**:
   ```python
   from p8fs_cluster.config.settings import config
   print(f"Tracing enabled: {config.tracing_enabled}")
   print(f"OTLP endpoint: {config.otel_exporter_otlp_endpoint}")
   ```

3. **Check worker logs**:
   ```bash
   kubectl logs deploy/storage-worker-small | grep -i "opentelemetry"
   ```

4. **Test local connectivity**:
   ```bash
   curl -v http://otel-collector:4318/v1/traces
   ```

### Distributed Traces Not Linking

1. **Verify headers are passed**:
   - Check NATS message has `traceparent` header
   - Log headers in router and worker

2. **Check trace context format**:
   ```
   traceparent: 00-<trace-id>-<span-id>-01
   ```

3. **Ensure same trace provider**:
   - Router and worker must use same OTel setup
   - Both must use TraceContextTextMapPropagator

### High Cardinality Warnings

If you see metric cardinality issues:

1. **Limit tenant_id usage**: Sample or aggregate
2. **Avoid unique IDs in labels**: Use exemplars instead
3. **Review metric labels**: Remove high-cardinality dimensions

## Related Files

### Observability Modules

- `p8fs-api/src/p8fs_api/observability.py` - API instrumentation
- `p8fs/src/p8fs/workers/observability.py` - Worker instrumentation
- `p8fs/src/p8fs/utils/otel_utils.py` - Agent tracing utilities
- `p8fs/src/p8fs/utils/span_kinds.py` - OpenInference span kinds

### Instrumented Services

- `p8fs/src/p8fs/workers/queues/tiered_router.py` - Router with tracing
- `p8fs/src/p8fs/workers/queues/storage_worker.py` - Worker with tracing
- `p8fs/src/p8fs/services/llm/memory_proxy.py` - Agent with tracing

### Tests

- `p8fs/tests/integration/test_agent_tracing.py` - Agent tracing integration test

### Configuration

- `p8fs-cluster/src/p8fs_cluster/config/settings.py` - Centralized config

## Future Enhancements

### Planned

1. **Auto-instrumentation for database queries**
2. **SeaweedFS S3 operation tracing**
3. **SLO tracking and alerting**
4. **Custom trace sampling rules**
5. **Automatic anomaly detection**

### Integration Opportunities

- Link API request IDs to worker traces
- Correlate user actions with backend processing
- Track LLM token usage in spans
- Add business metrics (cost per operation)
