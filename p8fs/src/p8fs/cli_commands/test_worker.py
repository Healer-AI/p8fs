"""Test worker command for publishing test events to NATS."""

import sys
import time
from pathlib import Path
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


async def test_worker_command(args):
    """Publish a test storage event to NATS for local worker testing."""
    try:
        from p8fs.services.nats.client import NATSClient

        # Validate file exists
        file_path = Path(args.file).resolve()
        if not file_path.exists():
            print(f"❌ File not found: {args.file}", file=sys.stderr)
            return 1

        # Get file info
        file_size = file_path.stat().st_size
        import mimetypes
        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "application/octet-stream"

        # Build tenant-scoped path
        tenant_path = f"buckets/{args.tenant_id}/uploads/{file_path.name}"

        # Create storage event
        event = {
            "event_type": "create",
            "path": tenant_path,
            "tenant_id": args.tenant_id,
            "file_size": file_size,
            "size": file_size,
            "content_type": mime_type,
            "mime_type": mime_type,
            "timestamp": time.time(),
            "source": "test_command"
        }

        logger.info(f"Publishing test event for {file_path.name} ({file_size} bytes)")

        # Connect to NATS and publish
        async with NATSClient() as client:
            # Determine subject based on file size
            if file_size < 100 * 1024 * 1024:  # < 100MB
                subject = "p8fs.storage.events.small"
                tier = "small"
            elif file_size < 1024 * 1024 * 1024:  # < 1GB
                subject = "p8fs.storage.events.medium"
                tier = "medium"
            else:
                subject = "p8fs.storage.events.large"
                tier = "large"

            # Publish event
            await client.publish_json(subject, event)

            print(f"✅ Published test storage event:")
            print(f"   File: {file_path.name}")
            print(f"   Size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
            print(f"   Type: {mime_type}")
            print(f"   Subject: {subject} ({tier} tier)")
            print(f"   Tenant: {args.tenant_id}")
            print(f"   Path: {tenant_path}")
            print(f"\n📋 Monitor worker logs to see processing:")
            print(f"   kubectl logs -n p8fs -l tier={tier} -f")

        return 0

    except Exception as e:
        logger.error(f"Test worker command failed: {e}", exc_info=True)
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
