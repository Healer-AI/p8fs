"""Miscellaneous utilities for P8FS Core."""

import base64
import datetime
import hashlib
import json
import uuid
from datetime import timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional, Union


def make_uuid(input_object: Union[str, Dict[str, Any]]) -> str:
    """
    Generate a UUID from input string or dictionary.
    
    Args:
        input_object: String or dictionary to generate UUID from
        
    Returns:
        UUID string
    """
    if isinstance(input_object, dict):
        return uuid_str_from_dict(input_object)
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, input_object))


def uuid_str_from_dict(d: Dict[str, Any]) -> str:
    """
    Generate a UUID string from a dictionary seed.
    
    Args:
        d: Dictionary to generate UUID from
        
    Returns:
        UUID string generated from sorted dictionary
    """
    m = hashlib.md5()
    m.update(json.dumps(d, sort_keys=True).encode("utf-8"))
    return str(uuid.UUID(m.hexdigest()))


def get_iso_timestamp() -> str:
    """
    Get current time as ISO 8601 formatted string.
    
    Returns:
        ISO formatted timestamp (YYYY-MM-DDTHH:MM:SS)
    """
    now = datetime.datetime.now()
    return now.isoformat()


def get_days_ago_iso_timestamp(n: int = 1) -> str:
    """
    Get timestamp for N days ago as ISO 8601 formatted string.
    
    Args:
        n: Number of days ago (default: 1)
        
    Returns:
        ISO formatted timestamp for N days ago
    """
    dt_n_days_ago = datetime.datetime.now(timezone.utc) - timedelta(days=n)
    return dt_n_days_ago.isoformat()


def parse_base64_dict(base64_data: str) -> Optional[Dict[str, Any]]:
    """
    Parse base64 encoded string to dictionary.
    
    Args:
        base64_data: Base64 encoded string
        
    Returns:
        Decoded dictionary or None if invalid
        
    Raises:
        Exception: If base64 data cannot be parsed
    """
    if not base64_data:
        return None
        
    decoded_bytes = base64.b64decode(base64_data)
    decoded_str = decoded_bytes.decode('utf-8')
    return json.loads(decoded_str)


def try_parse_base64_dict(base64_data: str) -> Optional[Dict[str, Any]]:
    """
    Safely parse base64 encoded string to dictionary.
    
    Args:
        base64_data: Base64 encoded string
        
    Returns:
        Decoded dictionary or None if parsing fails
    """
    try:
        return parse_base64_dict(base64_data)
    except Exception:
        return None


def batch_collection(collection: Union[str, List[Any]], batch_size: int) -> Iterator[Union[str, List[Any]]]:
    """
    Yield successive batches from collection.
    
    Args:
        collection: String or list to batch
        batch_size: Size of each batch
        
    Yields:
        Batches of the specified size
    """
    for i in range(0, len(collection), batch_size):
        yield collection[i:i + batch_size]


def split_string_into_chunks(string: str, chunk_size: int = 20000) -> List[str]:
    """
    Split string into chunks of specified size.
    
    Args:
        string: String to chunk
        chunk_size: Maximum size of each chunk (default: 20000)
        
    Returns:
        List of string chunks
    """
    return [string[i:i + chunk_size] for i in range(0, len(string), chunk_size)]