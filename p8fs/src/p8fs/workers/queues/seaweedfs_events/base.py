"""Base class for SeaweedFS event processors with common NATS functionality."""

import logging
from abc import ABC, abstractmethod
from typing import Any

from p8fs.services.nats import NATSClient

logger = logging.getLogger(__name__)


class SeaweedFSEventProcessor(ABC):
    """Abstract base class for SeaweedFS event processors."""
    
    def __init__(self, nats_client: NATSClient | None = None):
        """Initialize event processor.
        
        Args:
            nats_client: NATS client for publishing events. Creates new one if None.
        """
        self.nats_client = nats_client
        self.running = False
        self._own_nats_client = nats_client is None
        
    async def setup(self) -> None:
        """Set up NATS client and streams."""
        if self._own_nats_client:
            self.nats_client = NATSClient()
            await self.nats_client.connect()
            
        # Ensure P8FS storage events stream exists
        success = await self.nats_client.ensure_stream(
            "P8FS_STORAGE_EVENTS",
            ["p8fs.storage.events"],
            description="P8FS storage events from SeaweedFS"
        )
        
        if not success:
            raise RuntimeError("Failed to create/verify P8FS_STORAGE_EVENTS stream")
            
        logger.info("SeaweedFS event processor setup complete")
        
    async def cleanup(self) -> None:
        """Clean up resources."""
        self.running = False
        
        if self._own_nats_client and self.nats_client:
            await self.nats_client.disconnect()
            
    async def publish_event(self, event: dict[str, Any]) -> None:
        """Publish event to NATS JetStream.
        
        Args:
            event: Event dictionary to publish
        """
        try:
            await self.nats_client.publish_json("p8fs.storage.events", event)
            logger.debug(f"Published {event.get('type', 'unknown')} event for {event.get('path', 'unknown')}")
        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            raise
            
    def normalize_path(self, path: str) -> str:
        """Normalize path to consistent format.
        
        Args:
            path: Original path
            
        Returns:
            Normalized path starting with /
        """
        if not path.startswith("/"):
            path = f"/{path}"
        return path
        
    def extract_tenant_id(self, path: str) -> str | None:
        """Extract tenant ID from path.
        
        Args:
            path: File path
            
        Returns:
            Tenant ID if path is tenant-scoped, None otherwise
        """
        if path.startswith("/buckets/"):
            parts = path.split("/")
            if len(parts) >= 3:
                return parts[2]
        return None
        
    @abstractmethod
    async def start(self) -> None:
        """Start event processing. Must be implemented by subclasses."""
        pass
        
    @abstractmethod
    async def stop(self) -> None:
        """Stop event processing. Must be implemented by subclasses.""" 
        pass