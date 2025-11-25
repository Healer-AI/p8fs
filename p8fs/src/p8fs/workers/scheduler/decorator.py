"""Scheduler decorator for marking functions as scheduled tasks."""

from collections.abc import Callable
from functools import wraps

from p8fs_cluster.config.settings import config


def scheduled(
    minute: str | int | None = None,
    hour: str | int | None = None,
    day: str | int | None = None,
    envs: list[str] | None = None,
    worker_type: str | None = None,
    memory: str | None = None,
    description: str | None = None,
):
    """Mark a function as a scheduled task.

    Args:
        minute: Cron expression for minutes (e.g., '*/15' for every 15 minutes)
        hour: Cron expression for hours (e.g., '*/1' for every hour)
        day: Cron expression for days (e.g., '*/1' for every day)
        envs: List of environments where this task should run
        worker_type: Type of worker to handle this task
        memory: Memory requirement for the worker
        description: Human-readable description of the task

    Example:
        @scheduled(hour='*/1', description="Send hourly user insights")
        async def send_user_insights():
            pass
    """
    if envs is None:
        envs = ["development", "production"]
    
    if worker_type is None:
        worker_type = config.scheduler_default_worker_type
        
    if memory is None:
        memory = config.scheduler_default_memory

    def decorator(func: Callable) -> Callable:
        func._scheduled = True
        func._schedule_minute = minute
        func._schedule_hour = hour
        func._schedule_day = day
        func._schedule_envs = envs
        func._schedule_worker_type = worker_type
        func._schedule_memory = memory
        func._schedule_description = (
            description or func.__doc__ or f"Scheduled task: {func.__name__}"
        )

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        wrapper._scheduled = func._scheduled
        wrapper._schedule_minute = func._schedule_minute
        wrapper._schedule_hour = func._schedule_hour
        wrapper._schedule_day = func._schedule_day
        wrapper._schedule_envs = func._schedule_envs
        wrapper._schedule_worker_type = func._schedule_worker_type
        wrapper._schedule_memory = func._schedule_memory
        wrapper._schedule_description = func._schedule_description

        return wrapper

    return decorator