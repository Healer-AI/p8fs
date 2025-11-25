"""Centralized logging setup using Loguru."""

import sys
import warnings
from pathlib import Path
from typing import Any

from loguru import logger

from ..config.settings import config


def setup_logging(
    level: str | None = None,
    log_file: Path | None = None,
    rotation: str = "100 MB",
    retention: str = "7 days",
    compression: str = "gz",
    diagnose: bool | None = None,
    colorize: bool | None = None,
    format_template: str | None = None
) -> None:
    """Setup centralized logging configuration for P8FS.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file. If None, logs to stdout only
        rotation: Log rotation setting
        retention: Log retention period
        compression: Compression format for rotated logs
        diagnose: Enable diagnostic info in logs
        colorize: Enable colored output
        format_template: Custom format template
    """
    # Suppress Pydantic V2 deprecation warnings from inspect module
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        message=".*Pydantic.*",
        module="inspect"
    )

    # Remove default handler
    logger.remove()
    
    # Use config values if not specified
    level = level or config.log_level
    diagnose = diagnose if diagnose is not None else config.is_development
    colorize = colorize if colorize is not None else config.is_development
    
    # Level emoji mapping
    level_emoji = {
        "CRITICAL": "🚨",
        "ERROR": "🚨",
        "WARNING": "⚠️",
        "INFO": "",
        "DEBUG": "",
        "TRACE": ""
    }

    # Development format (colorized, detailed with emoji)
    dev_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{extra[emoji]}{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Production format (plain, structured with emoji)
    prod_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {extra[emoji]}{level: <8} | {name}:{function}:{line} | {message}"
    )
    
    format_template = format_template or (dev_format if config.is_development else prod_format)

    # Custom patcher to inject emoji based on level
    def patcher(record):
        record["extra"]["emoji"] = level_emoji.get(record["level"].name, "")

    # Console handler
    logger.add(
        sys.stderr,
        level=level,
        format=format_template,
        colorize=colorize,
        diagnose=diagnose,
        enqueue=True,  # Thread-safe logging
        catch=True      # Catch exceptions in logging
    )

    # File handler (if specified)
    if log_file:
        logger.add(
            log_file,
            level=level,
            format=prod_format,  # Always use plain format for files
            rotation=rotation,
            retention=retention,
            compression=compression,
            diagnose=diagnose,
            enqueue=True,
            catch=True
        )
    
    # Add service context
    logger_context = {
        "service": config.otel_service_name,
        "version": config.otel_service_version,
        "environment": config.environment,
        "tenant": config.default_tenant_id,
    }

    logger.configure(extra=logger_context, patcher=patcher)
    
    # Log startup info
    logger.info(
        "Logging initialized",
        level=level,
        service=config.otel_service_name,
        version=config.otel_service_version,
        environment=config.environment,
        file_logging=log_file is not None
    )


def get_logger(name: str) -> Any:
    """Get a logger instance with the given name.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logger.bind(name=name)


def setup_service_logging(service_name: str, log_dir: Path | None = None) -> None:
    """Setup logging for a specific P8FS service.
    
    Args:
        service_name: Name of the service (e.g., 'p8fs-api', 'p8fs')
        log_dir: Directory to store log files. If None, logs to stdout only
    """
    log_file = None
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{service_name}.log"
    
    setup_logging(log_file=log_file)
    
    # Bind service name to all logs
    logger.bind(service=service_name)


class P8FSLogger:
    """Context manager for structured logging with correlation IDs."""
    
    def __init__(self, correlation_id: str, **context):
        self.correlation_id = correlation_id
        self.context = context
        self.logger = logger.bind(correlation_id=correlation_id, **context)
    
    def __enter__(self):
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.logger.exception(
                "Exception occurred",
                exc_type=exc_type.__name__,
                exc_message=str(exc_val)
            )


def with_correlation_id(correlation_id: str, **context) -> P8FSLogger:
    """Create a logger with correlation ID for request tracing.
    
    Args:
        correlation_id: Unique identifier for the request/operation
        **context: Additional context to bind to the logger
        
    Returns:
        Context manager that provides a bound logger
    """
    return P8FSLogger(correlation_id, **context)