"""Document processor delegation system for JSON/YAML documents."""

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID

import yaml
from p8fs_cluster.logging import get_logger

from p8fs.repository import TenantRepository

logger = get_logger(__name__)


class DocumentProcessor(ABC): 
    """Abstract base class for document processors."""
    
    @abstractmethod
    def can_process(self, data: dict, content_type: str) -> bool:
        """Check if this processor can handle the document."""
        pass
    
    @abstractmethod
    async def process(self, data: dict, content_type: str, tenant_id: str, session_id: UUID | None) -> Dict[str, Any]:
        """Process the document and return results."""
        pass
    
    @property
    @abstractmethod
    def processor_name(self) -> str:
        """Name of this processor."""
        pass


class EngramDocumentProcessor(DocumentProcessor):
    """Processor for Engram kind documents."""
    
    def __init__(self, repo: TenantRepository):
        from p8fs.models.engram.processor import EngramProcessor
        self.engram_processor = EngramProcessor(repo)
    
    def can_process(self, data: dict, content_type: str) -> bool:
        """Check if document is an Engram kind."""
        kind = data.get("kind") or data.get("p8Kind")
        return kind == "engram"
    
    async def process(self, data: dict, content_type: str, tenant_id: str, session_id: UUID | None) -> Dict[str, Any]:
        """Process Engram document using EngramProcessor."""
        # Convert back to string for EngramProcessor
        if content_type == "application/x-yaml":
            content = yaml.dump(data)
        else:
            content = json.dumps(data)
        
        return await self.engram_processor.process(content, content_type, tenant_id, session_id)
    
    @property
    def processor_name(self) -> str:
        return "engram"


class GenericDocumentProcessor(DocumentProcessor):
    """Fallback processor for generic JSON/YAML documents."""
    
    def __init__(self, repo: TenantRepository):
        self.repo = repo
    
    def can_process(self, data: dict, content_type: str) -> bool:
        """Can process any document as fallback."""
        return True
    
    async def process(self, data: dict, content_type: str, tenant_id: str, session_id: UUID | None) -> Dict[str, Any]:
        """Store document as generic resource."""
        from uuid import uuid4
        
        resource_id = uuid4()
        
        await self.repo.create_resource({
            "id": str(resource_id),
            "tenant_id": tenant_id,
            "session_id": str(session_id) if session_id else None,
            "content": json.dumps(data),
            "content_type": content_type,
            "metadata": {
                "processor": self.processor_name,
                "document_keys": list(data.keys())[:10]  # Store some metadata about the document
            }
        })
        
        return {"resource_id": str(resource_id), "processor": self.processor_name}
    
    @property
    def processor_name(self) -> str:
        return "generic"


class ProcessorRegistry:
    """Registry for document processors with delegation logic."""
    
    def __init__(self, repo: TenantRepository):
        self.repo = repo
        self.processors: List[DocumentProcessor] = []
        self._initialize_processors()
    
    def _initialize_processors(self):
        """Initialize default processors in priority order."""
        # Add processors in priority order (most specific first)
        self.processors = [
            EngramDocumentProcessor(self.repo),
            GenericDocumentProcessor(self.repo),  # Fallback processor
        ]
    
    def register_processor(self, processor: DocumentProcessor):
        """Register a custom processor (will be checked first)."""
        self.processors.insert(0, processor)
    
    def get_processor(self, data: dict, content_type: str) -> DocumentProcessor:
        """Get the first processor that can handle this document."""
        for processor in self.processors:
            if processor.can_process(data, content_type):
                return processor
        
        # Should never reach here due to GenericDocumentProcessor fallback
        return self.processors[-1]
    
    async def process_document(self, content: str, content_type: str, tenant_id: str, session_id: UUID | None = None) -> Dict[str, Any]:
        """Process a JSON/YAML document using the appropriate processor."""
        try:
            # Parse content
            if content_type == "application/x-yaml":
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)
            
            # Get appropriate processor
            processor = self.get_processor(data, content_type)
            
            logger.info(f"Processing document with {processor.processor_name} processor")
            
            # Process document
            result = await processor.process(data, content_type, tenant_id, session_id)
            result["processor_used"] = processor.processor_name
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing document: {e}")
            raise


# Convenience functions for backward compatibility
async def process_json_yaml_document(content: str, content_type: str, tenant_id: str, repo: TenantRepository, session_id: UUID | None = None) -> Dict[str, Any]:
    """Process a JSON/YAML document using the processor registry."""
    registry = ProcessorRegistry(repo)
    return await registry.process_document(content, content_type, tenant_id, session_id)