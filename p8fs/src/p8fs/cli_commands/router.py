"""Router command for tiered storage routing."""

import sys
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config

logger = get_logger(__name__)


async def router_command(args):
    """Run the tiered storage router for NATS queue management."""
    try:
        from p8fs.workers.queues.tiered_router import TieredStorageRouter

        logger.info("Starting tiered storage router...")
        logger.info(f"NATS URL: {config.nats_url}")

        # Create router with optional worker ID
        router = TieredStorageRouter(worker_id=args.worker_id)

        # Setup and run
        await router.setup()
        logger.info("Router setup complete. Starting message processing...")

        try:
            await router.start()
        except KeyboardInterrupt:
            logger.info("Router interrupted by user")
        finally:
            # Cleanup
            await router.cleanup()

            # Print stats
            status = await router.get_status()
            print(f"\n📊 Router Statistics:")
            print(f"   Processed: {status['processed_count']} messages")
            print(f"   Errors: {status['error_count']}")
            print(f"   Worker ID: {status['worker_id']}")

        return 0

    except Exception as e:
        logger.error(f"Router command failed: {e}", exc_info=True)
        print(f"❌ Router error: {e}", file=sys.stderr)
        return 1
