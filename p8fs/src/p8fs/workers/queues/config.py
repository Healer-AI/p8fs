"""Queue configuration and constants for P8FS storage workers."""

from dataclasses import dataclass
from enum import Enum


class QueueSize(Enum):
    """File size-based queue categories."""
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


@dataclass(frozen=True)
class QueueThresholds:
    """File size thresholds for queue routing."""
    
    # Size thresholds in bytes
    SMALL_MAX = 100 * 1024 * 1024    # 100MB
    MEDIUM_MAX = 1024 * 1024 * 1024  # 1GB
    
    @classmethod
    def get_queue_size(cls, file_size_bytes: int) -> QueueSize:
        """Determine queue size based on file size.
        
        Args:
            file_size_bytes: File size in bytes
            
        Returns:
            Appropriate queue size category
        """
        if file_size_bytes <= cls.SMALL_MAX:
            return QueueSize.SMALL
        elif file_size_bytes <= cls.MEDIUM_MAX:
            return QueueSize.MEDIUM
        else:
            return QueueSize.LARGE


class QueueSubjects:
    """NATS subject names for P8FS queues."""
    
    # Main storage events subject
    STORAGE_EVENTS = "p8fs.storage.events"
    
    # Size-specific subjects
    STORAGE_EVENTS_SMALL = "p8fs.storage.events.small"
    STORAGE_EVENTS_MEDIUM = "p8fs.storage.events.medium"
    STORAGE_EVENTS_LARGE = "p8fs.storage.events.large"
    
    # Subject mapping by queue size
    SIZE_SUBJECTS = {
        QueueSize.SMALL: STORAGE_EVENTS_SMALL,
        QueueSize.MEDIUM: STORAGE_EVENTS_MEDIUM, 
        QueueSize.LARGE: STORAGE_EVENTS_LARGE,
    }
    
    @classmethod
    def get_subject_for_size(cls, queue_size: QueueSize) -> str:
        """Get NATS subject for a queue size.
        
        Args:
            queue_size: Queue size category
            
        Returns:
            NATS subject string
        """
        return cls.SIZE_SUBJECTS[queue_size]


class StreamNames:
    """NATS stream names for P8FS queues."""
    
    # Main stream
    STORAGE_EVENTS = "P8FS_STORAGE_EVENTS"
    
    # Size-specific streams
    STORAGE_EVENTS_SMALL = "P8FS_STORAGE_EVENTS_SMALL"
    STORAGE_EVENTS_MEDIUM = "P8FS_STORAGE_EVENTS_MEDIUM"
    STORAGE_EVENTS_LARGE = "P8FS_STORAGE_EVENTS_LARGE"
    
    # Stream mapping by queue size
    SIZE_STREAMS = {
        QueueSize.SMALL: STORAGE_EVENTS_SMALL,
        QueueSize.MEDIUM: STORAGE_EVENTS_MEDIUM,
        QueueSize.LARGE: STORAGE_EVENTS_LARGE,
    }
    
    @classmethod
    def get_stream_for_size(cls, queue_size: QueueSize) -> str:
        """Get stream name for a queue size.
        
        Args:
            queue_size: Queue size category
            
        Returns:
            Stream name string
        """
        return cls.SIZE_STREAMS[queue_size]


class ConsumerNames:
    """NATS consumer names for P8FS workers."""
    
    # Worker consumers
    SMALL_WORKERS = "small-workers"
    MEDIUM_WORKERS = "medium-workers" 
    LARGE_WORKERS = "large-workers"
    
    # Router consumer
    ROUTER_CONSUMER = "router-consumer"
    
    # Consumer mapping by queue size
    SIZE_CONSUMERS = {
        QueueSize.SMALL: SMALL_WORKERS,
        QueueSize.MEDIUM: MEDIUM_WORKERS,
        QueueSize.LARGE: LARGE_WORKERS,
    }
    
    @classmethod
    def get_consumer_for_size(cls, queue_size: QueueSize) -> str:
        """Get consumer name for a queue size.
        
        Args:
            queue_size: Queue size category
            
        Returns:
            Consumer name string
        """
        return cls.SIZE_CONSUMERS[queue_size]


@dataclass(frozen=True)
class WorkerConfig:
    """Configuration for storage workers."""
    
    # Processing timeouts by queue size (seconds)
    SMALL_TIMEOUT = 300     # 5 minutes
    MEDIUM_TIMEOUT = 600    # 10 minutes  
    LARGE_TIMEOUT = 1800    # 30 minutes
    
    # Batch sizes for message processing
    SMALL_BATCH_SIZE = 10
    MEDIUM_BATCH_SIZE = 5
    LARGE_BATCH_SIZE = 1
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 5
    
    # Queue-specific configurations
    SIZE_CONFIGS = {
        QueueSize.SMALL: {
            "timeout": SMALL_TIMEOUT,
            "batch_size": SMALL_BATCH_SIZE,
            "max_ack_pending": 100,
            "max_deliver": 3,
        },
        QueueSize.MEDIUM: {
            "timeout": MEDIUM_TIMEOUT, 
            "batch_size": MEDIUM_BATCH_SIZE,
            "max_ack_pending": 50,
            "max_deliver": 3,
        },
        QueueSize.LARGE: {
            "timeout": LARGE_TIMEOUT,
            "batch_size": LARGE_BATCH_SIZE, 
            "max_ack_pending": 10,
            "max_deliver": 2,
        },
    }
    
    @classmethod
    def get_config_for_size(cls, queue_size: QueueSize) -> dict:
        """Get worker configuration for a queue size.
        
        Args:
            queue_size: Queue size category
            
        Returns:
            Configuration dictionary
        """
        return cls.SIZE_CONFIGS[queue_size]


@dataclass(frozen=True)
class RouterConfig:
    """Configuration for the tiered storage router."""
    
    # Router processing settings
    FETCH_TIMEOUT = 30      # 30 second fetch timeout
    MAX_CONSECUTIVE_ERRORS = 3  # Fail after 3 errors
    
    # Message handling
    ACK_WAIT_SECONDS = 60   # 1 minute for routing
    MAX_DELIVER = 5         # More retries for router
    
    # Batch processing
    BATCH_SIZE = 1          # Process one at a time for simplicity
    

class KEDAScalingConfig:
    """KEDA scaling configuration for workers."""
    
    # Scaling parameters by queue size
    SCALING_CONFIGS = {
        QueueSize.SMALL: {
            "min_replicas": 2,
            "max_replicas": 50,
            "messages_per_replica": 10,
            "cooldown_period": 30,  # seconds
        },
        QueueSize.MEDIUM: {
            "min_replicas": 1,
            "max_replicas": 20, 
            "messages_per_replica": 5,
            "cooldown_period": 60,
        },
        QueueSize.LARGE: {
            "min_replicas": 0,  # Can scale to zero
            "max_replicas": 5,
            "messages_per_replica": 1,
            "cooldown_period": 120,
        },
    }
    
    @classmethod
    def get_scaling_config(cls, queue_size: QueueSize) -> dict:
        """Get KEDA scaling configuration for a queue size.
        
        Args:
            queue_size: Queue size category
            
        Returns:
            KEDA scaling configuration dictionary
        """
        return cls.SCALING_CONFIGS[queue_size]