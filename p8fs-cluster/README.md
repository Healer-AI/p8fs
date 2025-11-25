# P8FS Cluster Module

Cluster management and coordination services for the P8FS smart content management system. this is also a central configuration and environment that is used for logging and env centralisation so can be thought of as a "common" app library. Scheduler is also implemented here and provides access to cluster resources and deployment. The observability (OTEL) metrics etc are handled here.
We also provide the service wrappers or clients for 
- NATs
- TiKB/TiKV
- Seaweed
- Observability 

## Overview

The p8fs-cluster module handles deployment, orchestration, and operational management of P8FS components in Kubernetes environments. It provides administrative tools, health monitoring, metrics collection, and service discovery capabilities. This module also includes Kind cluster setup for local development.

## Architecture

### Components to Port

#### 1. Kubernetes Management (`src/p8fs/cli/commands/admin.py`)
- **Cluster Operations**: kubectl wrapper for cluster management
- **Resource Deployment**: Helm chart management
- **Service Discovery**: Dynamic service endpoint resolution
- **Config Management**: ConfigMap and Secret handling

#### 2. Health Monitoring (`src/p8fs/observability/health.py`)
- **Service Health Checks**: Liveness and readiness probes
- **Dependency Monitoring**: External service availability
- **Circuit Breakers**: Fault tolerance patterns
- **Health Aggregation**: Cluster-wide health status

#### 3. Metrics Collection (`src/p8fs/observability/metrics.py`)
- **Prometheus Integration**: Metric exposition
- **Custom Metrics**: Business-specific measurements
- **Metric Aggregation**: Cluster-wide statistics
- **Alert Rules**: Prometheus alerting configuration

#### 4. Victoria Metrics/ OTEL (`src/p8fs/observability/victoria_client.py`)
- **Long-term Storage**: Metric retention
- **Query Interface**: PromQL compatibility
- **Data Ingestion**: Remote write protocol
- **Retention Policies**: Storage optimization

#### 5. Service Mesh Integration
- **Traffic Management**: Load balancing, retries
- **Security Policies**: mTLS, authorization
- **Observability**: Distributed tracing
- **Traffic Splitting**: Canary deployments

#### 6. KEDA Configuration
- **Autoscaling Rules**: Worker scaling policies
- **Custom Scalers**: P8FS-specific metrics
- **Scale to Zero**: Cost optimization
- **Event-driven Scaling**: NATS queue depth

#### 7. Deployment Tools
- **Helm Charts**: Kubernetes manifests
- **Kind Setup**: Local development cluster
- **GitOps Integration**: ArgoCD/Flux support
- **Multi-environment**: Dev/staging/prod configs

## Refactoring Plan

### Phase 1: Local Development Environment
1. Create Kind cluster configuration
2. Set up local registry for images
3. Configure ingress and load balancer
4. Add persistent volume support

### Phase 2: Kubernetes Resources
1. Design Helm chart structure
2. Create base deployments and services
3. Add ConfigMaps and Secrets
4. Implement RBAC policies

### Phase 3: Monitoring Stack
1. Deploy Prometheus operator
2. Configure service monitors
3. Set up Victoria Metrics
4. Create Grafana dashboards

### Phase 4: Service Mesh
1. Evaluate Istio vs Linkerd
2. Implement traffic policies
3. Configure mTLS
4. Add distributed tracing

### Phase 5: Autoscaling
1. Deploy KEDA operator
2. Create ScaledObject definitions
3. Configure custom metrics
4. Test scaling scenarios

## Testing Strategy

### Unit Tests
- Kubernetes manifest validation
- Helm chart templating tests
- Configuration validation
- Health check logic

### Integration Tests
- Cluster deployment verification
- Service discovery testing
- Metrics collection validation
- Autoscaling behavior

### Chaos Testing
- Pod failure scenarios
- Network partition testing
- Resource exhaustion
- Recovery validation

## Dependencies

### Kubernetes Components
- Kind: Local cluster
- Helm: Package management
- kubectl: Cluster interaction
- KEDA: Autoscaling

### Monitoring Stack
- Prometheus: Metrics collection
- Victoria Metrics: Long-term storage
- Grafana: Visualization
- AlertManager: Alert routing

### Development Tools
- Skaffold: Development workflow
- Tilt: Local development
- k9s: Cluster navigation
- stern: Log aggregation

## Configuration

The p8fs-cluster module provides centralized configuration management for all P8FS services using Pydantic Settings with automatic environment variable loading.

### Core Configuration

```python
from p8fs_cluster import P8FSConfig

# Initialize configuration (loads from environment automatically)
config = P8FSConfig()

# Access configuration values
print(f"Environment: {config.environment}")
print(f"Log Level: {config.log_level}")
print(f"TiKV Endpoints: {config.tikv_endpoints}")
```

