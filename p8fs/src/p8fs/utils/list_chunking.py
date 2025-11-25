"""List-based content chunking utilities.

Provides intelligent chunking for list structures (e.g., lists of dicts, lists of objects)
by respecting record boundaries instead of splitting mid-record.
"""

import json
from typing import Any
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


def is_list_content(content: str | list) -> bool:
    """Detect if content is a list structure.

    Args:
        content: Content to check (string or list)

    Returns:
        True if content is a list or JSON string representing a list

    Example:
        >>> is_list_content([{"a": 1}, {"b": 2}])
        True
        >>> is_list_content('[{"a": 1}, {"b": 2}]')
        True
        >>> is_list_content('{"a": 1}')
        False
    """
    # Already a list
    if isinstance(content, list):
        return True

    # Try to parse as JSON
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            return isinstance(parsed, list)
        except (json.JSONDecodeError, ValueError):
            return False

    return False


def chunk_by_records(
    content: str | list,
    max_records_per_chunk: int | None = None,
    model_name: str | None = None
) -> list[str]:
    """Chunk list content by record boundaries.

    This ensures that individual records (list items) are never split across chunks,
    maintaining data integrity.

    Args:
        content: List content (as list or JSON string)
        max_records_per_chunk: Optional max records per chunk. If None and model_name provided,
                              calculates optimal size based on token limits.
        model_name: Optional model name for token-based optimization

    Returns:
        List of JSON string chunks, each containing complete records

    Example:
        >>> records = [{"id": 1}, {"id": 2}, {"id": 3}]
        >>> chunks = chunk_by_records(records, max_records_per_chunk=2)
        >>> len(chunks)
        2
        >>> json.loads(chunks[0])
        [{"id": 1}, {"id": 2}]
    """
    # Parse content if it's a string
    if isinstance(content, str):
        try:
            records = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse content as JSON: {e}")
            raise ValueError("Content must be valid JSON list") from e
    else:
        records = content

    if not isinstance(records, list):
        raise ValueError("Content must be a list")

    # Calculate optimal chunk size if not provided
    if max_records_per_chunk is None and model_name:
        max_records_per_chunk = _calculate_optimal_record_count(records, model_name)
        logger.debug(
            f"Calculated optimal record count for {model_name}: {max_records_per_chunk}"
        )
    elif max_records_per_chunk is None:
        # Default: try to fit reasonable number of records
        max_records_per_chunk = 100

    total_records = len(records)

    # If all records fit in one chunk, return as is
    if total_records <= max_records_per_chunk:
        logger.debug(f"All {total_records} records fit in single chunk")
        return [json.dumps(records)]

    # Chunk by record boundaries
    chunks = []
    start_idx = 0

    while start_idx < total_records:
        end_idx = min(start_idx + max_records_per_chunk, total_records)
        chunk_records = records[start_idx:end_idx]
        chunks.append(json.dumps(chunk_records))
        start_idx = end_idx

    logger.info(
        f"Split {total_records} records into {len(chunks)} chunks "
        f"(~{max_records_per_chunk} records each)"
    )

    return chunks


def _calculate_optimal_record_count(records: list, model_name: str) -> int:
    """Calculate optimal number of records per chunk based on model limits.

    Args:
        records: List of records to analyze
        model_name: Model name for context window detection

    Returns:
        Optimal number of records per chunk
    """
    from p8fs.utils.token_chunking import get_optimal_chunk_size, estimate_tokens

    if not records:
        return 100

    # Get optimal token count for the model
    optimal_tokens = get_optimal_chunk_size(model_name)

    # Sample first few records to estimate average size
    sample_size = min(10, len(records))
    sample_records = records[:sample_size]
    sample_json = json.dumps(sample_records)
    sample_tokens = estimate_tokens(sample_json, model_name)

    # Calculate average tokens per record
    avg_tokens_per_record = sample_tokens / sample_size

    # Add overhead for JSON array syntax (brackets, commas)
    overhead_per_record = 5  # Conservative estimate
    total_per_record = avg_tokens_per_record + overhead_per_record

    # Calculate how many records fit
    optimal_records = int(optimal_tokens / total_per_record)

    # Safety bounds
    optimal_records = max(1, min(optimal_records, 1000))

    logger.debug(
        f"Sample: {sample_tokens} tokens / {sample_size} records = "
        f"{avg_tokens_per_record:.1f} tokens/record. "
        f"Optimal: {optimal_records} records per chunk"
    )

    return optimal_records


def estimate_record_count(content: str | list, model_name: str) -> dict[str, Any]:
    """Estimate chunking statistics for list content.

    Args:
        content: List content (as list or JSON string)
        model_name: Model name for token estimation

    Returns:
        Dictionary with chunking statistics

    Example:
        >>> records = [{"id": i} for i in range(1000)]
        >>> stats = estimate_record_count(records, "claude-sonnet-4-5")
        >>> stats['total_records']
        1000
        >>> stats['estimated_chunks']
        10  # Example value
    """
    # Parse content
    if isinstance(content, str):
        try:
            records = json.loads(content)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON"}
    else:
        records = content

    if not isinstance(records, list):
        return {"error": "Content is not a list"}

    from p8fs.utils.token_chunking import estimate_tokens

    # Calculate statistics
    total_records = len(records)
    total_json = json.dumps(records)
    total_tokens = estimate_tokens(total_json, model_name)

    optimal_record_count = _calculate_optimal_record_count(records, model_name)
    estimated_chunks = max(1, total_records // optimal_record_count)

    return {
        "total_records": total_records,
        "total_tokens": total_tokens,
        "total_chars": len(total_json),
        "optimal_records_per_chunk": optimal_record_count,
        "estimated_chunks": estimated_chunks,
        "avg_tokens_per_record": total_tokens / total_records if total_records > 0 else 0
    }
