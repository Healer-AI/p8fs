"""
P8FS Client for interacting with the P8FS system.

This module provides the main client interface for P8FS operations.
"""

from typing import Any, Dict, List, Optional


class P8FSClient:
    """Main client for P8FS operations."""
    
    def __init__(self, tenant_id: Optional[str] = None, **kwargs):
        """Initialize P8FS client.
        
        Args:
            tenant_id: Optional tenant identifier
            **kwargs: Additional client configuration
        """
        self.tenant_id = tenant_id
        self.config = kwargs
    
    async def search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Search for resources.
        
        Args:
            query: Search query
            limit: Maximum results to return
            
        Returns:
            Search results
        """
        return {
            "results": [],
            "total": 0,
            "query": query,
            "limit": limit
        }
    
    async def get_entities(self, **kwargs) -> Dict[str, Any]:
        """Get entities from the system.
        
        Returns:
            Entities data
        """
        return {
            "entities": [],
            "total": 0
        }
    
    async def get_recent_uploads(self, limit: int = 10) -> Dict[str, Any]:
        """Get recent file uploads grouped by source file.

        Args:
            limit: Maximum uploads to return

        Returns:
            Dictionary with 'uploads' key containing list of file metadata:
            - file_name: Source file name from metadata or resource name
            - uri: File URI
            - chunk_count: Number of chunks for this file
            - chunk_entity_names: JSON list of objects with 'name' and 'ordinal'
            - first_created: When file was first uploaded
            - last_updated: Most recent update time
        """
        if not self.tenant_id:
            return {
                "files": [],
                "resource_names": [],
                "uploads": []
            }

        from p8fs.providers import get_provider

        provider = get_provider()
        conn = provider.connect_sync()

        try:
            with conn.cursor() as cur:
                query = """
                    WITH user_files AS (
                        SELECT
                            COALESCE(metadata->>'source_file', name) as source_file,
                            MIN(created_at) as first_created,
                            MAX(updated_at) as last_updated,
                            COUNT(*) as chunk_count,
                            MAX(uri) as uri,
                            json_agg(
                                json_build_object(
                                    'name', name,
                                    'ordinal', COALESCE(ordinal, 0)
                                ) ORDER BY COALESCE(ordinal, 0)
                            ) as chunk_entity_names
                        FROM resources
                        WHERE tenant_id = %s
                        GROUP BY COALESCE(metadata->>'source_file', name)
                        ORDER BY MAX(updated_at) DESC
                        LIMIT %s
                    )
                    SELECT
                        source_file as file_name,
                        first_created,
                        last_updated,
                        chunk_count,
                        uri,
                        chunk_entity_names
                    FROM user_files;
                """

                cur.execute(query, (self.tenant_id, limit))

                columns = [desc[0] for desc in cur.description]
                uploads = [dict(zip(columns, row)) for row in cur.fetchall()]

                return {
                    "files": [u['file_name'] for u in uploads],
                    "resource_names": [u['file_name'] for u in uploads],
                    "uploads": uploads
                }
        finally:
            conn.close()
    
    async def query(self, *args, **kwargs) -> Dict[str, Any]:
        """Query the system.
        
        Returns:
            Query results
        """
        return {
            "results": [],
            "total": 0
        }
        
    def entity(self, entity_type: str) -> 'EntityInterface':
        """Get entity interface for a specific type.
        
        Args:
            entity_type: Type of entity to interface with
            
        Returns:
            Entity interface
        """
        return EntityInterface(entity_type, self)


class EntityInterface:
    """Interface for entity operations."""
    
    def __init__(self, entity_type: str, client: P8FSClient):
        self.entity_type = entity_type
        self.client = client
    
    async def list(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List entities of this type.
        
        Args:
            limit: Maximum entities to return
            
        Returns:
            List of entities
        """
        return []


def get_client(tenant_id: Optional[str] = None) -> P8FSClient:
    """Get a P8FS client instance.
    
    Args:
        tenant_id: Optional tenant identifier
        
    Returns:
        P8FS client instance
    """
    return P8FSClient(tenant_id=tenant_id)