### Environment Variables

All configuration uses the `P8FS_` prefix. Here are the available settings:

#### Application Settings
- `P8FS_ENVIRONMENT`: Deployment environment (`development`, `production`, `testing`)
- `P8FS_LOG_LEVEL`: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- `P8FS_LOG_FORMAT`: Log format (`json`, `text`)

#### Database Configuration
- `P8FS_TIKV_ENDPOINTS`: TiKV cluster endpoints (JSON array, default: `["localhost:2379"]`)
- `P8FS_TIDB_HOST`: TiDB database host (default: `localhost`)
- `P8FS_TIDB_PORT`: TiDB database port (default: `4000`)
- `P8FS_TIDB_USER`: TiDB username (default: `root`)
- `P8FS_TIDB_PASSWORD`: TiDB password (default: empty)
- `P8FS_TIDB_DATABASE`: TiDB database name (default: `p8fs`)

#### Message Queue Configuration
- `P8FS_NATS_URL`: NATS server URL (default: `nats://localhost:4222`)
- `P8FS_NATS_USER`: NATS username (default: empty)
- `P8FS_NATS_PASSWORD`: NATS password (default: empty)

#### Storage Configuration
- `P8FS_SEAWEEDFS_MASTER`: SeaweedFS master URL (default: `localhost:9333`)
- `P8FS_SEAWEEDFS_VOLUME`: SeaweedFS volume server (default: `localhost:8080`)
- `P8FS_MAX_FILE_SIZE`: Maximum file size in bytes (default: `100MB`)

#### Machine Learning Configuration
- `P8FS_EMBEDDING_MODEL`: Embedding model name (default: `all-MiniLM-L6-v2`)
- `P8FS_EMBEDDING_DIMENSIONS`: Embedding vector dimensions (default: `384`)
- `P8FS_EMBEDDING_BATCH_SIZE`: Batch size for embeddings (default: `32`)

#### Processing Configuration
- `P8FS_PROCESSING_TIMEOUT`: Processing timeout in seconds (default: `300`)
- `P8FS_MAX_WORKERS`: Maximum worker processes (default: `4`)
- `P8FS_QUEUE_SIZE`: Queue size limit (default: `1000`)

#### OpenTelemetry Configuration
- `P8FS_OTEL_ENDPOINT`: OTEL collector endpoint (default: `http://localhost:4317`)
- `P8FS_OTEL_INSECURE`: Use insecure OTEL connection (default: `true`)
- `P8FS_OTEL_SERVICE_NAME`: Service name for tracing (auto-generated)

#### Kubernetes Configuration
- `P8FS_CLUSTER_NAME`: Kubernetes cluster identifier
- `P8FS_NAMESPACE`: Target namespace (default: `p8fs`)
- `P8FS_HELM_RELEASE`: Helm release name
- `P8FS_INGRESS_DOMAIN`: Base domain for services
- `P8FS_TLS_ENABLED`: Enable TLS for services (default: `false`)
- `P8FS_MONITORING_ENABLED`: Deploy monitoring stack (default: `true`)

### Configuration Methods

#### 1. Environment Variables
```bash
export P8FS_ENVIRONMENT=production
export P8FS_LOG_LEVEL=INFO
export P8FS_TIKV_ENDPOINTS='["tikv-1:2379", "tikv-2:2379", "tikv-3:2379"]'
```

#### 2. .env File
Create a `.env` file in your project root:
```env
P8FS_ENVIRONMENT=development
P8FS_LOG_LEVEL=DEBUG
P8FS_TIKV_ENDPOINTS=["localhost:2379"]
P8FS_NATS_URL=nats://localhost:4222
```

#### 3. Programmatic Configuration
```python
from p8fs_cluster import P8FSConfig

# Override specific values
config = P8FSConfig(
    environment="testing",
    log_level="DEBUG",
    tikv_endpoints=["test-tikv:2379"]
)
```

### Configuration Validation

The configuration system includes automatic validation:

```python
config = P8FSConfig()

# Validate configuration
try:
    config.model_validate(config.model_dump())
    print("Configuration is valid")
except ValidationError as e:
    print(f"Configuration error: {e}")
```

### Environment-Specific Defaults

The configuration provides different defaults based on the environment:

- **Development**: Localhost services, DEBUG logging
- **Testing**: In-memory/mock services where possible
- **Production**: Secure defaults, INFO logging, external services

### Configuration Properties

Access environment-specific properties:

```python
config = P8FSConfig()

if config.is_development:
    # Development-specific logic
    print("Running in development mode")
elif config.is_production:
    # Production-specific logic  
    print("Running in production mode")
elif config.is_testing:
    # Testing-specific logic
    print("Running in test mode")
```

