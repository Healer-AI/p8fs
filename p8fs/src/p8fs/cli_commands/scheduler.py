"""Scheduler command for running task scheduler."""

import sys
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


async def scheduler_command(args):
    """Run the task scheduler."""
    try:
        from p8fs.workers.scheduler import TaskScheduler

        logger.info(f"Starting task scheduler (tenant: {args.tenant_id})")

        scheduler = TaskScheduler(tenant_id=args.tenant_id)

        if args.list_tasks:
            # Just discover and list tasks without running
            await scheduler.setup()
            print(f"\nDiscovered {len(scheduler.tasks)} scheduled tasks:")
            for task in scheduler.tasks:
                print(f"  📋 {task.name} ({task.module})")
                print(f"      Description: {task.description}")
                print(f"      Schedule: minute={task.minute}, hour={task.hour}, day={task.day}")
                print(f"      Worker: {task.worker_type} ({task.memory})")
                print(f"      Environments: {', '.join(task.envs)}")
                print()
            return 0

        # Run the scheduler
        await scheduler.run()
        return 0

    except Exception as e:
        logger.error(f"Scheduler command failed: {e}", exc_info=True)
        print(f"❌ Scheduler error: {e}", file=sys.stderr)
        return 1
