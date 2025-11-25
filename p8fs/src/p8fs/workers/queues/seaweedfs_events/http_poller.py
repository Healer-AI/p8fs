"""SeaweedFS HTTP-based event detection via polling.

This is a fallback strategy when gRPC is unavailable. It polls the SeaweedFS
HTTP API and uses MD5 hashing to detect file changes.

Less efficient than gRPC but more compatible with different SeaweedFS deployments.
"""

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import aiohttp
from p8fs_cluster.config.settings import config

from .base import SeaweedFSEventProcessor

logger = logging.getLogger(__name__)


class SeaweedFSHTTPPoller(SeaweedFSEventProcessor):
    """HTTP-based SeaweedFS event detection via polling."""
    
    def __init__(self,
                 filer_host: str = None,
                 filer_http_port: int = 8888,
                 poll_interval: float = 5.0,
                 path_prefix: str = "/buckets/",
                 **kwargs):
        """Initialize HTTP poller.
        
        Args:
            filer_host: SeaweedFS filer hostname
            filer_http_port: SeaweedFS filer HTTP port
            poll_interval: Polling interval in seconds
            path_prefix: Path prefix to monitor
            **kwargs: Additional arguments passed to base class
        """
        super().__init__(**kwargs)
        
        # Connection configuration
        self.filer_host = filer_host or getattr(config, 'seaweedfs_filer_host', 'localhost')
        self.filer_http_port = filer_http_port
        self.base_url = f"http://{self.filer_host}:{self.filer_http_port}"
        self.poll_interval = poll_interval
        self.path_prefix = path_prefix
        
        # State tracking
        self.file_hashes: dict[str, str] = {}  # path -> md5 hash
        self.session: aiohttp.ClientSession | None = None
        
    async def setup(self) -> None:
        """Set up HTTP session and NATS streams."""
        await super().setup()
        
        # Create HTTP session
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=10)
        )
        
        logger.info(f"HTTP poller configured for {self.base_url}")
        
    async def start(self) -> None:
        """Start HTTP polling loop."""
        if self.running:
            logger.warning("HTTP poller already running")
            return
            
        self.running = True
        logger.info(f"Starting SeaweedFS HTTP poller with {self.poll_interval}s interval")
        
        try:
            # Initial scan to populate file hashes
            await self.scan_directory(self.path_prefix, initial=True)
            
            # Main polling loop
            while self.running:
                try:
                    await self.scan_directory(self.path_prefix)
                    await asyncio.sleep(self.poll_interval)
                except Exception as e:
                    logger.error(f"Error during polling scan: {e}")
                    await asyncio.sleep(self.poll_interval)
                    
        except Exception as e:
            logger.error(f"HTTP poller failed: {e}")
            raise
        finally:
            self.running = False
            
        logger.info("HTTP poller stopped")
        
    async def stop(self) -> None:
        """Stop HTTP polling."""
        logger.info("Stopping HTTP poller...")
        self.running = False
        
        if self.session:
            await self.session.close()
            
        await self.cleanup()
        
    async def scan_directory(self, path: str, initial: bool = False) -> None:
        """Scan directory for file changes.
        
        Args:
            path: Directory path to scan
            initial: True if this is the initial scan (don't generate events)
        """
        try:
            entries = await self.list_directory(path)
            current_files = set()
            
            for entry in entries:
                if entry.get("is_directory", False):
                    # Recursively scan subdirectories
                    subdir_path = f"{path.rstrip('/')}/{entry['name']}"
                    await self.scan_directory(subdir_path, initial)
                else:
                    # Process file
                    file_path = f"{path.rstrip('/')}/{entry['name']}"
                    current_files.add(file_path)
                    
                    if not initial:
                        await self.check_file_changes(file_path, entry)
                    else:
                        # Store initial hash without generating events
                        file_hash = await self.get_file_hash(file_path)
                        if file_hash:
                            self.file_hashes[file_path] = file_hash
                            
            # Detect deleted files (only if not initial scan)
            if not initial:
                # Find files that were tracked but no longer exist
                path_files = {f for f in self.file_hashes.keys() if f.startswith(path)}
                deleted_files = path_files - current_files
                
                for deleted_path in deleted_files:
                    await self.generate_event("delete", deleted_path)
                    del self.file_hashes[deleted_path]
                    
        except Exception as e:
            logger.error(f"Error scanning directory {path}: {e}")
            
    async def list_directory(self, path: str) -> list:
        """List directory contents via HTTP API.
        
        Args:
            path: Directory path to list
            
        Returns:
            List of directory entries
        """
        url = urljoin(self.base_url, path.lstrip('/'))
        
        async with self.session.get(url, params={"pretty": "1"}) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("Entries", [])
            elif response.status == 404:
                # Directory doesn't exist
                return []
            else:
                response.raise_for_status()
                return []
                
    async def get_file_hash(self, path: str) -> str | None:
        """Get MD5 hash of file content.
        
        Args:
            path: File path
            
        Returns:
            MD5 hash string or None if file cannot be read
        """
        try:
            url = urljoin(self.base_url, path.lstrip('/'))
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    return hashlib.md5(content).hexdigest()
                else:
                    return None
                    
        except Exception as e:
            logger.debug(f"Could not get hash for {path}: {e}")
            return None
            
    async def check_file_changes(self, path: str, entry: dict[str, Any]) -> None:
        """Check if file has changed and generate appropriate events.
        
        Args:
            path: File path
            entry: Directory entry information
        """
        current_hash = await self.get_file_hash(path)
        if not current_hash:
            return
            
        previous_hash = self.file_hashes.get(path)
        
        if previous_hash is None:
            # New file
            await self.generate_event("create", path, entry)
            self.file_hashes[path] = current_hash
        elif previous_hash != current_hash:
            # Modified file
            await self.generate_event("update", path, entry)
            self.file_hashes[path] = current_hash
            
    async def generate_event(self, event_type: str, path: str, entry: dict[str, Any] = None) -> None:
        """Generate and publish storage event.
        
        Args:
            event_type: Type of event (create, update, delete)
            path: File path
            entry: Optional directory entry information
        """
        # Normalize path
        path = self.normalize_path(path)
        
        # Extract tenant ID
        tenant_id = self.extract_tenant_id(path)
        if not tenant_id:
            logger.debug(f"Skipping non-tenant path: {path}")
            return
            
        # Create event
        event = {
            "type": event_type,
            "path": path,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "seaweedfs-http-poller",
            "tenant_id": tenant_id,
        }
        
        # Add entry information if available
        if entry:
            event["size"] = entry.get("Size", 0)
            event["mtime"] = entry.get("Mtime", 0)
            event["mode"] = entry.get("Mode", 0)
            
        # Publish event
        await self.publish_event(event)
        
        logger.info(f"Generated {event_type} event for {path}")