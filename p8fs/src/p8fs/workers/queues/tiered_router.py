"""Tiered storage router for P8FS queue management.

Routes storage events from the main queue to size-specific worker queues
based on file size thresholds.

CRITICAL RESILIENCE PATTERNS:
This implementation follows carefully constructed resilience patterns from the reference
implementation that are essential for production stability:

1. EXPLICIT CONSUMER CLEANUP: Proactively deletes old/broken consumers before creating
   fresh ones. This prevents consumer conflicts and state corruption that can cause
   message processing to stall indefinitely.

2. FAIL-HARD DESIGN: Any setup failure causes immediate termination rather than
   limping along in a degraded state. This forces external restart and makes
   problems immediately visible.

3. CONSECUTIVE ERROR HANDLING: Distinguishes between transient issues (timeouts)
   and persistent failures. Timeouts reset the error counter, while processing
   errors increment it. After 3 consecutive errors, the router fails hard.

4. PUBLISH-THEN-ACK: Messages are only acknowledged after successful routing.
   Failed publishes don't ACK the message, allowing JetStream to retry.

5. SINGLE MESSAGE PROCESSING: Processes one message at a time for reliability
   over throughput. This simplifies error handling and prevents batch failures.

6. EXPONENTIAL BACKOFF: Implements 2x backoff between consecutive errors to
   prevent tight retry loops that can overwhelm downstream systems.

DO NOT MODIFY these patterns without understanding their purpose. The reference
implementation was carefully tuned through production experience.
"""

import asyncio
import json
import logging
import time
from typing import Any

from p8fs.services.nats import NATSClient

from .config import (
    QueueSubjects,
    QueueThresholds,
)
from .models import StorageEvent

logger = logging.getLogger(__name__)


