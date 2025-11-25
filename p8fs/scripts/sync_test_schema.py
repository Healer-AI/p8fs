#!/usr/bin/env python3
"""
Synchronize test database schema with model definitions.

Run this after `docker compose up postgres` to ensure database matches models.
"""

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers import get_provider
from p8fs.models.p8 import Resources, Session, Moment

# Import our schema sync utility
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
from utils.schema_sync import sync_table_schema

logger = get_logger(__name__)


def main():
    """Sync all model schemas with database."""
    logger.info("Synchronizing database schema with models...")

    provider = get_provider()
    provider.connect_sync()

    # Sync Resources table
    logger.info("\nSyncing Resources table...")
    result = sync_table_schema(provider, Resources)
    logger.info(f"  Added: {result['added']}")
    logger.info(f"  Skipped: {len(result['skipped'])} existing columns")

    # Sync Session table
    logger.info("\nSyncing Session table...")
    result = sync_table_schema(provider, Session)
    logger.info(f"  Added: {result['added']}")
    logger.info(f"  Skipped: {len(result['skipped'])} existing columns")

    # Sync Moment table
    logger.info("\nSyncing Moment table...")
    result = sync_table_schema(provider, Moment)
    logger.info(f"  Added: {result['added']}")
    logger.info(f"  Skipped: {len(result['skipped'])} existing columns")

    logger.info("\n✅ Schema synchronization complete!")


if __name__ == "__main__":
    main()
