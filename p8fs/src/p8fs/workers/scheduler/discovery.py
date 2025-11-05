"""Task discovery for scheduled functions."""

import importlib
import inspect
import pkgutil
from collections.abc import Iterator
from pathlib import Path

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from .models import ScheduledTask

logger = get_logger(__name__)


class TaskDiscovery:
    """Discover scheduled tasks from configured package."""
    
    def __init__(self, package_name: str | None = None):
        """Initialize task discovery.
        
        Args:
            package_name: Package to search for scheduled tasks. 
                         Uses config.scheduler_discovery_package if None.
        """
        self.package_name = package_name or config.scheduler_discovery_package
        
    def discover_tasks(self) -> Iterator[ScheduledTask]:
        """Discover all functions decorated with @scheduled.
        
        Searches all modules in the configured package for functions with 
        the _scheduled attribute.
        
        Yields:
            ScheduledTask objects for discovered tasks.
        """
        current_env = config.environment
        logger.info(f"Discovering scheduled tasks for environment: {current_env}")
        
        # Try to find the package path
        package_path = self._get_package_path()
        if not package_path:
            logger.warning(f"Package {self.package_name} not found for task discovery")
            return
            
        # Walk through all modules in the package
        for module_info in pkgutil.walk_packages([str(package_path)], f"{self.package_name}."):
            # Skip __pycache__ and other non-Python files
            if "__pycache__" in module_info.name:
                continue
                
            try:
                # Import the module
                module = importlib.import_module(module_info.name)
                
                # Look for scheduled functions
                for name, obj in inspect.getmembers(module):
                    if hasattr(obj, "_scheduled") and obj._scheduled:
                        # Check if this task should run in current environment
                        if current_env not in obj._schedule_envs:
                            logger.debug(
                                f"Skipping task {name} in {module_info.name} "
                                f"(not enabled for {current_env})"
                            )
                            continue
                            
                        task = ScheduledTask(
                            name=name,
                            module=module_info.name,
                            function_name=name,
                            description=obj._schedule_description,
                            minute=obj._schedule_minute,
                            hour=obj._schedule_hour,
                            day=obj._schedule_day,
                            envs=obj._schedule_envs,
                            worker_type=obj._schedule_worker_type,
                            memory=obj._schedule_memory,
                        )
                        
                        logger.info(
                            f"Found scheduled task: {task.name} in {task.module} "
                            f"({task.description})"
                        )
                        yield task
                        
            except Exception as e:
                logger.error(f"Error importing module {module_info.name}: {e}")
                    
    def _get_package_path(self) -> Path | None:
        """Get the filesystem path for the discovery package."""
        try:
            # Try to import the package to get its path
            package = importlib.import_module(self.package_name)
            if hasattr(package, '__path__'):
                return Path(package.__path__[0])
            elif hasattr(package, '__file__'):
                return Path(package.__file__).parent
        except ImportError:
            # Package doesn't exist yet, that's ok
            pass
            
        return None