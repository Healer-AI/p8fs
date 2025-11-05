"""Central environment variable loading utilities."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv


def load_environment(env_file: str | Path | None = None) -> None:
    """Load environment variables from .env file if it exists.
    
    Args:
        env_file: Path to .env file. If None, looks for .env in current directory.
    """
    if env_file is None:
        env_file = Path.cwd() / ".env"
    
    if isinstance(env_file, str):
        env_file = Path(env_file)
    
    if env_file.exists():
        load_dotenv(env_file)


def get_env_list(key: str, default: list[str] | None = None) -> list[str]:
    """Get environment variable as a list, parsing JSON array format.
    
    Args:
        key: Environment variable name
        default: Default value if not found
        
    Returns:
        List of strings
        
    Examples:
        P8FS_TIKV_ENDPOINTS=["localhost:2379","localhost:2380"]
        P8FS_CORS_ORIGINS=["http://localhost:3000","http://localhost:8080"]
    """
    value = os.getenv(key)
    if not value:
        return default or []
    
    # Try to parse as JSON array first
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Fallback to comma-separated values
    return [item.strip() for item in value.split(",") if item.strip()]


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get environment variable as boolean.
    
    Args:
        key: Environment variable name
        default: Default value if not found
        
    Returns:
        Boolean value
    """
    value = os.getenv(key, "").lower()
    return value in ("true", "1", "yes", "on", "enabled") if value else default


def get_env_int(key: str, default: int = 0) -> int:
    """Get environment variable as integer.
    
    Args:
        key: Environment variable name
        default: Default value if not found
        
    Returns:
        Integer value
    """
    value = os.getenv(key)
    if not value:
        return default
    
    try:
        return int(value)
    except ValueError:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Invalid integer value for {key}='{value}', using default {default}")
        return default


def get_env_float(key: str, default: float = 0.0) -> float:
    """Get environment variable as float.
    
    Args:
        key: Environment variable name
        default: Default value if not found
        
    Returns:
        Float value
    """
    value = os.getenv(key)
    if not value:
        return default
    
    try:
        return float(value)
    except ValueError:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Invalid float value for {key}='{value}', using default {default}")
        return default


def parse_port(port_str: str, default: int = 8000) -> int:
    """Parse port from various formats including Kubernetes service format.
    
    Args:
        port_str: Port string (e.g., "8000", "tcp://10.107.144.156:8000")
        default: Default port if parsing fails
        
    Returns:
        Port number as integer
    """
    if not port_str:
        return default
    
    # Handle Kubernetes service format: tcp://ip:port
    if port_str.startswith("tcp://"):
        try:
            return int(port_str.split(":")[-1])
        except (ValueError, IndexError):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Invalid port format '{port_str}', using default {default}")
            return default
    
    # Handle plain integer
    try:
        return int(port_str)
    except ValueError:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Invalid port value '{port_str}', using default {default}")
        return default


def get_env_port(key: str, default: int = 8000) -> int:
    """Get environment variable as port number with Kubernetes support.
    
    Args:
        key: Environment variable name
        default: Default port if not found
        
    Returns:
        Port number as integer
    """
    value = os.getenv(key)
    return parse_port(value, default) if value else default