"""Scheduler data models."""


from pydantic import BaseModel


class ScheduledTask(BaseModel):
    """Scheduled task metadata."""
    
    name: str
    module: str
    function_name: str
    description: str
    minute: str | None = None
    hour: str | None = None
    day: str | None = None
    envs: list[str]
    worker_type: str
    memory: str