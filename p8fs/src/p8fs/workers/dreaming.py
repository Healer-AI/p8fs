"""Dreaming worker for processing user content insights.

The dreaming worker analyzes user sessions and resources to extract meaningful
moments, goals, fears, dreams, and relationships using the DreamModel agentlet.

Embedding Provider Configuration:
    IMPORTANT: Set the embedding provider to match your database vector dimensions.

    For PostgreSQL (1536 dimensions - default in production):
        export P8FS_DEFAULT_EMBEDDING_PROVIDER=text-embedding-3-small

    For local testing with FastEmbed (384 dimensions):
        export P8FS_DEFAULT_EMBEDDING_PROVIDER=all-MiniLM-L6-v2

    Note: The embedding provider determines the vector dimensions for all generated
    embeddings. Your database schema must match the provider's dimensions, or you'll
    get "expected X dimensions, not Y" errors.

Local Testing Setup:
    Before running the dreaming worker locally, populate PostgreSQL with test data:

    1. Start PostgreSQL:
       docker compose up postgres -d

    2. Set OpenAI API key:
       source ~/.bash_profile

    3. Populate test data with embeddings:
       uv run python scripts/populate_with_embeddings.py

       This script:
       - Sets P8FS_EMBEDDING_PROVIDER=text-embedding-3-small (OpenAI, 1536 dims)
       - Creates 3 resources (with embeddings and graph_paths)
       - Creates 3 sessions (linked to resources via graph_paths)
       - Creates 4 moments (with embeddings, tags, and temporal boundaries)

    4. Run dreaming worker:
       uv run python -m p8fs.workers.dreaming process --tenant-id tenant-test

    5. Verify results in PostgreSQL:
       docker exec percolate psql -U postgres -d app -c \
         "SELECT name, moment_type FROM moments WHERE tenant_id = 'tenant-test';"

Memory Considerations:
    Moments are batch-saved to optimize embedding generation (single API call
    instead of N calls). Memory usage is naturally bounded by LLM token limits
    (max_tokens=4000), making this safe for constrained environments (256Mi workers).
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

import typer
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config
from pydantic import BaseModel, Field

from p8fs.models.agentlets import (
    DreamModel,
    MomentBuilder,
    UserDataBatch,
    UserDreamAnalysisRequest,
    DreamAnalysisMetrics,
    PersonalGoal,
    PersonalFear,
    PersonalDream,
    PendingTask,
    Appointment,
    EntityRelationship,
)
from p8fs.services.llm.models import CallingContext
from p8fs.models.p8 import Moment
from p8fs.repository import TenantRepository
from p8fs.services.llm import MemoryProxy
from p8fs.algorithms.resource_affinity import ResourceAffinityBuilder
from p8fs.providers import get_provider
from .dreaming_repository import DreamingRepository

logger = get_logger(__name__)
app = typer.Typer(help="Dreaming worker for content analysis")


class ProcessingMode(str, Enum):
    BATCH = "batch"
    DIRECT = "direct"
    COMPLETION = "completion"


class DreamJob(BaseModel):
    """Dream analysis job."""

    id: str
    tenant_id: str
    status: str = "pending"
    mode: ProcessingMode = ProcessingMode.DIRECT
    batch_id: str | None = None
    memory_proxy_job_id: str | None = None  # MemoryProxy job ID for tracking
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None


class DreamingWorker:
    """Processes user content for insights and relationships using DreamModel."""

    def __init__(self, repo: DreamingRepository = None):
        self.repo = repo or DreamingRepository()
        self.memory_proxy = MemoryProxy()

    async def cleanup(self):
        """Clean up resources (close aiohttp sessions)."""
        try:
            if hasattr(self.memory_proxy, 'close'):
                await self.memory_proxy.close()
        except Exception as e:
            logger.debug(f"Error closing memory proxy: {e}")

    async def collect_user_data(
        self, tenant_id: str, time_window_hours: int = 24, only_new: bool = True
    ) -> UserDataBatch:
        """Collect user sessions and resources for analysis.

        Args:
            tenant_id: Tenant to collect data for
            time_window_hours: Hours to look back for data
            only_new: If True, exclude data that already has associated moments
        """
        # Get recent sessions (within time window)
        sessions = await self.repo.get_sessions(
            tenant_id=tenant_id,
            limit=100,
            since_hours=time_window_hours
        )

        # Get resources (within time window)
        resources = await self.repo.get_resources(
            tenant_id=tenant_id,
            limit=1000,
            since_hours=time_window_hours
        )

        # Filter out data that already has moments generated (prevent duplicates)
        if only_new and (sessions or resources):
            from p8fs.models.p8 import Moment
            from p8fs.repository import TenantRepository

            moment_repo = TenantRepository(Moment, tenant_id=tenant_id)

            # Get existing moments from last 48h to check for overlap
            existing_moments = await moment_repo.select(
                filters={},
                order_by=["-created_at"],
                limit=500
            )

            # Build set of session IDs and resource IDs that already have moments
            processed_session_ids = set()
            processed_resource_names = set()

            for moment in existing_moments:
                metadata = moment.metadata or {}
                # Check session_ids in metadata
                if 'session_ids' in metadata:
                    processed_session_ids.update(metadata['session_ids'])
                # Check if moment references a resource by name or URI
                if moment.uri:
                    processed_resource_names.add(moment.uri)
                if moment.name:
                    processed_resource_names.add(moment.name)

            # Filter sessions
            if sessions:
                original_count = len(sessions)
                sessions = [s for s in sessions if s.get('id') not in processed_session_ids]
                filtered_count = original_count - len(sessions)
                if filtered_count > 0:
                    logger.info(f"Filtered out {filtered_count} sessions that already have moments")

            # Filter resources
            if resources:
                original_count = len(resources)
                resources = [
                    r for r in resources
                    if r.get('name') not in processed_resource_names
                    and r.get('uri') not in processed_resource_names
                ]
                filtered_count = original_count - len(resources)
                if filtered_count > 0:
                    logger.info(f"Filtered out {filtered_count} resources that already have moments")

        # Get user profile information
        user_profile = await self.repo.get_tenant_profile(tenant_id) or {}

        logger.info(
            f"Collected data for {tenant_id} (last {time_window_hours}h, only_new={only_new}): "
            f"{len(sessions or [])} sessions, {len(resources or [])} resources"
        )

        return UserDataBatch(
            user_profile=user_profile,
            sessions=sessions or [],
            resources=resources or [],
            time_window_hours=time_window_hours,
        )

    async def _get_tenant_email(self, tenant_id: str) -> str | None:
        """Get tenant email from database, fallback to test email."""
        try:
            user_profile = await self.repo.get_tenant_profile(tenant_id)
            if user_profile and user_profile.get("email"):
                return user_profile["email"]
        except Exception as e:
            logger.warning(f"Failed to fetch tenant email from database: {e}")

        # Fallback for testing
        if tenant_id == "tenant-test":
            return "amartey@gmail.com"

        return None

    async def _send_moments_email(
        self,
        moments: list[Moment],
        recipient_email: str,
        tenant_id: str
    ) -> bool:
        """Send email digest of moments to recipient.

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        try:
            from p8fs.services.email import EmailService, MomentEmailBuilder
            from datetime import datetime

            logger.info(f"Preparing to send moments digest to {recipient_email} ({len(moments)} moments)")

            if not moments:
                logger.warning("No moments to send in email")
                return False

            # Build beautiful multi-moment digest using MomentEmailBuilder
            builder = MomentEmailBuilder(theme="warm")
            email_html = builder.build_moments_digest_html(
                moments=moments,
                date_title="Your Daily Moments"
            )

            # Build plain text version with all moments
            sorted_moments = sorted(
                moments,
                key=lambda m: m.resource_timestamp or m.created_at or datetime.min,
                reverse=True
            )
            text_sections = []
            for i, moment in enumerate(sorted_moments[:10], 1):
                text_sections.append(
                    f"{i}. {moment.name}\n"
                    f"   {moment.summary or moment.content[:150]}\n"
                )

            text_content = f"""Your Daily Moments - {datetime.now().strftime("%B %d, %Y")}

We captured {len(moments)} moment{'s' if len(moments) != 1 else ''} from your day.

{''.join(text_sections)}

---
Powered by EEPIS Memory System
"""

            # Send email
            email_service = EmailService()
            from_addr = email_service.username

            # Use fixed subject for email threading (deterministic)
            subject = "Your Daily Moments"

            logger.info(f"Sending moments digest from {from_addr} to {recipient_email} ({len(moments)} moments)")

            email_service.send_email(
                subject=subject,
                html_content=email_html,
                to_addrs=recipient_email,
                text_content=text_content
            )

            logger.info(f"Successfully sent moments digest to {recipient_email} ({len(moments)} moments)")
            return True

        except Exception as e:
            logger.error(f"Failed to send moments email: {e}", exc_info=True)
            return False

    async def analyze_user_dreams(
        self, tenant_id: str, data_batch: UserDataBatch, model: str = None
    ) -> DreamModel:
        """Analyze user data using LLM to create structured dream analysis."""
        if model is None:
            model = config.default_model
        # Build analysis prompt for the LLM
        analysis_prompt = self._build_analysis_prompt(data_batch)

        # Get structured analysis from LLM using DreamModel as the response format
        try:
            logger.info(f"Analyzing user data with LLM for tenant {tenant_id} (model: {model})")
            logger.debug(f"Analysis prompt length: {len(analysis_prompt)} characters")

            # Use MemoryProxy with DreamModel to get structured output
            from p8fs.services.llm.models import CallingContext

            proxy = MemoryProxy(DreamModel)

            context = CallingContext(
                model=model,
                tenant_id=tenant_id,
                temperature=0.1,  # Lower for structured output
                max_tokens=4000,  # Compatible with most models
                session_type="dreaming"  # Mark as dreaming to exclude from future dreaming analysis
            )

            # Use parse_content to get structured DreamModel output
            response = await proxy.parse_content(
                content=analysis_prompt,
                context=context,
                merge_strategy="last"
            )

            # Set user_id if not already set
            if hasattr(response, "user_id") and not response.user_id:
                response.user_id = tenant_id

            # Create metrics if not present
            if not hasattr(response, "metrics") or not response.metrics:
                response.metrics = DreamAnalysisMetrics(
                    total_documents_analyzed=len(data_batch.resources),
                    confidence_score=0.8,
                    data_completeness=(
                        0.9 if data_batch.sessions and data_batch.resources else 0.5
                    ),
                )

            return response

        except Exception as e:
            logger.error(f"Failed to analyze dreams for {tenant_id}: {e}")
            # Return minimal DreamModel on failure
            return DreamModel(
                user_id=tenant_id,
                executive_summary="Unable to complete analysis due to processing error.",
                key_themes=["error"],
                metrics=DreamAnalysisMetrics(
                    total_documents_analyzed=len(data_batch.resources),
                    confidence_score=0.0,
                    data_completeness=0.0,
                ),
            )
        finally:
            # Clean up proxy resources
            if 'proxy' in locals():
                try:
                    await proxy.close()
                except Exception as e:
                    logger.debug(f"Error closing dream proxy: {e}")

    def _build_analysis_prompt(self, data_batch: UserDataBatch) -> str:
        """Build comprehensive analysis prompt for the LLM."""
        sessions_summary = (
            f"{len(data_batch.sessions)} chat sessions"
            if data_batch.sessions
            else "no chat sessions"
        )
        resources_summary = (
            f"{len(data_batch.resources)} resources/documents"
            if data_batch.resources
            else "no documents"
        )

        # Extract some sample content for context
        sample_sessions = data_batch.sessions[:3] if data_batch.sessions else []
        sample_resources = data_batch.resources[:5] if data_batch.resources else []

        prompt = f"""
You are an expert personal insights analyst. Analyze the following user data to extract meaningful patterns and actionable intelligence.

User Profile: {data_batch.user_profile}

Data Summary:
- {sessions_summary}
- {resources_summary}
- Time window: {data_batch.time_window_hours} hours

Sample Recent Sessions:
{self._format_sessions(sample_sessions)}

Sample Resources:
{self._format_resources(sample_resources)}

Please provide a comprehensive analysis following the DreamModel structure:

1. Executive Summary: High-level summary of the user's current situation and focus areas
2. Key Themes: Major themes discovered across all documents
3. Entity Relationships: Key relationships between people, organizations, and concepts
4. Personal Insights:
   - Goals and objectives (career, personal, financial, health, etc.)
   - Fears and concerns (what's holding them back)
   - Dreams and aspirations (short-term and long-term)
5. Action Items:
   - Pending tasks and commitments
   - Appointments and scheduled events
6. Recommendations: AI-generated recommendations and priority actions

Focus on being insightful, actionable, empathetic, comprehensive, and respectful.
Provide confidence scores for relationships and categorize everything clearly.
"""
        return prompt

    def _format_sessions(self, sessions: list) -> str:
        """Format sessions for prompt context."""
        if not sessions:
            return "No recent sessions available."

        formatted = []
        for session in sessions[:3]:  # Limit to avoid token overflow
            content = session.get("content", session.get("messages", ""))[:200] + "..."
            formatted.append(f"- Session: {content}")

        return "\n".join(formatted)

    def _format_resources(self, resources: list) -> str:
        """Format resources for prompt context."""
        if not resources:
            return "No resources available."

        formatted = []
        for resource in resources[:5]:  # Limit to avoid token overflow
            title = resource.get("title", resource.get("name", "Untitled"))
            content = resource.get("content", resource.get("text", ""))[:150] + "..."
            formatted.append(f"- {title}: {content}")

        return "\n".join(formatted)

    async def process_batch(self, tenant_id: str) -> DreamJob:
        """Submit batch job to OpenAI using DreamModel structure."""
        data_batch = await self.collect_user_data(tenant_id)

        # Create job record
        job = DreamJob(id=str(uuid4()), tenant_id=tenant_id, mode=ProcessingMode.BATCH)

        # Build analysis request for batch processing
        analysis_request = UserDreamAnalysisRequest(
            user_id=tenant_id,
            data_batch=data_batch,
            analysis_depth="comprehensive",
            include_recommendations=True,
        )

        # Build prompt for batch processing
        analysis_prompt = self._build_analysis_prompt(data_batch)

        try:
            # Submit to OpenAI batch API using correct MemoryProxy interface
            from p8fs.services.llm.models import BatchCallingContext
            
            batch_context = BatchCallingContext.for_comprehensive_batch(
                model=config.default_model
            )
            batch_context.tenant_id = tenant_id
            batch_context.save_job = True
            
            batch_response = await self.memory_proxy.batch(
                analysis_prompt, 
                batch_context
            )

            job.batch_id = batch_response.batch_id
            if batch_response.job_id:
                job.memory_proxy_job_id = batch_response.job_id
            await self.repo.create_dream_job(job.model_dump())

            logger.info(
                f"Submitted batch dream analysis job: {job.id} (batch_id: {batch_response.batch_id}) for tenant {tenant_id}"
            )

        except Exception as e:
            logger.error(f"Failed to submit batch job for {tenant_id}: {e}")
            job.status = "failed"
            job.result = {"error": str(e)}
            job.completed_at = datetime.now(timezone.utc)
            await self.repo.create_dream_job(job.model_dump())

        return job

    async def process_direct(self, tenant_id: str, model: str = None, limit: int = None) -> DreamJob:
        """Process directly using DreamModel analysis.

        Args:
            tenant_id: Tenant ID to process
            model: LLM model to use (defaults to config)
            limit: Maximum number of resources to process (None = no limit)
        """
        if model is None:
            model = config.default_model
        data_batch = await self.collect_user_data(tenant_id)

        # Create job record
        job = DreamJob(id=str(uuid4()), tenant_id=tenant_id, mode=ProcessingMode.DIRECT)

        try:
            # Analyze using DreamModel
            dream_analysis = await self.analyze_user_dreams(tenant_id, data_batch, model=model)

            # Store the complete DreamModel result
            job.result = dream_analysis.model_dump()
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)

            # Save dream analysis to repository
            await self.repo.store_dream_analysis(dream_analysis)

            logger.info(
                f"Completed direct processing: {job.id} with {len(dream_analysis.goals)} goals, {len(dream_analysis.dreams)} dreams"
            )

        except Exception as e:
            logger.error(f"Direct processing failed for {tenant_id}: {e}")
            job.result = {"error": str(e)}
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)

        await self.repo.create_dream_job(job.model_dump())
        return job

    async def process_resource_affinity(
        self,
        tenant_id: str,
        use_llm: bool = None,
        limit: int = None,
    ) -> dict[str, Any]:
        """Process resource affinity to build knowledge graph relationships.

        Args:
            tenant_id: Tenant ID to process
            use_llm: Whether to use LLM mode for intelligent assessment (defaults to config)
            limit: Maximum number of resources to process (None = no limit)

        Returns:
            Statistics about affinity processing
        """
        if not config.dreaming_affinity_enabled:
            logger.info("Resource affinity processing is disabled in config")
            return {"enabled": False, "processed": 0}

        use_llm_mode = use_llm if use_llm is not None else config.dreaming_affinity_use_llm

        logger.info(f"Processing resource affinity for tenant {tenant_id} (LLM mode: {use_llm_mode})")

        provider = get_provider()
        provider.connect_sync()

        builder = ResourceAffinityBuilder(provider, tenant_id)

        total_stats = {
            "tenant_id": tenant_id,
            "basic_mode_processed": 0,
            "llm_mode_processed": 0,
            "total_updated": 0,
            "total_edges_added": 0,
        }

        try:
            logger.info("Running basic mode (semantic search)...")
            basic_stats = await builder.process_resource_batch(
                lookback_hours=config.dreaming_lookback_hours,
                batch_size=config.dreaming_affinity_basic_batch_size,
                mode="basic",
            )

            total_stats["basic_mode_processed"] = basic_stats["processed"]
            total_stats["total_updated"] += basic_stats["updated"]
            total_stats["total_edges_added"] += basic_stats["total_edges_added"]

            logger.info(
                f"Basic mode complete: {basic_stats['processed']} processed, "
                f"{basic_stats['updated']} updated, {basic_stats['total_edges_added']} edges"
            )

            if use_llm_mode:
                logger.info("Running LLM mode (intelligent assessment)...")
                llm_stats = await builder.process_resource_batch(
                    lookback_hours=config.dreaming_lookback_hours,
                    batch_size=config.dreaming_affinity_llm_batch_size,
                    mode="llm",
                )

                total_stats["llm_mode_processed"] = llm_stats["processed"]
                total_stats["total_updated"] += llm_stats["updated"]
                total_stats["total_edges_added"] += llm_stats["total_edges_added"]

                logger.info(
                    f"LLM mode complete: {llm_stats['processed']} processed, "
                    f"{llm_stats['updated']} updated, {llm_stats['total_edges_added']} edges"
                )

        except Exception as e:
            logger.error(f"Resource affinity processing failed for {tenant_id}: {e}")
            total_stats["error"] = str(e)

        logger.info(
            f"Resource affinity complete for {tenant_id}: "
            f"{total_stats['total_updated']} resources updated with "
            f"{total_stats['total_edges_added']} total edges"
        )

        return total_stats

    async def process_moments(
        self,
        tenant_id: str,
        model: str = "gpt-4o",
        recipient_email: str | None = None,
        limit: int = None,
        lookback_hours: int = 24,
    ) -> DreamJob:
        """Process user activity data to extract and save moments.

        Args:
            tenant_id: Tenant ID to process
            model: LLM model to use
            recipient_email: Email address to send moment digest
            limit: Maximum number of resources to process (None = no limit)
            lookback_hours: How many hours back to look for data (default: 24)
        """
        import json

        data_batch = await self.collect_user_data(tenant_id, time_window_hours=lookback_hours)

        # Create job record
        job = DreamJob(id=str(uuid4()), tenant_id=tenant_id, mode=ProcessingMode.DIRECT)

        try:
            logger.info(f"Analyzing moments for tenant {tenant_id} (model: {model})")
            logger.info(f"Data collected: {len(data_batch.sessions)} sessions, {len(data_batch.resources)} resources")

            # Early skip if no data to analyze
            if not data_batch.sessions and not data_batch.resources:
                logger.info(f"Skipping moment processing for {tenant_id}: no sessions or resources in {lookback_hours}h window")
                job.result = {
                    "total_moments": 0,
                    "moment_ids": [],
                    "analysis_summary": f"No activity found in {lookback_hours}h window",
                    "email_sent": False,
                    "skipped": True
                }
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc)
                await self.repo.create_dream_job(job.model_dump())
                return job

            # Build content from sessions and resources for moment extraction
            # Serialize to JSON with default=str to handle datetime objects
            content_for_analysis = json.dumps({
                "sessions": data_batch.sessions,
                "resources": data_batch.resources,
                "time_window_hours": data_batch.time_window_hours
            }, default=str)

            logger.info(f"Content for analysis length: {len(content_for_analysis)} chars")

            # Use MemoryProxy with MomentBuilder to get structured moments

            proxy = MemoryProxy(MomentBuilder)

            context = CallingContext(
                model=model,
                tenant_id=tenant_id,
                temperature=0.1,
                max_tokens=4000,
                session_type="dreaming"  # Mark as dreaming to exclude from future dreaming analysis
            )

            # Parse content into moments
            result = await proxy.parse_content(
                content=content_for_analysis,
                context=context,
                merge_strategy="last"
            )

            # Debug: Log the actual LLM response
            logger.info(f"LLM returned result type: {type(result)}")
            logger.info(f"Result moments count: {len(result.moments) if hasattr(result, 'moments') else 'N/A'}")
            logger.info(f"Result object: {result.model_dump() if hasattr(result, 'model_dump') else result}")
            if hasattr(result, 'moments') and result.moments:
                logger.info(f"First moment sample: {result.moments[0]}")

            # Check if result is valid
            if not hasattr(result, 'moments'):
                logger.warning(f"LLM did not return valid MomentBuilder object, got {type(result)}: {result}")
                job.result = {"total_moments": 0, "error": "LLM did not return valid response"}
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc)
                await self.repo.create_dream_job(job.model_dump())
                return job

            # Save moments to database
            moment_repo = TenantRepository(Moment, tenant_id=tenant_id)

            # Extract session IDs and resource names for tracking
            session_ids = [str(s.get('id')) for s in data_batch.sessions if s.get('id')]
            resource_names = [r.get('name') for r in data_batch.resources if r.get('name')]

            # Build list of all moments to batch upsert
            moments_to_save = []
            for moment_data in result.moments:
                # Get present_persons - keep as list for the model
                present_persons = moment_data.get('present_persons', [])
                # Ensure it's a list (model expects list[Person])
                if not isinstance(present_persons, list):
                    present_persons = []

                # Merge LLM metadata with source tracking
                moment_metadata = moment_data.get('metadata', {})
                moment_metadata['session_ids'] = session_ids  # Track which sessions this came from
                moment_metadata['resource_names'] = resource_names  # Track which resources this came from

                # Convert moment dict to Moment model
                # Only use fields that actually exist in database
                moment = Moment(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    name=moment_data.get('name') or "Untitled Moment",
                    content=moment_data.get('content') or moment_data.get('summary') or "",
                    summary=moment_data.get('summary'),
                    present_persons=present_persons,
                    location=moment_data.get('location'),
                    moment_type=moment_data.get('moment_type'),
                    emotion_tags=moment_data.get('emotion_tags', []),
                    topic_tags=moment_data.get('topic_tags', []),
                    resource_timestamp=moment_data.get('resource_timestamp'),
                    resource_ends_timestamp=moment_data.get('resource_ends_timestamp'),
                    metadata=moment_metadata
                )
                moments_to_save.append(moment)

            # Batch upsert all moments at once (generates embeddings in batch)
            if moments_to_save:
                logger.info(f"Upserting {len(moments_to_save)} moments in batch")

                # Debug: Log the moment data to see which fields have UUIDs
                for i, moment in enumerate(moments_to_save):
                    logger.debug(f"Moment {i} data types: {[(k, type(v).__name__) for k, v in moment.model_dump().items()]}")

                try:
                    result = await moment_repo.upsert(moments_to_save)
                    # Verify the upsert actually succeeded by checking affected_rows
                    if result and result.get("affected_rows", 0) > 0:
                        actual_rows = result.get("affected_rows", 0)
                        saved_moment_ids = [str(m.id) for m in moments_to_save]
                        saved_moments = moments_to_save
                        logger.info(f"✅ Successfully saved {actual_rows} moments to database (expected {len(moments_to_save)})")
                    else:
                        logger.error(f"❌ Failed to save moments - upsert returned: {result}")
                        saved_moment_ids = []
                        saved_moments = []
                except Exception as e:
                    import traceback
                    logger.error(f"❌ Failed to save moments to database: {e}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    saved_moment_ids = []
                    saved_moments = []
            else:
                saved_moment_ids = []
                saved_moments = []

            # Store result in job
            job.result = {
                "total_moments": len(saved_moment_ids),
                "moment_ids": saved_moment_ids,
                "analysis_summary": result.analysis_summary if hasattr(result, 'analysis_summary') else None,
                "email_sent": False  # Default to False
            }
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)

            logger.info(
                f"Completed moment processing: {job.id} with {len(saved_moment_ids)} moments saved"
            )

            # Send email if recipient is provided
            if recipient_email and saved_moments:
                email_sent = await self._send_moments_email(
                    moments=saved_moments,
                    recipient_email=recipient_email,
                    tenant_id=tenant_id
                )
                job.result["email_sent"] = email_sent

        except Exception as e:
            logger.error(f"Moment processing failed for {tenant_id}: {e}")
            import traceback
            traceback.print_exc()
            job.result = {"error": str(e)}
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
        finally:
            # Clean up proxy resources
            if 'proxy' in locals():
                try:
                    await proxy.close()
                except Exception as e:
                    logger.debug(f"Error closing moment proxy: {e}")

        await self.repo.create_dream_job(job.model_dump())
        return job

    async def check_completions(self):
        """Check and process completed batch jobs with DreamModel results."""
        # Get pending batch jobs
        jobs = await self.repo.get_dream_jobs(
            status="pending", mode=ProcessingMode.BATCH
        )

        for job_data in jobs:
            job = DreamJob(**job_data)

            try:
                # Check batch status using correct MemoryProxy interface
                # Use memory_proxy_job_id if available, otherwise fall back to batch_id
                job_id = getattr(job, 'memory_proxy_job_id', None) or job.batch_id
                
                job_status = await self.memory_proxy.get_job(
                    job_id=job_id,
                    tenant_id=job.tenant_id,
                    fetch_results=True
                )

                if job_status.is_complete:
                    # Extract results from job status
                    batch_result = None
                    if job_status.results and len(job_status.results) > 0:
                        # For batch jobs, results are typically a list
                        batch_result = job_status.results[0] if isinstance(job_status.results[0], dict) else {"content": job_status.results[0]}

                    # Parse result as DreamModel if possible
                    if batch_result and isinstance(batch_result, dict):
                        try:
                            dream_analysis = DreamModel(**batch_result)

                            # Store the structured analysis
                            await self.repo.store_dream_analysis(dream_analysis)

                            # Update job with result
                            job.result = dream_analysis.model_dump()
                            job.status = "completed"
                            job.completed_at = datetime.now(timezone.utc)

                            logger.info(
                                f"Completed batch job: {job.id} with {len(dream_analysis.goals)} goals, {len(dream_analysis.dreams)} dreams"
                            )

                        except Exception as parse_error:
                            logger.warning(
                                f"Failed to parse batch result as DreamModel for job {job.id}: {parse_error}"
                            )
                            # Store raw result if parsing fails
                            job.result = batch_result
                            job.status = "completed"
                            job.completed_at = datetime.now(timezone.utc)
                    else:
                        # Handle empty or invalid results
                        job.result = {"error": "No valid result from batch processing"}
                        job.status = "failed"
                        job.completed_at = datetime.now(timezone.utc)

                    await self.repo.update_dream_job(job.id, job.model_dump())

                elif hasattr(job_status, 'is_failed') and job_status.is_failed:
                    # Handle batch failure
                    job.status = "failed"
                    job.result = {"error": "Batch processing failed"}
                    job.completed_at = datetime.now(timezone.utc)
                    await self.repo.update_dream_job(job.id, job.model_dump())
                    logger.error(f"Batch job failed: {job.id}")

            except Exception as e:
                logger.error(f"Error checking completion for job {job.id}: {e}")
                # Mark job as failed
                job.status = "failed"
                job.result = {"error": str(e)}
                job.completed_at = datetime.now(timezone.utc)
                await self.repo.update_dream_job(job.id, job.model_dump())


