"""NATS JetStream Client for P8FS queue management."""

import json
import logging
from dataclasses import dataclass
from typing import Any

import nats
from nats.aio.msg import Msg
from nats.js import JetStreamContext
from nats.js.api import (
    AckPolicy,
    ConsumerConfig,
    RetentionPolicy,
    StorageType,
    StreamConfig,
)
from p8fs_cluster.config.settings import config

logger = logging.getLogger(__name__)


@dataclass
class NATSMessage:
    """Wrapper for NATS messages with metadata."""
    
    subject: str
    data: bytes
    reply: str | None = None
    headers: dict[str, str] | None = None
    metadata: dict[str, Any] | None = None
    _original_msg: Msg | None = None  # Keep reference for ACK/NAK


class NATSClient:
    """NATS JetStream client for P8FS queue operations."""
    
    def __init__(self, servers: list[str] | None = None):
        """Initialize NATS client.
        
        Args:
            servers: List of NATS server URLs. Uses config.nats_url if None.
        """
        self.servers = servers or [config.nats_url]
        self._nc: nats.NATS | None = None
        self._js: JetStreamContext | None = None
        self._connected = False
        
    async def connect(self) -> None:
        """Connect to NATS server with retry logic."""
        if self._connected and self._nc and not self._nc.is_closed:
            return
            
        try:
            self._nc = await nats.connect(
                servers=self.servers,
                max_reconnect_attempts=10,
                reconnect_time_wait=2,
                connect_timeout=10,
                error_cb=self._error_callback,
                disconnected_cb=self._disconnect_callback,
                reconnected_cb=self._reconnect_callback,
            )
            self._js = self._nc.jetstream()
            self._connected = True
            logger.info(f"Connected to NATS servers: {self.servers}")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            self._connected = False
            raise
            
    async def _ensure_connected(self) -> None:
        """Ensure NATS connection is active."""
        if not self.is_connected:
            await self.connect()
            
    async def _error_callback(self, error):
        """Handle NATS connection errors."""
        logger.error(f"NATS connection error: {error}")
        
    async def _disconnect_callback(self):
        """Handle NATS disconnection."""
        logger.warning("Disconnected from NATS server")
        self._connected = False
        
    async def _reconnect_callback(self):
        """Handle NATS reconnection."""
        logger.info("Reconnected to NATS server")
        self._connected = True
            
    async def disconnect(self) -> None:
        """Disconnect from NATS server."""
        if self._nc and not self._nc.is_closed:
            await self._nc.close()
            self._connected = False
            logger.info("Disconnected from NATS")
            
    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected and self._nc and not self._nc.is_closed
        
    @property
    def jetstream(self) -> JetStreamContext:
        """Get JetStream context."""
        if not self._js:
            raise RuntimeError("Not connected to NATS")
        return self._js
        
    async def ensure_stream(self, name: str, subjects: list[str], description: str = "", **kwargs) -> bool:
        """Ensure a JetStream stream exists with correct configuration.
        
        Args:
            name: Stream name
            subjects: List of subjects for the stream
            description: Stream description
            **kwargs: Additional stream configuration
            
        Returns:
            True if stream was created or already exists
        """
        await self._ensure_connected()
            
        # Default stream configuration
        config_dict = {
            "retention": RetentionPolicy.WORK_QUEUE,
            "storage": StorageType.FILE,
            "max_age": 24 * 60 * 60,  # 24 hours
            "max_bytes": -1,  # -1 means unlimited, let NATS manage it
            "num_replicas": 1,  # Use num_replicas instead of replicas
            "description": description,
            **kwargs
        }

        try:
            stream_config = StreamConfig(
                name=name,
                subjects=subjects,
                **config_dict
            )
            await self._js.add_stream(stream_config)
            logger.info(f"Created/verified stream '{name}' with subjects {subjects}")
            return True
        except Exception as e:
            if "already in use" in str(e).lower():
                logger.debug(f"Stream '{name}' already exists")
                return True
            else:
                logger.error(f"Failed to ensure stream '{name}': {e}")
                return False
            
    async def delete_stream(self, name: str) -> None:
        """Delete a JetStream stream.
        
        Args:
            name: Stream name to delete
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to NATS")
            
        try:
            await self._js.delete_stream(name)
            logger.info(f"Deleted stream '{name}'")
        except Exception as e:
            logger.error(f"Failed to delete stream '{name}': {e}")
            raise
            
    async def ensure_consumer(self, stream: str, consumer: str, description: str = "", **kwargs) -> bool:
        """Ensure a JetStream consumer exists with correct configuration.
        
        Args:
            stream: Stream name
            consumer: Consumer name
            description: Consumer description
            **kwargs: Additional consumer configuration
            
        Returns:
            True if consumer was created or already exists
        """
        await self._ensure_connected()
            
        # Default consumer configuration
        config_dict = {
            "durable_name": consumer,
            "ack_policy": AckPolicy.EXPLICIT,
            "max_deliver": 3,
            "ack_wait": 300,  # 5 minutes
            "description": description,
            **kwargs
        }
        
        try:
            consumer_config = ConsumerConfig(**config_dict)
            await self._js.add_consumer(stream=stream, config=consumer_config)
            logger.info(f"Created/verified consumer '{consumer}' for stream '{stream}'")
            return True
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.debug(f"Consumer '{consumer}' already exists")
                return True
            else:
                logger.error(f"Failed to ensure consumer '{consumer}' for stream '{stream}': {e}")
                return False
            
    async def delete_consumer(self, stream: str, consumer: str) -> None:
        """Delete a JetStream consumer.
        
        Args:
            stream: Stream name
            consumer: Consumer name
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to NATS")
            
        try:
            await self._js.delete_consumer(stream, consumer)
            logger.info(f"Deleted consumer '{consumer}' from stream '{stream}'")
        except Exception as e:
            logger.error(f"Failed to delete consumer '{consumer}' from stream '{stream}': {e}")
            raise
            
    async def publish(self, subject: str, data: bytes, headers: dict[str, str] | None = None) -> None:
        """Publish message to JetStream.
        
        Args:
            subject: Message subject
            data: Message data
            headers: Optional message headers
        """
        await self._ensure_connected()
            
        try:
            await self._js.publish(subject, data, headers=headers)
            logger.debug(f"Published message to subject '{subject}'")
        except Exception as e:
            logger.error(f"Failed to publish to subject '{subject}': {e}")
            raise
            
    async def publish_json(self, subject: str, data: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        """Publish JSON message to JetStream.
        
        Args:
            subject: Message subject
            data: Message data as dictionary
            headers: Optional message headers
        """
        json_data = json.dumps(data).encode('utf-8')
        await self.publish(subject, json_data, headers)
        
    async def create_pull_subscriber(self, stream: str, consumer: str, subject: str):
        """Create a pull subscriber for a consumer.
        
        Args:
            stream: Stream name
            consumer: Consumer name
            subject: Subject to subscribe to
            
        Returns:
            Pull subscription object
        """
        await self._ensure_connected()
        
        # Ensure consumer exists first
        await self.ensure_consumer(stream, consumer, f"Pull consumer for {subject}")
        
        # Create pull subscription
        return await self._js.pull_subscribe(subject, durable=consumer)
    
    async def pull_messages(self, stream: str, consumer: str, batch_size: int = 1, timeout: float = 30.0) -> list[NATSMessage]:
        """Pull messages from a JetStream consumer.
        
        Args:
            stream: Stream name
            consumer: Consumer name
            batch_size: Number of messages to pull
            timeout: Timeout in seconds
            
        Returns:
            List of NATSMessage objects with original message references
        """
        await self._ensure_connected()
            
        try:
            # Create pull subscription
            psub = await self._js.pull_subscribe("", durable=consumer)
            
            # Fetch messages
            msgs = await psub.fetch(batch_size, timeout=timeout)
            
            # Convert to NATSMessage objects with original reference
            result = []
            for msg in msgs:
                nats_msg = NATSMessage(
                    subject=msg.subject,
                    data=msg.data,
                    reply=msg.reply,
                    headers=msg.headers,
                    metadata=msg.metadata.__dict__ if msg.metadata else None,
                    _original_msg=msg  # Keep reference for ACK/NAK
                )
                result.append(nats_msg)
                
            return result
            
        except TimeoutError:
            # Timeout is expected when no messages are available
            return []
        except Exception as e:
            logger.error(f"Failed to pull from consumer '{consumer}' in stream '{stream}': {e}")
            raise
            
    async def ack_message(self, msg: NATSMessage) -> None:
        """Acknowledge a message.
        
        Args:
            msg: Message to acknowledge
        """
        if msg._original_msg:
            await msg._original_msg.ack()
        else:
            logger.warning("Cannot ACK message: no original message reference")
        
    async def nak_message(self, msg: NATSMessage) -> None:
        """Negatively acknowledge a message (for retry).
        
        Args:
            msg: Message to nack
        """
        if msg._original_msg:
            await msg._original_msg.nak()
        else:
            logger.warning("Cannot NAK message: no original message reference")
        
    async def get_stream_info(self, stream: str) -> dict[str, Any]:
        """Get stream information.
        
        Args:
            stream: Stream name
            
        Returns:
            Stream information dictionary
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to NATS")
            
        try:
            info = await self._js.stream_info(stream)
            return {
                "name": info.config.name,
                "subjects": info.config.subjects,
                "messages": info.state.messages,
                "bytes": info.state.bytes,
                "consumers": info.state.consumer_count,
            }
        except Exception as e:
            logger.error(f"Failed to get info for stream '{stream}': {e}")
            raise
            
    async def get_consumer_info(self, stream: str, consumer: str) -> dict[str, Any]:
        """Get consumer information.
        
        Args:
            stream: Stream name
            consumer: Consumer name
            
        Returns:
            Consumer information dictionary
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to NATS")
            
        try:
            info = await self._js.consumer_info(stream, consumer)
            return {
                "name": info.name,
                "stream_name": info.stream_name,
                "delivered": info.delivered.consumer_seq,
                "ack_pending": info.ack_pending.consumer_seq,
                "num_pending": info.num_pending,
            }
        except Exception as e:
            logger.error(f"Failed to get info for consumer '{consumer}' in stream '{stream}': {e}")
            raise
            
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()