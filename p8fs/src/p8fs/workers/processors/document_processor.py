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


class AgentDocumentProcessor(DocumentProcessor):
    """Processor for agent JSON Schema documents."""

    def __init__(self, repo: TenantRepository):
        self.repo = repo

    def can_process(self, data: dict, content_type: str) -> bool:
        """Check if document is an agent (p8-type == 'agent' or kind == 'agent')."""
        p8_type = data.get("p8-type") or data.get("p8Type") or data.get("kind")
        return p8_type == "agent"

    async def process(self, data: dict, content_type: str, tenant_id: str, session_id: UUID | None) -> Dict[str, Any]:
        """Store agent as resource with category='agent'."""
        from uuid import uuid4, NAMESPACE_DNS, uuid5

        # Extract agent metadata
        name = data.get("short_name") or data.get("name") or data.get("title", "unnamed-agent")
        version = data.get("version", "1.0.0")
        description = data.get("description", "")
        fully_qualified_name = data.get("fully_qualified_name", f"user.agents.{name}")
        use_in_dreaming = data.get("use_in_dreaming", False)

        # Generate deterministic ID based on tenant and name for upsert
        resource_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:agent:{name}"))

        # Store full JSON schema as content
        content_str = json.dumps(data, indent=2)

        # Prepare resource record
        resource = {
            "id": resource_id,
            "tenant_id": tenant_id,
            "name": name,
            "category": "agent",
            "content": content_str,
            "summary": description[:500] if description else None,
            "ordinal": 0,
            "graph_paths": [],
            "metadata": {
                "processor": self.processor_name,
                "version": version,
                "fully_qualified_name": fully_qualified_name,
                "use_in_dreaming": use_in_dreaming,
                "short_name": name,
                "schema_type": "agent",
                "properties": list(data.get("properties", {}).keys())[:20] if "properties" in data else [],
                "tools": data.get("tools", []) if "tools" in data else [],
            }
        }

        # Upsert resource (update if exists, create otherwise)
        await self.repo.upsert(resource)

        logger.info(f"Stored agent '{name}' (version {version}) as resource {resource_id}")

        return {
            "resource_id": resource_id,
            "processor": self.processor_name,
            "agent_name": name,
            "version": version,
            "use_in_dreaming": use_in_dreaming
        }

    @property
    def processor_name(self) -> str:
        return "agent"


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
            AgentDocumentProcessor(self.repo),
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