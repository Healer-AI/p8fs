"""Scheduled tasks for dreaming worker - moments and resource affinity processing.

NOTE: These tasks are currently DISABLED in favor of Kubernetes CronJobs.
The scheduler infrastructure remains available for local development and testing.
The dreaming worker CLI handles all these tasks: moments, affinity, emails, user summaries.
"""

from datetime import datetime, timezone
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config
from p8fs.workers.scheduler import scheduled

logger = get_logger(__name__)


# @scheduled(
#     hour="*/6",  # Every 6 hours
#     description="Generate moments and build resource affinity for all tenants",
#     worker_type="dreaming_worker",
#     memory="1Gi",
#     envs=["development", "production"]
# )
async def process_tenant_insights():
    """
    Process tenant insights including moments and resource affinity.

    This task runs every 6 hours and:
    1. Discovers all active tenants
    2. For each tenant:
       - Generates moments from recent activity
       - Builds resource affinity graph (semantic + LLM modes)
    3. Logs statistics for monitoring
    """
    from p8fs.workers.dreaming import DreamingWorker
    from p8fs.workers.dreaming_repository import DreamingRepository

    logger.info("Starting scheduled dreaming insights task")

    repo = DreamingRepository()
    worker = DreamingWorker(repo)

    # Get all active tenants
    tenants = await repo.get_all_active_tenants()
    logger.info(f"Found {len(tenants)} active tenants for insights processing")

    total_moments_generated = 0
    total_affinity_edges = 0
    total_tenants_processed = 0

    for tenant_data in tenants:
        tenant_id = tenant_data.get("tenant_id")

        try:
            logger.info(f"Processing insights for tenant: {tenant_id}")

            # 1. Generate moments from recent activity
            if config.dreaming_enabled:
                try:
                    moments_job = await worker.process_moments(
                        tenant_id=tenant_id,
                        model=config.default_model
                    )

                    if moments_job.result:
                        moment_count = moments_job.result.get("total_moments", 0)
                        total_moments_generated += moment_count
                        logger.info(f"  Generated {moment_count} moments for {tenant_id}")
                except Exception as e:
                    logger.error(f"  Failed to generate moments for {tenant_id}: {e}")

            # 2. Build resource affinity graph
            if config.dreaming_affinity_enabled:
                try:
                    affinity_stats = await worker.process_resource_affinity(
                        tenant_id=tenant_id,
                        use_llm=config.dreaming_affinity_use_llm
                    )

                    edges_added = affinity_stats.get("total_edges_added", 0)
                    total_affinity_edges += edges_added
                    logger.info(
                        f"  Built affinity graph for {tenant_id}: "
                        f"{affinity_stats.get('total_updated', 0)} resources, "
                        f"{edges_added} edges"
                    )
                except Exception as e:
                    logger.error(f"  Failed to build affinity for {tenant_id}: {e}")

            total_tenants_processed += 1

        except Exception as e:
            logger.error(f"Failed to process insights for tenant {tenant_id}: {e}")
            continue

    logger.info(
        f"Completed dreaming insights task: "
        f"{total_tenants_processed}/{len(tenants)} tenants processed, "
        f"{total_moments_generated} moments generated, "
        f"{total_affinity_edges} affinity edges created"
    )


# @scheduled(
#     day="*/1",  # Daily
#     hour="2",   # At 2 AM UTC
#     minute="0",
#     description="Daily deep resource affinity analysis with LLM",
#     worker_type="dreaming_worker",
#     memory="2Gi",
#     envs=["production"]
# )
async def daily_deep_affinity_analysis():
    """
    Perform deep resource affinity analysis daily using LLM mode.

    This task runs daily at 2 AM UTC and:
    1. Discovers all active tenants
    2. Runs resource affinity with LLM mode enabled
    3. Uses larger batch sizes for comprehensive analysis
    """
    from p8fs.workers.dreaming import DreamingWorker
    from p8fs.workers.dreaming_repository import DreamingRepository

    logger.info("Starting daily deep affinity analysis task")

    repo = DreamingRepository()
    worker = DreamingWorker(repo)

    # Get all active tenants
    tenants = await repo.get_all_active_tenants()
    logger.info(f"Found {len(tenants)} active tenants for deep analysis")

    total_edges = 0
    total_resources = 0

    for tenant_data in tenants:
        tenant_id = tenant_data.get("tenant_id")

        try:
            logger.info(f"Deep analysis for tenant: {tenant_id}")

            # Run with LLM mode for intelligent relationship assessment
            affinity_stats = await worker.process_resource_affinity(
                tenant_id=tenant_id,
                use_llm=True  # Always use LLM for deep analysis
            )

            resources_updated = affinity_stats.get("total_updated", 0)
            edges_added = affinity_stats.get("total_edges_added", 0)

            total_resources += resources_updated
            total_edges += edges_added

            logger.info(
                f"  Completed deep analysis for {tenant_id}: "
                f"{resources_updated} resources, {edges_added} edges"
            )

        except Exception as e:
            logger.error(f"Failed deep analysis for tenant {tenant_id}: {e}")
            continue

    logger.info(
        f"Completed daily deep affinity analysis: "
        f"{total_resources} resources updated, "
        f"{total_edges} total edges created"
    )
