"""Embedding providers for P8FS - OpenAI and local sentence-transformers."""

import logging
from abc import ABC, abstractmethod
from typing import Any

from ...config.embedding import EmbeddingProviderConfig

logger = logging.getLogger(__name__)


class BaseEmbeddingProvider(ABC):
    """Base class for embedding providers."""
    
    def __init__(self, config: EmbeddingProviderConfig):
        """
        Initialize embedding provider.
        
        Args:
            config: Provider configuration
        """
        self.config = config
        self.name = config.name
        self.dimensions = config.dimensions
        self.max_input_length = config.max_input_length
        
    @abstractmethod
    def encode(self, texts: str | list[str]) -> list[float] | list[list[float]]:
        """
        Generate embeddings for text(s).
        
        Args:
            texts: Single text or list of texts to encode
            
        Returns:
            Single embedding vector or list of embedding vectors
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and properly configured."""
        pass
    
    def validate_input(self, text: str) -> str:
        """
        Validate and potentially truncate input text.
        
        Args:
            text: Input text to validate
            
        Returns:
            Validated (possibly truncated) text
        """
        if not text or not isinstance(text, str):
            raise ValueError("Text must be a non-empty string")
        
        # Truncate if too long
        if len(text) > self.max_input_length:
            logger.warning(f"Text truncated from {len(text)} to {self.max_input_length} characters")
            text = text[:self.max_input_length]
        
        return text


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI embedding provider using REST API only - NO OpenAI Python library dependency."""
    
    def __init__(self, config: EmbeddingProviderConfig):
        super().__init__(config)
        # Get API key from centralized configuration
        from p8fs_cluster.config.settings import config as cluster_config
        if config.api_key_env_var == "OPENAI_API_KEY":
            self.api_key = cluster_config.openai_api_key
        elif config.api_key_env_var == "ANTHROPIC_API_KEY":
            self.api_key = cluster_config.anthropic_api_key
        elif config.api_key_env_var == "GOOGLE_API_KEY":
            self.api_key = cluster_config.google_api_key
        else:
            self.api_key = None
        
        if not self.api_key and config.api_key_env_var:
            raise RuntimeError(f"Missing required API key: {config.api_key_env_var} not configured in centralized settings")
        self.api_url = "https://api.openai.com/v1/embeddings"
        
    def is_available(self) -> bool:
        """Check if OpenAI API key is available (no library dependencies)."""
        return bool(self.api_key)
    
    def encode(self, texts: str | list[str]) -> list[float] | list[list[float]]:
        """Generate embeddings using OpenAI REST API only."""
        # API key is validated in __init__, so if we get here it should be available
        
        # Handle single text
        if isinstance(texts, str):
            texts = [texts]
            return_single = True
        else:
            return_single = False
        
        # Validate inputs
        validated_texts = [self.validate_input(text) for text in texts]
        
        try:
            import json
            import urllib.error
            import urllib.request
            
            # Prepare request payload
            payload = {
                "model": self.config.model_name,
                "input": validated_texts
            }
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Make REST request
            request = urllib.request.Request(
                self.api_url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            
            with urllib.request.urlopen(request) as response:
                if response.status != 200:
                    raise RuntimeError(f"OpenAI API returned status {response.status}")
                
                response_data = json.loads(response.read().decode('utf-8'))
            
            # Extract embeddings from response
            embeddings = [data["embedding"] for data in response_data["data"]]
            
            if return_single:
                return embeddings[0]
            return embeddings
            
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else "No error details"
            logger.error(f"OpenAI API HTTP error {e.code}: {error_body}")
            raise RuntimeError(f"OpenAI API request failed: HTTP {e.code}")
            
        except urllib.error.URLError as e:
            logger.error(f"OpenAI API connection error: {e}")
            raise RuntimeError(f"OpenAI API connection failed: {e}")
            
        except Exception as e:
            logger.error(f"OpenAI embedding failed for {self.name}: {e}")
            raise RuntimeError(f"OpenAI embedding generation failed: {e}")


class LocalEmbeddingProvider(BaseEmbeddingProvider):
    """Local sentence-transformers embedding provider."""
    
    def __init__(self, config: EmbeddingProviderConfig):
        super().__init__(config)
        self._model = None
        
    def _get_model(self):
        """Get or load the sentence-transformers model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.config.model_name)
                logger.info(f"Loaded local embedding model: {self.config.model_name}")
            except ImportError:
                raise ImportError(
                    "sentence-transformers library not installed. "
                    "Run: pip install sentence-transformers"
                )
        return self._model
    
    def is_available(self) -> bool:
        """Check if sentence-transformers is available."""
        try:
            self._get_model()
            return True
        except Exception as e:
            logger.debug(f"Local embedding provider not available: {e}")
            return False
    
    def encode(self, texts: str | list[str]) -> list[float] | list[list[float]]:
        """Generate embeddings using local sentence-transformers model."""
        if not self.is_available():
            raise RuntimeError(f"Local provider {self.name} is not available. Check sentence-transformers installation.")
        
        # Handle single text
        if isinstance(texts, str):
            texts = [texts]
            return_single = True
        else:
            return_single = False
        
        # Validate inputs
        validated_texts = [self.validate_input(text) for text in texts]
        
        try:
            model = self._get_model()
            embeddings = model.encode(validated_texts)
            
            # Convert numpy arrays to lists
            embeddings = [embedding.tolist() for embedding in embeddings]
            
            if return_single:
                return embeddings[0]
            return embeddings
            
        except Exception as e:
            logger.error(f"Local embedding failed for {self.name}: {e}")
            raise RuntimeError(f"Local embedding generation failed: {e}")


