"""Comprehensive unit tests for type mapping including JSONB detection.

This test ensures that Python type annotations are correctly mapped to SQL types,
especially for complex types like dict, List, Optional, and Union types.
"""

from typing import Dict, List, Optional, Any, Union
from uuid import UUID

import pytest

from p8fs.providers.postgresql import PostgreSQLProvider
from p8fs.providers.tidb import TiDBProvider
from p8fs.utils.typing import TypeInspector


class TestTypeMapping:
    """Comprehensive tests for type mapping."""
    
    @pytest.fixture
    def postgresql_provider(self):
        """Create a PostgreSQL provider instance."""
        return PostgreSQLProvider()
    
    @pytest.fixture
    def tidb_provider(self):
        """Create a TiDB provider instance."""
        return TiDBProvider()
    
    @pytest.fixture
    def type_inspector(self):
        """Create a TypeInspector instance."""
        return TypeInspector()
    
    def test_postgresql_basic_types(self, postgresql_provider):
        """Test basic Python type to PostgreSQL mapping."""
        provider = postgresql_provider
        
        # Basic types
        assert provider.map_python_type(str) == 'TEXT'
        assert provider.map_python_type(int) == 'BIGINT'
        assert provider.map_python_type(float) == 'DOUBLE PRECISION'
        assert provider.map_python_type(bool) == 'BOOLEAN'
        assert provider.map_python_type(UUID) == 'UUID'
    
    def test_postgresql_json_types(self, postgresql_provider):
        """Test JSON type mapping for PostgreSQL."""
        provider = postgresql_provider
        
        # Dict types should map to JSONB
        assert provider.map_python_type(dict) == 'JSONB'
        assert provider.map_python_type(Dict) == 'JSONB'
        assert provider.map_python_type(Dict[str, Any]) == 'JSONB'
        assert provider.map_python_type(dict[str, Any]) == 'JSONB'  # Python 3.9+ syntax
        
        # List types should map to JSONB (except vector types)
        assert provider.map_python_type(list) == 'JSONB'
        assert provider.map_python_type(List) == 'JSONB'
        assert provider.map_python_type(List[str]) == 'JSONB'
        assert provider.map_python_type(List[dict]) == 'JSONB'
        assert provider.map_python_type(list[str]) == 'JSONB'  # Python 3.9+ syntax
    
    def test_postgresql_optional_types(self, postgresql_provider):
        """Test Optional type handling for PostgreSQL."""
        provider = postgresql_provider
        
        # Optional basic types
        assert provider.map_python_type(Optional[str]) == 'TEXT'
        assert provider.map_python_type(Optional[int]) == 'BIGINT'
        assert provider.map_python_type(Optional[UUID]) == 'UUID'
        
        # Optional JSON types - should still be JSONB
        assert provider.map_python_type(Optional[dict]) == 'JSONB'
        assert provider.map_python_type(Optional[Dict[str, Any]]) == 'JSONB'
        assert provider.map_python_type(Optional[list]) == 'JSONB'
        assert provider.map_python_type(Optional[List[str]]) == 'JSONB'
    
    def test_postgresql_union_types(self, postgresql_provider):
        """Test Union type handling for PostgreSQL."""
        provider = postgresql_provider
        
        # New Python 3.10+ union syntax
        assert provider.map_python_type(dict[str, Any] | None) == 'JSONB'
        assert provider.map_python_type(list[str] | None) == 'JSONB'
        assert provider.map_python_type(str | None) == 'TEXT'
        assert provider.map_python_type(int | None) == 'BIGINT'
        
        # Traditional Union syntax
        assert provider.map_python_type(Union[dict, None]) == 'JSONB'
        assert provider.map_python_type(Union[Dict[str, Any], None]) == 'JSONB'
        assert provider.map_python_type(Union[list, None]) == 'JSONB'
        assert provider.map_python_type(Union[str, None]) == 'TEXT'
    
    def test_postgresql_vector_types(self, postgresql_provider):
        """Test vector type handling for PostgreSQL."""
        provider = postgresql_provider
        
        # Vector types (List[float]) should map to vector
        assert provider.map_python_type(List[float]) == 'vector(1536)'
        assert provider.map_python_type(list[float]) == 'vector(1536)'  # Python 3.9+
        
        # Optional vector types
        assert provider.map_python_type(Optional[List[float]]) == 'vector(1536)'
        assert provider.map_python_type(List[float] | None) == 'vector(1536)'  # Python 3.10+
    
    def test_tidb_json_types(self, tidb_provider):
        """Test JSON type mapping for TiDB."""
        provider = tidb_provider
        
        # TiDB should map dicts to some JSON-compatible type (JSON or TEXT)
        dict_mapping = provider.map_python_type(dict)
        assert dict_mapping in ['JSON', 'TEXT']  # Accept both as valid
        
        # Check that complex dict types are handled
        complex_dict_mapping = provider.map_python_type(Dict[str, Any])
        assert complex_dict_mapping in ['JSON', 'TEXT']
        
        # Optional types should be handled
        optional_dict_mapping = provider.map_python_type(Optional[dict])
        assert optional_dict_mapping in ['JSON', 'TEXT']
        
        # Modern union syntax should be handled  
        modern_union_mapping = provider.map_python_type(dict[str, Any] | None)
        assert modern_union_mapping in ['JSON', 'TEXT']
    
    def test_type_inspector_is_json(self, type_inspector):
        """Test TypeInspector JSON detection."""
        inspector = type_inspector
        
        # Dict types should be detected as JSON
        assert inspector.is_json_type(dict) is True
        assert inspector.is_json_type(Dict) is True
        assert inspector.is_json_type(Dict[str, Any]) is True
        assert inspector.is_json_type(dict[str, Any]) is True  # Python 3.9+
        
        # Optional dict types should be detected as JSON
        assert inspector.is_json_type(Optional[dict]) is True
        assert inspector.is_json_type(Optional[Dict[str, Any]]) is True
        assert inspector.is_json_type(dict[str, Any] | None) is True  # Python 3.10+
        
        # List types (non-vector) should be detected as JSON
        assert inspector.is_json_type(list) is True
        assert inspector.is_json_type(List[str]) is True
        assert inspector.is_json_type(Optional[List[dict]]) is True
        
        # Basic types should NOT be JSON
        assert inspector.is_json_type(str) is False
        assert inspector.is_json_type(int) is False
        assert inspector.is_json_type(UUID) is False
        assert inspector.is_json_type(Optional[str]) is False
    
    def test_type_inspector_union_detection(self, type_inspector):
        """Test TypeInspector union type detection."""
        inspector = type_inspector
        
        # Traditional Union
        assert inspector.is_union_type(Union[str, int]) is True
        assert inspector.is_union_type(Optional[str]) is True  # Optional is Union[T, None]
        
        # Python 3.10+ union
        assert inspector.is_union_type(str | int) is True
        assert inspector.is_union_type(dict[str, Any] | None) is True
        
        # Not unions
        assert inspector.is_union_type(str) is False
        assert inspector.is_union_type(dict) is False
        assert inspector.is_union_type(List[str]) is False
    
    def test_real_world_model_fields(self, postgresql_provider):
        """Test type mapping for real model field definitions."""
        provider = postgresql_provider
        
        # Common model field patterns
        metadata_type = dict[str, Any] | None  # As used in Session model
        assert provider.map_python_type(metadata_type) == 'JSONB'
        
        device_ids_type = list[str]  # As used in Tenant model  
        assert provider.map_python_type(device_ids_type) == 'JSONB'
        
        roles_type = Optional[List[str]]  # As used in User model
        assert provider.map_python_type(roles_type) == 'JSONB'
        
        embedding_type = Optional[List[float]]  # Vector embedding
        assert provider.map_python_type(embedding_type) == 'vector(1536)'
    
    def test_edge_cases(self, postgresql_provider, type_inspector):
        """Test edge cases and complex types."""
        provider = postgresql_provider
        inspector = type_inspector
        
        # Nested complex types
        complex_type = Dict[str, List[Dict[str, Any]]]
        assert provider.map_python_type(complex_type) == 'JSONB'
        assert inspector.is_json_type(complex_type) is True
        
        # Multiple union members with dict - dict takes precedence for JSONB
        multi_union = Union[str, int, dict, None]
        # Should use dict for JSONB since it's a complex type
        assert provider.map_python_type(multi_union) == 'JSONB'
        
        # Multiple union members without dict - first type takes precedence
        simple_union = Union[str, int, None]
        assert provider.map_python_type(simple_union) == 'TEXT'
        
        # Unknown/custom types should fall back to TEXT
        class CustomType:
            pass
        
        assert provider.map_python_type(CustomType) == 'TEXT'
    
    @pytest.mark.parametrize("python_type,expected_sql", [
        # Comprehensive type mapping test cases
        (str, 'TEXT'),
        (int, 'BIGINT'),
        (float, 'DOUBLE PRECISION'),
        (bool, 'BOOLEAN'),
        (UUID, 'UUID'),
        (dict, 'JSONB'),
        (list, 'JSONB'),
        (Dict[str, Any], 'JSONB'),
        (List[str], 'JSONB'),
        (List[float], 'vector(1536)'),
        (Optional[dict], 'JSONB'),
        (dict[str, Any] | None, 'JSONB'),
        (Optional[List[float]], 'vector(1536)'),
    ])
    def test_type_mapping_parametrized(self, postgresql_provider, python_type, expected_sql):
        """Parametrized test for comprehensive type coverage."""
        assert postgresql_provider.map_python_type(python_type) == expected_sql