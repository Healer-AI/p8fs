"""P8FS Queue Workers.

Tiered queue system for processing storage events based on file size.
Routes events from main queue to size-specific worker queues.
"""

from .config import (
    ConsumerNames,
    QueueSize,
    QueueSubjects,
    QueueThresholds,
    StreamNames,
)
from .models import (
    StorageEvent,
    StorageEventMetadata,
    StorageEventType,
    StoragePathInfo,
)
from .storage_worker import StorageEventWorker, WorkerManager, WorkerStatus
from .tiered_router import TieredStorageRouter

# CLI with optional dependencies
try:
    from .cli import app as cli_app
    _cli_available = True
except ImportError:
    _cli_available = False
    cli_app = None

# SeaweedFS events processing
try:
    from .seaweedfs_events import (
        SeaweedFSEventCapturer,
        SeaweedFSgRPCSubscriber,
        SeaweedFSHTTPPoller,
    )
    _seaweedfs_available = True
except ImportError:
    _seaweedfs_available = False

__all__ = [
    # Configuration
    "QueueSize",
    "QueueThresholds", 
    "QueueSubjects",
    "StreamNames",
    "ConsumerNames",
    
    # Data Models
    "StorageEvent",
    "StorageEventType",
    "StoragePathInfo", 
    "StorageEventMetadata",
    
    # Core components
    "TieredStorageRouter",
    "StorageEventWorker",
    "WorkerManager", 
    "WorkerStatus",
    
    # CLI
    "cli_app",
]

# Add SeaweedFS components if available
if _seaweedfs_available:
    __all__.extend([
        "SeaweedFSgRPCSubscriber",
        "SeaweedFSHTTPPoller", 
        "SeaweedFSEventCapturer",
    ])