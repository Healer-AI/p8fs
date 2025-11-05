"""P8FS Core - Memory system with RAG/IR features and database repositories."""

try:
    from p8fs_cluster import P8FSConfig, get_logger, setup_logging
    from p8fs_cluster.config.settings import config as settings
    
    # Initialize logging for the core module
    logger = get_logger(__name__)
    __all__ = ["P8FSConfig", "settings", "setup_logging", "get_logger", "logger"]
except ImportError:
    # Fallback logger if p8fs_cluster is not available
    import logging
    logger = logging.getLogger(__name__)
    __all__ = ["logger"]

__version__ = "0.1.0"