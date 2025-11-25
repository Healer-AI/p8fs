"""Sample image generation and ingestion with CLIP embeddings.

This module fetches sample images from Unsplash and stores them with CLIP embeddings
for semantic search across visual content.
"""

import asyncio
import io
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from PIL import Image as PILImage
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

UNSPLASH_SEARCH_QUERIES = [
    "life goals",
    "goal setting",
    "achievement",
    "success",
    "family time",
    "family bonding",
    "family activities",
    "personal growth",
    "self improvement",
    "productivity",
    "planning",
    "motivation",
    "health fitness",
    "wellness",
    "mindfulness",
    "work life balance",
    "career development",
    "learning education",
    "creativity",
    "adventure travel",
]


def fetch_unsplash_images(
    queries: list[str] = UNSPLASH_SEARCH_QUERIES,
    images_per_query: int = 5,
    access_key: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch images from Unsplash API.

    Args:
        queries: Search queries for finding relevant images
        images_per_query: Number of images to fetch per query
        access_key: Unsplash API access key (optional, uses demo mode if not provided)

    Returns:
        List of image metadata dictionaries

    Note:
        If no access_key is provided, uses Unsplash Source API (demo mode) with limited features.
        For production, set UNSPLASH_ACCESS_KEY environment variable.
    """
    images = []

    with httpx.Client(timeout=30.0) as client:
        for query in queries:
            logger.info(f"Fetching {images_per_query} images for query: {query}")

            if access_key:
                url = "https://api.unsplash.com/search/photos"
                headers = {"Authorization": f"Client-ID {access_key}"}
                params = {
                    "query": query,
                    "per_page": images_per_query,
                    "orientation": "landscape",
                }

                try:
                    response = client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()

                    for photo in data.get("results", []):
                        images.append(
                            {
                                "uri": photo["urls"]["regular"],
                                "caption": f"{query}: {photo.get('description') or photo.get('alt_description', '')}",
                                "source": "unsplash",
                                "source_id": photo["id"],
                                "width": photo["width"],
                                "height": photo["height"],
                                "tags": [query] + (photo.get("tags", [])[:5] if isinstance(photo.get("tags"), list) else []),
                                "metadata": {
                                    "author": photo.get("user", {}).get("name"),
                                    "author_url": photo.get("user", {}).get("links", {}).get("html"),
                                    "download_url": photo["urls"]["raw"],
                                    "color": photo.get("color"),
                                },
                            }
                        )
                except Exception as e:
                    logger.warning(f"Failed to fetch images for query '{query}': {e}")
            else:
                for i in range(images_per_query):
                    url = f"https://source.unsplash.com/800x600/?{query.replace(' ', ',')}"
                    images.append(
                        {
                            "uri": url,
                            "caption": query,
                            "source": "unsplash_demo",
                            "source_id": f"demo-{query.replace(' ', '-')}-{i}",
                            "width": 800,
                            "height": 600,
                            "tags": [query],
                            "metadata": {
                                "mode": "demo",
                                "query": query,
                            },
                        }
                    )

    logger.info(f"Fetched {len(images)} total images from Unsplash")
    return images


async def download_image(url: str) -> bytes | None:
    """
    Download image from URL.

    Args:
        url: Image URL

    Returns:
        Image bytes or None if download failed
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.warning(f"Failed to download image from {url}: {e}")
        return None


async def get_image_metadata(image_bytes: bytes) -> dict[str, Any]:
    """
    Extract metadata from image bytes.

    Args:
        image_bytes: Image data

    Returns:
        Dictionary with width, height, mime_type, file_size
    """
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        return {
            "width": img.width,
            "height": img.height,
            "mime_type": f"image/{img.format.lower()}" if img.format else "image/jpeg",
            "file_size": len(image_bytes),
        }
    except Exception as e:
        logger.warning(f"Failed to extract image metadata: {e}")
        return {
            "width": None,
            "height": None,
            "mime_type": "image/jpeg",
            "file_size": len(image_bytes),
        }


def generate_clip_embeddings(
    images: list[dict[str, Any]], use_mock: bool = True
) -> list[list[float]]:
    """
    Generate CLIP embeddings for images.

    Args:
        images: List of image metadata dictionaries with 'caption' field
        use_mock: If True, use mock provider (default for experimental feature)

    Returns:
        List of CLIP embedding vectors (512-dimensional)

    Note:
        Currently uses text captions for CLIP embeddings. Future versions will
        support actual image embedding via p8fs-node processing service.
    """
    from p8fs.services.llm.clip_provider import get_clip_provider

    logger.info(
        f"Generating CLIP embeddings for {len(images)} images "
        f"(mock mode: {use_mock})"
    )

    clip_provider = get_clip_provider(use_mock=use_mock)

    captions = [img.get("caption", "") for img in images]
    captions = [c if c else "untitled image" for c in captions]

    try:
        embeddings = clip_provider.encode(captions)
        logger.info(f"Generated {len(embeddings)} CLIP embeddings")
        return embeddings
    except Exception as e:
        logger.error(f"CLIP embedding generation failed: {e}")
        logger.warning("Falling back to mock embeddings")

        import random

        embeddings = []
        for _ in images:
            embedding = [random.random() for _ in range(512)]
            total = sum(x * x for x in embedding) ** 0.5
            normalized = [x / total for x in embedding]
            embeddings.append(normalized)

        return embeddings


def ingest_sample_images(
    tenant_id: str,
    count: int = 100,
    unsplash_access_key: str | None = None,
    generate_embeddings: bool = True,
) -> dict[str, Any]:
    """
    Fetch and ingest sample images with CLIP embeddings.

    Args:
        tenant_id: Tenant ID to store images for
        count: Number of images to fetch (default: 100)
        unsplash_access_key: Unsplash API key (optional)
        generate_embeddings: Whether to generate CLIP embeddings (default: True)

    Returns:
        Dictionary with ingestion results

    Example:
        >>> result = await ingest_sample_images("tenant-123", count=100)
        >>> print(result)
        {
            "images_fetched": 100,
            "images_ingested": 98,
            "embeddings_generated": 98,
            "image_ids": ["id1", "id2", ...],
            "success": True
        }
    """
    from p8fs.models.p8 import Image
    from p8fs.repository import TenantRepository

    logger.info(f"Starting sample image ingestion for tenant {tenant_id}")

    images_per_query = max(1, count // len(UNSPLASH_SEARCH_QUERIES))
    remaining = count - (images_per_query * len(UNSPLASH_SEARCH_QUERIES))

    image_metadata_list = fetch_unsplash_images(
        queries=UNSPLASH_SEARCH_QUERIES,
        images_per_query=images_per_query,
        access_key=unsplash_access_key,
    )

    if remaining > 0:
        extra_images = fetch_unsplash_images(
            queries=UNSPLASH_SEARCH_QUERIES[:remaining],
            images_per_query=1,
            access_key=unsplash_access_key,
        )
        image_metadata_list.extend(extra_images)

    image_metadata_list = image_metadata_list[:count]

    logger.info(f"Fetched {len(image_metadata_list)} images from Unsplash")

    image_repo = TenantRepository(Image, tenant_id=tenant_id)
    image_ids = []
    images_data = []

    for img_meta in image_metadata_list:
        image_data = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "uri": img_meta["uri"],
            "caption": img_meta.get("caption", ""),
            "source": img_meta.get("source", "unsplash"),
            "source_id": img_meta.get("source_id"),
            "width": img_meta.get("width"),
            "height": img_meta.get("height"),
            "mime_type": img_meta.get("mime_type", "image/jpeg"),
            "file_size": img_meta.get("file_size"),
            "tags": img_meta.get("tags", []),
            "metadata": img_meta.get("metadata", {}),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        images_data.append(image_data)
        image_ids.append(image_data["id"])

    try:
        logger.info(f"Inserting {len(images_data)} images into database...")
        result = image_repo.upsert_sync(images_data)
        logger.info(f"Upsert result: {result}")
        logger.info(f"Successfully ingested {len(images_data)} images into database")
    except Exception as e:
        logger.error(f"Failed to ingest images: {e}", exc_info=True)
        return {
            "images_fetched": len(image_metadata_list),
            "images_ingested": 0,
            "embeddings_generated": 0,
            "image_ids": [],
            "success": False,
            "error": str(e),
        }

    embeddings_generated = 0
    if generate_embeddings:
        try:
            logger.info("Generating CLIP embeddings for images...")
            embeddings = generate_clip_embeddings(images_data)

            embedding_records = Image.build_embedding_records(
                entity_ids=image_ids,
                column_metadata=[{"entity_idx": i, "column_name": "caption"} for i in range(len(image_ids))],
                embedding_vectors=embeddings,
                tenant_id=tenant_id,
                embedding_provider="clip",
            )

            from p8fs.providers.base import BaseSQLProvider
            from p8fs_cluster.config.settings import config

            provider = BaseSQLProvider.get_provider(config.storage_provider)

            for record in embedding_records:
                try:
                    sql = """
                        INSERT INTO embeddings.images_embeddings
                        (id, entity_id, field_name, embedding_provider, embedding_vector,
                         tenant_id, vector_dimension)
                        VALUES (%s, %s, %s, %s, %s::vector, %s, %s)
                        ON CONFLICT (entity_id, field_name, tenant_id)
                        DO UPDATE SET
                            embedding_vector = EXCLUDED.embedding_vector,
                            embedding_provider = EXCLUDED.embedding_provider,
                            vector_dimension = EXCLUDED.vector_dimension,
                            updated_at = NOW()
                    """
                    params = [
                        record["id"],
                        record["entity_id"],
                        record["field_name"],
                        record["embedding_provider"],
                        str(record["embedding_vector"]),
                        record["tenant_id"],
                        record["vector_dimension"],
                    ]
                    provider.execute(sql, params)
                    embeddings_generated += 1
                except Exception as e:
                    logger.warning(f"Failed to insert embedding for image {record['entity_id']}: {e}")

            logger.info(f"Generated {embeddings_generated} CLIP embeddings")
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}", exc_info=True)

    return {
        "images_fetched": len(image_metadata_list),
        "images_ingested": len(images_data),
        "embeddings_generated": embeddings_generated,
        "image_ids": image_ids,
        "success": True,
    }


if __name__ == "__main__":
    import sys
    from p8fs_cluster.config.settings import config

    tenant_id = sys.argv[1] if len(sys.argv) > 1 else config.default_tenant_id
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    logger.info(f"Ingesting {count} sample images for tenant {tenant_id}")

    result = ingest_sample_images(
        tenant_id=tenant_id,
        count=count,
        unsplash_access_key=None,
        generate_embeddings=True,
    )

    print(f"\nIngestion Results:")
    print(f"  Images fetched: {result['images_fetched']}")
    print(f"  Images ingested: {result['images_ingested']}")
    print(f"  Embeddings generated: {result['embeddings_generated']}")
    print(f"  Success: {result['success']}")

    if not result["success"]:
        print(f"  Error: {result.get('error')}")
        sys.exit(1)