class EmbeddingService:
    """Main embedding service that manages providers."""
    
    def __init__(self):
        """Initialize embedding service."""
        self._providers: dict[str, BaseEmbeddingProvider] = {}
        self._load_providers()
    
    def _load_providers(self):
        """Load and initialize available embedding providers."""
        from ...config.embedding import EMBEDDING_PROVIDERS
        
        for provider_name, config in EMBEDDING_PROVIDERS.items():
            if provider_name == "default":
                continue  # Skip default mapping
                
            try:
                if config.provider_type == "openai":
                    provider = OpenAIEmbeddingProvider(config)
                elif config.provider_type == "local":
                    provider = LocalEmbeddingProvider(config)
                else:
                    logger.warning(f"Unknown provider type: {config.provider_type}")
                    continue
                
                self._providers[provider_name] = provider
                logger.debug(f"Registered embedding provider: {provider_name}")
                
            except RuntimeError as e:
                # API key missing - only fail if this is the default provider
                from ...config.embedding import get_default_embedding_provider
                if provider_name == get_default_embedding_provider():
                    logger.error(f"Default embedding provider {provider_name} failed to initialize: {e}")
                    raise e  # Fail fast for default provider
                else:
                    logger.warning(f"Optional provider {provider_name} not available: {e}")
            except Exception as e:
                logger.warning(f"Failed to initialize provider {provider_name}: {e}")
    
    def get_provider(self, provider_name: str) -> BaseEmbeddingProvider:
        """
        Get embedding provider by name.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            BaseEmbeddingProvider instance
            
        Raises:
            ValueError: If provider not found
        """
        # Handle 'default' mapping
        if provider_name == "default":
            from ...config.embedding import get_default_embedding_provider
            provider_name = get_default_embedding_provider()
        
        if provider_name not in self._providers:
            raise ValueError(f"Provider {provider_name} not found. Available: {list(self._providers.keys())}")
        
        return self._providers[provider_name]
    
    def encode(self, text: str, provider_name: str = "default") -> list[float]:
        """
        Generate embedding for text using specified provider.
        
        Args:
            text: Text to encode
            provider_name: Name of provider to use
            
        Returns:
            Embedding vector as list of floats
        """
        provider = self.get_provider(provider_name)
        return provider.encode(text)
    
    def encode_batch(self, texts: list[str], provider_name: str = "default") -> list[list[float]]:
        """
        Generate embeddings for multiple texts using specified provider.
        
        Args:
            texts: List of texts to encode
            provider_name: Name of provider to use
            
        Returns:
            List of embedding vectors
        """
        provider = self.get_provider(provider_name)
        return provider.encode(texts)
    
    def get_available_providers(self) -> dict[str, dict[str, Any]]:
        """
        Get information about available embedding providers.
        
        Returns:
            Dict mapping provider names to their info
        """
        providers_info = {}
        
        for name, provider in self._providers.items():
            providers_info[name] = {
                "name": provider.name,
                "dimensions": provider.dimensions,
                "max_input_length": provider.max_input_length,
                "provider_type": provider.config.provider_type,
                "available": provider.is_available(),
                "description": provider.config.description
            }
        
        return providers_info
    
    def validate_provider(self, provider_name: str) -> bool:
        """
        Validate that a provider is available.
        
        Args:
            provider_name: Name of provider to validate
            
        Returns:
            True if provider is available
        """
        try:
            provider = self.get_provider(provider_name)
            return provider.is_available()
        except Exception:
            return False


# Global embedding service instance
_embedding_service = None


def get_embedding_service() -> EmbeddingService:
    """Get the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service