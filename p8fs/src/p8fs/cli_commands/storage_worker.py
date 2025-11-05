"""Storage worker command for processing files from NATS queues."""

import asyncio
import sys
import time
from pathlib import Path
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config

logger = get_logger(__name__)


async def storage_worker_command(args):
    """Run storage worker with optional self-test mode."""
    try:
        from p8fs.workers.queues.storage_worker import StorageEventWorker, QueueSize
        from p8fs.services.nats.client import NATSClient

        # Determine queue size
        queue_size = QueueSize(args.tier)

        logger.info(f"Starting {args.tier} storage worker for tenant {args.tenant_id}")

        # Connect to NATS
        client = NATSClient()
        await client.connect()

        # For self-test mode, use TEST queue instead of production queue
        if args.send_sample:
            stream_name = "P8FS_STORAGE_EVENTS_TEST"
            consumer_name = "test-workers"
            subject = "p8fs.storage.events.test"
            logger.info(f"Using TEST queue: {stream_name}")
        else:
            stream_name = None  # Use default production queue
            consumer_name = None
            subject = None

        # Create worker with optional TEST queue override
        worker = StorageEventWorker(
            queue_size,
            client,
            args.tenant_id,
            stream_name=stream_name,
            consumer_name=consumer_name,
            subject=subject
        )
        await worker.setup()

        # If --send-sample flag is set, upload file, publish event, then process
        if args.send_sample:
            logger.info("Running in self-test mode with --send-sample")

            # Get sample file
            sample_file = Path(args.send_sample).resolve()
            if not sample_file.exists():
                print(f"❌ Sample file not found: {args.send_sample}", file=sys.stderr)
                return 1

            print(f"\n📤 Step 1: Uploading {sample_file.name} to SeaweedFS...")

            # Upload to SeaweedFS (via port-forward or cluster)
            from p8fs.services.s3_storage import S3StorageService
            s3 = S3StorageService()

            # Upload file
            import mimetypes
            mime_type, _ = mimetypes.guess_type(str(sample_file))
            mime_type = mime_type or "application/octet-stream"

            upload_result = await s3.upload_file(
                sample_file,
                f"test/{sample_file.name}",
                args.tenant_id,
                mime_type
            )

            # S3 returns the actual path with uploads/ prefix and date
            s3_path = upload_result['path']
            print(f"✅ Uploaded to: {s3_path}")
            print(f"   Size: {upload_result['size_bytes']:,} bytes")

            # Give SeaweedFS a moment to finish
            await asyncio.sleep(0.5)

            print(f"\n📨 Step 2: Publishing test event to NATS...")

            # Create storage event matching gRPC event format
            # Path format from SeaweedFS gRPC: /buckets/{tenant_id}/{s3_path}
            event = {
                "event_type": "create",
                "path": f"/buckets/{args.tenant_id}/{s3_path}",
                "tenant_id": args.tenant_id,
                "file_size": upload_result['size_bytes'],
                "size": upload_result['size_bytes'],
                "content_type": mime_type,
                "mime_type": mime_type,
                "timestamp": time.time(),
                "source": "self_test"
            }

            # Publish event to TEST queue
            test_subject = "p8fs.storage.events.test"
            await client.publish_json(test_subject, event)
            print(f"✅ Published to: {test_subject}")

            # Give NATS a moment to route the message
            await asyncio.sleep(0.5)

            print(f"\n⚙️  Step 3: Processing event from queue...")

            # Process one message from the TEST queue
            raw_msgs = await worker.subscriber.fetch(batch=1, timeout=5.0)

            if raw_msgs:
                # Convert to NATSMessage
                from p8fs.services.nats.client import NATSMessage
                msg = raw_msgs[0]
                nats_msg = NATSMessage(
                    subject=msg.subject,
                    data=msg.data,
                    reply=msg.reply,
                    headers=msg.headers,
                    metadata=msg.metadata.__dict__ if msg.metadata else None,
                    _original_msg=msg
                )

                print(f"✅ Received message from queue")

                # Process the message
                await worker._process_single_message(nats_msg)
                await client.ack_message(nats_msg)

                print(f"✅ Successfully processed {sample_file.name}")
                print(f"\n📊 Verify in database:")
                print(f"   docker exec percolate psql -U postgres -d app -c \\")
                print(f"   \"SELECT name, category, length(content) as size FROM resources \\")
                print(f"    WHERE tenant_id = '{args.tenant_id}' ORDER BY created_at DESC LIMIT 5;\"")

                return 0
            else:
                print(f"⚠️  No message received from queue (timeout after 5s)")
                print(f"   This might indicate the queue consumer isn't set up correctly")
                return 1

        else:
            # Regular mode - just run the worker
            print(f"✅ {args.tier.capitalize()} worker started")
            print(f"   Tenant: {args.tenant_id}")
            print(f"   Queue: {queue_size.value}")
            print(f"   Subject: p8fs.storage.events.{args.tier}")
            print(f"\n🎯 Worker is now listening for events...")
            print(f"   Use Ctrl+C to stop\n")

            # Start worker (blocks until interrupted)
            await worker.start()

        return 0

    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
        print("\n✋ Worker stopped")
        return 0
    except Exception as e:
        logger.error(f"Storage worker command failed: {e}", exc_info=True)
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
    finally:
        # Cleanup
        if 'worker' in locals():
            await worker.stop()
        if 'client' in locals():
            await client.disconnect()
