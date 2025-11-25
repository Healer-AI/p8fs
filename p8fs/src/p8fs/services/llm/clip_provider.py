"""CLIP embedding provider for visual and text content."""

import io
import logging
from abc import ABC
from typing import Any

from ...config.embedding import EmbeddingProviderConfig
from .embedding_providers import BaseEmbeddingProvider

logger = logging.getLogger(__name__)


class CLIPEmbeddingProvider(BaseEmbeddingProvider):
    """
    CLIP embedding provider for multimodal image and text embeddings.

    This provider generates 512-dimensional embeddings using OpenAI's CLIP model,
    enabling semantic search across both visual and textual content.

    Note:
        This is currently a placeholder implementation. Full CLIP integration
        should be implemented in p8fs-node as a processing service.
    """

    def __init__(self, config: EmbeddingProviderConfig):
        super().__init__(config)
        self.model = None
        self.processor = None
        self._initialized = False

    def _lazy_init(self):
        """Lazy initialization of CLIP model to avoid import overhead."""
        if self._initialized:
            return

        try:
            from transformers import CLIPModel, CLIPProcessor

            logger.info(f"Loading CLIP model: {self.config.model_name}")
            self.model = CLIPModel.from_pretrained(self.config.model_name)
            self.processor = CLIPProcessor.from_pretrained(self.config.model_name)
            self._initialized = True
            logger.info("CLIP model loaded successfully")
        except ImportError:
            logger.error(
                "transformers library not installed. "
                "Install with: pip install transformers torch pillow"
            )
            raise RuntimeError("CLIP dependencies not available")
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            raise RuntimeError(f"CLIP model initialization failed: {e}")

    def is_available(self) -> bool:
        """Check if CLIP model dependencies are available."""
        try:
            import transformers
            import torch
            from PIL import Image

            return True
        except ImportError:
            return False

    def encode(self, texts: str | list[str]) -> list[float] | list[list[float]]:
        """
        Generate CLIP text embeddings.

        Args:
            texts: Single text or list of texts to encode

        Returns:
            Single embedding vector or list of embedding vectors (512-dimensional)
        """
        self._lazy_init()

        if isinstance(texts, str):
            texts = [texts]
            return_single = True
        else:
            return_single = False

        validated_texts = [self.validate_input(text) for text in texts]

        try:
            import torch

            inputs = self.processor(
                text=validated_texts, return_tensors="pt", padding=True, truncation=True
            )

            with torch.no_grad():
                text_features = self.model.get_text_features(**inputs)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

            embeddings = text_features.cpu().numpy().tolist()

            if return_single:
                return embeddings[0]
            return embeddings

        except Exception as e:
            logger.error(f"CLIP text encoding failed: {e}")
            raise RuntimeError(f"CLIP text encoding error: {e}")

    def encode_image(
        self, image_data: bytes | list[bytes]
    ) -> list[float] | list[list[float]]:
        """
        Generate CLIP image embeddings.

        Args:
            image_data: Single image bytes or list of image bytes

        Returns:
            Single embedding vector or list of embedding vectors (512-dimensional)
        """
        self._lazy_init()

        if isinstance(image_data, bytes):
            image_data = [image_data]
            return_single = True
        else:
            return_single = False

        try:
            import torch
            from PIL import Image

            images = []
            for img_bytes in image_data:
                img = Image.open(io.BytesIO(img_bytes))
                if img.mode != "RGB":
                    img = img.convert("RGB")
                images.append(img)

            inputs = self.processor(images=images, return_tensors="pt")

            with torch.no_grad():
                image_features = self.model.get_image_features(**inputs)
                image_features = image_features / image_features.norm(
                    dim=-1, keepdim=True
                )

            embeddings = image_features.cpu().numpy().tolist()

            if return_single:
                return embeddings[0]
            return embeddings

        except Exception as e:
            logger.error(f"CLIP image encoding failed: {e}")
            raise RuntimeError(f"CLIP image encoding error: {e}")

    def encode_image_url(self, url: str | list[str]) -> list[float] | list[list[float]]:
        """
        Generate CLIP embeddings from image URL(s).

        Args:
            url: Single image URL or list of image URLs

        Returns:
            Single embedding vector or list of embedding vectors
        """
        if isinstance(url, str):
            url = [url]
            return_single = True
        else:
            return_single = False

        try:
            import httpx

            async def download_images():
                async with httpx.AsyncClient(timeout=30.0) as client:
                    tasks = [client.get(u) for u in url]
                    responses = await asyncio.gather(*tasks)
                    return [r.content for r in responses if r.status_code == 200]

            import asyncio

            image_data = asyncio.run(download_images())

            embeddings = self.encode_image(image_data)

            if return_single:
                return embeddings[0] if embeddings else []
            return embeddings

        except Exception as e:
            logger.error(f"Failed to download and encode images from URLs: {e}")
            raise RuntimeError(f"CLIP URL encoding error: {e}")


class MockCLIPProvider(BaseEmbeddingProvider):
    """
    Mock CLIP provider for testing and development.

    Generates random normalized vectors for demonstration purposes.
    Replace with actual CLIP provider when ready.
    """

    def __init__(self, config: EmbeddingProviderConfig):
        super().__init__(config)
        self.dimensions = 512

    def is_available(self) -> bool:
        """Mock provider is always available."""
        return True

    def encode(self, texts: str | list[str]) -> list[float] | list[list[float]]:
        """Generate mock text embeddings."""
        if isinstance(texts, str):
            texts = [texts]
            return_single = True
        else:
            return_single = False

        import random

        embeddings = []
        for text in texts:
            embedding = [random.random() for _ in range(self.dimensions)]
            total = sum(x * x for x in embedding) ** 0.5
            normalized = [x / total for x in embedding]
            embeddings.append(normalized)

        if return_single:
            return embeddings[0]
        return embeddings

    def encode_image(
        self, image_data: bytes | list[bytes]
    ) -> list[float] | list[list[float]]:
        """Generate mock image embeddings."""
        if isinstance(image_data, bytes):
            image_data = [image_data]
            return_single = True
        else:
            return_single = False

        import random

        embeddings = []
        for _ in image_data:
            embedding = [random.random() for _ in range(self.dimensions)]
            total = sum(x * x for x in embedding) ** 0.5
            normalized = [x / total for x in embedding]
            embeddings.append(normalized)

        if return_single:
            return embeddings[0]
        return embeddings


def get_clip_provider(use_mock: bool = False) -> BaseEmbeddingProvider:
    """
    Get CLIP embedding provider instance.

    Args:
        use_mock: If True, return mock provider for testing

    Returns:
        CLIP embedding provider instance
    """
    from ...config.embedding import EmbeddingProviderConfig

    config = EmbeddingProviderConfig(
        name="clip",
        model_name="openai/clip-vit-base-patch32",
        dimensions=512,
        max_input_length=77,
        provider_type="local",
        requires_api_key=False,
        description="CLIP multimodal embeddings for images and text",
    )

    if use_mock:
        logger.info("Using mock CLIP provider")
        return MockCLIPProvider(config)

    try:
        return CLIPEmbeddingProvider(config)
    except RuntimeError:
        logger.warning("CLIP provider unavailable, falling back to mock provider")
        return MockCLIPProvider(config)