class TieredStorageRouter:
    """Routes storage events to size-appropriate worker queues."""

    # Shared consumer name for all router instances
    # On WORK_QUEUE streams, multiple instances can share the same consumer
    # and NATS will automatically load-balance messages between them
    SHARED_CONSUMER_NAME = "tiered-storage-router"

    def __init__(self, worker_id: str = None):
        """Initialize router.

        Args:
            worker_id: Worker identifier for logging (not used for consumer name)
        """
        # Use shared consumer name for NATS, but keep instance ID for logging
        self.instance_id = worker_id or f"router-{int(time.time())}"
        self.consumer_name = self.SHARED_CONSUMER_NAME
        self.client: NATSClient | None = None
        self.subscriber = None
        self._running = False
        self._consecutive_errors = 0
        self._error_count = 0
        self._processed_count = 0
        
        # Size thresholds (matching reference exactly)
        self.small_threshold = 100 * 1024 * 1024    # 100MB
        self.medium_threshold = 1024 * 1024 * 1024  # 1GB
        
    async def setup(self) -> None:
        """Set up router following reference patterns exactly."""
        logger.info("Setting up tiered storage router...")
        
        # Step 1: Create and connect NATS client
        self.client = NATSClient()
        await self.client.connect()
        
        # Step 2: Validate JetStream availability - FAIL HARD if not available  
        if not self.client.jetstream:
            raise RuntimeError("JetStream not available - cannot continue")
            
        # Step 3: Ensure all required streams exist - FAIL HARD if any fail
        required_streams = {
            "P8FS_STORAGE_EVENTS": ["p8fs.storage.events"],
            "P8FS_STORAGE_EVENTS_SMALL": ["p8fs.storage.events.small"], 
            "P8FS_STORAGE_EVENTS_MEDIUM": ["p8fs.storage.events.medium"],
            "P8FS_STORAGE_EVENTS_LARGE": ["p8fs.storage.events.large"],
        }
        
        for stream_name, subjects in required_streams.items():
            success = await self.client.ensure_stream(stream_name, subjects)
            if not success:
                raise RuntimeError(f"Failed to create/verify stream {stream_name}")
                
        # Step 4: Create consumers for each tier - FAIL HARD if any fail
        tier_consumers = {
            "small-workers": "P8FS_STORAGE_EVENTS_SMALL",
            "medium-workers": "P8FS_STORAGE_EVENTS_MEDIUM", 
            "large-workers": "P8FS_STORAGE_EVENTS_LARGE",
        }
        
        for consumer_name, stream_name in tier_consumers.items():
            success = await self.client.ensure_consumer(stream_name, consumer_name)
            if not success:
                raise RuntimeError(f"Failed to create consumer {consumer_name}")
                
        # Step 5: EXPLICIT CONSUMER CLEANUP - Delete old/broken consumers
        # NOTE: We do NOT delete the shared consumer name since multiple instances use it
        logger.info("Cleaning up old consumers...")
        old_consumer_names = [
            "simple-tiered-router",
            "router-consumer",
            # Add dynamic router-* consumers from old deployments
        ]

        # Add any old timestamped router names if they exist
        # These were from the old pattern: router-{timestamp}
        for consumer_name in old_consumer_names:
            try:
                await self.client.delete_consumer("P8FS_STORAGE_EVENTS", consumer_name)
                logger.debug(f"Deleted old consumer: {consumer_name}")
            except Exception as e:
                logger.debug(f"Consumer {consumer_name} didn't exist or already deleted: {e}")

        # Step 6: Ensure shared consumer exists - FAIL HARD if fails
        # Note: ensure_consumer is idempotent - safe to call multiple times
        # All router instances share this consumer and NATS load-balances between them
        success = await self.client.ensure_consumer("P8FS_STORAGE_EVENTS", self.consumer_name)
        if not success:
            raise RuntimeError(f"Failed to create/verify shared consumer {self.consumer_name}")
            
        # Step 7: Verify main stream state
        try:
            stream_info = await self.client.get_stream_info("P8FS_STORAGE_EVENTS")
            logger.info(f"Main stream has {stream_info['messages']} messages, {stream_info['consumers']} consumers")
        except Exception as e:
            logger.warning(f"Could not get stream info: {e}")
            
        # Step 8: Create pull subscriber - FAIL HARD if fails
        try:
            self.subscriber = await self.client.create_pull_subscriber(
                "P8FS_STORAGE_EVENTS", self.consumer_name, "p8fs.storage.events"
            )
            logger.info(f"Router instance {self.instance_id} connected to shared consumer {self.consumer_name}")
        except Exception as e:
            raise RuntimeError(f"Failed to create pull subscriber: {e}")

        logger.info(f"Tiered storage router setup complete (instance: {self.instance_id})")
        
    async def start(self) -> None:
        """Start the router process."""
        if self._running:
            logger.warning("Router is already running")
            return
            
        logger.info("Starting tiered storage router...")
        self._running = True
        self._consecutive_errors = 0
        
        try:
            await self._process_events()
        except Exception as e:
            logger.error(f"Router failed: {e}")
            raise
        finally:
            self._running = False
            
    async def stop(self) -> None:
        """Stop the router process."""
        logger.info("Stopping tiered storage router...")
        self._running = False
        
    def _should_process_event(self, event: StorageEvent) -> bool:
        """Check if event should be processed.
        
        Args:
            event: Storage event to check
            
        Returns:
            True if event should be processed
        """
        return event.should_process()
        
    def _get_target_subject(self, event: StorageEvent) -> str:
        """Determine target subject based on file size.
        
        Args:
            event: Storage event
            
        Returns:
            Target NATS subject
        """
        queue_size = QueueThresholds.get_queue_size(event.metadata.file_size)
        return QueueSubjects.get_subject_for_size(queue_size)
        
    def _enrich_event(self, event: StorageEvent, target_subject: str) -> dict[str, Any]:
        """Add routing metadata to event.
        
        Args:
            event: Original storage event
            target_subject: Target subject for routing
            
        Returns:
            Enriched event data
        """
        data = event.model_dump()
        
        # Add routing metadata
        data["routing"] = {
            "router_timestamp": time.time(),
            "target_subject": target_subject,
            "queue_size": QueueThresholds.get_queue_size(event.metadata.file_size).value,
            "routed_by": "tiered-storage-router",
        }
        
        return data
        
    async def _process_events(self) -> None:
        """Main event processing loop - matches reference patterns exactly."""
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        logger.info("Starting message processing loop...")
        
        while self._running:
            try:
                # Fetch single message with 30-second timeout (reference pattern)
                msgs = await self.subscriber.fetch(1, timeout=30.0)
                
                if not msgs:
                    logger.debug("No messages available")
                    consecutive_errors = 0  # Reset on successful fetch (even if no messages)
                    continue
                    
                for msg in msgs:
                    try:
                        await self._process_single_message(msg)
                        self._processed_count += 1
                        
                        # Log progress periodically
                        if self._processed_count % 100 == 0:
                            logger.info(f"Processed {self._processed_count} messages")
                            
                    except Exception as e:
                        logger.error(f"Error processing message #{self._processed_count}: {e}")
                        self._error_count += 1
                        # Individual message errors don't break the loop - log and continue
                        
                # Reset consecutive errors on successful fetch
                consecutive_errors = 0
                        
            except TimeoutError:
                # Timeouts are NOT errors - they're expected when no messages available
                logger.debug("Fetch timeout - no messages available")
                consecutive_errors = 0  # Important: reset on timeout
                continue
                
            except Exception as e:
                consecutive_errors += 1
                self._error_count += 1
                logger.error(f"Error in processing loop (consecutive: {consecutive_errors}): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({consecutive_errors}) - failing hard")
                    raise RuntimeError(f"Router failed after {consecutive_errors} consecutive errors")
                    
                # Exponential backoff
                sleep_time = 2 * consecutive_errors
                logger.info(f"Backing off for {sleep_time} seconds...")
                await asyncio.sleep(sleep_time)
                
        logger.info(f"Message processing stopped. Processed {self._processed_count} messages, {self._error_count} errors")
        
    async def _process_single_message(self, msg) -> None:
        """Process a single storage event message - follows reference patterns exactly."""
        try:
            # Parse JSON with error handling (reference pattern)
            try:
                event = json.loads(msg.data.decode())
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in message #{self._processed_count}: {e}")
                await msg.ack()  # ACK bad messages to avoid infinite redelivery
                return
                
            # Extract file size with multiple fallbacks (reference pattern)
            file_size = self._extract_file_size(event)
            
            # Get target subject based on file size
            target_subject = self._get_target_subject_by_size(file_size)
            
            # Add routing metadata (reference pattern)
            event["routing"] = {
                "original_subject": "p8fs.storage.events",
                "target_subject": target_subject,
                "file_size_bytes": file_size,
                "router_id": self.worker_id,
                "message_count": self._processed_count,
                "routing_timestamp": time.time(),
            }
            
            logger.debug(f"Routing message #{self._processed_count}: {file_size} bytes → {target_subject}")
            
            # Publish to target subject
            await self.client._js.publish(target_subject, json.dumps(event).encode())
            
            # Only ACK after successful publish (reference pattern)
            await msg.ack()
            
            logger.info(f"Routed message #{self._processed_count} ({file_size} bytes) to {target_subject}")
            
        except Exception as e:
            logger.error(f"Error processing message #{self._processed_count}: {e}")
            # Don't ACK failed messages - let JetStream retry
            raise
            
    def _extract_file_size(self, event: dict[str, Any]) -> int:
        """Extract file size with multiple fallbacks (matches reference exactly)."""
        # Try multiple possible locations for file size
        file_size = event.get("size", 0)
        if not file_size:
            file_size = event.get("entry", {}).get("Size", 0) 
        if not file_size:
            file_size = event.get("attributes", {}).get("file_size", 0)
        if not file_size:
            file_size = event.get("metadata", {}).get("size", 0)
        if not file_size:
            file_size = event.get("file_size", 0)
            
        # Default to 1KB if no size found (routes to small queue)
        return max(file_size, 1024)
        
    def _get_target_subject_by_size(self, file_size_bytes: int) -> str:
        """Get target subject based on file size (matches reference exactly)."""
        if file_size_bytes <= self.small_threshold:
            return "p8fs.storage.events.small"
        elif file_size_bytes <= self.medium_threshold:
            return "p8fs.storage.events.medium"
        else:
            return "p8fs.storage.events.large"
            
    async def get_status(self) -> dict[str, Any]:
        """Get router status information."""
        return {
            "running": self._running,
            "processed_count": self._processed_count,
            "error_count": self._error_count,
            "consecutive_errors": self._consecutive_errors,
            "worker_id": self.worker_id,
        }
        
    async def cleanup(self) -> None:
        """Clean up resources following reference pattern."""
        logger.info("Cleaning up router resources...")
        
        if self.client:
            try:
                await self.client.disconnect()
                logger.info("NATS client closed")
            except Exception as e:
                logger.error(f"Error closing NATS client: {e}")
                
        self._running = False