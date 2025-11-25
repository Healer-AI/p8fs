"""Storage event worker for processing files from size-specific queues.

Integrates with existing storage worker functionality while managing
NATS queue processing for different file sizes.

## Testing with Real NATS (Cluster)

### Prerequisites
1. Port-forward NATS from cluster:
   ```bash
   kubectl port-forward -n p8fs svc/nats 4222:4222 &
   ```

2. Port-forward TiDB from cluster:
   ```bash
   kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000 &
   ```

3. Set environment variables:
   ```bash
   export P8FS_NATS_URL=nats://localhost:4222
   export P8FS_STORAGE_PROVIDER=tidb
   export P8FS_TIDB_HOST=127.0.0.1
   export P8FS_TIDB_PORT=4000
   export P8FS_TIDB_USER=root
   export P8FS_TIDB_PASSWORD=""
   export P8FS_TIDB_DATABASE=public
   ```

### Manual Testing
Test the storage worker end-to-end with real NATS and database:

```bash
# Terminal 1: Port-forward services
kubectl port-forward -n p8fs svc/nats 4222:4222 &
kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000 &

# Terminal 2: Start tiered router (routes messages to size-specific queues)
cd /Users/sirsh/code/p8fs-modules/p8fs
P8FS_STORAGE_PROVIDER=tidb P8FS_NATS_URL=nats://localhost:4222 \
uv run python -m p8fs.workers.router

# Terminal 3: Start storage worker for small files
P8FS_STORAGE_PROVIDER=tidb P8FS_NATS_URL=nats://localhost:4222 \
uv run python -m p8fs.workers.storage_worker --queue small

# Terminal 4: Publish test event to main queue
P8FS_STORAGE_PROVIDER=tidb P8FS_NATS_URL=nats://localhost:4222 \
uv run python tests/workers/queues/publish_test_event.py
```

### Automated Test Script
Run integration test that uses real NATS via port-forwarding:

```bash
# Start port-forwards in background
kubectl port-forward -n p8fs svc/nats 4222:4222 &
kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000 &

# Run integration test
P8FS_STORAGE_PROVIDER=tidb P8FS_NATS_URL=nats://localhost:4222 \
uv run pytest tests/integration/workers/test_storage_worker_nats.py -v -s
```

### Verify Event Flow
Check messages in NATS streams:

```bash
# Install nats CLI
brew install nats-io/nats-tools/nats

# Check main stream
nats -s nats://localhost:4222 stream info P8FS_STORAGE_EVENTS

# Check small queue
nats -s nats://localhost:4222 stream info P8FS_STORAGE_EVENTS_SMALL

# Publish test message
nats -s nats://localhost:4222 pub p8fs.storage.events '{
  "path": "/buckets/tenant-test/content/test.txt",
  "event_type": "create",
  "size": 1024,
  "tenant_id": "tenant-test"
}'
```

### Debug NATS Consumer State
Check consumer state and pending messages:

```bash
# View consumer info
nats -s nats://localhost:4222 consumer info P8FS_STORAGE_EVENTS_SMALL small-workers

# View pending messages
nats -s nats://localhost:4222 consumer next P8FS_STORAGE_EVENTS_SMALL small-workers --count 1
```
"""

import asyncio
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from p8fs_cluster.logging import get_logger
from p8fs.repository import TenantRepository
from p8fs.services.nats import ConsumerManager, NATSClient
from p8fs.workers.observability import (
    WorkerMetrics as OTelWorkerMetrics,
    continue_trace,
    get_tracer,
    setup_worker_observability,
    trace_file_processing,
)
from p8fs.workers.storage import StorageEvent as BaseStorageEvent
from p8fs.workers.storage import StorageWorker

from .config import ConsumerNames, QueueSize, WorkerConfig
from .models import StorageEvent

logger = get_logger(__name__)


