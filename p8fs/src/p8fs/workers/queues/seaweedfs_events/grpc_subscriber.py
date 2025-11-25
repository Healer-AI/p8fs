"""SeaweedFS gRPC event subscriber for real-time file system events.

This is the primary event processing strategy that provides real-time streaming
of metadata events from SeaweedFS using gRPC protocol.

CRITICAL: This implementation follows the exact patterns from the reference
implementation for production stability and compatibility.

LOCAL TESTING:

To test the gRPC subscriber locally before deploying to the cluster:

1. Port-forward required services:
   kubectl port-forward -n seaweed svc/seaweedfs-filer 8888:8888 &    # HTTP API
   kubectl port-forward -n seaweed svc/seaweedfs-filer 18888:18888 &  # gRPC
   kubectl port-forward -n p8fs svc/nats 4222:4222 &                  # NATS

2. Run the subscriber locally:
   cd p8fs
   env SEAWEEDFS_FILER_HOST=localhost \
       SEAWEEDFS_FILER_GRPC_PORT=18888 \
       WATCH_PATH_PREFIX=/buckets/ \
       P8FS_NATS_URL=nats://localhost:4222 \
       uv run python -m p8fs.workers.queues.seaweedfs_events grpc

3. Upload a test file to trigger an event:
   echo "Test file - $(date)" > /tmp/test.txt
   curl -F "file=@/tmp/test.txt" \
        "http://localhost:8888/buckets/tenant-test/test-$(date +%s).txt"

4. Verify the subscriber processes the event without errors:
   - Look for "Published <event_type> event for <path>" in the logs
   - No ERROR messages should appear
   - Event should be successfully published to NATS

This local testing approach catches issues before deployment and saves significant
time compared to deploying to the cluster for each change.
"""

import asyncio
import time
from datetime import datetime
from typing import Any

import grpc
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from .base import SeaweedFSEventProcessor
from .proto.seaweedfs import filer_pb2, filer_pb2_grpc

logger = get_logger(__name__)


