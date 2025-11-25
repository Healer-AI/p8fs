"""Configuration module for P8FS."""

from .embedding import (
    EMBEDDING_PROVIDERS,
    EmbeddingProviderConfig,
    get_default_embedding_provider,
    get_embedding_provider_config,
    get_vector_dimensions,
    validate_embedding_provider,
)

__all__ = [
    "EmbeddingProviderConfig",
    "EMBEDDING_PROVIDERS", 
    "get_embedding_provider_config",
    "get_default_embedding_provider",
    "validate_embedding_provider",
    "get_vector_dimensions",
]