class WorkerStatus(Enum):
    """Worker status states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class WorkerMetrics:
    """Worker performance metrics."""
    
    messages_processed: int = 0
    messages_failed: int = 0
    files_processed: int = 0
    resources_created: int = 0
    processing_time_total: float = 0.0
    last_activity: float | None = None
    start_time: float = 0.0
    
    @property
    def average_processing_time(self) -> float:
        """Calculate average processing time per message."""
        if self.messages_processed == 0:
            return 0.0
        return self.processing_time_total / self.messages_processed
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        total = self.messages_processed + self.messages_failed
        if total == 0:
            return 0.0
        return (self.messages_processed / total) * 100.0


class StorageEventWorker:
    """Processes storage events from size-specific NATS queues."""

    def __init__(
        self,
        queue_size: QueueSize,
        nats_client: NATSClient,
        tenant_id: str,
        stream_name: str | None = None,
        consumer_name: str | None = None,
        subject: str | None = None
    ):
        """Initialize storage event worker.

        Args:
            queue_size: Size of queue to process (small, medium, large, or test)
            nats_client: Connected NATS client
            tenant_id: Tenant ID for repository initialization
            stream_name: Optional custom stream name (overrides queue_size default)
            consumer_name: Optional custom consumer name (overrides queue_size default)
            subject: Optional custom subject (overrides queue_size default)
        """
        self.queue_size = queue_size
        self.client = nats_client
        self.tenant_id = tenant_id

        # Get configuration for this queue size
        self.config = WorkerConfig.get_config_for_size(queue_size)

        # Allow custom stream/consumer/subject names (for TEST queue)
        self.stream_name = stream_name or f"P8FS_STORAGE_EVENTS_{queue_size.value.upper()}"
        self.consumer_name = consumer_name or ConsumerNames.get_consumer_for_size(queue_size)
        self.subject = subject or f"p8fs.storage.events.{queue_size.value}"
        
        # Initialize components
        self.consumer_manager = ConsumerManager(nats_client)
        self.repository: TenantRepository | None = None
        self.storage_worker: StorageWorker | None = None
        self.subscriber = None  # Pull subscriber (created in setup)

        # State management
        self._status = WorkerStatus.STOPPED
        self._running = False
        self.worker_metrics = WorkerMetrics()

        # Initialize OpenTelemetry
        setup_worker_observability(f"p8fs-storage-worker-{queue_size.value}")
        self.tracer = get_tracer()
        self.otel_metrics = OTelWorkerMetrics()
        
    async def setup(self) -> None:
        """Set up worker components."""
        import p8fs
        logger.info(f"Setting up {self.queue_size.value} storage worker for tenant {self.tenant_id} (p8fs v{p8fs.__version__})")

        self._status = WorkerStatus.STARTING

        # Initialize storage worker with tenant_id
        self.storage_worker = StorageWorker(self.tenant_id)

        # Keep reference to repository for health checks
        from p8fs.models.p8 import Files
        self.repository = TenantRepository(Files, tenant_id=self.tenant_id)

        # Verify stream exists (router should have already created it)
        logger.info(f"Verifying stream {self.stream_name} exists")
        try:
            await self.client.get_stream_info(self.stream_name)
            logger.info(f"Stream {self.stream_name} verified")
        except Exception as e:
            raise RuntimeError(f"Stream {self.stream_name} not found - router must create streams first: {e}")

        # Connect to existing pull subscriber (router already created the consumer)
        logger.info(f"Connecting to existing consumer {self.consumer_name} on stream {self.stream_name}")
        self.subscriber = await self.client.connect_to_pull_subscriber(self.stream_name, self.consumer_name)
        logger.info(f"Connected to consumer {self.consumer_name}")

        self.worker_metrics.start_time = time.time()
        logger.info(f"Setup complete for {self.queue_size.value} worker")
        
    async def start(self) -> None:
        """Start processing messages from the queue."""
        if self._running:
            logger.warning(f"{self.queue_size.value} worker is already running")
            return
            
        if not self.storage_worker:
            raise RuntimeError("Worker not set up. Call setup() first.")
            
        logger.info(f"Starting {self.queue_size.value} storage worker...")
        self._running = True
        self._status = WorkerStatus.RUNNING
        
        try:
            await self._process_queue()
        except Exception as e:
            logger.error(f"{self.queue_size.value} worker failed: {e}")
            self._status = WorkerStatus.ERROR
            raise
        finally:
            self._running = False
            
    async def stop(self) -> None:
        """Stop processing messages."""
        logger.info(f"Stopping {self.queue_size.value} storage worker...")
        self._status = WorkerStatus.STOPPING
        self._running = False
        
        # Clean up storage worker NATS connection
        if self.storage_worker:
            await self.storage_worker.cleanup()
            
        self._status = WorkerStatus.STOPPED
        logger.info(f"{self.queue_size.value} worker stopped")
        
    def _record_event_attributes(self, span, event: StorageEvent) -> None:
        """Record event attributes to span."""
        span.set_attribute("file.name", event.path)
        span.set_attribute("file.size", event.metadata.file_size)
        span.set_attribute("file.size_mb", event.metadata.file_size / (1024 * 1024))
        span.set_attribute("tenant.id", event.tenant_id)
        span.set_attribute("queue.name", self.queue_size.value)
        span.set_attribute("event.type", event.event_type.value)

    def _record_success_metrics(self, event: StorageEvent, processing_time: float) -> None:
        """Record success metrics."""
        self.worker_metrics.messages_processed += 1
        self.worker_metrics.processing_time_total += processing_time
        self.worker_metrics.last_activity = time.time()

        self.otel_metrics.files_processed.add(
            1,
            {
                "queue": self.queue_size.value,
                "tenant_id": event.tenant_id,
                "event_type": event.event_type.value
            }
        )
        self.otel_metrics.processing_duration.record(
            processing_time,
            {"queue": self.queue_size.value}
        )
        self.otel_metrics.file_size_processed.record(
            event.metadata.file_size,
            {"queue": self.queue_size.value}
        )

    def _record_error_metrics(self, span, error: Exception, error_type: str = None) -> None:
        """Record error metrics and span attributes."""
        error_type = error_type or type(error).__name__

        self.otel_metrics.processing_errors.add(
            1,
            {"queue": self.queue_size.value, "error_type": error_type}
        )
        span.set_attribute("status", "error")
        span.set_attribute("error.type", error_type)
        span.set_attribute("error.message", str(error))
        span.record_exception(error)

    async def _process_event_business_logic(self, event: StorageEvent) -> None:
        """Core business logic for processing storage events.

        IMPORTANT: This worker processes ALL events it receives from the queue.
        Event filtering should be done at the router/publisher level (gRPC subscriber),
        not here. The worker is a consumer that trusts its upstream producers.
        """
        legacy_data = event.to_legacy_format()
        legacy_event = BaseStorageEvent(**legacy_data)

        if event.event_type.value == "delete":
            from uuid import NAMESPACE_DNS, uuid5
            file_id = str(uuid5(NAMESPACE_DNS, f"{legacy_event.tenant_id}:{legacy_event.file_path}"))
            await self.repository.delete_file(file_id)
        else:
            # Process all non-delete events (create, update, rename, etc.)
            await self.storage_worker.process_file(
                legacy_event.file_path,
                legacy_event.tenant_id,
                legacy_event.s3_key
            )
            self.worker_metrics.files_processed += 1

    async def _process_queue(self) -> None:
        """Main queue processing loop."""
        logger.info(f"Starting queue processing for {self.queue_size.value} queue")

        while self._running:
            try:
                # Fetch messages from pull subscriber
                raw_msgs = await self.subscriber.fetch(
                    batch=self.config["batch_size"],
                    timeout=self.config["timeout"]
                )

                # Convert to NATSMessage format
                messages = []
                for msg in raw_msgs:
                    from p8fs.services.nats.client import NATSMessage
                    nats_msg = NATSMessage(
                        subject=msg.subject,
                        data=msg.data,
                        reply=msg.reply,
                        headers=msg.headers,
                        metadata=msg.metadata.__dict__ if msg.metadata else None,
                        _original_msg=msg
                    )
                    messages.append(nats_msg)
                
                if not messages:
                    logger.debug(f"No messages received from {self.queue_size.value} queue")
                    continue

                logger.debug(f"Received {len(messages)} message(s) from {self.queue_size.value} queue")

                # Process each message
                for msg in messages:
                    if not self._running:
                        break

                    try:
                        await self._process_single_message(msg)
                        # Acknowledge message after successful processing
                        await self.client.ack_message(msg)
                        logger.debug(f"Message acknowledged successfully")
                        
                    except Exception as e:
                        logger.error(f"Failed to process message in {self.queue_size.value} queue: {e}")
                        # NACK message for retry
                        await self.client.nak_message(msg)
                        self.worker_metrics.messages_failed += 1
                        
            except TimeoutError:
                logger.debug(f"Message fetch timeout for {self.queue_size.value} queue")
                continue
            except Exception as e:
                logger.error(f"Error in {self.queue_size.value} queue processing: {e}")
                await asyncio.sleep(1)  # Brief pause before retry
                
        logger.info(f"Queue processing stopped for {self.queue_size.value}")
        
    async def _process_single_message(self, msg) -> None:
        """Process a single storage event message.

        Args:
            msg: NATS message containing storage event with trace context in headers
        """
        start_time = time.time()
        headers = msg.headers if hasattr(msg, 'headers') else None

        with continue_trace(headers, f"worker.{self.queue_size.value}.process_message") as span:
            try:
                raw_event_data = json.loads(msg.data.decode('utf-8'))
                logger.debug(f"Raw event data: {json.dumps(raw_event_data)}")

                try:
                    event = StorageEvent.from_raw_event(raw_event_data)
                except ValueError as e:
                    logger.warning(f"Skipping invalid event: {e}")
                    logger.debug(f"Failed to parse raw event: {json.dumps(raw_event_data)}")
                    span.set_attribute("status", "skipped")
                    span.set_attribute("skip_reason", str(e))
                    return

                self._record_event_attributes(span, event)

                logger.info(f"Processing {event.event_type.value} event: {event.path} ({event.metadata.file_size} bytes, tenant: {event.tenant_id})")

                await self._process_event_business_logic(event)

                processing_time = time.time() - start_time
                self._record_success_metrics(event, processing_time)

                span.set_attribute("status", "success")
                span.set_attribute("processing.duration", processing_time)

                logger.info(f"✅ Successfully processed: {event.path} ({processing_time:.2f}s)")

            except json.JSONDecodeError as e:
                self._record_error_metrics(span, e, "json_decode")
                logger.exception(f"❌ Failed to parse message as JSON: {e}")
                raise

            except Exception as e:
                self._record_error_metrics(span, e)
                # Try to extract file path from event if available
                file_info = "unknown file"
                try:
                    if 'event' in locals():
                        file_info = f"{event.path} (tenant: {event.tenant_id})"
                except:
                    pass
                logger.exception(f"❌ Failed to process {file_info}: {e}")
                raise
            
    async def get_status(self) -> dict[str, Any]:
        """Get worker status and metrics.
        
        Returns:
            Status dictionary with metrics and configuration
        """
        consumer_info = {}
        try:
            consumer_info = await self.consumer_manager.get_consumer_status()
            consumer_info = consumer_info.get(self.consumer_name, {})
        except Exception as e:
            logger.error(f"Failed to get consumer info: {e}")
            
        uptime = time.time() - self.worker_metrics.start_time if self.worker_metrics.start_time > 0 else 0
        
        return {
            "queue_size": self.queue_size.value,
            "status": self._status.value,
            "running": self._running,
            "tenant_id": self.tenant_id,
            "consumer_name": self.consumer_name,
            "uptime_seconds": uptime,
            "metrics": {
                "messages_processed": self.worker_metrics.messages_processed,
                "messages_failed": self.worker_metrics.messages_failed,
                "files_processed": self.worker_metrics.files_processed,
                "success_rate": self.worker_metrics.success_rate,
                "average_processing_time": self.worker_metrics.average_processing_time,
                "last_activity": self.worker_metrics.last_activity,
            },
            "consumer_info": consumer_info,
            "config": self.config,
        }
        
    async def health_check(self) -> dict[str, Any]:
        """Perform health check on worker.
        
        Returns:
            Health check results
        """
        health = {
            "healthy": True,
            "checks": {},
        }
        
        # Check NATS client connection
        try:
            health["checks"]["nats_connected"] = self.client.is_connected
            if not self.client.is_connected:
                health["healthy"] = False
        except Exception as e:
            health["checks"]["nats_connected"] = False
            health["checks"]["nats_error"] = str(e)
            health["healthy"] = False
            
        # Check repository connection
        try:
            if self.repository:
                # Simple query to test database connection - select 1 file
                await self.repository.select(limit=1)
                health["checks"]["repository_connected"] = True
            else:
                health["checks"]["repository_connected"] = False
                health["healthy"] = False
        except Exception as e:
            health["checks"]["repository_connected"] = False
            health["checks"]["repository_error"] = str(e)
            health["healthy"] = False
            
        # Check recent activity
        if self.worker_metrics.last_activity:
            time_since_activity = time.time() - self.worker_metrics.last_activity
            health["checks"]["recent_activity"] = time_since_activity < 300  # 5 minutes
            health["checks"]["seconds_since_activity"] = time_since_activity
        else:
            health["checks"]["recent_activity"] = False
            health["checks"]["seconds_since_activity"] = None
            
        return health


class WorkerManager:
    """Manages multiple storage workers for different queue sizes."""
    
    def __init__(self, nats_client: NATSClient, tenant_id: str):
        """Initialize worker manager.
        
        Args:
            nats_client: Connected NATS client
            tenant_id: Tenant ID for workers
        """
        self.client = nats_client
        self.tenant_id = tenant_id
        self.workers: dict[QueueSize, StorageEventWorker] = {}
        
    async def setup_worker(self, queue_size: QueueSize) -> StorageEventWorker:
        """Set up a worker for a specific queue size.
        
        Args:
            queue_size: Queue size to create worker for
            
        Returns:
            Configured worker instance
        """
        if queue_size in self.workers:
            logger.warning(f"Worker for {queue_size.value} already exists")
            return self.workers[queue_size]
            
        worker = StorageEventWorker(queue_size, self.client, self.tenant_id)
        await worker.setup()
        self.workers[queue_size] = worker
        
        logger.info(f"Set up {queue_size.value} worker")
        return worker
        
    async def start_worker(self, queue_size: QueueSize) -> None:
        """Start a worker for a specific queue size.
        
        Args:
            queue_size: Queue size to start worker for
        """
        if queue_size not in self.workers:
            await self.setup_worker(queue_size)
            
        await self.workers[queue_size].start()
        
    async def stop_worker(self, queue_size: QueueSize) -> None:
        """Stop a worker for a specific queue size.
        
        Args:
            queue_size: Queue size to stop worker for
        """
        if queue_size in self.workers:
            await self.workers[queue_size].stop()
            
    async def start_all_workers(self) -> None:
        """Start workers for all queue sizes."""
        tasks = []
        for queue_size in QueueSize:
            if queue_size not in self.workers:
                await self.setup_worker(queue_size)
            task = asyncio.create_task(self.workers[queue_size].start())
            tasks.append(task)
            
        await asyncio.gather(*tasks)
        
    async def stop_all_workers(self) -> None:
        """Stop all workers."""
        tasks = []
        for worker in self.workers.values():
            task = asyncio.create_task(worker.stop())
            tasks.append(task)
            
        await asyncio.gather(*tasks)
        
    async def get_status(self) -> dict[str, Any]:
        """Get status of all workers.
        
        Returns:
            Combined status dictionary
        """
        status = {
            "tenant_id": self.tenant_id,
            "workers": {},
            "summary": {
                "total_workers": len(self.workers),
                "running_workers": 0,
                "total_messages_processed": 0,
                "total_files_processed": 0,
            }
        }
        
        for queue_size, worker in self.workers.items():
            worker_status = await worker.get_status()
            status["workers"][queue_size.value] = worker_status
            
            if worker_status["running"]:
                status["summary"]["running_workers"] += 1
            status["summary"]["total_messages_processed"] += worker_status["metrics"]["messages_processed"]
            status["summary"]["total_files_processed"] += worker_status["metrics"]["files_processed"]
            
        return status