@app.command()
def process(
    mode: ProcessingMode = typer.Option(ProcessingMode.DIRECT, help="Processing mode"),
    tenant_id: str | None = typer.Option(None, help="Tenant ID (for batch/direct)"),
    completion: bool = typer.Option(False, help="Check completions mode"),
):
    """Process dreaming tasks in different modes."""

    async def run():
        if completion or mode == ProcessingMode.COMPLETION:
            # Completion mode - check all tenants
            worker = DreamingWorker()
            await worker.check_completions()

        else:
            if not tenant_id:
                typer.echo("Tenant ID required for batch/direct mode")
                raise typer.Exit(1)

            # Initialize dreaming worker with default repository
            worker = DreamingWorker()

            if mode == ProcessingMode.BATCH:
                await worker.process_batch(tenant_id)
            elif mode == ProcessingMode.DIRECT:
                await worker.process_direct(tenant_id)

    asyncio.run(run())


@app.command()
def affinity(
    tenant_id: str | None = typer.Option(None, help="Tenant ID to process (None = all tenants)"),
    use_llm: bool = typer.Option(None, help="Use LLM mode (defaults to config)"),
    lookback_hours: int = typer.Option(None, help="Hours to look back (defaults to config)"),
):
    """Process resource affinity to build knowledge graph relationships."""

    async def run():
        worker = DreamingWorker()

        if tenant_id:
            # Process single tenant
            logger.info(f"Processing affinity for tenant: {tenant_id}")
            stats = await worker.process_resource_affinity(tenant_id, use_llm=use_llm)
            logger.info(f"Affinity processing complete: {stats}")
        else:
            # Process all tenants
            logger.info("Processing affinity for all tenants")

            provider = get_provider()
            provider.connect_sync()

            tenants = provider.execute(
                "SELECT DISTINCT tenant_id FROM resources WHERE created_at >= NOW() - INTERVAL '%s hours'",
                (lookback_hours or config.dreaming_lookback_hours,),
            )

            if not tenants:
                logger.info("No tenants found with recent resources")
                return

            logger.info(f"Found {len(tenants)} tenants to process")

            for tenant in tenants:
                tid = tenant["tenant_id"]
                logger.info(f"\nProcessing tenant: {tid}")
                try:
                    stats = await worker.process_resource_affinity(tid, use_llm=use_llm)
                    logger.info(f"  Complete: {stats['total_updated']} resources updated, {stats['total_edges_added']} edges added")
                except Exception as e:
                    logger.error(f"  Failed: {e}")

            logger.info("\nAll tenants processed")

    asyncio.run(run())


