"""Storage event worker for processing files from size-specific queues.

Integrates with existing storage worker functionality while managing
NATS queue processing for different file sizes.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from p8fs.repository import TenantRepository
from p8fs.services.nats import ConsumerManager, NATSClient
from p8fs.workers.storage import StorageEvent as BaseStorageEvent
from p8fs.workers.storage import StorageWorker

from .config import ConsumerNames, QueueSize, WorkerConfig
from .models import StorageEvent

logger = logging.getLogger(__name__)


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
        self.metrics = WorkerMetrics()
        
    async def setup(self) -> None:
        """Set up worker components."""
        logger.info(f"Setting up {self.queue_size.value} storage worker for tenant {self.tenant_id}")

        self._status = WorkerStatus.STARTING

        # Initialize storage worker with tenant_id
        self.storage_worker = StorageWorker(self.tenant_id)

        # Keep reference to repository for health checks
        from p8fs.models.p8 import Files
        self.repository = TenantRepository(Files, tenant_id=self.tenant_id)

        # Ensure stream exists
        logger.info(f"Ensuring stream {self.stream_name} with subject {self.subject}")
        stream_success = await self.client.ensure_stream(self.stream_name, [self.subject])
        if not stream_success:
            raise RuntimeError(f"Failed to create/verify stream {self.stream_name}")

        # Create pull subscriber (this ensures consumer exists and creates the subscription)
        logger.info(f"Creating pull subscriber for consumer {self.consumer_name}")
        self.subscriber = await self.client.create_pull_subscriber(
            self.stream_name,
            self.consumer_name,
            self.subject
        )

        self.metrics.start_time = time.time()
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
                    
                # Process each message
                for msg in messages:
                    if not self._running:
                        break
                        
                    try:
                        await self._process_single_message(msg)
                        # Acknowledge message after successful processing
                        await self.client.ack_message(msg)
                        
                    except Exception as e:
                        logger.error(f"Failed to process message in {self.queue_size.value} queue: {e}")
                        # NACK message for retry
                        await self.client.nak_message(msg)
                        self.metrics.messages_failed += 1
                        
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
            msg: NATS message containing storage event
        """
        start_time = time.time()
        
        try:
            # Parse storage event data
            raw_event_data = json.loads(msg.data.decode('utf-8'))
            
            # Create validated StorageEvent
            try:
                event = StorageEvent.from_raw_event(raw_event_data)
            except ValueError as e:
                logger.debug(f"Skipping invalid event: {e}")
                return  # Skip invalid events without error
            
            logger.debug(f"Processing {event.event_type.value} for {event.path} ({event.metadata.file_size} bytes)")
            
            # Convert to legacy format for existing storage worker
            legacy_data = event.to_legacy_format()
            legacy_event = BaseStorageEvent(**legacy_data)
            
            # Process using existing storage worker logic
            if event.event_type.value in ["create", "update"]:
                await self.storage_worker.process_file(
                    legacy_event.file_path,
                    legacy_event.tenant_id,
                    legacy_event.s3_key
                )
                self.metrics.files_processed += 1
                
            elif event.event_type.value == "delete":
                # Handle file deletion
                from uuid import NAMESPACE_DNS, uuid5
                file_id = str(uuid5(NAMESPACE_DNS, f"{legacy_event.tenant_id}:{legacy_event.file_path}"))
                await self.repository.delete_file(file_id)
                
            # Update metrics
            processing_time = time.time() - start_time
            self.metrics.messages_processed += 1
            self.metrics.processing_time_total += processing_time
            self.metrics.last_activity = time.time()
            
            logger.info(f"Processed {event.path} in {processing_time:.2f}s")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message as JSON: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to process storage event: {e}")
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
            
        uptime = time.time() - self.metrics.start_time if self.metrics.start_time > 0 else 0
        
        return {
            "queue_size": self.queue_size.value,
            "status": self._status.value,
            "running": self._running,
            "tenant_id": self.tenant_id,
            "consumer_name": self.consumer_name,
            "uptime_seconds": uptime,
            "metrics": {
                "messages_processed": self.metrics.messages_processed,
                "messages_failed": self.metrics.messages_failed,
                "files_processed": self.metrics.files_processed,
                "success_rate": self.metrics.success_rate,
                "average_processing_time": self.metrics.average_processing_time,
                "last_activity": self.metrics.last_activity,
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
        if self.metrics.last_activity:
            time_since_activity = time.time() - self.metrics.last_activity
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