class SeaweedFSgRPCSubscriber(SeaweedFSEventProcessor):
    """SeaweedFS gRPC-based event subscriber."""
    
    def __init__(self, 
                 filer_host: str = None,
                 filer_grpc_port: int = 18888,
                 path_prefix: str = "/buckets/",
                 client_name: str = None,
                 **kwargs):
        """Initialize gRPC subscriber.
        
        Args:
            filer_host: SeaweedFS filer hostname
            filer_grpc_port: SeaweedFS filer gRPC port
            path_prefix: Path prefix to monitor (default: /buckets/)
            client_name: Unique client identifier
            **kwargs: Additional arguments passed to base class
        """
        super().__init__(**kwargs)
        
        # Connection configuration
        self.filer_host = filer_host or getattr(config, 'seaweedfs_filer_host', 'localhost')
        self.filer_grpc_port = filer_grpc_port
        self.path_prefix = path_prefix
        self.client_name = client_name or f"p8fs-grpc-subscriber-{int(time.time())}"
        
        # gRPC client components
        self.channel: grpc.aio.Channel | None = None
        self.stub: filer_pb2_grpc.SeaweedFilerStub | None = None
        
    async def setup(self) -> None:
        """Set up gRPC connection and NATS streams."""
        await super().setup()
        
        # Create gRPC channel and stub
        self.channel = grpc.aio.insecure_channel(f"{self.filer_host}:{self.filer_grpc_port}")
        self.stub = filer_pb2_grpc.SeaweedFilerStub(self.channel)
        
        logger.info(f"gRPC subscriber configured for {self.filer_host}:{self.filer_grpc_port}")
        
    async def start(self) -> None:
        """Start gRPC event streaming with automatic reconnection."""
        if self.running:
            logger.warning("gRPC subscriber already running")
            return
            
        self.running = True
        logger.info(f"Starting SeaweedFS gRPC subscriber: {self.client_name}")
        
        # Main processing loop with reconnection logic
        while self.running:
            try:
                await self.subscribe_metadata()
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.warning("SeaweedFS gRPC unavailable, retrying in 5 seconds...")
                    await asyncio.sleep(5)
                    continue
                else:
                    logger.error(f"gRPC error: {e}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error in gRPC subscriber: {e}")
                if self.running:  # Only sleep if still supposed to be running
                    await asyncio.sleep(5)
                    
        logger.info("gRPC subscriber stopped")
        
    async def stop(self) -> None:
        """Stop gRPC event streaming."""
        logger.info("Stopping gRPC subscriber...")
        self.running = False
        
        if self.channel:
            await self.channel.close()
            
        await self.cleanup()
        
    async def subscribe_metadata(self) -> None:
        """Subscribe to SeaweedFS metadata events via gRPC streaming."""
        logger.info(f"Subscribing to metadata events with prefix: {self.path_prefix}")
        
        # Create subscription request (matches reference exactly)
        request = filer_pb2.SubscribeMetadataRequest(
            client_name=self.client_name,
            path_prefix=self.path_prefix,
            since_ns=int(time.time() * 1e9),  # Start from now
            client_id=hash(self.client_name) % (2**31),  # Generate client ID
            client_epoch=1,
        )
        
        logger.info(f"Starting metadata subscription: client_id={request.client_id}")
        
        # Stream metadata events
        try:
            async for response in self.stub.SubscribeMetadata(request):
                if not self.running:
                    break
                    
                try:
                    await self.process_metadata_event(response)
                except Exception as e:
                    logger.error(f"Error processing metadata event: {e}", exc_info=True)
                    # Continue processing other events - don't let one failure stop the stream
                    
        except grpc.RpcError as e:
            logger.error(f"gRPC streaming error: {e}")
            raise
        except Exception as e:
            logger.error(f"Metadata subscription error: {e}")
            raise
            
    async def process_metadata_event(self, response) -> None:
        """Process a single metadata event from SeaweedFS.
        
        Args:
            response: SubscribeMetadataResponse from SeaweedFS
        """
        directory = response.directory
        event_notification = response.event_notification
        timestamp_ns = response.ts_ns
        
        # Skip directory events - only process files (matches reference)
        if event_notification.new_entry and event_notification.new_entry.is_directory:
            logger.debug(f"Skipping directory creation: {directory}/{event_notification.new_entry.name}")
            return
            
        # Determine event type
        event_type = self.determine_event_type(event_notification)
        
        # Extract path information
        entry_name = ""
        if event_notification.new_entry:
            entry_name = event_notification.new_entry.name
        elif event_notification.old_entry:
            entry_name = event_notification.old_entry.name
            
        path = f"{directory.rstrip('/')}/{entry_name}" if entry_name else directory
        path = self.normalize_path(path)
        
        # Create event structure (matches reference exactly)
        event = {
            "type": event_type,
            "path": path,
            "directory": directory,
            "timestamp": datetime.fromtimestamp(timestamp_ns / 1e9).isoformat(),
            "timestamp_ns": timestamp_ns,
            "source": "seaweedfs-grpc",
        }
        
        # Extract tenant_id from path
        tenant_id = self.extract_tenant_id(path)
        if tenant_id:
            event["tenant_id"] = tenant_id
            
        # Add entry details if available
        if event_notification.new_entry:
            event["entry"] = self.entry_to_dict(event_notification.new_entry)

            # Extract file size and MIME type - use HasField() for protobuf optional fields
            if event_notification.new_entry.HasField("attributes"):
                attrs = event_notification.new_entry.attributes
                event["size"] = attrs.file_size if hasattr(attrs, "file_size") else 0
                event["mime_type"] = attrs.mime if hasattr(attrs, "mime") else ""
            else:
                event["size"] = 0
                event["mime_type"] = ""
                
        # Handle rename operations
        if event_notification.new_parent_path:
            event["new_parent_path"] = event_notification.new_parent_path
            event["old_path"] = path
            event["new_path"] = f"{event_notification.new_parent_path.rstrip('/')}/{entry_name}"
            
        # Add directory flag
        event["is_directory"] = (event_notification.new_entry and 
                               event_notification.new_entry.is_directory) if event_notification.new_entry else False
        
        # Publish event to NATS
        await self.publish_event(event)
        
        logger.info(f"Published {event_type} event for {path}")
        
    def determine_event_type(self, notification) -> str:
        """Determine event type from notification (matches reference exactly)."""
        if notification.old_entry and not notification.new_entry:
            return "delete"
        elif not notification.old_entry and notification.new_entry:
            return "create"
        elif notification.old_entry and notification.new_entry:
            if notification.new_parent_path:
                return "rename"
            else:
                return "update"
        else:
            return "unknown"
            
    def file_id_to_dict(self, file_id) -> dict[str, Any]:
        """Convert protobuf FileId to dictionary for JSON serialization."""
        if not file_id:
            return {}
        return {
            "volume_id": file_id.volume_id if hasattr(file_id, "volume_id") else 0,
            "file_key": file_id.file_key if hasattr(file_id, "file_key") else 0,
            "cookie": file_id.cookie if hasattr(file_id, "cookie") else 0,
        }

    def entry_to_dict(self, entry) -> dict[str, Any]:
        """Convert protobuf Entry to dictionary (matches reference exactly)."""
        result = {
            "name": entry.name,
            "is_directory": entry.is_directory,
            "chunks": len(entry.chunks),
        }
        
        # Add attributes if present - use hasattr() for safe protobuf field access
        if entry.HasField("attributes"):
            attrs = entry.attributes
            result["attributes"] = {
                "file_size": attrs.file_size if hasattr(attrs, "file_size") else 0,
                "mtime": attrs.mtime if hasattr(attrs, "mtime") else 0,
                "file_mode": attrs.file_mode if hasattr(attrs, "file_mode") else 0,
                "uid": attrs.uid if hasattr(attrs, "uid") else 0,
                "gid": attrs.gid if hasattr(attrs, "gid") else 0,
                "mime": attrs.mime if hasattr(attrs, "mime") else "",
                "replication": attrs.replication if hasattr(attrs, "replication") else "",
                "collection": attrs.collection if hasattr(attrs, "collection") else "",
                "ttl_sec": attrs.ttl_sec if hasattr(attrs, "ttl_sec") else 0,
                "disk_type": attrs.disk_type if hasattr(attrs, "disk_type") else "",
            }
        else:
            result["attributes"] = {}
            
        # Add extended attributes if present
        if entry.extended:
            result["extended"] = dict(entry.extended)
            
        # Add chunk details if present
        if entry.chunks:
            result["chunk_details"] = [
                {
                    "fid": self.file_id_to_dict(chunk.fid) if hasattr(chunk, "fid") else {},
                    "offset": chunk.offset if hasattr(chunk, "offset") else 0,
                    "size": chunk.size if hasattr(chunk, "size") else 0,
                    "mtime": chunk.mtime if hasattr(chunk, "mtime") else 0,
                    "e_tag": chunk.e_tag if hasattr(chunk, "e_tag") else "",
                    "source_fid": self.file_id_to_dict(chunk.source_fid) if hasattr(chunk, "source_fid") else {},
                    "crc": chunk.crc if hasattr(chunk, "crc") else 0,
                }
                for chunk in entry.chunks
            ]
        else:
            result["chunk_details"] = []
            
        return result