## Centralized Logging

The p8fs-cluster module provides centralized logging using Loguru with structured logging, correlation IDs, and context management.

### Basic Logging Setup

```python
from p8fs_cluster import setup_logging, get_logger

# Setup logging for the entire application
setup_logging(level="INFO", format_type="json")

# Get a logger for your module
logger = get_logger("my.service")

# Log messages
logger.info("Service started", service="my-service", port=8000)
logger.warning("High memory usage", memory_mb=512, threshold=400)
logger.error("Database connection failed", error="timeout")
```

### Correlation ID Support

Use correlation IDs to track requests across services:

```python
from p8fs_cluster.logging.setup import with_correlation_id

# In a web handler or service method
correlation_id = "req-123-456"

with with_correlation_id(correlation_id, service="api") as logger:
    logger.info("Processing request", user_id=123)
    
    # Call other services - they'll inherit the correlation ID
    result = await process_data()
    
    logger.info("Request completed", result_count=len(result))
```

### Structured Logging

All logs include structured fields for easy querying:

```python
logger.info(
    "User action completed",
    user_id=123,
    action="upload",
    file_size=1024000,
    processing_time_ms=250,
    status="success"
)
```

### Service-Specific Loggers

Each P8FS service gets its own logger context:

```python
# In p8fs-api
from p8fs_cluster import get_logger
logger = get_logger("p8fs.api")

# In p8fs  
from p8fs_cluster import get_logger
logger = get_logger("p8fs.core")

# In p8fs-node
from p8fs_cluster import get_logger
logger = get_logger("p8fs.node")
```

### Log Formats

#### JSON Format (Production)
```json
{
  "timestamp": "2024-01-15T10:30:00.123Z",
  "level": "INFO",
  "logger": "p8fs.api",
  "message": "Request processed",
  "correlation_id": "req-123-456",
  "service": "api",
  "user_id": 123,
  "processing_time_ms": 45
}
```

#### Text Format (Development)
```
2024-01-15 10:30:00.123 | INFO | p8fs.api | Request processed | correlation_id=req-123-456 service=api user_id=123
```

### Configuration Options

Logging can be configured via environment variables:

```bash
# Log level
export P8FS_LOG_LEVEL=INFO

# Log format (json or text)
export P8FS_LOG_FORMAT=json

# Enable/disable logging to file
export P8FS_LOG_TO_FILE=true
export P8FS_LOG_FILE_PATH=/var/log/p8fs/app.log

# Log rotation
export P8FS_LOG_MAX_SIZE=100MB
export P8FS_LOG_RETENTION_DAYS=30
```

### Advanced Usage

#### Custom Log Processors

```python
from p8fs_cluster.logging.setup import setup_logging

# Custom log processor
def add_hostname(record):
    import socket
    record["hostname"] = socket.gethostname()
    return record

# Setup with custom processor  
setup_logging(level="INFO", processors=[add_hostname])
```

#### Performance Logging

```python
from p8fs_cluster.logging.setup import log_performance

@log_performance("file_processing")
async def process_file(file_path: str):
    # Your file processing logic
    await heavy_processing(file_path)
    return result
```

#### Error Context

```python
try:
    result = await risky_operation()
except Exception as e:
    logger.error(
        "Operation failed",
        operation="risky_operation",
        error_type=type(e).__name__,
        error_message=str(e),
        traceback=True  # Include full traceback
    )
    raise
```

### Integration with Other Services

#### FastAPI Integration

```python
from fastapi import FastAPI, Request
from p8fs_cluster.logging.setup import with_correlation_id
import uuid

app = FastAPI()

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    
    with with_correlation_id(correlation_id, service="api") as logger:
        logger.info("Request started", method=request.method, url=str(request.url))
        
        response = await call_next(request)
        
        logger.info("Request completed", status_code=response.status_code)
        response.headers["X-Correlation-ID"] = correlation_id
        
        return response
```

#### Background Task Logging

```python
from p8fs_cluster import get_logger
import asyncio

logger = get_logger("p8fs.worker")

async def background_task(task_id: str):
    with with_correlation_id(task_id, service="worker") as task_logger:
        task_logger.info("Task started", task_type="background")
        
        try:
            # Your task logic
            await process_task()
            task_logger.info("Task completed successfully")
        except Exception as e:
            task_logger.error("Task failed", error=str(e))
            raise
```

## Usage Examples

### Complete Service Setup

Here's how to set up p8fs-cluster in your service:

