"""Graph service provider for P8FS using Apache AGE and PostgreSQL."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class GraphAssociation(BaseModel):
    """Model for creating graph associations/relationships."""
    
    from_entity_id: str
    to_entity_id: str
    relationship_type: str
    from_entity_type: Optional[str] = None
    to_entity_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    tenant_id: Optional[str] = None


class PostgresGraphProvider:
    """
    Graph operations provider using PostgreSQL with Apache AGE.
    Wraps low-level SQL functions for graph queries and mutations.
    """
    
    def __init__(self, pg_provider):
        """Initialize with a PostgreSQL provider instance."""
        self.pg_provider = pg_provider
        self.graph_name = "p8graph"
    
    def execute_sync(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute SQL query synchronously using PostgreSQLProvider."""
        try:
            # Use PostgreSQLProvider's execute method which handles connection management automatically
            return self.pg_provider.execute(query, params)
        except Exception as e:
            logger.error(f"Graph query execution failed: {e}")
            raise
    
    def cypher_query(self, cypher: str, columns: str = "result agtype") -> List[Dict[str, Any]]:
        """
        Execute a raw Cypher query against the p8graph.
        
        Args:
            cypher: The Cypher query string
            columns: Return column specification
            
        Returns:
            List of query results as dictionaries
        """
        query = f"SELECT * FROM p8.cypher_query(%s, %s, %s)"
        return self.execute_sync(query, (cypher, columns, self.graph_name))
    
    def ensure_nodes(self, table_names: List[str]) -> Dict[str, int]:
        """
        Ensure graph nodes exist for the specified tables.
        
        Args:
            table_names: List of table names to sync nodes for
            
        Returns:
            Dictionary with table names as keys and count of nodes created as values
        """
        results = {}
        for table_name in table_names:
            try:
                query = "SELECT * FROM p8.add_nodes(%s)"
                result = self.execute_sync(query, (table_name,))
                count = result[0].get('add_nodes', 0) if result else 0
                results[table_name] = count
                logger.info(f"Ensured {count} nodes for table {table_name}")
            except Exception as e:
                logger.error(f"Failed to ensure nodes for {table_name}: {e}")
                results[table_name] = 0
        
        return results
    
    def create_association(self, association: GraphAssociation) -> Optional[Dict[str, Any]]:
        """
        Create a relationship edge between two nodes using MERGE to ensure nodes exist.
        
        Args:
            association: GraphAssociation model with relationship details
            
        Returns:
            Result of the relationship creation or None if failed
        """
        try:
            # Sanitize relationship type for Cypher (uppercase, replace hyphens)
            rel_type = association.relationship_type.upper().replace("-", "_").replace(" ", "_")
            
            # Build metadata properties for relationship
            metadata_props = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "tenant_id": association.tenant_id or "",
                **(association.metadata or {})
            }
            
            # Format properties as Cypher SET clauses for the relationship
            # Skip created_at since we handle it separately with COALESCE
            prop_set_clauses = []
            for key, value in metadata_props.items():
                if key != "created_at":  # Skip created_at to avoid duplication
                    escaped_value = str(value).replace("'", "\\'")
                    prop_set_clauses.append(f"r.{key} = '{escaped_value}'")
            
            prop_set_clause = ", " + ", ".join(prop_set_clauses) if prop_set_clauses else ""
            created_at_value = metadata_props["created_at"]
            
            # Use MERGE pattern to ensure both nodes exist before creating relationship
            # This follows the Percolate pattern for robust node and relationship creation
            cypher_query = f'''
            MERGE (a:public__{association.from_entity_type or "resource"} {{uid: "{association.from_entity_id}"}})
            MERGE (b:public__{association.to_entity_type or "resource"} {{uid: "{association.to_entity_id}"}})
            WITH a, b
            MERGE (a)-[r:{rel_type}]->(b)
            SET r.created_at = COALESCE(r.created_at, "{created_at_value}"){prop_set_clause}
            RETURN a.uid AS from_uid, type(r) AS relationship_type, b.uid AS to_uid
            '''
            
            result = self.cypher_query(cypher_query, "from_uid text, relationship_type text, to_uid text")
            
            if result:
                logger.info(f"Created graph edge: {association.from_entity_id} -[{rel_type}]-> {association.to_entity_id}")
                return result[0]
            else:
                logger.warning(f"No relationship created: {association.from_entity_id} -> {association.to_entity_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create graph association: {e}")
            logger.debug(f"Association data: {association.model_dump()}")
            return None
    
    def create_associations(self, associations: List[GraphAssociation]) -> int:
        """
        Create multiple relationship edges in batch.
        
        Args:
            associations: List of GraphAssociation models
            
        Returns:
            Number of associations successfully created
        """
        count = 0
        for association in associations:
            result = self.create_association(association)
            if result:
                count += 1
        return count
    
    def get_relationships(
        self,
        from_entity_id: Optional[str] = None,
        to_entity_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query existing relationships in the graph.
        
        Args:
            from_entity_id: Source node UID filter
            to_entity_id: Target node UID filter  
            relationship_type: Relationship type filter
            
        Returns:
            List of matching relationships
        """
        try:
            # Build dynamic Cypher query based on filters
            where_clauses = []
            if from_entity_id:
                where_clauses.append(f'a.uid = "{from_entity_id}"')
            if to_entity_id:
                where_clauses.append(f'b.uid = "{to_entity_id}"')
            
            where_clause = " AND ".join(where_clauses) if where_clauses else "true"
            
            # Add relationship type filter if provided
            rel_pattern = f":{relationship_type.upper().replace('-', '_')}" if relationship_type else ""
            
            cypher_query = f'''
            MATCH (a)-[r{rel_pattern}]->(b)
            WHERE {where_clause}
            RETURN a.uid as from_id, type(r) as relationship, b.uid as to_id, properties(r) as metadata
            '''
            
            logger.debug(f"Executing cypher query: {cypher_query}")
            result = self.cypher_query(cypher_query, "from_id text, relationship text, to_id text, metadata agtype")
            logger.debug(f"Cypher query result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to query relationships: {e}")
            return []
    
    def delete_relationship(
        self,
        from_entity_id: str,
        to_entity_id: str, 
        relationship_type: Optional[str] = None
    ) -> bool:
        """
        Delete a relationship between two nodes.
        
        Args:
            from_entity_id: Source node UID
            to_entity_id: Target node UID
            relationship_type: Optional specific relationship type to delete
            
        Returns:
            True if deletion succeeded, False otherwise
        """
        try:
            rel_pattern = f":{relationship_type.upper().replace('-', '_')}" if relationship_type else ""
            
            cypher_query = f'''
            MATCH (a)-[r{rel_pattern}]->(b)
            WHERE a.uid = "{from_entity_id}" AND b.uid = "{to_entity_id}"
            DELETE r
            RETURN count(r) as deleted_count
            '''
            
            result = self.cypher_query(cypher_query, "deleted_count int")
            deleted_count = result[0].get('deleted_count', 0) if result else 0
            
            logger.info(f"Deleted {deleted_count} relationships between {from_entity_id} -> {to_entity_id}")
            return deleted_count > 0
            
        except Exception as e:
            logger.error(f"Failed to delete relationship: {e}")
            return False