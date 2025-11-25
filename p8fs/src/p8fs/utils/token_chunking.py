"""Token-based content chunking utilities.

Provides smart, token-aware chunking that maximizes context window usage
while respecting model limits.
"""

from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

# Model context windows (tokens)
MODEL_CONTEXT_WINDOWS = {
    "claude-sonnet-4-5": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-opus-4": 200_000,
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
}

# Default overhead (system prompt + schema)
DEFAULT_OVERHEAD_TOKENS = 1500

# Default response buffer ratio (reserve 20% for response)
DEFAULT_RESPONSE_BUFFER_RATIO = 0.20


def get_optimal_chunk_size(
    model_name: str,
    overhead_tokens: int = DEFAULT_OVERHEAD_TOKENS,
    response_buffer_ratio: float = DEFAULT_RESPONSE_BUFFER_RATIO
) -> int:
    """Calculate optimal chunk size for a given model.

    Args:
        model_name: Model name (e.g., "claude-sonnet-4-5", "gpt-4o")
        overhead_tokens: Tokens to reserve for system prompt + schema (default: 1500)
        response_buffer_ratio: Ratio of available space to reserve for response (default: 0.20)

    Returns:
        Optimal chunk size in tokens

    Example:
        >>> get_optimal_chunk_size("claude-sonnet-4-5")
        158800  # 200k context - 1500 overhead - 20% buffer
    """
    max_context = MODEL_CONTEXT_WINDOWS.get(model_name, 100_000)
    available = max_context - overhead_tokens
    optimal_chunk = int(available * (1 - response_buffer_ratio))

    # Cap at 25K tokens to respect typical TPM limits (e.g., OpenAI free tier 30K TPM)
    # This ensures we leave room for response tokens and don't hit rate limits
    tpm_safe_limit = 25_000
    if optimal_chunk > tpm_safe_limit:
        logger.debug(
            f"Capping chunk size from {optimal_chunk:,} to {tpm_safe_limit:,} tokens "
            f"to respect TPM rate limits"
        )
        optimal_chunk = tpm_safe_limit

    logger.debug(
        f"Optimal chunk size for {model_name}: {optimal_chunk:,} tokens "
        f"(from {max_context:,} context window)"
    )

    return optimal_chunk


def estimate_tokens(content: str, model_name: str) -> int:
    """Estimate token count for content using tiktoken.

    Args:
        content: Content to estimate
        model_name: Model name for token counting

    Returns:
        Estimated token count

    Example:
        >>> estimate_tokens("This is a test", "gpt-4o")
        4
    """
    try:
        import tiktoken
    except ImportError:
        logger.warning("tiktoken not available, estimating ~4 chars per token")
        return len(content) // 4

    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        logger.debug(f"Unknown model {model_name}, using cl100k_base encoding")
        encoding = tiktoken.get_encoding("cl100k_base")

    return len(encoding.encode(content))


def chunk_by_tokens(
    content: str,
    model_name: str,
    max_chunk_tokens: int | None = None
) -> list[str]:
    """Split content into chunks by token count using tiktoken.

    This provides smart, token-aware chunking that maximizes context window
    usage while respecting model limits.

    Args:
        content: Content to chunk
        model_name: Model name for token counting (e.g., "claude-sonnet-4-5", "gpt-4o")
        max_chunk_tokens: Optional max tokens per chunk. If None, calculates
                        optimal size based on model context window.

    Returns:
        List of content chunks

    Example:
        >>> chunks = chunk_by_tokens(large_diary, "claude-sonnet-4-5")
        >>> # Returns ~2 chunks of 158k tokens each instead of 100+ small chunks
        >>> len(chunks)
        2
    """
    try:
        import tiktoken
    except ImportError:
        logger.warning("tiktoken not available, falling back to character-based chunking")
        # Fallback: estimate ~4 chars per token
        char_chunk_size = (max_chunk_tokens or 100_000) * 4
        return _chunk_by_chars(content, char_chunk_size)

    # Calculate optimal chunk size if not provided
    if max_chunk_tokens is None:
        max_chunk_tokens = get_optimal_chunk_size(model_name)

    # Get encoding for token counting
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        logger.debug(f"Unknown model {model_name}, using cl100k_base encoding")
        encoding = tiktoken.get_encoding("cl100k_base")

    # Encode full content
    tokens = encoding.encode(content)
    total_tokens = len(tokens)

    logger.debug(
        f"Content: {len(content):,} chars, {total_tokens:,} tokens "
        f"(~{len(content)/total_tokens:.2f} chars/token)"
    )

    # If content fits in one chunk, return as is
    if total_tokens <= max_chunk_tokens:
        logger.debug(f"Content fits in single chunk ({total_tokens:,} tokens)")
        return [content]

    # Split into chunks
    chunks = []
    start_idx = 0

    while start_idx < total_tokens:
        # Get chunk of tokens
        end_idx = min(start_idx + max_chunk_tokens, total_tokens)
        chunk_tokens = tokens[start_idx:end_idx]

        # Decode back to text
        chunk_text = encoding.decode(chunk_tokens)
        chunks.append(chunk_text)

        start_idx = end_idx

    logger.info(
        f"Split {total_tokens:,} tokens into {len(chunks)} chunks "
        f"(~{max_chunk_tokens:,} tokens each)"
    )

    return chunks


def _chunk_by_chars(content: str, chunk_size: int) -> list[str]:
    """Fallback character-based chunking when tiktoken is not available."""
    if len(content) <= chunk_size:
        return [content]

    chunks = []
    start = 0
    while start < len(content):
        end = start + chunk_size
        chunks.append(content[start:end])
        start = end

    return chunks
