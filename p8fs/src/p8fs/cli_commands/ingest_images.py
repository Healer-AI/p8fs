"""CLI command for ingesting sample images with CLIP embeddings."""

from argparse import Namespace

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


def ingest_images_command(args: Namespace):
    """
    Ingest sample images from Unsplash with CLIP embeddings.

    Args:
        args: Command line arguments containing:
            - tenant_id: Tenant ID to store images for
            - count: Number of images to fetch
            - unsplash_key: Unsplash API key (optional)
    """
    from p8fs.utils.sample_images import ingest_sample_images

    tenant_id = args.tenant_id or config.default_tenant_id
    count = args.count
    unsplash_key = args.unsplash_key

    logger.info(f"Starting sample image ingestion for tenant: {tenant_id}")
    logger.info(f"Number of images to fetch: {count}")
    logger.info(
        f"Unsplash API key: {'provided' if unsplash_key else 'not provided (using demo mode)'}"
    )

    result = ingest_sample_images(
        tenant_id=tenant_id,
        count=count,
        unsplash_access_key=unsplash_key,
        generate_embeddings=True,
    )

    print("\n" + "=" * 60)
    print("Sample Image Ingestion Results")
    print("=" * 60)
    print(f"Tenant ID:             {tenant_id}")
    print(f"Images fetched:        {result['images_fetched']}")
    print(f"Images ingested:       {result['images_ingested']}")
    print(f"Embeddings generated:  {result['embeddings_generated']}")
    print(f"Success:               {result['success']}")

    if not result["success"]:
        print(f"Error:                 {result.get('error')}")
        return 1

    if result["image_ids"]:
        print(f"\nFirst 5 image IDs:")
        for img_id in result["image_ids"][:5]:
            print(f"  - {img_id}")

    print("\n" + "=" * 60)
    print("Image ingestion completed successfully!")
    print("=" * 60)

    return 0
