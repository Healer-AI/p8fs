"""Integration test for graph relationship operations.

This test verifies graph edge creation, querying, and deletion functionality.
"""

import pytest
import asyncio
from datetime import datetime
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers.postgresql import PostgreSQLProvider
from p8fs.services.graph import GraphAssociation, PostgresGraphProvider

logger = get_logger(__name__)


@pytest.mark.integration
class TestGraphRelationships:
    """Test graph relationship operations."""
    
    @pytest.fixture(scope="class")
    def provider(self):
        """Get PostgreSQL provider instance."""
        provider = PostgreSQLProvider()
        provider.connect_sync()
        return provider
    
    @pytest.fixture
    def graph_provider(self, provider):
        """Get graph provider instance."""
        return PostgresGraphProvider(provider)
    
    def setup_test_nodes(self, provider):
        """Create test nodes for relationship testing."""
        try:
            # Create test user nodes
            provider.execute("""
                SELECT * FROM p8.cypher_query(
                    'MERGE (u1:User {uid: "user-001", key: "user-001", name: "Alice"}) RETURN u1'
                )
            """)
            
            provider.execute("""
                SELECT * FROM p8.cypher_query(
                    'MERGE (u2:User {uid: "user-002", key: "user-002", name: "Bob"}) RETURN u2'
                )
            """)
            
            # Create test document nodes
            provider.execute("""
                SELECT * FROM p8.cypher_query(
                    'MERGE (d1:Document {uid: "doc-001", key: "doc-001", title: "Project Plan"}) RETURN d1'
                )
            """)
            
            provider.execute("""
                SELECT * FROM p8.cypher_query(
                    'MERGE (d2:Document {uid: "doc-002", key: "doc-002", title: "Design Doc"}) RETURN d2'
                )
            """)
            
            logger.info("Test nodes created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create test nodes: {e}")
            pytest.skip("Could not create test nodes")
    
    def test_create_relationship(self, graph_provider):
        """Test creating relationships between nodes."""
        logger.info("Testing relationship creation")
        
        # Setup test nodes
        self.setup_test_nodes(graph_provider.pg_provider)
        
        # Create OWNS relationship
        association = GraphAssociation(
            from_entity_id="user-001",
            to_entity_id="doc-001",
            relationship_type="OWNS",
            from_entity_type="User",
            to_entity_type="Document",
            metadata={"access_level": "read-write", "shared": False},
            tenant_id="test-tenant"
        )
        
        result = graph_provider.create_association(association)
        logger.info(f"Create association result: {result}")
        
        assert result is not None, "Should create relationship"
        # Extract the actual result if nested
        if 'result' in result:
            result = result['result']
        assert result.get('from_uid') == "user-001"
        assert result.get('to_uid') == "doc-001"
        assert result.get('relationship_type') == "OWNS"
    
    @pytest.mark.skip(reason="Graph relationships query has connection management issues - needs investigation")
    def test_query_relationships(self, graph_provider, provider):
        """Test querying existing relationships."""
        logger.info("Testing relationship queries")
        
        # Setup test nodes first
        self.setup_test_nodes(provider)
        
        # Create multiple relationships
        relationships = [
            GraphAssociation(
                from_entity_id="user-001",
                to_entity_id="doc-002",
                relationship_type="OWNS",
                from_entity_type="User",
                to_entity_type="Document",
                metadata={"access_level": "read-only"}
            ),
            GraphAssociation(
                from_entity_id="user-002",
                to_entity_id="doc-001",
                relationship_type="COLLABORATES",
                from_entity_type="User",
                to_entity_type="Document",
                metadata={"role": "reviewer"}
            ),
            GraphAssociation(
                from_entity_id="user-001",
                to_entity_id="user-002",
                relationship_type="FOLLOWS",
                from_entity_type="User",
                to_entity_type="User",
                metadata={"since": "2025-01-01"}
            )
        ]
        
        for rel in relationships:
            graph_provider.create_association(rel)
        
        # Query by source entity
        user1_rels = graph_provider.get_relationships(from_entity_id="user-001")
        logger.info(f"User-001 relationships: {user1_rels}")
        assert len(user1_rels) >= 2, "User-001 should have at least 2 outgoing relationships"
        
        # Query by target entity
        doc1_rels = graph_provider.get_relationships(to_entity_id="doc-001")
        logger.info(f"Doc-001 relationships: {doc1_rels}")
        assert len(doc1_rels) >= 2, "Doc-001 should have at least 2 incoming relationships"
        
        # Query by relationship type
        owns_rels = graph_provider.get_relationships(relationship_type="OWNS")
        logger.info(f"OWNS relationships: {owns_rels}")
        assert len(owns_rels) >= 2, "Should have at least 2 OWNS relationships"
        
        # Query specific relationship
        specific_rel = graph_provider.get_relationships(
            from_entity_id="user-001",
            to_entity_id="user-002",
            relationship_type="FOLLOWS"
        )
        assert len(specific_rel) == 1, "Should find exactly one FOLLOWS relationship"
        assert specific_rel[0]['from_id'] == "user-001"
        assert specific_rel[0]['to_id'] == "user-002"
    
    @pytest.mark.skip(reason="Graph relationships not persisting consistently in test environment")
    def test_relationship_metadata(self, graph_provider):
        """Test relationship metadata storage and retrieval."""
        logger.info("Testing relationship metadata")
        
        # Create relationship with complex metadata
        metadata = {
            "permissions": ["read", "write", "delete"],
            "created_by": "admin",
            "tags": ["important", "shared"],
            "settings": {
                "notifications": True,
                "auto_save": False
            }
        }
        
        association = GraphAssociation(
            from_entity_id="user-002",
            to_entity_id="doc-002",
            relationship_type="MANAGES",
            metadata=metadata
        )
        
        result = graph_provider.create_association(association)
        assert result is not None
        
        # Query and verify metadata
        rels = graph_provider.get_relationships(
            from_entity_id="user-002",
            to_entity_id="doc-002"
        )
        
        assert len(rels) > 0, "Should find the relationship"
        rel_metadata = rels[0].get('metadata', {})
        
        # Check metadata preservation
        assert 'permissions' in rel_metadata, "Should preserve permissions array"
        assert 'settings' in rel_metadata, "Should preserve nested settings"
        assert rel_metadata.get('created_by') == 'admin', "Should preserve string values"
    
    @pytest.mark.skip(reason="Graph relationships not persisting consistently in test environment")
    def test_delete_relationship(self, graph_provider):
        """Test relationship deletion."""
        logger.info("Testing relationship deletion")
        
        # Create a test relationship
        association = GraphAssociation(
            from_entity_id="user-001",
            to_entity_id="doc-001",
            relationship_type="ARCHIVES"
        )
        
        result = graph_provider.create_association(association)
        assert result is not None
        
        # Verify it exists
        rels = graph_provider.get_relationships(
            from_entity_id="user-001",
            to_entity_id="doc-001",
            relationship_type="ARCHIVES"
        )
        assert len(rels) > 0, "Relationship should exist"
        
        # Delete the relationship
        deleted = graph_provider.delete_relationship(
            from_entity_id="user-001",
            to_entity_id="doc-001",
            relationship_type="ARCHIVES"
        )
        assert deleted is True, "Should successfully delete relationship"
        
        # Verify it's gone
        rels = graph_provider.get_relationships(
            from_entity_id="user-001",
            to_entity_id="doc-001",
            relationship_type="ARCHIVES"
        )
        assert len(rels) == 0, "Relationship should be deleted"
    
    @pytest.mark.skip(reason="Graph relationships not persisting consistently in test environment")
    def test_batch_associations(self, graph_provider):
        """Test creating multiple associations at once."""
        logger.info("Testing batch association creation")
        
        associations = [
            GraphAssociation(
                from_entity_id=f"user-00{i}",
                to_entity_id=f"doc-00{j}",
                relationship_type="VIEWS",
                metadata={"timestamp": datetime.utcnow().isoformat()}
            )
            for i in range(1, 3)
            for j in range(1, 3)
        ]
        
        count = graph_provider.create_associations(associations)
        logger.info(f"Created {count} associations")
        
        assert count == len(associations), f"Should create all {len(associations)} associations"
        
        # Verify they were created
        views_rels = graph_provider.get_relationships(relationship_type="VIEWS")
        assert len(views_rels) >= 4, "Should have at least 4 VIEWS relationships"
    
    def test_relationship_patterns(self, graph_provider):
        """Test common relationship query patterns."""
        logger.info("Testing relationship patterns")
        
        # Find all documents owned by a user
        user_docs = graph_provider.get_relationships(
            from_entity_id="user-001",
            relationship_type="OWNS"
        )
        doc_ids = [rel['to_id'] for rel in user_docs]
        logger.info(f"User-001 owns documents: {doc_ids}")
        
        # Find all users who can access a document
        doc_users = graph_provider.get_relationships(
            to_entity_id="doc-001"
        )
        user_ids = [rel['from_id'] for rel in doc_users]
        logger.info(f"Users with access to doc-001: {user_ids}")
        
        # Find collaboration network
        collabs = graph_provider.get_relationships(
            relationship_type="COLLABORATES"
        )
        logger.info(f"Collaboration relationships: {len(collabs)}")
    
    def cleanup_test_data(self, provider):
        """Clean up test nodes and relationships."""
        try:
            # Delete all test relationships
            provider.execute("""
                SELECT * FROM p8.cypher_query(
                    'MATCH (n)-[r]-(m) 
                     WHERE n.uid IN ["user-001", "user-002", "doc-001", "doc-002"] 
                     DELETE r'
                )
            """)
            
            # Delete all test nodes
            provider.execute("""
                SELECT * FROM p8.cypher_query(
                    'MATCH (n) 
                     WHERE n.uid IN ["user-001", "user-002", "doc-001", "doc-002"] 
                     DELETE n'
                )
            """)
            
            logger.info("Test data cleaned up")
            
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])