```python
# main.py
from p8fs_cluster import P8FSConfig, setup_logging, get_logger

# Initialize configuration and logging
config = P8FSConfig()
setup_logging(level=config.log_level, format_type="json" if config.is_production else "text")
logger = get_logger(__name__)

# Use configuration throughout your service
logger.info("Service starting", 
           environment=config.environment,
           tikv_endpoints=config.tikv_endpoints,
           nats_url=config.nats_url)

# Your service logic here
if config.is_development:
    logger.debug("Development mode enabled")
    
async def main():
    logger.info("Service ready")
    # Your async service logic
```

### Multi-Service Communication

Track requests across multiple P8FS services:

```python
# Service A (p8fs-api)
from p8fs_cluster.logging.setup import with_correlation_id
import uuid

async def handle_request(request):
    correlation_id = str(uuid.uuid4())
    
    with with_correlation_id(correlation_id, service="api") as logger:
        logger.info("API request received", endpoint="/upload")
        
        # Call p8fs service
        result = await core_client.process_file(file_data, correlation_id)
        
        logger.info("API request completed", result_id=result.id)
        return result

# Service B (p8fs) 
async def process_file(file_data, correlation_id):
    with with_correlation_id(correlation_id, service="core") as logger:
        logger.info("File processing started", file_size=len(file_data))
        
        # Process the file
        result = await heavy_processing(file_data)
        
        logger.info("File processing completed", processing_time_ms=result.time)
        return result
```

### Environment-Specific Configuration

```python
from p8fs_cluster import P8FSConfig

config = P8FSConfig()

# Database connection based on environment
if config.is_development:
    # Use local TiKV/TiDB
    db_config = {
        "host": "localhost",
        "port": 4000,
        "endpoints": config.tikv_endpoints
    }
elif config.is_production:
    # Use production cluster
    db_config = {
        "host": config.tidb_host,
        "port": config.tidb_port,
        "endpoints": config.tikv_endpoints,
        "ssl": True
    }

# Storage configuration
storage_config = {
    "master": config.seaweedfs_master,
    "volume": config.seaweedfs_volume,
    "max_size": config.max_file_size
}

logger.info("Service configured", 
           environment=config.environment,
           database_endpoints=len(config.tikv_endpoints),
           storage_master=config.seaweedfs_master)
```

### Docker Compose Integration

```yaml
# docker-compose.yml
version: '3.8'
services:
  p8fs-api:
    build: ./p8fs-api
    environment:
      - P8FS_ENVIRONMENT=development
      - P8FS_LOG_LEVEL=DEBUG
      - P8FS_LOG_FORMAT=json
      - P8FS_TIKV_ENDPOINTS=["tikv:2379"]
      - P8FS_NATS_URL=nats://nats:4222
      - P8FS_SEAWEEDFS_MASTER=seaweedfs:9333
    depends_on:
      - tikv
      - nats
      - seaweedfs

  p8fs:
    build: ./p8fs
    environment:
      - P8FS_ENVIRONMENT=development
      - P8FS_LOG_LEVEL=DEBUG
      - P8FS_TIKV_ENDPOINTS=["tikv:2379"]
      - P8FS_NATS_URL=nats://nats:4222
```

## Deployment Architecture

### Development Environment
```yaml
kind-cluster:
  nodes: 3
  ingress: nginx
  registry: local
  storage: hostPath
  monitoring: enabled
```

### Production Architecture
```yaml
production:
  nodes: 10+
  zones: multi-az
  ingress: cloud-lb
  storage: cloud-volumes
  monitoring: full-stack
  backup: enabled
```

## Kind Cluster Setup

### Local Development
1. **Cluster Creation**: Multi-node setup
2. **Registry**: Local image registry
3. **Ingress**: NGINX controller
4. **Storage**: Local persistent volumes
5. **Monitoring**: Minimal Prometheus

### Configuration Files
- `kind-config.yaml`: Cluster definition
- `values-dev.yaml`: Development values
- `values-prod.yaml`: Production values

## Monitoring Strategy

### Service Level Objectives
- **Availability**: 99.9% uptime
- **Latency**: p99 < 500ms
- **Error Rate**: < 0.1%
- **Throughput**: 1000 req/s

### Key Metrics
- Request rate and latency
- Error rates by service
- Resource utilization
- Queue depths
- Processing times

### Dashboards
- Cluster overview
- Service health
- Worker performance
- Storage metrics
- Cost analysis

## Security Configuration

### Network Policies
- Service-to-service communication
- Ingress restrictions
- Egress controls
- Pod security policies

### RBAC Configuration
- Service accounts
- Role definitions
- ClusterRole bindings
- Security contexts

## Operational Procedures

### Deployment Process
1. Build and push images
2. Update Helm values
3. Deploy with Helm
4. Verify health checks
5. Monitor metrics

### Backup Strategy
- Database backups
- Configuration backups
- Volume snapshots
- Disaster recovery

### Maintenance Tasks
- Certificate rotation
- Secret updates
- Version upgrades
- Capacity planning