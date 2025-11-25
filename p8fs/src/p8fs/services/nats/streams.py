"""JetStream stream management for P8FS queues."""

import logging
from dataclasses import dataclass

from .client import NATSClient

logger = logging.getLogger(__name__)


@dataclass
class StreamConfig:
    """Stream configuration definition."""
    
    name: str
    subjects: list[str]
    retention_hours: int = 24
    max_consumers: int = -1
    max_msgs: int = -1
    max_bytes: int = -1
    replicas: int = 1


class StreamManager:
    """Manages JetStream streams for P8FS queues."""
    
    # P8FS storage event streams
    STORAGE_STREAMS = {
        "P8FS_STORAGE_EVENTS": StreamConfig(
            name="P8FS_STORAGE_EVENTS",
            subjects=["p8fs.storage.events"],
            retention_hours=24,
            max_consumers=10,
        ),
        "P8FS_STORAGE_EVENTS_SMALL": StreamConfig(
            name="P8FS_STORAGE_EVENTS_SMALL", 
            subjects=["p8fs.storage.events.small"],
            retention_hours=24,
            max_consumers=50,  # More consumers for small files
        ),
        "P8FS_STORAGE_EVENTS_MEDIUM": StreamConfig(
            name="P8FS_STORAGE_EVENTS_MEDIUM",
            subjects=["p8fs.storage.events.medium"], 
            retention_hours=24,
            max_consumers=20,
        ),
        "P8FS_STORAGE_EVENTS_LARGE": StreamConfig(
            name="P8FS_STORAGE_EVENTS_LARGE",
            subjects=["p8fs.storage.events.large"],
            retention_hours=48,  # Longer retention for large files
            max_consumers=5,
        ),
    }
    
    def __init__(self, client: NATSClient):
        """Initialize stream manager.
        
        Args:
            client: Connected NATS client
        """
        self.client = client
        
    async def setup_storage_streams(self) -> None:
        """Set up all P8FS storage event streams."""
        logger.info("Setting up P8FS storage event streams...")
        
        for stream_name, config in self.STORAGE_STREAMS.items():
            await self._create_stream(config)
            
        logger.info(f"Successfully set up {len(self.STORAGE_STREAMS)} storage streams")
        
    async def _create_stream(self, config: StreamConfig) -> bool:
        """Create a single stream from configuration.
        
        Args:
            config: Stream configuration
            
        Returns:
            True if stream was created or already exists
        """
        kwargs = {
            "max_age": config.retention_hours * 60 * 60,  # Convert to seconds
            "replicas": config.replicas,
        }
        
        # Add optional limits if specified
        if config.max_consumers > 0:
            kwargs["max_consumers"] = config.max_consumers
        if config.max_msgs > 0:
            kwargs["max_msgs"] = config.max_msgs
        if config.max_bytes > 0:
            kwargs["max_bytes"] = config.max_bytes
            
        return await self.client.ensure_stream(
            name=config.name,
            subjects=config.subjects,
            description=f"P8FS storage events stream for {config.name}",
            **kwargs
        )
        
    async def delete_storage_streams(self) -> None:
        """Delete all P8FS storage event streams."""
        logger.warning("Deleting all P8FS storage event streams...")
        
        for stream_name in self.STORAGE_STREAMS.keys():
            try:
                await self.client.delete_stream(stream_name)
            except Exception as e:
                logger.error(f"Failed to delete stream '{stream_name}': {e}")
                
        logger.info("Completed storage stream deletion")
        
    async def get_stream_status(self) -> dict[str, dict]:
        """Get status of all P8FS storage streams.
        
        Returns:
            Dictionary mapping stream names to their status info
        """
        status = {}
        
        for stream_name in self.STORAGE_STREAMS.keys():
            try:
                info = await self.client.get_stream_info(stream_name)
                status[stream_name] = {
                    "status": "active",
                    "messages": info["messages"],
                    "bytes": info["bytes"], 
                    "consumers": info["consumers"],
                }
            except Exception as e:
                status[stream_name] = {
                    "status": "error",
                    "error": str(e),
                }
                
        return status
        
    async def purge_stream(self, stream_name: str) -> None:
        """Purge all messages from a stream.
        
        Args:
            stream_name: Name of stream to purge
        """
        if stream_name not in self.STORAGE_STREAMS:
            raise ValueError(f"Unknown stream: {stream_name}")
            
        try:
            # Delete and recreate stream (NATS doesn't have direct purge)
            config = self.STORAGE_STREAMS[stream_name]
            await self.client.delete_stream(stream_name)
            await self._create_stream(config)
            logger.info(f"Purged stream '{stream_name}'")
        except Exception as e:
            logger.error(f"Failed to purge stream '{stream_name}': {e}")
            raise
            
    async def validate_streams(self) -> dict[str, bool]:
        """Validate that all required streams exist and are healthy.
        
        Returns:
            Dictionary mapping stream names to their health status
        """
        health = {}
        
        for stream_name in self.STORAGE_STREAMS.keys():
            try:
                await self.client.get_stream_info(stream_name)
                health[stream_name] = True
            except Exception:
                health[stream_name] = False
                
        return health
        
    def get_stream_config(self, stream_name: str) -> StreamConfig | None:
        """Get configuration for a stream.
        
        Args:
            stream_name: Stream name
            
        Returns:
            Stream configuration or None if not found
        """
        return self.STORAGE_STREAMS.get(stream_name)