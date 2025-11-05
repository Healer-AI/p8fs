"""Dreaming command for content analysis worker."""

import asyncio
import sys
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


async def dreaming_command(args):
    """Run dreaming worker to analyze tenant content."""
    try:
        from p8fs.workers.dreaming import DreamingWorker, ProcessingMode

        polling_mode = args.polling
        poll_interval = args.poll_interval

        if polling_mode:
            logger.info(f"Starting dreaming worker in polling mode (interval: {poll_interval}s, mode: {args.mode})")
        else:
            logger.info(f"Starting dreaming worker (mode: {args.mode})")

        worker = DreamingWorker()

        async def process_once():
            """Process tenants once (single iteration)."""
            if args.mode == "completion":
                # Check completion mode - process all pending batch jobs
                await worker.check_completions()
                print("✅ Checked completions for pending batch jobs")
                return 0

            # For batch/direct modes, process tenants with content
            if args.tenant_id:
                # Process specific tenant
                tenant_ids = [args.tenant_id]
            else:
                # Find tenants with recent activity
                from p8fs.workers.dreaming_repository import DreamingRepository
                repo = DreamingRepository()

                # Get tenants with resources or sessions
                tenant_ids = await repo.get_active_tenants(
                    lookback_hours=args.lookback_hours
                )

                if not tenant_ids:
                    if not polling_mode:
                        print("No active tenants found in specified time window")
                    return 0

                print(f"Found {len(tenant_ids)} active tenants")

            # Process each tenant
            for tenant_id in tenant_ids:
                logger.info(f"Processing tenant: {tenant_id}")
                print(f"\n📊 Processing tenant: {tenant_id}")

                try:
                    if args.mode == "batch":
                        job = await worker.process_batch(tenant_id)
                        print(f"   ✅ Submitted batch job: {job.id}")
                        if job.batch_id:
                            print(f"   📋 Batch ID: {job.batch_id}")
                    else:  # direct mode
                        if args.task == "moments":
                            # Get recipient email from args or tenant database
                            recipient_email = args.recipient_email
                            if not recipient_email:
                                recipient_email = await worker._get_tenant_email(tenant_id)

                            job = await worker.process_moments(
                                tenant_id,
                                model=args.model,
                                recipient_email=recipient_email
                            )
                            print(f"   ✅ Completed moment processing: {job.id}")
                            if job.result:
                                result = job.result
                                print(f"   📅 Moments: {result.get('total_moments', 0)}")
                                if result.get('analysis_summary'):
                                    print(f"   📝 Summary: {result.get('analysis_summary')}")
                            if recipient_email:
                                print(f"   📧 Email sent to: {recipient_email}")
                        else:  # default: dreams
                            job = await worker.process_direct(tenant_id, model=args.model)
                            print(f"   ✅ Completed analysis: {job.id}")
                            if job.result:
                                result = job.result
                                print(f"   📈 Goals: {len(result.get('goals', []))}")
                                print(f"   💭 Dreams: {len(result.get('dreams', []))}")
                                print(f"   😰 Fears: {len(result.get('fears', []))}")

                except Exception as e:
                    logger.error(f"Failed to process tenant {tenant_id}: {e}")
                    print(f"   ❌ Error: {e}")
                    continue

            return 0

        # Run in polling mode or single execution
        if polling_mode:
            print(f"🔄 Polling mode enabled (checking every {poll_interval}s)")
            print("   Press Ctrl+C to stop")

            while True:
                try:
                    await process_once()
                    logger.info(f"Sleeping for {poll_interval}s before next poll")
                    await asyncio.sleep(poll_interval)
                except KeyboardInterrupt:
                    logger.info("Polling stopped by user")
                    print("\n⏹  Polling stopped")
                    return 0
        else:
            # Single execution
            return await process_once()

    except Exception as e:
        logger.error(f"Dreaming command failed: {e}", exc_info=True)
        print(f"❌ Dreaming error: {e}", file=sys.stderr)
        return 1
