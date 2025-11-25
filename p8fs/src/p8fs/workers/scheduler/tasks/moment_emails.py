"""Scheduled tasks for sending moment emails to tenants.

NOTE: These tasks are currently DISABLED in favor of Kubernetes CronJobs.
The scheduler infrastructure remains available for local development and testing.
The dreaming worker CLI handles email sending as part of moment processing.
"""

from datetime import datetime, timedelta, timezone
from p8fs_cluster.logging import get_logger
from p8fs.workers.scheduler import scheduled

logger = get_logger(__name__)


# @scheduled(
#     hour="*/3",
#     description="Send moment emails to all active tenants",
#     worker_type="user_insight_worker",
#     memory="512Mi",
#     envs=["development", "production"]
# )
async def send_tenant_moment_emails():
    """
    Send moment emails to all tenants with moments created in the last 3 hours.

    This task runs every 3 hours and:
    1. Queries all active tenants
    2. For each tenant, finds moments created in the last 3 hours
    3. Sends a digest email if moments exist
    """
    from p8fs.workers.dreaming import DreamingWorker
    from p8fs.workers.dreaming_repository import DreamingRepository
    from p8fs.models.p8 import Moment

    logger.info("Starting scheduled moment email task")

    repo = DreamingRepository()
    worker = DreamingWorker(repo)

    # Get all active tenants
    tenants = await repo.get_all_active_tenants()
    logger.info(f"Found {len(tenants)} active tenants")

    total_emails_sent = 0
    time_window_start = datetime.now(timezone.utc) - timedelta(hours=3)

    for tenant_data in tenants:
        tenant_id = tenant_data.get("tenant_id")

        try:
            # Get tenant email
            recipient_email = await worker._get_tenant_email(tenant_id)

            if not recipient_email:
                logger.debug(f"No email configured for tenant {tenant_id}, skipping")
                continue

            # Get moments created in the last 3 hours
            moments = await repo.get_recent_moments(
                tenant_id=tenant_id,
                since=time_window_start,
                limit=10
            )

            if not moments:
                logger.debug(f"No recent moments for tenant {tenant_id}")
                continue

            # Convert to Moment objects
            moment_objects = [Moment(**m) for m in moments]

            logger.info(
                f"Sending moment email to {recipient_email} "
                f"({len(moment_objects)} moments for tenant {tenant_id})"
            )

            # Send email
            await worker._send_moments_email(
                moments=moment_objects,
                recipient_email=recipient_email,
                tenant_id=tenant_id
            )

            total_emails_sent += 1

        except Exception as e:
            logger.error(f"Failed to send moment email for tenant {tenant_id}: {e}")
            # Continue with other tenants even if one fails
            continue

    logger.info(
        f"Completed moment email task: sent {total_emails_sent} emails to "
        f"{len(tenants)} active tenants"
    )


# @scheduled(
#     hour="9",
#     minute="0",
#     description="Send daily moment summary at 9 AM UTC",
#     worker_type="user_insight_worker",
#     memory="512Mi",
#     envs=["production"]
# )
async def send_daily_moment_summary():
    """
    Send daily moment summary emails at 9 AM UTC.

    This task:
    1. Queries all active tenants
    2. For each tenant, finds moments from the previous day
    3. Sends a daily digest email
    """
    from p8fs.workers.dreaming import DreamingWorker
    from p8fs.workers.dreaming_repository import DreamingRepository
    from p8fs.models.p8 import Moment

    logger.info("Starting daily moment summary task")

    repo = DreamingRepository()
    worker = DreamingWorker(repo)

    # Get all active tenants
    tenants = await repo.get_all_active_tenants()
    logger.info(f"Found {len(tenants)} active tenants for daily summary")

    total_emails_sent = 0
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    for tenant_data in tenants:
        tenant_id = tenant_data.get("tenant_id")

        try:
            # Get tenant email
            recipient_email = await worker._get_tenant_email(tenant_id)

            if not recipient_email:
                logger.debug(f"No email configured for tenant {tenant_id}, skipping")
                continue

            # Get yesterday's moments
            moments = await repo.get_recent_moments(
                tenant_id=tenant_id,
                since=yesterday,
                limit=50
            )

            if not moments:
                logger.debug(f"No moments from yesterday for tenant {tenant_id}")
                continue

            # Convert to Moment objects
            moment_objects = [Moment(**m) for m in moments]

            logger.info(
                f"Sending daily summary to {recipient_email} "
                f"({len(moment_objects)} moments for tenant {tenant_id})"
            )

            # Send email with custom title
            await worker._send_moments_email(
                moments=moment_objects,
                recipient_email=recipient_email,
                tenant_id=tenant_id
            )

            total_emails_sent += 1

        except Exception as e:
            logger.error(f"Failed to send daily summary for tenant {tenant_id}: {e}")
            continue

    logger.info(
        f"Completed daily moment summary: sent {total_emails_sent} emails to "
        f"{len(tenants)} active tenants"
    )
