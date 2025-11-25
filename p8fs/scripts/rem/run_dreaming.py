#!/usr/bin/env python3
"""
Run dreaming worker for REM testing

Executes first-order and second-order dreaming for specified tenants.

Usage:
    python scripts/rem/run_dreaming.py --tenant dev-tenant-001 --mode moments
    python scripts/rem/run_dreaming.py --tenant dev-tenant-001 --mode affinity
    python scripts/rem/run_dreaming.py --tenant dev-tenant-001 --mode both
"""

import asyncio
import argparse
import os
from datetime import datetime

from p8fs.workers.dreaming import DreamingWorker
from p8fs.providers import get_provider
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config

# Set default embedding provider for local testing
os.environ.setdefault("P8FS_DEFAULT_EMBEDDING_PROVIDER", "text-embedding-3-small")

logger = get_logger(__name__)


async def run_moment_dreaming(tenant_id: str, lookback_hours: int):
    """Run first-order dreaming (moment extraction)"""
    logger.info(f"Running moment dreaming for {tenant_id}, lookback={lookback_hours}h")

    worker = DreamingWorker()

    try:
        result = await worker.process_moments(
            tenant_id=tenant_id,
            lookback_hours=lookback_hours,
            batch_mode=False,  # Direct processing for testing
        )

        logger.info(f"Moment dreaming completed:")
        logger.info(f"  Moments created: {result.get('moments_created', 0)}")
        logger.info(f"  Resources processed: {result.get('resources_processed', 0)}")
        logger.info(f"  Sessions analyzed: {result.get('sessions_analyzed', 0)}")

        return result

    except Exception as e:
        logger.error(f"Moment dreaming failed: {e}")
        raise


async def run_affinity_dreaming(tenant_id: str, lookback_hours: int, use_llm: bool):
    """Run second-order dreaming (resource affinity)"""
    logger.info(f"Running affinity dreaming for {tenant_id}, lookback={lookback_hours}h, llm={use_llm}")

    worker = DreamingWorker()

    try:
        result = await worker.process_resource_affinity(
            tenant_id=tenant_id,
            lookback_hours=lookback_hours,
            use_llm=use_llm,
        )

        logger.info(f"Affinity dreaming completed:")
        logger.info(f"  Edges created: {result.get('edges_created', 0)}")
        logger.info(f"  Resources processed: {result.get('resources_processed', 0)}")
        logger.info(f"  Similarities found: {result.get('similarities_found', 0)}")

        return result

    except Exception as e:
        logger.error(f"Affinity dreaming failed: {e}")
        raise


async def verify_results(tenant_id: str):
    """Verify dreaming results in database"""
    logger.info(f"Verifying dreaming results for {tenant_id}")

    from p8fs.models.engram.models import Moment, Resource
    from p8fs.repository.TenantRepository import TenantRepository

    # Check moments
    moment_repo = TenantRepository(Moment, tenant_id)
    moments = await moment_repo.select(filters={"tenant_id": tenant_id}, limit=100)
    logger.info(f"Moments: {len(moments)} found")

    # Check resources
    resource_repo = TenantRepository(Resource, tenant_id)
    resources = await resource_repo.select(filters={"tenant_id": tenant_id}, limit=100)
    logger.info(f"Resources: {len(resources)} found")

    # Check resources with graph paths
    resources_with_paths = [r for r in resources if r.graph_paths and len(r.graph_paths) > 0]
    logger.info(f"Resources with graph paths: {len(resources_with_paths)}")


async def main():
    parser = argparse.ArgumentParser(description="Run dreaming worker for testing")
    parser.add_argument(
        "--tenant",
        required=True,
        help="Tenant ID to process",
    )
    parser.add_argument(
        "--mode",
        choices=["moments", "affinity", "both"],
        default="both",
        help="Dreaming mode to run",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=24,
        help="Hours to look back for processing",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use LLM mode for affinity (slower, higher quality)",
    )
    parser.add_argument(
        "--provider",
        choices=["postgresql", "tidb"],
        default="postgresql",
        help="Database provider",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify results after processing",
    )
    args = parser.parse_args()

    # Override config
    config.storage_provider = args.provider

    logger.info(f"Starting dreaming worker")
    logger.info(f"  Tenant: {args.tenant}")
    logger.info(f"  Mode: {args.mode}")
    logger.info(f"  Provider: {args.provider}")
    logger.info(f"  Lookback: {args.lookback_hours}h")

    start_time = datetime.utcnow()

    try:
        if args.mode in ["moments", "both"]:
            await run_moment_dreaming(args.tenant, args.lookback_hours)

        if args.mode in ["affinity", "both"]:
            await run_affinity_dreaming(args.tenant, args.lookback_hours, args.use_llm)

        if args.verify:
            await verify_results(args.tenant)

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"✓ Dreaming completed in {duration:.2f}s")

    except Exception as e:
        logger.error(f"✗ Dreaming failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
