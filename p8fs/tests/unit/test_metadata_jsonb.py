"""Test that metadata fields are properly handled as JSONB."""

import json
import pytest
from datetime import datetime
from uuid import uuid4

from p8fs.models.p8 import Session, User, Resources, Agent, Error
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.providers.postgresql import PostgreSQLProvider


class TestMetadataJSONB:
    """Test JSONB metadata handling across all models."""
    
    def test_session_metadata_dict(self):
        """Test that Session metadata accepts and stores dict properly."""
        metadata = {
            "model": "gpt-4",
            "temperature": 0.7,
            "response_preview": "The answer is...",
            "nested": {
                "key": "value",
                "array": [1, 2, 3]
            }
        }
        
        session = Session(
            id=str(uuid4()),
            name="Test Session",
            query="What is the meaning of life?",
            metadata=metadata,
            tenant_id="test-tenant"
        )
        
        # Verify metadata is stored as dict
        assert isinstance(session.metadata, dict)
        assert session.metadata["model"] == "gpt-4"
        assert session.metadata["temperature"] == 0.7
        assert session.metadata["nested"]["array"] == [1, 2, 3]
    
    def test_user_metadata_dict(self):
        """Test that User metadata accepts and stores dict properly."""
        metadata = {
            "preferences": {
                "theme": "dark",
                "language": "en"
            },
            "tags": ["admin", "developer"],
            "score": 95.5
        }
        
        user = User(
            id=str(uuid4()),
            email="test@example.com",
            description="Test user",
            metadata=metadata,
            tenant_id="test-tenant"
        )
        
        assert isinstance(user.metadata, dict)
        assert user.metadata["preferences"]["theme"] == "dark"
        assert user.metadata["tags"] == ["admin", "developer"]
        assert user.metadata["score"] == 95.5
    
    def test_agent_metadata_and_functions(self):
        """Test that Agent metadata and functions accept dict/list properly."""
        from p8fs.models.p8 import Function
        
        metadata = {
            "version": "1.0",
            "capabilities": ["chat", "code", "analysis"]
        }
        
        # Create Function objects since Agent expects list[Function]
        func = Function(
            id=str(uuid4()),
            name="get_weather",
            description="Get weather for a location",
            function_spec={
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                }
            },
            tenant_id="test-tenant"
        )
        
        agent = Agent(
            id=str(uuid4()),
            name="Test Agent",
            description="A test agent",
            metadata=metadata,
            functions=[func],
            tenant_id="test-tenant"
        )
        
        assert isinstance(agent.metadata, dict)
        assert isinstance(agent.functions, list)
        assert agent.metadata["capabilities"] == ["chat", "code", "analysis"]
        assert len(agent.functions) == 1
        assert agent.functions[0].name == "get_weather"
        
        # Test that functions can be serialized to JSON
        agent_dict = agent.model_dump()
        assert isinstance(agent_dict["functions"], list)
        assert isinstance(agent_dict["functions"][0], dict)
        assert agent_dict["functions"][0]["name"] == "get_weather"
    
    def test_postgresql_type_mapping(self):
        """Test that PostgreSQL provider maps dict to JSONB."""
        provider = PostgreSQLProvider()
        
        # Test basic dict type
        assert provider.map_python_type(dict) == "JSONB"
        assert provider.map_python_type(list) == "JSONB"
        
        # Test generic dict type
        from typing import Dict, Any, List
        assert provider.map_python_type(Dict[str, Any]) == "JSONB"
        assert provider.map_python_type(List[str]) == "JSONB"
        
        # Test optional dict type
        from typing import Optional
        assert provider.map_python_type(Optional[dict]) == "JSONB"
        assert provider.map_python_type(Optional[Dict[str, Any]]) == "JSONB"
    
    def test_create_table_sql_uses_jsonb(self):
        """Test that create_table_sql generates JSONB columns."""
        provider = PostgreSQLProvider()
        
        # Test that create_table_sql generates JSONB for metadata fields
        from p8fs.models.p8 import Session
        sql = provider.create_table_sql(Session)
        
        # Should contain JSONB column for metadata
        assert "metadata JSONB" in sql
        # Should create GIN index for metadata JSONB column
        assert "idx_sessions_metadata_gin" in sql
        assert "USING GIN (metadata)" in sql
    
    @pytest.mark.parametrize("model_class,field_name", [
        (Session, "metadata"),
        (User, "metadata"),
        (Resources, "metadata"),
        (Agent, "metadata"),
        (Error, "metadata"),
    ])
    def test_all_models_metadata_as_dict(self, model_class, field_name):
        """Test that all models with metadata fields use dict type."""
        field_info = model_class.model_fields.get(field_name)
        assert field_info is not None
        
        # Get the type annotation
        field_type = field_info.annotation
        
        # Check if it's a dict type (could be dict, Dict[str, Any], Optional[dict], etc.)
        type_str = str(field_type)
        assert "dict" in type_str.lower() or "Dict" in type_str
    
    def test_metadata_serialization(self):
        """Test that metadata is properly serialized for database storage."""
        metadata = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "array": [1, 2, 3],
            "nested": {"key": "value"}
        }
        
        session = Session(
            id=str(uuid4()),
            name="Test",
            query="test",
            metadata=metadata,
            tenant_id="test"
        )
        
        # Test model_dump preserves dict structure
        dumped = session.model_dump()
        assert isinstance(dumped["metadata"], dict)
        assert dumped["metadata"] == metadata
        
        # Test JSON serialization
        json_str = json.dumps(dumped["metadata"])
        reloaded = json.loads(json_str)
        assert reloaded == metadata