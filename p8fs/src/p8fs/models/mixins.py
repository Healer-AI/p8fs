"""Mixins for AbstractModel with additional functionality."""

import inspect
from collections.abc import Callable
from datetime import datetime
from typing import Any


class AbstractModelMixin:
    """Mixin providing utility methods for model introspection and metadata."""

    @classmethod
    def get_model_functions(cls) -> dict[str, Callable]:
        """Get all methods that can be exposed as functions/tools."""
        functions = {}
        
        for name, method in inspect.getmembers(cls, predicate=inspect.ismethod):
            if not name.startswith('_') and hasattr(method, '__annotations__'):
                functions[name] = method
        
        # Include class methods that are decorated as tools
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if hasattr(method, '_tool_spec') or hasattr(method, '_function_spec'):
                functions[name] = method
        
        return functions

    @classmethod
    def get_field_constraints(cls, field_name: str) -> dict[str, Any]:
        """Get validation constraints for a field."""
        field_info = cls.model_fields.get(field_name)
        if not field_info:
            return {}
        
        constraints = {}
        
        # Pydantic field constraints
        for attr in ['min_length', 'max_length', 'pattern', 'gt', 'ge', 'lt', 'le']:
            if hasattr(field_info, attr) and getattr(field_info, attr) is not None:
                constraints[attr] = getattr(field_info, attr)
        
        return constraints

    @classmethod
    def get_field_examples(cls, field_name: str) -> list[Any]:
        """Get example values for a field."""
        field_info = cls.model_fields.get(field_name)
        if not field_info or not field_info.json_schema_extra:
            return []
        
        examples = field_info.json_schema_extra.get('examples', [])
        if not isinstance(examples, list):
            examples = [examples]
        
        return examples

    @classmethod
    def get_model_version(cls) -> str:
        """Get model version for schema evolution."""
        config = getattr(cls, 'Config', None)
        if config and hasattr(config, 'version'):
            return config.version
        return '1.0.0'

    @classmethod
    def get_model_description(cls) -> str:
        """Get model description from docstring or config."""
        if cls.__doc__:
            return cls.__doc__.strip()
        
        config = getattr(cls, 'Config', None)
        if config and hasattr(config, 'description'):
            return config.description
        
        return f"{cls.__name__} model"

    @classmethod
    def get_model_tags(cls) -> list[str]:
        """Get tags for categorizing models."""
        config = getattr(cls, 'Config', None)
        if config and hasattr(config, 'tags'):
            return config.tags
        return []

    @classmethod
    def supports_full_text_search(cls) -> bool:
        """Check if model supports full-text search."""
        config = getattr(cls, 'Config', None)
        if config and hasattr(config, 'full_text_search'):
            return config.full_text_search
        
        # Auto-detect based on text fields
        for field_name, field_info in cls.model_fields.items():
            if field_info.annotation == str:
                metadata = cls.get_field_metadata(field_name)
                if metadata.get('searchable', False):
                    return True
        
        return False

    @classmethod
    def get_search_fields(cls) -> list[str]:
        """Get fields that should be included in full-text search."""
        search_fields = []
        
        for field_name, field_info in cls.model_fields.items():
            if field_info.annotation == str:
                metadata = cls.get_field_metadata(field_name)
                if metadata.get('searchable', False):
                    search_fields.append(field_name)
        
        return search_fields

    @classmethod
    def get_indexed_fields(cls) -> list[str]:
        """Get fields that should have database indexes."""
        indexed_fields = []
        
        for field_name, field_info in cls.model_fields.items():
            metadata = cls.get_field_metadata(field_name)
            if metadata.get('indexed', False):
                indexed_fields.append(field_name)
        
        # Always index the key field
        key_field = cls.get_model_key_field()
        if key_field not in indexed_fields:
            indexed_fields.append(key_field)
        
        return indexed_fields

    def update_timestamp(self):
        """Update the updated_at timestamp if field exists."""
        if hasattr(self, 'updated_at'):
            self.updated_at = datetime.utcnow()

    def get_changed_fields(self, other: 'AbstractModel') -> list[str]:
        """Get list of fields that differ from another instance."""
        if not isinstance(other, self.__class__):
            raise ValueError("Cannot compare with different model type")
        
        changed_fields = []
        current_data = self.model_dump()
        other_data = other.model_dump()
        
        for field_name in current_data.keys():
            if current_data[field_name] != other_data.get(field_name):
                changed_fields.append(field_name)
        
        return changed_fields

    def merge_from(self, other: 'AbstractModel', fields: list[str] | None = None):
        """Merge fields from another model instance."""
        if not isinstance(other, self.__class__):
            raise ValueError("Cannot merge from different model type")
        
        other_data = other.model_dump()
        
        if fields is None:
            fields = list(other_data.keys())
        
        for field_name in fields:
            if field_name in other_data and hasattr(self, field_name):
                setattr(self, field_name, other_data[field_name])
        
        self.update_timestamp()

    def validate_business_rules(self) -> list[str]:
        """Validate business rules and return list of errors."""
        errors = []
        
        # Subclasses can override this method to add custom validation
        # Example business rule validation would go here
        
        return errors