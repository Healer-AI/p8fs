"""Dreaming worker for processing user content insights."""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

import typer
from p8fs_cluster.logging import get_logger
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
from p8fs.models.engram.models import Moment
from p8fs.repository import TenantRepository
from p8fs.services.llm import MemoryProxy
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

    async def collect_user_data(
        self, tenant_id: str, time_window_hours: int = 24
    ) -> UserDataBatch:
        """Collect user sessions and resources for analysis."""
        # Get recent sessions
        sessions = await self.repo.get_sessions(tenant_id=tenant_id, limit=100)

        # Get resources
        resources = await self.repo.get_resources(tenant_id=tenant_id, limit=1000)

        # Get user profile information
        user_profile = await self.repo.get_tenant_profile(tenant_id) or {}

        logger.info(f"Collected data for {tenant_id}: {len(sessions or [])} sessions, {len(resources or [])} resources")

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
    ):
        """Send email digest of moments to recipient."""
        try:
            from p8fs.services.email import EmailService, MomentEmailBuilder

            logger.info(f"Preparing to send moments email to {recipient_email}")

            # Build HTML email for each moment (or combine them)
            # For now, send the first moment as a sample
            if not moments:
                logger.warning("No moments to send in email")
                return

            # Use the first moment for the email
            moment = moments[0]

            # Build email
            builder = MomentEmailBuilder()
            email_html = builder.build_moment_email_html(
                moment=moment,
                date_title="Your Daily Moments"
            )

            # Get email subject from moment name
            subject = f"EEPIS Moments: {moment.name}"

            # Send email
            email_service = EmailService()
            email_service.send_email(
                subject=subject,
                html_content=email_html,
                to_addrs=recipient_email,
                text_content=f"{moment.name}\n\n{moment.content}"
            )

            logger.info(f"Successfully sent moments email to {recipient_email}")

        except Exception as e:
            logger.error(f"Failed to send moments email: {e}")
            # Don't fail the job if email fails
            pass

    async def analyze_user_dreams(
        self, tenant_id: str, data_batch: UserDataBatch, model: str = "gpt-4-turbo-preview"
    ) -> DreamModel:
        """Analyze user data using LLM to create structured dream analysis."""
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
                max_tokens=4000  # Compatible with most models
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
                model="gpt-4-turbo-preview"
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

    async def process_direct(self, tenant_id: str, model: str = "gpt-4-turbo-preview") -> DreamJob:
        """Process directly using DreamModel analysis."""
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

    async def process_moments(
        self,
        tenant_id: str,
        model: str = "gpt-4o",
        recipient_email: str | None = None
    ) -> DreamJob:
        """Process user activity data to extract and save moments."""
        import json

        data_batch = await self.collect_user_data(tenant_id)

        # Create job record
        job = DreamJob(id=str(uuid4()), tenant_id=tenant_id, mode=ProcessingMode.DIRECT)

        try:
            logger.info(f"Analyzing moments for tenant {tenant_id} (model: {model})")
            logger.info(f"Data collected: {len(data_batch.sessions)} sessions, {len(data_batch.resources)} resources")

            # Build content from sessions and resources for moment extraction
            # Serialize to JSON with default=str to handle datetime objects
            content_for_analysis = json.dumps({
                "sessions": data_batch.sessions,
                "resources": data_batch.resources,
                "time_window_hours": data_batch.time_window_hours
            }, default=str)

            logger.info(f"Content for analysis length: {len(content_for_analysis)} chars")

            # Use MemoryProxy with MomentBuilder to get structured moments
            from p8fs.services.llm.models import CallingContext

            proxy = MemoryProxy(MomentBuilder)

            context = CallingContext(
                model=model,
                tenant_id=tenant_id,
                temperature=0.1,
                max_tokens=4000
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
            saved_moment_ids = []
            saved_moments = []

            for moment_data in result.moments:
                # Convert present_persons from list to dict if needed
                present_persons = moment_data.get('present_persons', {})
                if isinstance(present_persons, list):
                    # Convert list of person objects to dict keyed by fingerprint_id
                    # Use person_N as key if fingerprint_id is None/missing
                    present_persons = {
                        person.get('fingerprint_id') or f'person_{i}': person
                        for i, person in enumerate(present_persons)
                    }

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
                    metadata=moment_data.get('metadata', {})
                )

                # Save to database
                saved_moment = await moment_repo.upsert(moment)
                # Handle both dict and object returns
                moment_id = saved_moment.id if hasattr(saved_moment, 'id') else saved_moment.get('id', moment.id)
                saved_moment_ids.append(str(moment_id))
                saved_moments.append(saved_moment)

                logger.info(
                    f"Saved moment: {moment.name} ({moment.moment_type}) "
                    f"[{moment.resource_timestamp} - {moment.resource_ends_timestamp}]"
                )

            # Store result in job
            job.result = {
                "total_moments": len(saved_moment_ids),
                "moment_ids": saved_moment_ids,
                "analysis_summary": result.analysis_summary if hasattr(result, 'analysis_summary') else None
            }
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)

            logger.info(
                f"Completed moment processing: {job.id} with {len(saved_moment_ids)} moments saved"
            )

            # Send email if recipient is provided
            if recipient_email and saved_moments:
                await self._send_moments_email(
                    moments=saved_moments,
                    recipient_email=recipient_email,
                    tenant_id=tenant_id
                )

        except Exception as e:
            logger.error(f"Moment processing failed for {tenant_id}: {e}")
            import traceback
            traceback.print_exc()
            job.result = {"error": str(e)}
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)

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


if __name__ == "__main__":
    app()
