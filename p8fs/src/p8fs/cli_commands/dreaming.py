"""Dreaming command for content analysis worker."""

import asyncio
import sys
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


async def dreaming_command(args):
    """Run dreaming worker to analyze tenant content."""
    worker = None
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

            # Collect moments by email to send one digest per email address
            moments_by_email = {}

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
                            # Process moments WITHOUT sending email (we'll batch later)
                            job = await worker.process_moments(
                                tenant_id,
                                model=args.model,
                                recipient_email=None,  # Don't send yet
                                limit=args.limit
                            )
                            print(f"   ✅ Completed moment processing: {job.id}")
                            if job.result:
                                result = job.result
                                moment_count = result.get('total_moments', 0)
                                print(f"   📅 Moments: {moment_count}")
                                if result.get('analysis_summary'):
                                    print(f"   📝 Summary: {result.get('analysis_summary')}")

                                # Collect moments for later email batching
                                if moment_count > 0:
                                    recipient_email = args.recipient_email or await worker._get_tenant_email(tenant_id)
                                    if recipient_email:
                                        if recipient_email not in moments_by_email:
                                            moments_by_email[recipient_email] = []
                                        moments_by_email[recipient_email].append({
                                            'tenant_id': tenant_id,
                                            'moment_ids': result.get('moment_ids', []),
                                            'moment_count': moment_count
                                        })
                            else:
                                print(f"   ⚠️  No results returned")

                        elif args.task == "affinity":
                            # Build resource affinity graph
                            affinity_stats = await worker.process_resource_affinity(
                                tenant_id=tenant_id,
                                use_llm=args.use_llm,
                                limit=args.limit
                            )
                            print(f"   ✅ Completed affinity processing")
                            print(f"   📊 Resources updated: {affinity_stats.get('total_updated', 0)}")
                            print(f"   🔗 Edges added: {affinity_stats.get('total_edges_added', 0)}")
                            if args.use_llm:
                                print(f"   🤖 Mode: LLM-enhanced (intelligent relationship assessment)")
                            else:
                                print(f"   ⚡ Mode: Semantic similarity (fast)")

                        elif args.task == "both":
                            # Process moments WITHOUT sending email (we'll batch later)
                            moments_job = await worker.process_moments(
                                tenant_id,
                                model=args.model,
                                recipient_email=None,  # Don't send yet
                                limit=args.limit
                            )
                            print(f"   ✅ Completed moment processing: {moments_job.id}")
                            if moments_job.result:
                                result = moments_job.result
                                moment_count = result.get('total_moments', 0)
                                print(f"   📅 Moments: {moment_count}")

                                # Collect moments for later email batching
                                if moment_count > 0:
                                    recipient_email = args.recipient_email or await worker._get_tenant_email(tenant_id)
                                    if recipient_email:
                                        if recipient_email not in moments_by_email:
                                            moments_by_email[recipient_email] = []
                                        moments_by_email[recipient_email].append({
                                            'tenant_id': tenant_id,
                                            'moment_ids': result.get('moment_ids', []),
                                            'moment_count': moment_count
                                        })

                            # Build resource affinity
                            affinity_stats = await worker.process_resource_affinity(
                                tenant_id=tenant_id,
                                use_llm=args.use_llm,
                                limit=args.limit
                            )
                            print(f"   ✅ Completed affinity processing")
                            print(f"   🔗 Edges added: {affinity_stats.get('total_edges_added', 0)}")

                        else:  # default: dreams
                            job = await worker.process_direct(tenant_id, model=args.model, limit=args.limit)
                            print(f"   ✅ Completed analysis: {job.id} (tenant: {tenant_id})")
                            if job.result:
                                result = job.result
                                print(f"   📈 Goals: {len(result.get('goals', []))}")
                                print(f"   💭 Dreams: {len(result.get('dreams', []))}")
                                print(f"   😰 Fears: {len(result.get('fears', []))}")

                except Exception as e:
                    logger.error(f"Failed to process tenant {tenant_id}: {e}")
                    print(f"   ❌ Error: {e}")
                    continue

            # Send ONE email per unique email address with all their moments
            if moments_by_email and args.task in ["moments", "both"]:
                print(f"\n📧 Sending moment digests to {len(moments_by_email)} unique email addresses")
                for recipient_email, tenant_moments in moments_by_email.items():
                    try:
                        total_moments = sum(tm['moment_count'] for tm in tenant_moments)
                        tenant_list = [tm['tenant_id'] for tm in tenant_moments]

                        logger.info(f"Sending digest to {recipient_email}: {total_moments} moments from {len(tenant_list)} tenants")

                        # Get all moment objects for this email
                        from p8fs.models.p8 import Moment
                        from p8fs.repository import TenantRepository

                        all_moments = []
                        for tm in tenant_moments:
                            moment_repo = TenantRepository(Moment, tenant_id=tm['tenant_id'])
                            for moment_id in tm['moment_ids']:
                                moment = await moment_repo.get(moment_id)
                                if moment:
                                    all_moments.append(moment)

                        if all_moments:
                            email_sent = await worker._send_moments_email(
                                moments=all_moments,
                                recipient_email=recipient_email,
                                tenant_id=tenant_list[0]  # Use first tenant for tracking
                            )
                            if email_sent:
                                print(f"   ✅ Sent digest to {recipient_email} ({total_moments} moments from {len(tenant_list)} accounts)")
                            else:
                                print(f"   ⚠️  Failed to send digest to {recipient_email}")
                    except Exception as e:
                        logger.error(f"Failed to send email digest to {recipient_email}: {e}")
                        print(f"   ❌ Email error for {recipient_email}: {e}")

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
                    break
        else:
            # Single execution
            return await process_once()

    except Exception as e:
        logger.error(f"Dreaming command failed: {e}", exc_info=True)
        print(f"❌ Dreaming error: {e}", file=sys.stderr)
        return 1
    finally:
        # Clean up resources
        if worker:
            try:
                await worker.cleanup()
                logger.info("Worker cleanup completed")
            except Exception as e:
                logger.warning(f"Error during worker cleanup: {e}")
