# P8FS Queue Workers - Execution Guide

**Note** we keep the Seaweed rGRPC and tasks size queue routers here but the docker image they run on should support not need heavy deps - buts it easier to keep the code in one place
use the minimial lib install and test that it does not load anything it should

This document provides execution instructions for the P8FS queue workers and SeaweedFS event processing system.

## ✅ **Fully Executable Components**

### 1. **Queue Management CLI**

The main queue management interface with comprehensive tooling:

```bash
# Access all queue management tools
python -m p8fs.workers.queues.cli --help

# Setup streams and consumers
python -m p8fs.workers.queues.cli setup

# Show status of all queues
python -m p8fs.workers.queues.cli status

# Start tiered storage router
python -m p8fs.workers.queues.cli router start

# Start storage workers
python -m p8fs.workers.queues.cli worker start --tenant-id my-tenant

# Show current configuration
python -m p8fs.workers.queues.cli config-info
```

### 2. **SeaweedFS Event Processing**

Real-time event processing from SeaweedFS storage:

#### **Via Main CLI (Recommended)**
```bash
# Start gRPC subscriber (primary method)
python -m p8fs.workers.queues.cli seaweedfs-events grpc

# Start HTTP poller (fallback method)  
python -m p8fs.workers.queues.cli seaweedfs-events http

# Capture events for debugging
python -m p8fs.workers.queues.cli seaweedfs-events capture

# Show SeaweedFS configuration
python -m p8fs.workers.queues.cli seaweedfs-events config
```

#### **Direct Execution**
```bash
# Direct execution of SeaweedFS events CLI
python -m p8fs.workers.queues.seaweedfs_events grpc
python -m p8fs.workers.queues.seaweedfs_events http
python -m p8fs.workers.queues.seaweedfs_events capture
```

#### **With Custom Configuration**
```bash
# gRPC subscriber with custom settings
python -m p8fs.workers.queues.cli seaweedfs-events grpc \
  --filer-host seaweedfs-filer.example.com \
  --filer-port 18888 \
  --path-prefix "/buckets/" \
  --debug

# HTTP poller with custom polling
python -m p8fs.workers.queues.cli seaweedfs-events http \
  --filer-host seaweedfs-filer.example.com \
  --filer-port 8888 \
  --poll-interval 10.0 \
  --debug

# Event capturer with custom output
python -m p8fs.workers.queues.cli seaweedfs-events capture \
  --output-dir ./debug-events \
  --client-name debug-capturer \
  --debug
```

## 🔧 **Configuration**

### **Environment Variables**

All services support configuration via environment variables:

#### **NATS Configuration**
- `NATS_URL`: NATS server URL (default: `nats://localhost:4222`)

#### **SeaweedFS Configuration**  
- `SEAWEEDFS_FILER_HOST`: Filer hostname (default: `localhost`)
- `SEAWEEDFS_FILER_GRPC_PORT`: gRPC port (default: `18888`)
- `SEAWEEDFS_FILER_HTTP_PORT`: HTTP port (default: `8888`)
- `WATCH_PATH_PREFIX`: Path prefix to monitor (default: `/buckets/`)

#### **Kubernetes Detection**
- `KUBERNETES_SERVICE_HOST`: Auto-detected for Kubernetes deployments
  - Automatically sets SeaweedFS host to `seaweedfs-filer.p8fs.svc.cluster.local`
  - Automatically sets NATS URL to `nats://nats.p8fs.svc.cluster.local:4222`

### **Configuration Examples**

#### **Local Development**
```bash
export SEAWEEDFS_FILER_HOST=localhost
export SEAWEEDFS_FILER_GRPC_PORT=18888
export NATS_URL=nats://localhost:4222
export WATCH_PATH_PREFIX="/buckets/"
```

#### **Production/Kubernetes**
```bash
export SEAWEEDFS_FILER_HOST=seaweedfs-filer.p8fs.svc.cluster.local
export SEAWEEDFS_FILER_GRPC_PORT=18888
export NATS_URL=nats://nats.p8fs.svc.cluster.local:4222
export WATCH_PATH_PREFIX="/buckets/"
```

## 🏗️ **Architecture Overview**

### **Complete Event Flow**
```
SeaweedFS → gRPC Events → NATS Stream → Tiered Router → Size-Specific Queues → Storage Workers
```

### **Components**

1. **SeaweedFS gRPC Subscriber**: Captures real-time file system events
2. **Tiered Storage Router**: Routes events based on file size (SMALL/MEDIUM/LARGE)
3. **Storage Event Workers**: Process files and create searchable resources
4. **NATS JetStream**: Reliable message queuing with persistence

### **Queue Tiers**

- **SMALL**: 0-100MB files (high concurrency)
- **MEDIUM**: 100MB-1GB files (moderate concurrency)  
- **LARGE**: 1GB+ files (low concurrency, longer timeouts)

## 🚀 **Production Deployment**

### **Recommended Setup**

1. **Start SeaweedFS Event Subscriber**
   ```bash
   python -m p8fs.workers.queues.cli seaweedfs-events grpc
   ```

2. **Start Tiered Router** (separate process)
   ```bash
   python -m p8fs.workers.queues.cli router start
   ```

3. **Start Storage Workers** (separate processes per tenant)
   ```bash
   python -m p8fs.workers.queues.cli worker start --tenant-id tenant-1
   python -m p8fs.workers.queues.cli worker start --tenant-id tenant-2
   ```

### **Health Monitoring**

```bash
# Check queue status
python -m p8fs.workers.queues.cli status

# Check router status  
python -m p8fs.workers.queues.cli router status

# Check worker status
python -m p8fs.workers.queues.cli worker status --tenant-id tenant-1
```

## 🔍 **Debugging & Troubleshooting**

### **Event Capture for Debugging**
```bash
# Capture raw SeaweedFS events
python -m p8fs.workers.queues.cli seaweedfs-events capture \
  --output-dir ./debug-events \
  --debug

# View captured events
ls -la ./debug-events/
cat ./debug-events/event_*.json | jq '.'
```

### **Debug Logging**
```bash
# Enable debug logging for any service
python -m p8fs.workers.queues.cli seaweedfs-events grpc --debug
python -m p8fs.workers.queues.cli router start --debug
```

### **Configuration Verification**
```bash
# Show current configuration
python -m p8fs.workers.queues.cli config-info
python -m p8fs.workers.queues.cli seaweedfs-events config
```

## 📦 **Dependencies**

### **Runtime Dependencies**
- `nats-py`: NATS client library
- `grpcio`: gRPC protocol support  
- `typer`: CLI framework
- `rich`: Rich terminal output
- `aiohttp`: Async HTTP client (for HTTP poller)

### **Optional Dependencies**
- `typer[all]`: Enhanced CLI features
- `rich`: Better terminal output
- `grpcio-tools`: Protocol buffer compilation

## 🔒 **Security Notes**

- **Tenant Isolation**: All events are filtered to tenant-scoped paths (`/buckets/{tenant_id}/`)
- **Path Validation**: Non-tenant paths are automatically rejected
- **Consumer Cleanup**: Automatic cleanup prevents resource leaks
- **Connection Security**: Uses insecure gRPC for internal cluster communication

---

**The system is now fully executable and production-ready** with comprehensive CLI interfaces, proper error handling, and resilience patterns from the reference implementation.