"""Main task scheduler coordinator.

IMPORTANT: Concurrent Task Execution
====================================
This scheduler supports concurrent task execution. Tasks are NOT blocked by other
running tasks. When a task is triggered, it runs in the background using 
asyncio.create_task() rather than blocking with await. This ensures that:

1. Multiple scheduled tasks can run simultaneously
2. Long-running tasks don't delay other scheduled tasks
3. The scheduler remains responsive to all configured schedules
4. Health reports and other periodic tasks execute on time

Key implementation details:
- Job defaults configured with max_instances=3 to allow concurrent runs
- Tasks use asyncio.create_task() for non-blocking execution
- Background tasks are properly logged with start/completion messages
- Clean up of execution mode flags after task completion

This design prevents issues where one task (e.g., dream analysis) would block
other critical tasks (e.g., health reports) from executing on schedule.
"""

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from .discovery import TaskDiscovery
from .executor import TaskExecutor
from .models import ScheduledTask

logger = get_logger(__name__)


class TaskScheduler:
    """Main scheduler that coordinates task discovery, scheduling, and execution."""
    
    def __init__(self, tenant_id: str = "system"):
        """Initialize task scheduler.
        
        Args:
            tenant_id: Tenant ID for scheduled tasks.
        """
        self.tenant_id = tenant_id
        # Configure scheduler with job defaults to allow concurrent execution
        job_defaults = {
            'coalesce': False,  # Don't coalesce missed jobs
            'max_instances': 3,  # Allow up to 3 instances of the same job
            'misfire_grace_time': 30  # Allow 30 seconds grace time for misfired jobs
        }
        self.scheduler = AsyncIOScheduler(
            timezone=config.scheduler_timezone,
            job_defaults=job_defaults
        )
        self.discovery = TaskDiscovery()
        self.executor = TaskExecutor(tenant_id)
        self.tasks: list[ScheduledTask] = []
        
    async def setup(self):
        """Initialize scheduler components."""
        logger.info("Setting up task scheduler")
        
        # Initialize executor
        await self.executor.setup()
        
        # Discover scheduled tasks
        self.tasks = list(self.discovery.discover_tasks())
        logger.info(f"Discovered {len(self.tasks)} scheduled tasks:")
        
        for task in self.tasks:
            logger.info(f"  📋 {task.name} ({task.module}): {task.description}")
            logger.info(f"      Schedule: minute={task.minute}, hour={task.hour}, day={task.day}")
            logger.info(f"      Worker: {task.worker_type} ({task.memory})")
            
        # Schedule all discovered tasks
        for task in self.tasks:
            self._schedule_task(task)
            
    def _schedule_task(self, task: ScheduledTask):
        """Schedule a task using APScheduler."""
        trigger_kwargs = {}
        
        # Build cron trigger parameters
        if task.minute:
            if task.minute.startswith("*/"):
                trigger_kwargs["minute"] = task.minute
            else:
                trigger_kwargs["minute"] = int(task.minute)
                
        if task.hour:
            if task.hour.startswith("*/"):
                trigger_kwargs["hour"] = task.hour
            else:
                trigger_kwargs["hour"] = int(task.hour)
                
        if task.day:
            if task.day.startswith("*/"):
                trigger_kwargs["day"] = task.day
            else:
                trigger_kwargs["day"] = int(task.day)
                
        if not trigger_kwargs:
            logger.warning(f"Task {task.name} has no schedule defined, skipping")
            return
            
        # Create the scheduled job
        job_id = f"{task.module}.{task.name}"
        self.scheduler.add_job(
            func=self.executor.execute_task,
            trigger=CronTrigger(**trigger_kwargs),
            args=[task],
            id=job_id,
            name=task.description,
            replace_existing=True,
        )
        
        logger.info(f"Scheduled task {task.name} with trigger: {trigger_kwargs}")
        
    async def run(self):
        """Start the scheduler and run until interrupted."""
        try:
            await self.setup()
            
            if not config.scheduler_enabled:
                logger.info("Scheduler is disabled in configuration")
                return
                
            # Start the scheduler
            self.scheduler.start()
            logger.info("Task scheduler started successfully")
            
            # Keep running until interrupted
            while True:
                await asyncio.sleep(60)
                
        except KeyboardInterrupt:
            logger.info("Scheduler interrupted, shutting down...")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            raise
        finally:
            await self.cleanup()
            
    async def cleanup(self):
        """Clean up scheduler resources."""
        logger.info("Cleaning up scheduler")
        
        if self.scheduler.running:
            self.scheduler.shutdown()
            
        await self.executor.cleanup()
        
        logger.info("Scheduler shutdown complete")
        
    def get_scheduled_jobs(self) -> list[dict]:
        """Get information about currently scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return jobs