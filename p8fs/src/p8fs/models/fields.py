"""Field utilities for P8FS models with embedding support."""

from typing import Any

from pydantic import Field


def EmbeddingField(embedding_provider: str = 'default', **kwargs) -> Any:
    """
    Create a Pydantic Field with embedding metadata.
    
    Args:
        embedding_provider: The embedding model to use (e.g., 'text-embedding-ada-002')
        **kwargs: Additional Field arguments
    
    Returns:
        A Pydantic Field with embedding_provider metadata
        
    Usage:
        description: str = EmbeddingField(
            embedding_provider='text-embedding-ada-002',
            description="Content to be semantically searched"
        )
    """
    # Add embedding provider to json_schema_extra
    json_schema_extra = kwargs.get('json_schema_extra', {})
    json_schema_extra['embedding_provider'] = embedding_provider
    kwargs['json_schema_extra'] = json_schema_extra
    
    return Field(**kwargs)


def DefaultEmbeddingField(default: Any = None, **kwargs) -> Any:
    """
    Create an embedding field with the default embedding provider.
    
    Equivalent to percolate's DefaultEmbeddingField pattern.
    
    Args:
        default: Default value for the field
        **kwargs: Additional Field arguments
        
    Returns:
        A Pydantic Field configured for embedding generation
        
    Usage:
        description: str = DefaultEmbeddingField(
            default="",
            description="Content description for semantic search"
        )
    """
    if default is not None:
        kwargs['default'] = default
        
    return EmbeddingField(embedding_provider='default', **kwargs)


# Specific embedding field types for common providers
def OpenAIEmbeddingField(model: str = 'text-embedding-ada-002', **kwargs) -> Any:
    """Create an embedding field using OpenAI's embedding models."""
    return EmbeddingField(embedding_provider=model, **kwargs)


def HuggingFaceEmbeddingField(model: str = 'sentence-transformers/all-MiniLM-L6-v2', **kwargs) -> Any:
    """Create an embedding field using HuggingFace models."""
    return EmbeddingField(embedding_provider=model, **kwargs)


# Provider name constants
class EmbeddingProviders:
    """Common embedding provider identifiers."""
    
    # OpenAI models
    OPENAI_ADA_002 = 'text-embedding-ada-002'
    OPENAI_SMALL = 'text-embedding-3-small'
    OPENAI_LARGE = 'text-embedding-3-large'
    
    # HuggingFace models  
    MINILM_L6_V2 = 'sentence-transformers/all-MiniLM-L6-v2'
    MINILM_L12_V2 = 'sentence-transformers/all-MiniLM-L12-v2'
    MPNET_BASE_V2 = 'sentence-transformers/all-mpnet-base-v2'
    
    # Default
    DEFAULT = 'default'


def resolve_embedding_provider(provider: str) -> str:
    """Resolve embedding provider name to actual model identifier."""
    if provider == 'default':
        return EmbeddingProviders.OPENAI_ADA_002
    return provider