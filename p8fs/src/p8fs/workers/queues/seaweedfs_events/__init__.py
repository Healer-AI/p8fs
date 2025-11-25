"""SeaweedFS event processing for P8FS.

This module provides real-time event processing from SeaweedFS storage using
multiple strategies for maximum reliability:

1. gRPC Subscriber (Primary): Real-time streaming of metadata events via gRPC
2. HTTP Poller (Fallback): Polling-based detection using HTTP API  
3. Event Capturer (Debug): Raw event capture for analysis

The gRPC subscriber is the recommended approach for production deployments as it
provides real-time event delivery with minimal latency.

## Usage

### Via Queue Management CLI
```bash
# Access via main queue CLI
python -m p8fs.workers.queues.cli seaweedfs-events grpc

# Direct execution  
python -m p8fs.workers.queues.seaweedfs_events grpc
```

### Programmatic Usage
```python
from p8fs.workers.queues.seaweedfs_events import SeaweedFSgRPCSubscriber

subscriber = SeaweedFSgRPCSubscriber(
    filer_host="localhost",
    filer_grpc_port=18888,
    path_prefix="/buckets/",
)

await subscriber.setup()
await subscriber.start()
```
"""

try:
    from .base import SeaweedFSEventProcessor
    from .event_capturer import SeaweedFSEventCapturer
    from .grpc_subscriber import SeaweedFSgRPCSubscriber
    from .http_poller import SeaweedFSHTTPPoller

    # CLI is available when dependencies are present
    try:
        from .cli import app as cli_app
        __all__ = [
            "SeaweedFSEventProcessor",
            "SeaweedFSgRPCSubscriber",
            "SeaweedFSHTTPPoller", 
            "SeaweedFSEventCapturer",
            "cli_app",
        ]
    except ImportError:
        __all__ = [
            "SeaweedFSEventProcessor",
            "SeaweedFSgRPCSubscriber",
            "SeaweedFSHTTPPoller", 
            "SeaweedFSEventCapturer",
        ]
        
except ImportError:
    # Graceful degradation if dependencies aren't available
    __all__ = []