@app.command()
def insights(
    tenant_id: str | None = typer.Option(None, help="Tenant ID to process (None = all tenants)"),
    use_llm: bool = typer.Option(None, help="Use LLM mode for affinity (defaults to config)"),
    model: str = typer.Option(None, help="Model for moments generation (defaults to config)"),
    lookback_hours: int = typer.Option(12, help="Hours to look back for data (default: 12)"),
):
    """Process complete insights: moments generation + resource affinity."""

    async def run():
        worker = DreamingWorker()

        if tenant_id:
            # Process single tenant
            logger.info(f"Processing insights for tenant: {tenant_id} (lookback: {lookback_hours}h)")

            # 1. Generate moments
            if config.dreaming_enabled:
                logger.info("  Generating moments...")
                try:
                    # Get recipient email for moment digest
                    recipient_email = await worker._get_tenant_email(tenant_id)

                    moments_job = await worker.process_moments(
                        tenant_id=tenant_id,
                        model=model or config.default_model,
                        recipient_email=recipient_email,
                        lookback_hours=lookback_hours
                    )
                    if moments_job.result:
                        moment_count = moments_job.result.get("total_moments", 0)
                        logger.info(f"  ✓ Generated {moment_count} moments")
                except Exception as e:
                    logger.error(f"  ✗ Moments generation failed: {e}")

            # 2. Build resource affinity
            if config.dreaming_affinity_enabled:
                logger.info("  Building resource affinity...")
                try:
                    affinity_stats = await worker.process_resource_affinity(
                        tenant_id=tenant_id,
                        use_llm=use_llm
                    )
                    logger.info(
                        f"  ✓ Affinity complete: {affinity_stats['total_updated']} resources, "
                        f"{affinity_stats['total_edges_added']} edges"
                    )
                except Exception as e:
                    logger.error(f"  ✗ Affinity processing failed: {e}")

            logger.info(f"\nInsights processing complete for {tenant_id}")

        else:
            # Process all tenants
            logger.info(f"Processing insights for all tenants (lookback: {lookback_hours}h)")

            # Get active tenants from repository (handles dialect correctly)
            repo = DreamingRepository()
            tenant_ids = await repo.get_active_tenants(lookback_hours=lookback_hours)

            if not tenant_ids:
                logger.info("No tenants found with recent activity")
                return

            logger.info(f"Found {len(tenant_ids)} tenants to process\n")

            total_moments = 0
            total_edges = 0

            # Group tenants by email to avoid sending duplicate emails
            email_to_tenants = {}

            for tid in tenant_ids:
                # Get tenant email
                recipient_email = await worker._get_tenant_email(tid)
                if recipient_email:
                    if recipient_email not in email_to_tenants:
                        email_to_tenants[recipient_email] = []
                    email_to_tenants[recipient_email].append(tid)

            logger.info(f"Email deduplication: {len(tenant_ids)} tenants → {len(email_to_tenants)} unique emails\n")

            # Process each tenant
            tenant_moments_by_email = {}  # Track moments per email for batched sending

            for tid in tenant_ids:
                logger.info(f"Processing tenant: {tid}")

                # 1. Generate moments (without sending email yet)
                if config.dreaming_enabled:
                    try:
                        moments_job = await worker.process_moments(
                            tenant_id=tid,
                            model=model or config.default_model,
                            recipient_email=None,  # Don't send email yet
                            lookback_hours=lookback_hours
                        )
                        if moments_job.result:
                            moment_count = moments_job.result.get("total_moments", 0)
                            if moment_count > 0:
                                total_moments += moment_count
                                logger.info(f"  Moments: {moment_count}")

                                # Track moments for email batching
                                recipient_email = await worker._get_tenant_email(tid)
                                if recipient_email:
                                    if recipient_email not in tenant_moments_by_email:
                                        tenant_moments_by_email[recipient_email] = []
                                    tenant_moments_by_email[recipient_email].append((tid, moment_count))
                            else:
                                logger.info(f"  Moments: 0 (skipped - no data)")
                    except Exception as e:
                        logger.error(f"  Moments failed: {e}")

                # 2. Build resource affinity
                if config.dreaming_affinity_enabled:
                    try:
                        affinity_stats = await worker.process_resource_affinity(tid, use_llm=use_llm)
                        edges = affinity_stats['total_edges_added']
                        total_edges += edges
                        logger.info(f"  Affinity: {affinity_stats['total_updated']} resources, {edges} edges")
                    except Exception as e:
                        logger.error(f"  Affinity failed: {e}")

            logger.info(f"\n{'=' * 80}")
            logger.info(f"ALL TENANTS COMPLETE")
            logger.info(f"{'=' * 80}")
            logger.info(f"Total moments generated: {total_moments}")
            logger.info(f"Total affinity edges: {total_edges}")
            logger.info(f"Unique emails to notify: {len(tenant_moments_by_email)}")
            logger.info(f"{'=' * 80}\n")

    asyncio.run(run())


