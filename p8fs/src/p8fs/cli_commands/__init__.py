"""CLI command modules for P8FS."""

from .agent import agent_command
from .query import query_command
from .process import process_command
from .scheduler import scheduler_command
from .sql_gen import sql_gen_command
from .router import router_command
from .dreaming import dreaming_command
from .files import files_command
from .test_worker import test_worker_command
from .eval import eval_command
from .storage_worker import storage_worker_command
from .ingest_images import ingest_images_command
from .retry import retry_command

__all__ = [
    "agent_command",
    "query_command",
    "process_command",
    "scheduler_command",
    "sql_gen_command",
    "router_command",
    "dreaming_command",
    "files_command",
    "test_worker_command",
    "eval_command",
    "storage_worker_command",
    "ingest_images_command",
    "retry_command",
]
