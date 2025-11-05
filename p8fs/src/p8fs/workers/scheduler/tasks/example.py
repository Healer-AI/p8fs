"""Example scheduled tasks for P8FS scheduler."""

from p8fs_cluster.logging import get_logger

from p8fs.workers.scheduler import scheduled

logger = get_logger(__name__)


@scheduled(
    hour="*/1",  # Every hour
    description="Hourly system status check",
    worker_type="status_worker",
    envs=["development", "production"],
)
async def hourly_status_check():
    """Run system status check every hour."""
    logger.info("Running hourly system status check")
    logger.info("All systems operational")


@scheduled(
    day="*/1",  # Daily
    hour="3",  # At 3 AM
    minute="0",
    description="Daily maintenance and optimization",
    worker_type="maintenance_worker",
    memory="512Mi",
    envs=["production"],
)
async def daily_maintenance():
    """Run daily maintenance tasks."""
    logger.info("Running daily maintenance tasks")
    logger.info("Daily maintenance completed")
