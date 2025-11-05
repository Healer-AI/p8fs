"""
Retry command for re-processing files already in SeaweedFS.

This command publishes storage events to NATS for files already uploaded to SeaweedFS,
triggering the worker processing pipeline without re-uploading the file.

Architecture:
    Manual Event → NATS → Router → Size-specific Queue → Worker → Database

Note: Requires NATS port-forward for CLI usage:
    kubectl port-forward -n p8fs svc/nats 4222:4222
"""

import sys
from pathlib import Path
import time
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config

logger = get_logger(__name__)


async def retry_command(args):
    """
    Retry processing for a file already uploaded to SeaweedFS.

    This publishes a storage event to NATS, triggering the full processing pipeline:
    - Router routes to size-specific queue (small/medium/large)
    - Worker pulls from queue and processes file
    - Content extracted and stored in database

    Prerequisites:
        - File must already be uploaded to SeaweedFS
        - NATS must be accessible (port-forward for CLI: kubectl port-forward -n p8fs svc/nats 4222:4222)
        - SeaweedFS admin credentials required if using --check-exists
    """
    try:
        from p8fs.services.nats.client import NATSClient
        from p8fs.services.s3_storage import S3StorageService
    except ImportError as e:
        print(f"❌ Failed to import required services: {e}", file=sys.stderr)
        return 1

    uri = args.uri
    tenant_id = args.tenant_id

    # Normalize URI to SeaweedFS path format
    if not uri.startswith("/buckets/"):
        # Handle partial paths
        if uri.startswith("/"):
            uri = f"/buckets/{tenant_id}{uri}"
        else:
            # Just filename or relative path - don't add uploads/ if already present
            if uri.startswith("uploads/"):
                uri = f"/buckets/{tenant_id}/{uri}"
            else:
                uri = f"/buckets/{tenant_id}/uploads/{uri}"

    # Extract tenant from path if present
    if "/buckets/" in uri:
        path_parts = uri.split("/")
        if len(path_parts) > 2:
            extracted_tenant = path_parts[2]
            if extracted_tenant and extracted_tenant != tenant_id:
                tenant_id = extracted_tenant
                logger.info(f"Extracted tenant ID from path: {tenant_id}")

    print(f"\n🔄 Retry Processing for File")
    print(f"   URI: {uri}")
    print(f"   Tenant: {tenant_id}\n")

    # Check if file exists (if requested and credentials available)
    file_size = None
    file_info = None

    if args.check_exists:
        print("🔍 Checking if file exists in SeaweedFS...")

        try:
            s3 = S3StorageService()

            # Extract S3 key from SeaweedFS path
            # Path format: /buckets/{tenant_id}/{s3_key}
            if uri.startswith("/buckets/"):
                s3_key = "/".join(uri.split("/")[3:])  # Skip /buckets/{tenant}/
            else:
                s3_key = uri.lstrip("/")

            # Check if file exists
            file_info = await s3.get_file_info(s3_key, tenant_id)

            if not file_info:
                print(f"❌ File not found in SeaweedFS: {uri}", file=sys.stderr)
                print(f"\n💡 Upload the file first:")
                print(f"   uv run python -m p8fs.cli files upload <local_file> --tenant-id {tenant_id}")
                return 1

            file_size = file_info.get('size', file_info.get('content_length'))
            print(f"✅ File exists")
            print(f"   Size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
            print(f"   Type: {file_info.get('content_type', 'unknown')}\n")

        except Exception as e:
            logger.warning(f"Could not check file existence: {e}")
            print(f"⚠️  Could not verify file exists (continuing anyway)")
            print(f"   Error: {e}\n")

    # If size not determined from file check, use provided size or estimate
    if not file_size:
        if args.size:
            file_size = args.size
        else:
            # Default to small if unknown
            file_size = 1024 * 1024  # 1MB default
            print(f"⚠️  File size unknown, assuming small file (1MB)\n")

    # Determine queue tier based on file size
    MB_100 = 100 * 1024 * 1024
    GB_1 = 1024 * 1024 * 1024

    if file_size < MB_100:
        tier = "small"
        queue = "p8fs.storage.events.small"
    elif file_size < GB_1:
        tier = "medium"
        queue = "p8fs.storage.events.medium"
    else:
        tier = "large"
        queue = "p8fs.storage.events.large"

    print(f"📊 Processing Details:")
    print(f"   Tier: {tier.upper()}")
    print(f"   Queue: {queue}")
    print(f"   Worker: storage-worker-{tier}\n")

    # Connect to NATS
    print("🔗 Connecting to NATS...")
    client = NATSClient()

    try:
        await client.connect()
        print("✅ Connected to NATS\n")
    except Exception as e:
        print(f"❌ Failed to connect to NATS: {e}\n", file=sys.stderr)
        print("💡 Make sure NATS is accessible:")
        print("   kubectl port-forward -n p8fs svc/nats 4222:4222\n")
        return 1

    # Create storage event
    event = {
        "event_type": "create",
        "type": "create",
        "path": uri,
        "tenant_id": tenant_id,
        "file_size": file_size,
        "size": file_size,
        "mime_type": file_info.get('content_type', 'application/octet-stream') if file_info else "application/octet-stream",
        "content_type": file_info.get('content_type', 'application/octet-stream') if file_info else "application/octet-stream",
        "timestamp": time.time(),
        "source": "cli_retry"
    }

    # Publish event
    subject = "p8fs.storage.events"  # Main subject, router will route to correct queue

    print(f"📤 Publishing event to {subject}...")
    try:
        await client.publish_json(subject, event)
        print(f"✅ Event published!\n")
    except Exception as e:
        print(f"❌ Failed to publish event: {e}", file=sys.stderr)
        await client.disconnect()
        return 1

    await client.disconnect()

    # Show monitoring commands
    print("🔍 Monitor Processing:")
    print(f"   # Watch {tier} worker logs")
    print(f"   kubectl logs -n p8fs deployment/storage-worker-{tier} --tail=50 -f\n")

    print(f"   # Check {tier} queue status")
    print(f"   kubectl exec -n p8fs deployment/nats-box -- \\")
    print(f"     nats consumer info P8FS_STORAGE_EVENTS_{tier.upper()} {tier}-workers\n")

    print("   # Verify in database")
    print("   kubectl exec -n tikv-cluster tidb-cluster-tidb-0 -- \\")
    print(f"     mysql -u root public -e \"SELECT name, category, created_at FROM resources WHERE tenant_id = '{tenant_id}' ORDER BY created_at DESC LIMIT 5;\"\n")

    print(f"✅ Event queued for processing")

    return 0
