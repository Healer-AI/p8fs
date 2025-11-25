"""Sample functions for LLM testing."""

import asyncio
from typing import Any


def simple_function(name: str, age: int = 25) -> str:
    """Simple function with basic types.
    
    Args:
        name: Person's name
        age: Person's age (default: 25)
        
    Returns:
        Formatted greeting string
    """
    return f"Hello {name}, you are {age} years old"


def complex_function(
    items: list[dict[str, Any]], 
    options: str | int | None = None,
    filters: dict[str, str | int | bool] = None
) -> list[str] | dict[str, int]:
    """Complex function with nested types.
    
    Args:
        items: List of item dictionaries
        options: Optional configuration (string or integer)
        filters: Optional filtering parameters
        
    Returns:
        Processed items as list of strings or summary dict
    """
    if not items:
        return []
    
    if filters:
        # Apply filters (stub implementation)
        pass
    
    if isinstance(options, str):
        return [str(item) for item in items]
    else:
        return {"count": len(items), "processed": len(items)}


async def async_function(query: str, limit: int = 10) -> list[str]:
    """Async function for testing async detection.
    
    Args:
        query: Search query string
        limit: Maximum results to return
        
    Returns:
        List of matching document IDs
    """
    await asyncio.sleep(0.1)  # Simulate async work
    return [f"doc_{i}_{query}" for i in range(min(limit, 5))]


def vector_function(embeddings: list[float], threshold: float = 0.8) -> bool:
    """Function with vector-like parameters.
    
    Args:
        embeddings: Vector embeddings as list of floats
        threshold: Similarity threshold
        
    Returns:
        Whether vector meets threshold criteria
    """
    return len(embeddings) > 0 and max(embeddings) >= threshold


def no_args_function() -> str:
    """Function with no arguments."""
    return "no args"


def optional_heavy_function(
    required_param: str,
    optional_str: str | None = None,
    optional_int: int | None = None,
    optional_list: list[str] | None = None,
    optional_dict: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Function with many optional parameters.
    
    Args:
        required_param: Required string parameter
        optional_str: Optional string parameter
        optional_int: Optional integer parameter  
        optional_list: Optional list of strings
        optional_dict: Optional dictionary
        
    Returns:
        Summary of provided parameters
    """
    result = {"required": required_param}
    
    if optional_str is not None:
        result["str"] = optional_str
    if optional_int is not None:
        result["int"] = optional_int
    if optional_list is not None:
        result["list"] = optional_list
    if optional_dict is not None:
        result["dict"] = optional_dict
        
    return result


def error_function(should_error: bool = False) -> str:
    """Function that can raise errors for testing.
    
    Args:
        should_error: Whether to raise an error
        
    Returns:
        Success message
        
    Raises:
        ValueError: When should_error is True
    """
    if should_error:
        raise ValueError("Test error for error handling")
    return "Success"


# Functions for testing edge cases
def union_types_function(
    param: str | int | list[float] | None
) -> str | dict[str, Any]:
    """Function with complex union types."""
    if param is None:
        return "null"
    elif isinstance(param, str):
        return f"string: {param}"
    elif isinstance(param, int):
        return {"type": "int", "value": param}
    elif isinstance(param, list):
        return {"type": "list", "length": len(param), "sum": sum(param)}
    else:
        return "unknown"


def nested_types_function(
    data: list[dict[str, str | int | None]]
) -> dict[str, list[str]] | None:
    """Function with deeply nested types."""
    if not data:
        return None
    
    result = {}
    for item in data:
        for key, value in item.items():
            if key not in result:
                result[key] = []
            result[key].append(str(value))
    
    return result