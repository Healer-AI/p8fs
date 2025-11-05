"""Repository for dreaming worker operations."""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from p8fs_cluster.logging import get_logger
from p8fs.repository import SystemRepository
from p8fs.models.p8 import Session, Resources, Tenant
from p8fs.models.agentlets import DreamModel

logger = get_logger(__name__)


class DreamingRepository:
    """Repository for dreaming worker that wraps SystemRepository for different models."""
    
    def __init__(self):
        """Initialize repositories for different models."""
        self.session_repo = SystemRepository(Session)
        self.resource_repo = SystemRepository(Resources) 
        self.tenant_repo = SystemRepository(Tenant)
    
    async def get_sessions(self, tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent sessions for a tenant."""
        try:
            # Use raw query for tenant filtering
            query = """
                SELECT * FROM sessions 
                WHERE tenant_id = %s 
                ORDER BY created_at DESC 
                LIMIT %s
            """
            
            results = self.session_repo.execute(query, (tenant_id, limit))
            
            # Convert to dictionaries
            session_list = [dict(row) for row in results] if results else []
            
            logger.info(f"Retrieved {len(session_list)} sessions for tenant {tenant_id}")
            return session_list
            
        except Exception as e:
            logger.error(f"Failed to get sessions for {tenant_id}: {e}")
            return []
    
    async def get_resources(self, tenant_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get resources/documents for a tenant."""
        try:
            # Use raw query for tenant filtering
            query = """
                SELECT * FROM resources 
                WHERE tenant_id = %s 
                ORDER BY created_at DESC 
                LIMIT %s
            """
            
            results = self.resource_repo.execute(query, (tenant_id, limit))
            
            # Convert to dictionaries
            resource_list = [dict(row) for row in results] if results else []
            
            logger.info(f"Retrieved {len(resource_list)} resources for tenant {tenant_id}")
            return resource_list
            
        except Exception as e:
            logger.error(f"Failed to get resources for {tenant_id}: {e}")
            return []
    
    async def get_tenant_profile(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant profile information."""
        try:
            # Use raw query for tenant lookup
            query = """
                SELECT * FROM tenants 
                WHERE tenant_id = %s 
                LIMIT 1
            """
            
            results = self.tenant_repo.execute(query, (tenant_id,))
            
            if results:
                profile = dict(results[0])
                logger.info(f"Retrieved profile for tenant {tenant_id}")
                return profile
            else:
                logger.warning(f"No tenant profile found for {tenant_id}")
                return {"tenant_id": tenant_id, "name": "Unknown User"}
                
        except Exception as e:
            logger.error(f"Failed to get tenant profile for {tenant_id}: {e}")
            return {"tenant_id": tenant_id, "name": "Unknown User"}
    
    async def store_dream_analysis(self, dream_analysis: DreamModel) -> bool:
        """Log dream analysis result (no persistent storage needed)."""
        try:
            logger.info(f"Dream analysis completed: {dream_analysis.analysis_id} for user {dream_analysis.user_id}")
            logger.info(f"  Executive Summary: {dream_analysis.executive_summary}")
            logger.info(f"  Key Themes: {dream_analysis.key_themes}")
            logger.info(f"  Goals: {len(dream_analysis.goals)} goals identified")
            logger.info(f"  Dreams: {len(dream_analysis.dreams)} dreams identified")
            logger.info(f"  Tasks: {len(dream_analysis.pending_tasks)} pending tasks")
            logger.info(f"  Confidence: {dream_analysis.metrics.confidence_score}")
            
            # Dream analysis is temporary - no database storage needed
            return True
            
        except Exception as e:
            logger.error(f"Failed to log dream analysis {dream_analysis.analysis_id}: {e}")
            return False
    
    async def create_dream_job(self, job_data: Dict[str, Any]) -> bool:
        """Store dream job record."""
        try:
            # For now, just log the job creation
            # In a full implementation, you might have a DreamJob model and repository
            logger.info(f"Dream job created: {job_data.get('id')} for tenant {job_data.get('tenant_id')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create dream job: {e}")
            return False
    
    async def update_dream_job(self, job_id: str, job_data: Dict[str, Any]) -> bool:
        """Update dream job record."""
        try:
            # For now, just log the job update
            logger.info(f"Dream job updated: {job_id} - Status: {job_data.get('status')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update dream job {job_id}: {e}")
            return False
    
    async def get_dream_jobs(self, status: str = None, mode: str = None) -> List[Dict[str, Any]]:
        """Get dream jobs by status and mode."""
        try:
            # For now, return empty list since we don't have a DreamJob model yet
            # In a full implementation, you would query the job table
            logger.info(f"Querying dream jobs with status={status}, mode={mode}")
            return []
            
        except Exception as e:
            logger.error(f"Failed to get dream jobs: {e}")
            return []
    
    async def get_recent_sessions_since(
        self, 
        tenant_id: str, 
        since: datetime, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get sessions since a specific datetime."""
        try:
            # Use raw query for date filtering
            query = """
                SELECT * FROM sessions 
                WHERE tenant_id = %s AND created_at >= %s 
                ORDER BY created_at DESC 
                LIMIT %s
            """
            
            results = self.session_repo.execute(
                query, 
                (tenant_id, since, limit)
            )
            
            logger.info(f"Retrieved {len(results)} recent sessions for tenant {tenant_id}")
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to get recent sessions for {tenant_id}: {e}")
            return []
    
    async def get_resources_by_type(
        self,
        tenant_id: str,
        resource_type: str = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get resources filtered by type."""
        try:
            filters = {"tenant_id": tenant_id}
            if resource_type:
                filters["resource_type"] = resource_type

            resources = await self.resource_repo.select_where(
                **filters,
                limit=limit
            )

            # Convert to dictionaries
            resource_list = []
            for resource in resources:
                if hasattr(resource, 'model_dump'):
                    resource_list.append(resource.model_dump())
                else:
                    resource_list.append(resource.__dict__)

            logger.info(f"Retrieved {len(resource_list)} {resource_type or 'all'} resources for tenant {tenant_id}")
            return resource_list

        except Exception as e:
            logger.error(f"Failed to get resources for {tenant_id}: {e}")
            return []

    async def get_active_tenants(self, lookback_hours: int = 24) -> List[str]:
        """Get tenants with activity (sessions or resources) in the lookback period."""
        try:
            since = datetime.now() - timedelta(hours=lookback_hours)

            # Query for tenants with recent resources or sessions
            query = """
                SELECT DISTINCT tenant_id FROM (
                    SELECT tenant_id FROM resources WHERE created_at >= %s
                    UNION
                    SELECT tenant_id FROM sessions WHERE created_at >= %s
                ) AS active_tenants
            """

            results = self.resource_repo.execute(query, (since, since))

            tenant_ids = [row[0] if isinstance(row, tuple) else row['tenant_id'] for row in results]

            logger.info(f"Found {len(tenant_ids)} active tenants in last {lookback_hours} hours")
            return tenant_ids

        except Exception as e:
            logger.error(f"Failed to get active tenants: {e}")
            return []

    async def get_all_active_tenants(self, lookback_hours: int = 24) -> List[Dict[str, Any]]:
        """Get full tenant data for all active tenants."""
        try:
            # Get active tenant IDs
            tenant_ids = await self.get_active_tenants(lookback_hours)

            if not tenant_ids:
                return []

            # Get full tenant data for each
            tenants = []
            for tenant_id in tenant_ids:
                tenant_data = await self.get_tenant_profile(tenant_id)
                if tenant_data:
                    tenants.append(tenant_data)

            logger.info(f"Retrieved {len(tenants)} active tenant profiles")
            return tenants

        except Exception as e:
            logger.error(f"Failed to get all active tenants: {e}")
            return []

    async def get_recent_moments(
        self,
        tenant_id: str,
        since: datetime,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get moments created since a specific datetime."""
        try:
            query = """
                SELECT * FROM moments
                WHERE tenant_id = %s AND created_at >= %s
                ORDER BY created_at DESC
                LIMIT %s
            """

            results = self.resource_repo.execute(
                query,
                (tenant_id, since, limit)
            )

            moments = [dict(row) for row in results] if results else []

            logger.info(
                f"Retrieved {len(moments)} moments for tenant {tenant_id} "
                f"since {since.isoformat()}"
            )
            return moments

        except Exception as e:
            logger.error(f"Failed to get recent moments for {tenant_id}: {e}")
            return []