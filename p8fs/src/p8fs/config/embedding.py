"""Embedding configuration and provider settings for P8FS."""

from dataclasses import dataclass


@dataclass
class EmbeddingProviderConfig:
    """Configuration for an embedding provider."""
    
    name: str
    model_name: str
    dimensions: int
    max_input_length: int
    provider_type: str  # 'openai', 'local', 'huggingface'
    requires_api_key: bool = False
    api_key_env_var: str | None = None
    local_model_path: str | None = None
    description: str = ""


# Default embedding providers configuration
EMBEDDING_PROVIDERS = {
    # OpenAI embeddings - good for development, requires API key
    "text-embedding-3-small": EmbeddingProviderConfig(
        name="text-embedding-3-small",
        model_name="text-embedding-3-small", 
        dimensions=1536,
        max_input_length=8191,
        provider_type="openai",
        requires_api_key=True,
        api_key_env_var="OPENAI_API_KEY",
        description="OpenAI's small embedding model - fast and cost-effective"
    ),
    
    "text-embedding-ada-002": EmbeddingProviderConfig(
        name="text-embedding-ada-002",
        model_name="text-embedding-ada-002",
        dimensions=1536,
        max_input_length=8191,
        provider_type="openai", 
        requires_api_key=True,
        api_key_env_var="OPENAI_API_KEY",
        description="OpenAI's legacy embedding model - stable and reliable"
    ),
    
    # Local sentence-transformers - good for production, no API costs
    "all-MiniLM-L6-v2": EmbeddingProviderConfig(
        name="all-MiniLM-L6-v2",
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        dimensions=384,
        max_input_length=256,
        provider_type="local",
        requires_api_key=False,
        description="Local sentence-transformers model - fast and private"
    ),
    
    # Default provider (maps to 'default' in field metadata)
    "default": EmbeddingProviderConfig(
        name="default",
        model_name="text-embedding-3-small", 
        dimensions=1536,
        max_input_length=8191,
        provider_type="openai",
        requires_api_key=True,
        api_key_env_var="OPENAI_API_KEY",
        description="Default embedding provider"
    ),
}


def get_embedding_provider_config(provider_name: str) -> EmbeddingProviderConfig:
    """
    Get embedding provider configuration by name.
    
    Args:
        provider_name: Name of the embedding provider
        
    Returns:
        EmbeddingProviderConfig for the provider
        
    Raises:
        ValueError: If provider not found
    """
    if provider_name in EMBEDDING_PROVIDERS:
        return EMBEDDING_PROVIDERS[provider_name]
    
    # Check if it's configured as the default provider
    try:
        from p8fs_cluster.config import config
        if config.default_embedding_provider in EMBEDDING_PROVIDERS:
            return EMBEDDING_PROVIDERS[config.default_embedding_provider]
    except ImportError:
        pass
    
    raise ValueError(f"Unknown embedding provider: {provider_name}. Available: {list(EMBEDDING_PROVIDERS.keys())}")


def get_default_embedding_provider() -> str:
    """
    Get the default embedding provider name from central config.
    
    Returns:
        Default embedding provider name
    """
    try:
        from p8fs_cluster.config import config
        return config.default_embedding_provider
    except ImportError:
        return "text-embedding-3-small"


def validate_embedding_provider(provider_name: str) -> bool:
    """
    Validate that an embedding provider is configured and available.
    
    Args:
        provider_name: Name of the provider to validate
        
    Returns:
        True if provider is valid and available
    """
    try:
        provider_config = get_embedding_provider_config(provider_name)
        
        # Check API key requirements
        if provider_config.requires_api_key and provider_config.api_key_env_var:
            try:
                from p8fs_cluster.config import config
                # Map environment variable names to config attributes
                api_key_map = {
                    "OPENAI_API_KEY": config.openai_api_key,
                    "ANTHROPIC_API_KEY": config.anthropic_api_key,
                    "GOOGLE_API_KEY": config.google_api_key
                }
                api_key = api_key_map.get(provider_config.api_key_env_var, "")
                if not api_key:
                    return False
            except ImportError:
                return False
        
        return True
        
    except ValueError:
        return False


def get_vector_dimensions(provider_name: str) -> int:
    """
    Get the vector dimensions for an embedding provider.
    
    Args:
        provider_name: Name of the embedding provider
        
    Returns:
        Number of dimensions in the embedding vector
    """
    config = get_embedding_provider_config(provider_name)
    return config.dimensions