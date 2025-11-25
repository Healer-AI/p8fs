"""Tiered storage router for P8FS queue management.

Routes storage events from the main queue to size-specific worker queues
based on file size thresholds.

## Testing with Real NATS (Cluster)

### Prerequisites
1. Port-forward NATS from cluster:
   ```bash
   kubectl port-forward -n p8fs svc/nats 4222:4222 &
   ```

2. Set environment variables:
   ```bash
   export P8FS_NATS_URL=nats://localhost:4222
   ```

### Run Router Locally
Start router that connects to cluster NATS:

```bash
# Set NATS connection
export P8FS_NATS_URL=nats://localhost:4222

# Run router
cd /Users/sirsh/code/p8fs-modules/p8fs
uv run python -m p8fs.workers.router
```

### Monitor Router Activity
Check router logs and stream state:

```bash
# View main stream (router consumes from here)
nats -s nats://localhost:4222 stream info P8FS_STORAGE_EVENTS

# View routed messages in size-specific streams
nats -s nats://localhost:4222 stream info P8FS_STORAGE_EVENTS_SMALL
nats -s nats://localhost:4222 stream info P8FS_STORAGE_EVENTS_MEDIUM
nats -s nats://localhost:4222 stream info P8FS_STORAGE_EVENTS_LARGE

# Publish test event to main queue
nats -s nats://localhost:4222 pub p8fs.storage.events '{
  "path": "/buckets/tenant-test/content/test.txt",
  "event_type": "create",
  "size": 50000000,
  "tenant_id": "tenant-test"
}'

# Check that message was routed to small queue
nats -s nats://localhost:4222 stream info P8FS_STORAGE_EVENTS_SMALL
```

### Verify Router Consumer
Check router consumer state:

```bash
# View router consumer
nats -s nats://localhost:4222 consumer info P8FS_STORAGE_EVENTS tiered-storage-router

# Peek at next message (without consuming)
nats -s nats://localhost:4222 consumer next P8FS_STORAGE_EVENTS tiered-storage-router --count 1
```

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
import time
from typing import Any

from p8fs_cluster.logging import get_logger
from p8fs.services.nats import NATSClient
from p8fs.workers.observability import (
    RouterMetrics,
    get_tracer,
    inject_trace_context,
    setup_worker_observability,
)

from .config import (
    QueueSubjects,
    QueueThresholds,
)
from .models import StorageEvent

logger = get_logger(__name__)


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

        self.small_threshold = 100 * 1024 * 1024
        self.medium_threshold = 1024 * 1024 * 1024

        setup_worker_observability(f"p8fs-tiered-router-{self.instance_id}")
        self.tracer = get_tracer()
        self.metrics = RouterMetrics()

        self._queue_sizes = {
            "main": 0,
            "small": 0,
            "medium": 0,
            "large": 0,
        }
        
    async def setup(self) -> None:
        """Set up router following reference patterns exactly."""
        import p8fs
        logger.info(f"Setting up tiered storage router (p8fs v{p8fs.__version__})...")

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
        ]

        # First, clean up statically named old consumers
        for consumer_name in old_consumer_names:
            try:
                await self.client.delete_consumer("P8FS_STORAGE_EVENTS", consumer_name)
                logger.debug(f"Deleted old consumer: {consumer_name}")
            except Exception as e:
                logger.debug(f"Consumer {consumer_name} didn't exist or already deleted: {e}")

        # Second, clean up any old timestamped router consumers (router-{timestamp})
        # These are from old deployments that used unique consumer names per instance
        try:
            stream_info = await self.client.get_stream_info("P8FS_STORAGE_EVENTS")
            if stream_info.get("consumers", 0) > 0:
                # Get list of all consumers on the stream
                consumers_list = await self.client._js.consumers_info("P8FS_STORAGE_EVENTS")
                async for consumer_info in consumers_list:
                    consumer_name = consumer_info.name
                    # Delete any consumer that matches old pattern: router-{timestamp}
                    if consumer_name.startswith("router-") and consumer_name != self.SHARED_CONSUMER_NAME:
                        try:
                            await self.client.delete_consumer("P8FS_STORAGE_EVENTS", consumer_name)
                            logger.info(f"Deleted old timestamped consumer: {consumer_name}")
                        except Exception as e:
                            logger.warning(f"Failed to delete old consumer {consumer_name}: {e}")
        except Exception as e:
            logger.warning(f"Could not list/cleanup old timestamped consumers: {e}")

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
        """Process a single storage event message with distributed tracing."""
        start_time = time.time()

        with self.tracer.start_as_current_span("router.route_message") as span:
            try:
                try:
                    event = json.loads(msg.data.decode())
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in message #{self._processed_count}: {e}")
                    span.set_attribute("error", "invalid_json")
                    await msg.ack()
                    return

                file_size = self._extract_file_size(event)
                file_name = event.get("path") or event.get("file_name", "unknown")
                tenant_id = event.get("tenant_id", "unknown")

                span.set_attribute("file.name", file_name)
                span.set_attribute("file.size", file_size)
                span.set_attribute("file.size_mb", file_size / (1024 * 1024))
                span.set_attribute("tenant.id", tenant_id)
                span.set_attribute("message.count", self._processed_count)

                target_subject = self._get_target_subject_by_size(file_size)
                queue_tier = target_subject.split(".")[-1]

                span.set_attribute("queue.target", target_subject)
                span.set_attribute("queue.tier", queue_tier)

                event["routing"] = {
                    "original_subject": "p8fs.storage.events",
                    "target_subject": target_subject,
                    "file_size_bytes": file_size,
                    "router_id": self.instance_id,
                    "message_count": self._processed_count,
                    "routing_timestamp": time.time(),
                }

                headers = inject_trace_context()

                logger.info(f"[ROUTER] Processing message #{self._processed_count}: {file_name} ({file_size} bytes) → {target_subject}")

                await self.client._js.publish(
                    target_subject,
                    json.dumps(event).encode(),
                    headers=headers
                )

                duration = time.time() - start_time
                self.metrics.messages_routed.add(
                    1,
                    {"queue_tier": queue_tier, "tenant_id": tenant_id}
                )
                self.metrics.routing_duration.record(
                    duration,
                    {"queue_tier": queue_tier}
                )

                # Log successful routing at INFO level
                file_size_mb = file_size / (1024 * 1024)
                logger.info(f"Routed {file_name} ({file_size_mb:.2f}MB) to {queue_tier} queue for tenant {tenant_id}")

                await msg.ack()

                span.set_attribute("status", "success")
                span.set_attribute("routing.duration", duration)

                logger.info(f"Routed message #{self._processed_count} ({file_size} bytes) to {target_subject}")

            except Exception as e:
                self.metrics.routing_errors.add(1, {"error_type": type(e).__name__})

                span.set_attribute("status", "error")
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.record_exception(e)

                logger.error(f"Error processing message #{self._processed_count}: {e}")
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

        # Ensure file_size is an integer (handle string values from events)
        try:
            file_size = int(file_size) if file_size else 0
        except (ValueError, TypeError):
            logger.warning(f"Invalid file_size value: {file_size}, defaulting to 0")
            file_size = 0

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
            "instance_id": self.instance_id,
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