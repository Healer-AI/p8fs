"""
Simple instrumentation utilities for tracking model usage.

This provides basic observability for API endpoints.
"""

import functools
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


def track_model_usage(tenant_id_attr: str = None, model_attr: str = None):
    """
    Decorator to track model usage for observability.
    
    This is a simplified implementation that logs usage information.
    In production, this would integrate with proper observability tools.
    
    Args:
        tenant_id_attr: Attribute path to extract tenant ID (e.g., "current_user.tenant_id")
        model_attr: Attribute path to extract model name (e.g., "request.model")
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract tenant ID if specified
            tenant_id = "unknown"
            if tenant_id_attr:
                try:
                    tenant_id = _extract_attribute_value(kwargs, tenant_id_attr)
                except Exception:
                    tenant_id = "unknown"
            
            # Extract model if specified  
            model = "unknown"
            if model_attr:
                try:
                    model = _extract_attribute_value(kwargs, model_attr)
                except Exception:
                    model = "unknown"
            
            # Log the usage
            logger.info(f"Model usage - tenant: {tenant_id}, model: {model}, endpoint: {func.__name__}")
            
            # Execute the actual function
            result = await func(*args, **kwargs)
            
            # Log completion
            logger.debug(f"Model usage completed - tenant: {tenant_id}, model: {model}")
            
            return result
        
        return wrapper
    return decorator


def _extract_attribute_value(kwargs: dict, attr_path: str) -> str:
    """
    Extract value from nested attribute path like 'current_user.tenant_id'.
    
    Args:
        kwargs: Function keyword arguments
        attr_path: Dot-separated attribute path
        
    Returns:
        String value of the attribute
    """
    parts = attr_path.split('.')
    value = kwargs
    
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = getattr(value, part, None)
        
        if value is None:
            return "unknown"
    
    return str(value) if value is not None else "unknown"