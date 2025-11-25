"""SeaweedFS event capturer for debugging and testing.

This utility captures raw protobuf events from SeaweedFS and serializes them
to JSON for analysis and testing purposes.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import grpc
from p8fs_cluster.config.settings import config

from .base import SeaweedFSEventProcessor
from .proto.seaweedfs import filer_pb2, filer_pb2_grpc

logger = logging.getLogger(__name__)


class SeaweedFSEventCapturer(SeaweedFSEventProcessor):
    """Captures and saves SeaweedFS events for debugging."""
    
    def __init__(self,
                 filer_host: str = None,
                 filer_grpc_port: int = 18888,
                 path_prefix: str = "/buckets/",
                 output_dir: str = "./seaweedfs_events",
                 client_name: str = None,
                 **kwargs):
        """Initialize event capturer.
        
        Args:
            filer_host: SeaweedFS filer hostname
            filer_grpc_port: SeaweedFS filer gRPC port
            path_prefix: Path prefix to monitor
            output_dir: Directory to save captured events
            client_name: Unique client identifier
            **kwargs: Additional arguments passed to base class
        """
        super().__init__(**kwargs)
        
        # Connection configuration
        self.filer_host = filer_host or getattr(config, 'seaweedfs_filer_host', 'localhost')
        self.filer_grpc_port = filer_grpc_port
        self.path_prefix = path_prefix
        self.client_name = client_name or f"p8fs-event-capturer-{int(time.time())}"
        
        # Output configuration
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # gRPC client components
        self.channel: grpc.aio.Channel | None = None
        self.stub: filer_pb2_grpc.SeaweedFilerStub | None = None
        self.event_count = 0
        
    async def setup(self) -> None:
        """Set up gRPC connection."""
        # Don't set up NATS - we're just capturing events
        
        # Create gRPC channel and stub
        self.channel = grpc.aio.insecure_channel(f"{self.filer_host}:{self.filer_grpc_port}")
        self.stub = filer_pb2_grpc.SeaweedFilerStub(self.channel)
        
        logger.info(f"Event capturer configured for {self.filer_host}:{self.filer_grpc_port}")
        logger.info(f"Saving events to: {self.output_dir}")
        
    async def start(self) -> None:
        """Start capturing events."""
        if self.running:
            logger.warning("Event capturer already running")
            return
            
        self.running = True
        logger.info(f"Starting SeaweedFS event capturer: {self.client_name}")
        
        try:
            await self.capture_events()
        except KeyboardInterrupt:
            logger.info("Capture interrupted by user")
        except Exception as e:
            logger.error(f"Event capturer failed: {e}")
            raise
        finally:
            self.running = False
            
        logger.info(f"Event capturer stopped. Captured {self.event_count} events")
        
    async def stop(self) -> None:
        """Stop capturing events."""
        logger.info("Stopping event capturer...")
        self.running = False
        
        if self.channel:
            await self.channel.close()
            
    async def capture_events(self) -> None:
        """Capture events from SeaweedFS."""
        logger.info(f"Starting event capture with prefix: {self.path_prefix}")
        
        # Create subscription request
        request = filer_pb2.SubscribeMetadataRequest(
            client_name=self.client_name,
            path_prefix=self.path_prefix,
            since_ns=int(time.time() * 1e9),  # Start from now
            client_id=hash(self.client_name) % (2**31),
            client_epoch=1,
        )
        
        logger.info(f"Starting metadata subscription: client_id={request.client_id}")
        
        # Stream and capture events
        async for response in self.stub.SubscribeMetadata(request):
            if not self.running:
                break
                
            try:
                await self.save_event(response)
                self.event_count += 1
                
                if self.event_count % 10 == 0:
                    logger.info(f"Captured {self.event_count} events")
                    
            except Exception as e:
                logger.error(f"Error saving event: {e}")
                
    async def save_event(self, response) -> None:
        """Save event response to disk.
        
        Args:
            response: SubscribeMetadataResponse from SeaweedFS
        """
        timestamp = int(time.time() * 1000)  # milliseconds
        filename = f"event_{timestamp}_{self.event_count:06d}.json"
        filepath = self.output_dir / filename
        
        # Convert protobuf to dictionary
        event_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_count": self.event_count,
            "directory": response.directory,
            "ts_ns": response.ts_ns,
            "event_notification": self.event_notification_to_dict(response.event_notification),
        }
        
        # Save to file
        with filepath.open('w') as f:
            json.dump(event_data, f, indent=2, default=str)
            
        logger.debug(f"Saved event to {filename}")
        
    def event_notification_to_dict(self, notification) -> dict:
        """Convert EventNotification protobuf to dictionary."""
        result = {
            "delete_chunks": notification.delete_chunks,
            "new_parent_path": notification.new_parent_path,
            "is_from_other_cluster": notification.is_from_other_cluster,
        }
        
        # Add old entry if present
        if notification.old_entry:
            result["old_entry"] = self.entry_to_dict(notification.old_entry)
            
        # Add new entry if present
        if notification.new_entry:
            result["new_entry"] = self.entry_to_dict(notification.new_entry)
            
        # Add signatures
        if notification.signatures:
            result["signatures"] = [int(sig) for sig in notification.signatures]
            
        return result
        
    def entry_to_dict(self, entry) -> dict:
        """Convert Entry protobuf to dictionary."""
        result = {
            "name": entry.name,
            "is_directory": entry.is_directory,
            "chunks": len(entry.chunks),
        }
        
        # Add attributes if present
        if entry.HasField("attributes"):
            attrs = entry.attributes
            result["attributes"] = {
                "file_size": getattr(attrs, 'file_size', 0),
                "mtime": getattr(attrs, 'mtime', 0),
                "file_mode": getattr(attrs, 'file_mode', 0),
                "uid": getattr(attrs, 'uid', 0),
                "gid": getattr(attrs, 'gid', 0),
                "mime": getattr(attrs, 'mime', ''),
                "replication": getattr(attrs, 'replication', ''),
                "collection": getattr(attrs, 'collection', ''),
                "ttl_sec": getattr(attrs, 'ttl_sec', 0),
                "disk_type": getattr(attrs, 'disk_type', ''),
            }
            
        # Add extended attributes if present
        if entry.extended:
            result["extended"] = dict(entry.extended)
            
        # Add chunk details if present
        if entry.chunks:
            result["chunk_details"] = [
                {
                    "fid": chunk.fid,
                    "offset": chunk.offset,
                    "size": chunk.size,
                    "mtime": chunk.mtime,
                    "e_tag": chunk.e_tag,
                    "source_fid": chunk.source_fid,
                    "crc": chunk.crc,
                }
                for chunk in entry.chunks
            ]
            
        # Add content if small file
        if entry.content:
            try:
                result["content"] = entry.content.decode('utf-8')
            except UnicodeDecodeError:
                result["content"] = f"<binary content: {len(entry.content)} bytes>"
                
        return result
        
    async def publish_event(self, event: dict) -> None:
        """Override to prevent publishing - we're just capturing."""
        pass