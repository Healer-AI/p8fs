"""
Structured Data Content Provider for JSON and YAML files.

This provider handles JSON and YAML files, with special processing for
files that contain a 'kind' attribute (e.g., Engrams).
"""

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from p8fs_node.models.content import ContentChunk, ContentMetadata, ContentType
from p8fs_node.providers.base import ContentProvider
from p8fs_node.providers.mixins import TextBasedProviderMixin

logger = logging.getLogger(__name__)


class StructuredDataContentProvider(TextBasedProviderMixin, ContentProvider):
    """Content provider for JSON and YAML files with special kind processing."""
    
    @property
    def supported_types(self) -> list[ContentType]:
        return [ContentType.JSON, ContentType.YAML]
        
    @property
    def provider_name(self) -> str:
        return "structured_data_provider"
        
    @classmethod
    def can_handle(cls, file_path: str | Path) -> bool:
        """Check if this provider can handle the given file."""
        path = Path(file_path)
        return path.suffix.lower() in ['.json', '.yaml', '.yml']
    
    def _can_process(self, file_path: Path) -> bool:
        """Check if this provider can process the given file."""
        return file_path.suffix.lower() in ['.json', '.yaml', '.yml']
        
    def supports_file(self, file_path: str | Path) -> bool:
        """Check if this provider specifically supports this file."""
        path = Path(file_path)
        return path.suffix.lower() in ['.json', '.yaml', '.yml']
    
    async def extract_text(self, content_path: str | Path) -> str:
        """
        Extract raw text content from structured data file.
        
        Args:
            content_path: Path to the JSON/YAML file
            
        Returns:
            Raw text content of the file
        """
        path = Path(content_path)
        
        if not path.exists():
            return f"[File not found: {content_path}]"
        
        try:
            # Read the raw text content
            return self._extract_text_safely(path, "utf-8")
        except Exception as e:
            logger.error(f"Error extracting text from structured file {content_path}: {e}")
            return f"[Structured data extraction failed: {str(e)}]"
    
    async def to_markdown_chunks(
        self, content_path: str | Path, extended: bool = False, **options: Any
    ) -> list[ContentChunk]:
        """Convert JSON/YAML to markdown chunks, with special kind processing."""
        path = Path(content_path)
        
        if not self._can_process(path):
            # Fallback to text processing
            return await super().to_markdown_chunks(content_path, extended, **options)
        
        try:
            # Parse the structured data
            with open(path, encoding='utf-8') as f:
                content = f.read()
                
            if path.suffix.lower() == '.json':
                data = json.loads(content)
                format_type = "json"
            else:  # .yaml or .yml
                data = yaml.safe_load(content)
                format_type = "yaml"
            
            # Check if this is a special kind document
            kind = data.get('kind') or data.get('p8Kind')
            if kind:
                logger.info(f"Processing {kind} document: {path}")
                # For now, process as regular structured data
                # In the future, this could delegate to specialized processors
            
            # Regular structured data processing
            return await self._process_regular_structured_data(
                data, content, path, format_type, **options
            )
            
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            logger.warning(f"Failed to parse {format_type} file {path}: {e}")
            # Fallback to text processing
            return await super().to_markdown_chunks(content_path, extended, **options)
    
    async def _process_regular_structured_data(
        self, 
        data: Any, 
        content: str, 
        path: Path, 
        format_type: str, 
        **options: Any
    ) -> list[ContentChunk]:
        """Process regular JSON/YAML data (not a special kind)."""
        # Convert structured data to markdown
        markdown_content = self._data_to_markdown(data, format_type, str(path))
        
        # Create chunks
        chunks = self._create_text_chunks(
            markdown_content, 
            path, 
            f"structured_data_{format_type}",
            **options
        )
        
        # Add structured data metadata
        for chunk in chunks:
            chunk.metadata.update({
                "format": format_type,
                "data_type": type(data).__name__,
                "is_structured": True
            })
        
        return chunks
    
    def _data_to_markdown(self, data: Any, format_type: str, file_path: str) -> str:
        """Convert structured data to markdown representation."""
        lines = [
            f"# {format_type.upper()} Data: {Path(file_path).name}",
            ""
        ]
        
        if isinstance(data, dict):
            lines.extend(self._dict_to_markdown(data))
        elif isinstance(data, list):
            lines.extend(self._list_to_markdown(data))
        else:
            lines.extend([
                f"**Value:** `{data}`",
                f"**Type:** {type(data).__name__}"
            ])
        
        return "\n".join(lines)
    
    def _dict_to_markdown(self, data: dict, level: int = 0) -> list[str]:
        """Convert dictionary to markdown."""
        lines = []
        indent = "  " * level
        
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{indent}**{key}:**")
                lines.extend(self._dict_to_markdown(value, level + 1))
            elif isinstance(value, list):
                lines.append(f"{indent}**{key}:** (list)")
                lines.extend(self._list_to_markdown(value, level + 1))
            else:
                lines.append(f"{indent}**{key}:** `{value}`")
        
        return lines
    
    def _list_to_markdown(self, data: list, level: int = 0) -> list[str]:
        """Convert list to markdown."""
        lines = []
        indent = "  " * level
        
        for i, item in enumerate(data):
            if isinstance(item, dict):
                lines.append(f"{indent}{i + 1}.")
                lines.extend(self._dict_to_markdown(item, level + 1))
            elif isinstance(item, list):
                lines.append(f"{indent}{i + 1}. (nested list)")
                lines.extend(self._list_to_markdown(item, level + 1))
            else:
                lines.append(f"{indent}{i + 1}. `{item}`")
        
        return lines
    
    async def to_metadata(
        self,
        content_path: str | Path,
        markdown_chunks: list[ContentChunk] | None = None,
    ) -> ContentMetadata:
        """Extract metadata from structured data files."""
        path = Path(content_path)
        
        # Get base metadata
        metadata = self._create_base_metadata(path, markdown_chunks)
        
        if not self._can_process(path):
            return metadata
        
        try:
            # Parse and extract structured data metadata
            with open(path, encoding='utf-8') as f:
                if path.suffix.lower() == '.json':
                    data = json.load(f)
                    metadata.mime_type = "application/json"
                else:
                    data = yaml.safe_load(f)
                    metadata.mime_type = "text/x-yaml"
            
            # Add structured data specific metadata
            metadata.properties.update({
                "data_type": type(data).__name__,
                "is_structured": True
            })
            
            # Check for special kind
            kind = data.get('kind') or data.get('p8Kind')
            if kind:
                metadata.properties["kind"] = kind
            
            # Extract title from structured data
            if isinstance(data, dict):
                # Try various title fields
                for title_field in ['name', 'title', 'metadata.name']:
                    if '.' in title_field:
                        # Handle nested fields like 'metadata.name'
                        parts = title_field.split('.')
                        value = data
                        for part in parts:
                            if isinstance(value, dict) and part in value:
                                value = value[part]
                            else:
                                value = None
                                break
                        if value:
                            metadata.title = str(value)
                            break
                    elif title_field in data:
                        metadata.title = str(data[title_field])
                        break
            
        except Exception as e:
            logger.warning(f"Failed to extract metadata from {path}: {e}")
        
        return metadata