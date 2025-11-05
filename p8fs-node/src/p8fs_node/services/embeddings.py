"""Embeddings service for generating vector representations."""

import hashlib
import logging
from typing import List, Optional

from p8fs_cluster.config.settings import config

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating embeddings from text content with fallback mechanisms."""
    
    def __init__(self, model_name: Optional[str] = None, dimension: int = 384):
        """Initialize the embedding service."""
        # Use centralized embedding provider instead of local sentence-transformers
        self.provider_name = getattr(config, 'default_embedding_provider', 'text-embedding-3-small')
        self.model_name = model_name or self.provider_name
        self.dimension = dimension
        self._model = None
        self._core_service = None
        self._load_model()
    
    def _load_model(self):
        """Load the embedding model with centralized provider system."""
        # Try to use the centralized embedding service from p8fs
        try:
            from p8fs.services.llm import get_embedding_service
            self._core_service = get_embedding_service()
            logger.info(f"Using centralized embedding provider: {self.provider_name}")
            return
        except ImportError:
            logger.debug("p8fs embedding service not available, falling back to local service")
        
        # Only try sentence-transformers if explicitly configured (not in dev with OpenAI)
        if 'sentence-transformers' in self.model_name or self.provider_name.startswith('sentence-transformers'):
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                logger.info(f"Loaded local embedding model: {self.model_name}")
                return
            except ImportError:
                logger.warning("sentence-transformers not available")
            except Exception as e:
                logger.error(f"Failed to load embedding model {self.model_name}: {e}")
        
        # No embedding service available - this will cause errors when used
        logger.warning(f"No embedding service available for provider: {self.provider_name}")
        self._model = None
        self._core_service = None
    
    async def generate_embedding(self, text: str) -> list[float]:
        """
        Generate embeddings for the given text.
        
        Args:
            text: Text to generate embeddings for
            
        Returns:
            Vector embedding as list of floats
        """
        if not text.strip():
            return [0.0] * self.dimension
        
        # Try centralized service first (OpenAI, etc.)
        if self._core_service is not None:
            try:
                return self._core_service.encode(text, self.provider_name)
            except Exception as e:
                logger.error(f"Core embedding service failed: {e}")
                raise RuntimeError(f"Embedding service failed: {e}") from e
        
        # Try local sentence-transformers model
        if self._model is not None:
            try:
                embedding = self._model.encode([text])[0]
                return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
            except Exception as e:
                logger.error(f"Local model failed: {e}")
                raise RuntimeError(f"Local embedding model failed: {e}") from e
            
        # No embedding service available
        raise RuntimeError(
            f"No embedding service available. Provider '{self.provider_name}' is not configured. "
            "Please configure either a centralized embedding service or install sentence-transformers."
        )
    
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts efficiently.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embeddings
        """
        if not texts:
            return []
        
        # Try centralized service first
        if self._core_service is not None:
            try:
                return self._core_service.encode_batch(texts, self.provider_name)
            except Exception as e:
                logger.error(f"Core batch embedding failed: {e}")
                raise RuntimeError(f"Batch embedding service failed: {e}") from e
        
        # Try local model
        if self._model is not None:
            try:
                embeddings = self._model.encode(texts, convert_to_tensor=True, batch_size=32)
                return embeddings.cpu().tolist()
            except Exception as e:
                logger.error(f"Local batch embedding failed: {e}")
                raise RuntimeError(f"Local batch embedding failed: {e}") from e
        
        # No embedding service available
        raise RuntimeError(
            f"No embedding service available. Provider '{self.provider_name}' is not configured. "
            "Please configure either a centralized embedding service or install sentence-transformers."
        )
    
    def get_dimension(self) -> int:
        """Get the embedding dimension."""
        return self.dimension


# Global instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service