async def summarize_user(
    tenant_id: str,
    max_sessions: int = 100,
    max_moments: int = 20,
    max_resources: int = 20,
    max_files: int = 10
) -> dict[str, Any]:
    """
    Summarize user's recent activity to create/update p8fs-user-info Resource.

    Loads recent chat sessions, moment keys, resource keys, and file uploads
    to generate a comprehensive user summary using LLM analysis.

    Args:
        tenant_id: Tenant identifier
        max_sessions: Maximum number of recent chat sessions to analyze (default: 100)
        max_moments: Maximum number of recent moment keys to include (default: 20)
        max_resources: Maximum number of recent resource keys to include (default: 20)
        max_files: Maximum number of recent file uploads to include (default: 10)

    Returns:
        Dictionary containing:
        - success: Whether the operation succeeded
        - summary: Generated user summary
        - sessions_analyzed: Number of sessions analyzed
        - moments_available: Number of moment keys included
        - resources_available: Number of resource keys included
        - files_available: Number of file uploads included
        - error: Error message if failed
    """
    from p8fs.models.p8 import Session, Resources, Files
    from p8fs.models.user_context import UserContext

    logger.info(f"Summarizing user activity for {tenant_id} (sessions={max_sessions}, moments={max_moments}, resources={max_resources})")

    try:
        # 1. Load recent chat sessions with messages
        session_repo = TenantRepository(model_class=Session, tenant_id=tenant_id)
        sessions = await session_repo.select(
            filters={},
            order_by=["-created_at"],
            limit=max_sessions
        )

        session_summaries = []
        for session in sessions:
            metadata = session.metadata or {}
            messages = metadata.get("messages", [])
            session_summaries.append({
                "date": session.created_at.isoformat() if session.created_at else "unknown",
                "query": session.query or "No query",
                "message_count": len(messages),
                "total_tokens": metadata.get("total_tokens", 0),
                "model": metadata.get("model", "unknown")
            })

        # 2. Load recent moment keys (names/IDs only)
        moment_repo = TenantRepository(model_class=Moment, tenant_id=tenant_id)
        moments = await moment_repo.select(
            filters={},
            order_by=["-created_at"],
            limit=max_moments
        )

        moment_keys = [
            {
                "name": moment.name,
                "date": moment.created_at.isoformat() if moment.created_at else "unknown",
                "summary": moment.summary or ""
            }
            for moment in moments
        ]

        # 3. Load recent resource keys (names/IDs only)
        resource_repo = TenantRepository(model_class=Resources, tenant_id=tenant_id)
        resources = await resource_repo.select(
            filters={},
            order_by=["-created_at"],
            limit=max_resources
        )

        resource_keys = [
            {
                "name": resource.name,
                "category": resource.category,
                "date": resource.created_at.isoformat() if resource.created_at else "unknown"
            }
            for resource in resources
        ]

        # 4. Load recent file uploads
        file_repo = TenantRepository(model_class=Files, tenant_id=tenant_id)
        files = await file_repo.select(
            filters={},
            order_by=["-created_at"],
            limit=max_files
        )

        file_list = [
            {
                "uri": f.uri,
                "date": f.created_at.isoformat() if f.created_at else "unknown"
            }
            for f in files
        ]

        # 5. Generate summary using MemoryProxy
        current_date = datetime.now().isoformat()

        summarization_prompt = f"""You are analyzing a user's recent activity to create a comprehensive user profile summary.

Current Date: {current_date}

**Recent Chat Sessions ({len(session_summaries)} sessions)**:
{_format_session_list(session_summaries)}

**Available Moment Keys ({len(moment_keys)} moments)** - Use REM LOOKUP to retrieve full content:
{_format_key_list(moment_keys)}

**Available Resource Keys ({len(resource_keys)} resources)** - Use REM LOOKUP to retrieve full content:
{_format_key_list(resource_keys)}

**Recent File Uploads ({len(file_list)} files)**:
{_format_file_list(file_list)}

---

Based on this activity, create a concise user summary (200-400 words) that captures:

1. **User Interests & Focus Areas**: What topics does the user engage with?
2. **Activity Patterns**: When and how often does the user interact?
3. **Key Projects/Goals**: What are they working on or trying to achieve?
4. **Preferred Tools/Technologies**: What tools, languages, or systems do they use?
5. **Recent Context**: What have they been doing lately?

IMPORTANT: End your summary with a hint about using REM LOOKUP to retrieve more details:
"Use REM LOOKUP with the moment names, resource names, or file URIs listed above to retrieve full content and learn more about specific items."

Write in third person, factual tone. Focus on actionable insights."""

        # Use MemoryProxy to call LLM
        context = CallingContext(
            model=config.query_engine_model or "gpt-4.1-mini",
            temperature=0.3,
            tenant_id=tenant_id,
            user_id=tenant_id
        )

        async with MemoryProxy() as proxy:
            summary = await proxy.run(summarization_prompt, context)

        # 6. Update p8fs-user-info Resource
        await UserContext.update_summary(
            tenant_id=tenant_id,
            summary=summary,
            metadata={
                "last_updated": current_date,
                "sessions_analyzed": len(session_summaries),
                "moments_available": len(moment_keys),
                "resources_available": len(resource_keys),
                "files_available": len(file_list),
                "total_tokens": sum(s["total_tokens"] for s in session_summaries)
            }
        )

        logger.info(
            f"User summary updated: {len(session_summaries)} sessions, "
            f"{len(moment_keys)} moments, {len(resource_keys)} resources"
        )

        return {
            "success": True,
            "summary": summary,
            "sessions_analyzed": len(session_summaries),
            "moments_available": len(moment_keys),
            "resources_available": len(resource_keys),
            "files_available": len(file_list),
            "moment_keys": moment_keys,
            "resource_keys": resource_keys,
            "file_list": file_list
        }

    except Exception as e:
        logger.error(f"Failed to summarize user: {e}")
        return {
            "success": False,
            "error": str(e),
            "sessions_analyzed": 0,
            "moments_available": 0,
            "resources_available": 0,
            "files_available": 0
        }


def _format_session_list(sessions: list[dict]) -> str:
    """Format session list for prompt."""
    if not sessions:
        return "No recent sessions"

    lines = []
    for s in sessions[:10]:
        lines.append(
            f"- {s['date']}: {s['message_count']} messages, {s['total_tokens']} tokens, "
            f"query: \"{s['query'][:100]}...\""
        )

    if len(sessions) > 10:
        lines.append(f"... and {len(sessions) - 10} more sessions")

    return "\n".join(lines)


def _format_key_list(items: list[dict]) -> str:
    """Format key list for prompt."""
    if not items:
        return "No items available"

    lines = []
    for item in items:
        extra = f" ({item.get('category', '')})" if item.get('category') else ""
        lines.append(f"- {item['name']}{extra} - {item['date']}")

    return "\n".join(lines)


def _format_file_list(files: list[dict]) -> str:
    """Format file list for prompt."""
    if not files:
        return "No recent file uploads"

    lines = []
    for f in files:
        lines.append(f"- {f['uri']} - {f['date']}")

    return "\n".join(lines)


if __name__ == "__main__":
    app()
