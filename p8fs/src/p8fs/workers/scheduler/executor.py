"""Task executor for scheduled tasks.

IMPORTANT: Concurrent Task Execution
====================================
This executor supports concurrent task execution. Tasks are NOT blocked by other
running tasks. When a task is triggered, it runs in the background using 
asyncio.create_task() rather than blocking with await. This ensures that:

1. Multiple scheduled tasks can run simultaneously
2. Long-running tasks don't delay other scheduled tasks
3. The scheduler remains responsive to all configured schedules
4. Health reports and other periodic tasks execute on time

Key implementation details:
- Tasks use asyncio.create_task() for non-blocking execution
- Background tasks are properly logged with start/completion messages
- Clean up of execution mode flags after task completion

This design prevents issues where one task (e.g., dream analysis) would block
other critical tasks (e.g., health reports) from executing on schedule.
"""

import asyncio
import importlib
import os
from datetime import datetime

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from p8fs.services.nats.client import NATSClient

from .models import ScheduledTask

logger = get_logger(__name__)


class TaskExecutor:
    """Execute scheduled tasks via NATS or direct execution."""
    
    def __init__(self, tenant_id: str = "system"):
        """Initialize task executor.
        
        Args:
            tenant_id: Tenant ID for scheduled tasks.
        """
        self.tenant_id = tenant_id
        self.nats_client: NATSClient | None = None
        
    async def setup(self):
        """Initialize NATS connection."""
        try:
            self.nats_client = NATSClient()
            await self.nats_client.connect()
            logger.info("Task executor NATS client connected")
        except Exception as e:
            logger.warning(f"NATS connection failed: {e}")
            logger.info("Task executor will run in direct execution mode")
            self.nats_client = None
            
    async def execute_task(self, task: ScheduledTask):
        """Execute a scheduled task.
        
        Tries to send the task to a NATS worker queue first. If that fails
        or NATS is unavailable, falls back to direct execution.
        
        Args:
            task: The scheduled task to execute.
        """
        try:
            logger.info(f"Executing scheduled task: {task.name}")
            logger.info(f"Task: {task.description}")
            logger.info(f"Worker: {task.worker_type} ({task.memory})")
            logger.info(f"Time: {datetime.utcnow().isoformat()}")
            
            # Check if forced inline execution is enabled
            if config.scheduler_force_inline or os.getenv("P8FS_SCHEDULER_FORCE_INLINE", "").lower() == "true":
                logger.info("Forced inline execution enabled - executing task directly")
                await self._execute_directly(task, "FORCED_INLINE")
                return
                
            # Try to send message to NATS
            if self.nats_client and self.nats_client.is_connected:
                try:
                    await self._execute_via_nats(task)
                    return
                except Exception as e:
                    logger.warning(f"NATS execution failed: {e}")
                    logger.info("Falling back to direct execution")
                    await self._execute_directly(task, "NATS_FAILURE_FALLBACK")
                    return
                    
            # Fall back to direct execution
            logger.info("NATS unavailable - executing task directly")
            await self._execute_directly(task, "NATS_UNAVAILABLE")
            
        except Exception as e:
            logger.error(f"Error executing task {task.name}: {e}")
            
    async def _run_task_with_logging(self, task_name: str, task_coro):
        """Run a task coroutine with proper logging and error handling."""
        try:
            logger.info(f"⚡ Background task {task_name} started execution")
            result = await task_coro
            logger.info(f"✅ Background task {task_name} completed successfully")
            return result
        except Exception as e:
            logger.error(f"❌ Background task {task_name} failed: {e}")
            raise
        finally:
            # Clean up the execution mode flag
            os.environ.pop("P8FS_EXECUTION_MODE", None)
    
    async def _execute_via_nats(self, task: ScheduledTask):
        """Execute task by sending message to NATS worker queue."""
        message = {
            "tenant_id": self.tenant_id,
            "task_name": task.name,
            "module": task.module,
            "function_name": task.function_name,
            "worker_type": task.worker_type,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        # Send to the appropriate worker queue
        subject = f"jobs.{task.worker_type}"
        await self.nats_client.publish_json(subject, message)
        
        logger.info(f"Sent message to NATS subject: {subject}")
        logger.info("NATS message sent - worker should process task")
        
    async def _execute_directly(self, task: ScheduledTask, execution_mode: str):
        """Execute task directly by importing and calling the function."""
        try:
            # Import and execute the task directly
            module = importlib.import_module(task.module)
            task_function = getattr(module, task.function_name)
            
            # Set execution mode flag
            os.environ["P8FS_EXECUTION_MODE"] = execution_mode
            
            logger.info(f"Directly executing: {task.function_name}")
            if asyncio.iscoroutinefunction(task_function):
                # Create a task to run concurrently instead of blocking
                task_coro = task_function()
                asyncio.create_task(self._run_task_with_logging(task.name, task_coro))
                logger.info(f"🚀 Task {task.name} started in background")
            else:
                task_function()
                logger.info("✅ Synchronous task completed")
                # Clean up flag for synchronous tasks
                os.environ.pop("P8FS_EXECUTION_MODE", None)
            
        except Exception as e:
            logger.error(f"Direct execution failed: {e}")
            # Clean up flag on error
            os.environ.pop("P8FS_EXECUTION_MODE", None)
            raise
            
    async def cleanup(self):
        """Clean up resources."""
        if self.nats_client:
            await self.nats_client.disconnect()
            self.nats_client = None