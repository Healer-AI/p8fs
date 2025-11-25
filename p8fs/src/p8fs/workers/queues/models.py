"""Data models for P8FS storage events."""

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class StorageEventType(str, Enum):
    """Storage event types."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RENAME = "rename"


@dataclass(frozen=True)
class StoragePathInfo:
    """Structured storage path information."""
    
    full_path: str
    tenant_id: str | None = None
    bucket: str | None = None
    category: str | None = None
    file_path: str | None = None
    is_tenant_path: bool = False
    is_directory: bool = False
    
    @classmethod
    def from_full_path(cls, path: str) -> "StoragePathInfo":
        """Parse a full path into structured components.
        
        Args:
            path: Full storage path
            
        Returns:
            StoragePathInfo with parsed components
        """
        # Remove leading slash if present
        clean_path = path.lstrip('/')
        
        # Check if it's a tenant path: buckets/{tenant_id}/...
        tenant_match = re.match(r'^buckets/([^/]+)/(.*)$', clean_path)
        
        if tenant_match:
            tenant_id = tenant_match.group(1)
            remaining_path = tenant_match.group(2)
            
            # Parse remaining path for category/file structure
            parts = remaining_path.split('/', 1)
            category = parts[0] if parts else None
            file_path = parts[1] if len(parts) > 1 else None
            
            return cls(
                full_path=path,
                tenant_id=tenant_id,
                bucket="buckets",
                category=category,
                file_path=file_path,
                is_tenant_path=True,
                is_directory=path.endswith('/') or not file_path
            )
        else:
            return cls(
                full_path=path,
                is_tenant_path=False,
                is_directory=path.endswith('/')
            )


@dataclass
class StorageEventMetadata:
    """Storage event metadata."""
    
    file_size: int = 0
    content_type: str | None = None
    last_modified: str | None = None
    etag: str | None = None
    source: str = "unknown"
    
    def __post_init__(self):
        """Validate after initialization."""
        if self.file_size < 0:
            raise ValueError(f"file_size must be >= 0, got {self.file_size}")
    
    
@dataclass
class StorageEvent:
    """Validated storage event with structured data."""
    
    event_type: StorageEventType
    path: str
    path_info: StoragePathInfo
    metadata: StorageEventMetadata
    tenant_id: str
    relative_path: str
    full_path: str
    timestamp: float
    
    def __post_init__(self):
        """Validate after initialization."""
        if not self.path:
            raise ValueError("path cannot be empty")
        if not self.tenant_id:
            raise ValueError("tenant_id cannot be empty")
    
    @classmethod
    def _normalize_event_type(cls, event_type_str: str) -> StorageEventType:
        """Normalize event type string to enum."""
        # Handle common aliases
        type_map = {
            "create": StorageEventType.CREATE,
            "put": StorageEventType.CREATE,
            "upload": StorageEventType.CREATE,
            "update": StorageEventType.UPDATE,
            "modify": StorageEventType.UPDATE,
            "delete": StorageEventType.DELETE,
            "remove": StorageEventType.DELETE,
            "rename": StorageEventType.RENAME,
            "move": StorageEventType.RENAME,
        }
        
        normalized = type_map.get(event_type_str.lower())
        if normalized:
            return normalized
            
        # Try direct enum lookup
        try:
            return StorageEventType(event_type_str.lower())
        except ValueError:
            raise ValueError(f"Unsupported event type: {event_type_str}")
    
    @classmethod
    def _extract_tenant_id(cls, path: str, provided_tenant_id: str | None = None) -> str:
        """Extract tenant ID from path."""
        if provided_tenant_id:
            return provided_tenant_id
            
        match = re.match(r'^/?buckets/([^/]+)/', path)
        if match:
            return match.group(1)
            
        raise ValueError(f"Cannot extract tenant_id from path: {path}")
        
    @classmethod 
    def _extract_relative_path(cls, path_info: StoragePathInfo) -> str:
        """Extract relative path within tenant bucket."""
        if path_info.is_tenant_path:
            if path_info.category and path_info.file_path:
                return f"{path_info.category}/{path_info.file_path}"
            elif path_info.category:
                return path_info.category
        return ""
        
    @classmethod
    def from_raw_event(cls, raw_event: dict[str, Any]) -> "StorageEvent":
        """Create StorageEvent from raw event data.
        
        Args:
            raw_event: Raw event dictionary
            
        Returns:
            Validated StorageEvent instance
            
        Raises:
            ValueError: If event data is invalid or unsupported
        """
        # Extract event type with fallbacks
        event_type_str = raw_event.get("event_type", raw_event.get("operation", raw_event.get("type", "unknown")))
        event_type = cls._normalize_event_type(event_type_str)
        
        # Extract path with fallbacks
        path = raw_event.get("path", raw_event.get("key", raw_event.get("entry", {}).get("FullPath", "")))
        if not path:
            raise ValueError("No path found in event data")
            
        # Parse path information
        path_info = StoragePathInfo.from_full_path(path)
        
        # Validate tenant paths only
        if not path_info.is_tenant_path:
            raise ValueError(f"Non-tenant paths not supported: {path}")
            
        # Skip directory events
        if path_info.is_directory:
            raise ValueError(f"Directory events not supported: {path}")
            
        # Build metadata - extract file_size from nested structure
        # Try multiple locations for file_size
        file_size = raw_event.get("size", 0)
        if not file_size:
            file_size = raw_event.get("file_size", 0)
        if not file_size:
            # SeaweedFS format: entry.attributes.file_size
            entry = raw_event.get("entry", {})
            attributes = entry.get("attributes", {})
            file_size = attributes.get("file_size", 0)

        # Ensure file_size is an integer (not string)
        try:
            file_size = int(file_size) if file_size else 0
        except (ValueError, TypeError):
            file_size = 0

        metadata = StorageEventMetadata(
            file_size=file_size,
            content_type=raw_event.get("content_type", raw_event.get("mime_type")),
            last_modified=raw_event.get("last_modified", raw_event.get("timestamp")),
            etag=raw_event.get("etag"),
            source=raw_event.get("source", "seaweedfs")
        )

        # Extract tenant ID and relative path
        tenant_id = cls._extract_tenant_id(path, path_info.tenant_id)
        relative_path = cls._extract_relative_path(path_info)

        # Ensure timestamp is a float, use current time if missing/invalid
        timestamp_value = raw_event.get("timestamp")
        try:
            timestamp = float(timestamp_value) if timestamp_value else time.time()
        except (ValueError, TypeError):
            timestamp = time.time()

        # Create validated event
        return cls(
            event_type=event_type,
            path=path,
            path_info=path_info,
            metadata=metadata,
            tenant_id=tenant_id,
            relative_path=relative_path,
            full_path=path,
            timestamp=timestamp
        )
        
    def should_process(self) -> bool:
        """Check if this event should be processed.
        
        Returns:
            True if event should be processed
        """
        # Skip multipart uploads (temporary files)
        if "uploadId=" in self.path:
            return False
            
        # Only process tenant-scoped paths
        if not self.path_info.is_tenant_path:
            return False
            
        # Skip directory events
        if self.path_info.is_directory:
            return False
            
        # Only process create and update operations
        if self.event_type not in [StorageEventType.CREATE, StorageEventType.UPDATE]:
            return False
            
        return True
        
    def to_legacy_format(self) -> dict[str, Any]:
        """Convert to legacy StorageEvent format for existing workers.
        
        Returns:
            Dictionary in legacy format
        """
        return {
            "tenant_id": self.tenant_id,
            "file_path": self.relative_path,
            "operation": self.event_type.value,
            "size": self.metadata.file_size,
            "mime_type": self.metadata.content_type,
            "s3_key": self.path
        }