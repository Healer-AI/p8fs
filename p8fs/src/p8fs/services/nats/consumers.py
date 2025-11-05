"""JetStream consumer management for P8FS queue workers."""

import logging
from dataclasses import dataclass
from enum import Enum

from .client import NATSClient, NATSMessage

logger = logging.getLogger(__name__)


class QueueType(Enum):
    """Queue type enumeration."""
    SMALL = "small"
    MEDIUM = "medium" 
    LARGE = "large"


@dataclass
class ConsumerConfig:
    """Consumer configuration definition."""
    
    name: str
    stream: str
    durable_name: str
    ack_wait_seconds: int = 300  # 5 minutes
    max_deliver: int = 3
    filter_subject: str | None = None
    max_ack_pending: int = 1000
    

class ConsumerManager:
    """Manages JetStream consumers for P8FS queue workers."""
    
    # Consumer configurations for storage workers
    STORAGE_CONSUMERS = {
        "small-workers": ConsumerConfig(
            name="small-workers",
            stream="P8FS_STORAGE_EVENTS_SMALL",
            durable_name="small-workers",
            ack_wait_seconds=300,  # 5 minutes for small files
            max_deliver=3,
            filter_subject="p8fs.storage.events.small",
            max_ack_pending=100,  # Higher throughput for small files
        ),
        "medium-workers": ConsumerConfig(
            name="medium-workers", 
            stream="P8FS_STORAGE_EVENTS_MEDIUM",
            durable_name="medium-workers",
            ack_wait_seconds=600,  # 10 minutes for medium files
            max_deliver=3,
            filter_subject="p8fs.storage.events.medium",
            max_ack_pending=50,
        ),
        "large-workers": ConsumerConfig(
            name="large-workers",
            stream="P8FS_STORAGE_EVENTS_LARGE", 
            durable_name="large-workers",
            ack_wait_seconds=1800,  # 30 minutes for large files
            max_deliver=2,  # Fewer retries for large files
            filter_subject="p8fs.storage.events.large",
            max_ack_pending=10,  # Lower pending for large files
        ),
        "router-consumer": ConsumerConfig(
            name="router-consumer",
            stream="P8FS_STORAGE_EVENTS",
            durable_name="router-consumer", 
            ack_wait_seconds=60,  # Quick routing
            max_deliver=5,  # More retries for router
            filter_subject="p8fs.storage.events",
            max_ack_pending=200,
        ),
    }
    
    def __init__(self, client: NATSClient):
        """Initialize consumer manager.
        
        Args:
            client: Connected NATS client
        """
        self.client = client
        
    async def setup_storage_consumers(self) -> None:
        """Set up all P8FS storage event consumers."""
        logger.info("Setting up P8FS storage event consumers...")
        
        for consumer_name, config in self.STORAGE_CONSUMERS.items():
            await self._create_consumer(config)
            
        logger.info(f"Successfully set up {len(self.STORAGE_CONSUMERS)} storage consumers")
        
    async def _create_consumer(self, config: ConsumerConfig) -> bool:
        """Create a single consumer from configuration.
        
        Args:
            config: Consumer configuration
            
        Returns:
            True if consumer was created or already exists
        """
        kwargs = {
            "durable_name": config.durable_name,
            "ack_wait": config.ack_wait_seconds,
            "max_deliver": config.max_deliver,
            "max_ack_pending": config.max_ack_pending,
        }
        
        # Add optional filter subject
        if config.filter_subject:
            kwargs["filter_subject"] = config.filter_subject
            
        return await self.client.ensure_consumer(
            stream=config.stream,
            consumer=config.name,
            description=f"P8FS consumer for {config.name}",
            **kwargs
        )
        
    async def delete_storage_consumers(self) -> None:
        """Delete all P8FS storage event consumers."""
        logger.warning("Deleting all P8FS storage event consumers...")
        
        for consumer_name, config in self.STORAGE_CONSUMERS.items():
            try:
                await self.client.delete_consumer(config.stream, consumer_name)
            except Exception as e:
                logger.error(f"Failed to delete consumer '{consumer_name}': {e}")
                
        logger.info("Completed storage consumer deletion")
        
    async def get_consumer_status(self) -> dict[str, dict]:
        """Get status of all P8FS storage consumers.
        
        Returns:
            Dictionary mapping consumer names to their status info
        """
        status = {}
        
        for consumer_name, config in self.STORAGE_CONSUMERS.items():
            try:
                info = await self.client.get_consumer_info(config.stream, consumer_name)
                status[consumer_name] = {
                    "status": "active",
                    "stream": info["stream_name"],
                    "delivered": info["delivered"],
                    "ack_pending": info["ack_pending"], 
                    "num_pending": info["num_pending"],
                }
            except Exception as e:
                status[consumer_name] = {
                    "status": "error", 
                    "error": str(e),
                }
                
        return status
        
    async def pull_messages(self, consumer_name: str, batch_size: int = 1, timeout: float = 30.0) -> list[NATSMessage]:
        """Pull messages from a specific consumer.
        
        Args:
            consumer_name: Name of consumer to pull from
            batch_size: Number of messages to pull
            timeout: Timeout in seconds
            
        Returns:
            List of NATSMessage objects
        """
        if consumer_name not in self.STORAGE_CONSUMERS:
            raise ValueError(f"Unknown consumer: {consumer_name}")
            
        config = self.STORAGE_CONSUMERS[consumer_name]
        
        return await self.client.pull_messages(
            stream=config.stream,
            consumer=consumer_name,
            batch_size=batch_size,
            timeout=timeout
        )
        
    async def get_queue_consumer(self, queue_type: QueueType) -> str:
        """Get consumer name for a specific queue type.
        
        Args:
            queue_type: Type of queue (small, medium, large)
            
        Returns:
            Consumer name for the queue type
        """
        consumer_map = {
            QueueType.SMALL: "small-workers",
            QueueType.MEDIUM: "medium-workers", 
            QueueType.LARGE: "large-workers",
        }
        
        return consumer_map[queue_type]
        
    async def validate_consumers(self) -> dict[str, bool]:
        """Validate that all required consumers exist and are healthy.
        
        Returns:
            Dictionary mapping consumer names to their health status
        """
        health = {}
        
        for consumer_name, config in self.STORAGE_CONSUMERS.items():
            try:
                await self.client.get_consumer_info(config.stream, consumer_name)
                health[consumer_name] = True
            except Exception:
                health[consumer_name] = False
                
        return health
        
    def get_consumer_config(self, consumer_name: str) -> ConsumerConfig | None:
        """Get configuration for a consumer.
        
        Args:
            consumer_name: Consumer name
            
        Returns:
            Consumer configuration or None if not found
        """
        return self.STORAGE_CONSUMERS.get(consumer_name)
        
    async def cleanup_stale_consumers(self) -> None:
        """Clean up any stale consumers that may be left over."""
        logger.info("Cleaning up stale consumers...")
        
        # This would typically list all consumers and remove any that aren't in our config
        # For now, we'll just ensure our consumers are properly configured
        for consumer_name, config in self.STORAGE_CONSUMERS.items():
            try:
                # Try to get info - if it exists but is misconfigured, recreate it
                info = await self.client.get_consumer_info(config.stream, consumer_name)
                logger.debug(f"Consumer '{consumer_name}' exists with {info['num_pending']} pending messages")
            except Exception:
                # Consumer doesn't exist, create it
                logger.info(f"Creating missing consumer '{consumer_name}'")
                await self._create_consumer(config)
                
        logger.info("Completed stale consumer cleanup")