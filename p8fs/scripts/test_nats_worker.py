#!/usr/bin/env python3
"""Test script for storage worker with NATS integration and S3 upload.

This script demonstrates the complete file processing workflow:
1. Upload PDF file to SeaweedFS S3
2. Publish storage event to NATS
3. Worker consumes message from NATS
4. Downloads file from S3
5. Processes with appropriate content provider
6. Saves chunked resources to database

Prerequisites:
- NATS server running (port 4222)
- SeaweedFS S3 running (port 8333 or via ingress)
- Database accessible (PostgreSQL or TiDB)
- p8fs-node installed for content processing

Usage:
    # Using local port-forward (development)
    kubectl port-forward -n p8fs svc/nats 4222:4222 &
    kubectl port-forward -n seaweed svc/seaweedfs-s3 8333:8333 &
    uv run python scripts/test_nats_worker.py

    # Using ingress (production)
    P8FS_SEAWEEDFS_S3_ENDPOINT=https://s3.eepis.ai \
    P8FS_NATS_URL=nats://localhost:4222 \
    uv run python scripts/test_nats_worker.py
"""

import asyncio
import json
from pathlib import Path

from p8fs_cluster.config import config
from p8fs_cluster.logging import get_logger
from p8fs.services.s3_storage import S3StorageService
from p8fs.workers.storage import StorageWorker, StorageEvent
from nats.aio.client import Client as NATS

logger = get_logger(__name__)

# Test configuration
TENANT_ID = "tenant-test"
TEST_FILE = Path("tests/sample_data/content/Sample.pdf")
TEST_SUBJECT = "p8fs.storage.events.test2"  # Separate test queue with fresh name


async def upload_test_file() -> dict:
    """Upload test file to S3 and return file info."""
    logger.info(f"📤 Step 1: Uploading {TEST_FILE.name} to SeaweedFS...")

    # Initialize S3 service
    s3 = S3StorageService()

    # Upload file to tenant's date-partitioned path
    result = await s3.upload_file(
        local_path=TEST_FILE,
        remote_path=TEST_FILE.name,
        tenant_id=TENANT_ID,
        content_type="application/pdf"
    )

    logger.info(f"✅ Uploaded to: {result['path']}")
    logger.info(f"   Size: {result['size_bytes']:,} bytes")
    logger.info(f"   Method: {result['upload_method']}")

    return result


async def setup_test_stream():
    """Create test stream and consumer before publishing."""
    logger.info(f"\n📋 Step 2: Setting up test stream and consumer...")

    nc = NATS()
    await nc.connect(servers=[config.nats_url])
    js = nc.jetstream()

    # Try to create stream (may already exist)
    try:
        await js.add_stream(
            name="P8FS_STORAGE_EVENTS_TEST2",
            subjects=[TEST_SUBJECT]
        )
        logger.info("✅ Created test stream")
    except Exception as e:
        logger.debug(f"Stream may already exist: {e}")

    await nc.close()


async def publish_storage_event(file_info: dict):
    """Publish storage event to NATS test queue."""
    logger.info(f"\n📨 Step 3: Publishing test event to NATS...")

    # Create storage event
    event = StorageEvent(
        tenant_id=TENANT_ID,
        file_path=file_info['path'],
        operation="create",
        size=file_info['size_bytes'],
        mime_type="application/pdf",
        s3_key=file_info['path']  # S3 key for download
    )

    # Connect to NATS
    nc = NATS()
    await nc.connect(servers=[config.nats_url])

    # Publish event
    await nc.publish(
        TEST_SUBJECT,
        event.model_dump_json().encode()
    )

    logger.info(f"✅ Published to: {TEST_SUBJECT}")
    logger.info(f"   Event: {event.operation} - {event.file_path}")

    await nc.close()


async def process_from_queue():
    """Run storage worker to process the test event."""
    logger.info(f"\n⚙️  Step 4: Processing event from queue...")

    # Initialize worker
    worker = StorageWorker(tenant_id=TENANT_ID)

    # Connect to NATS
    await worker.connect_nats()

    # Subscribe to test subject
    sub = await worker.js.pull_subscribe(TEST_SUBJECT, "test-workers")

    # Process one message
    try:
        msgs = await sub.fetch(batch=1, timeout=5)

        if not msgs:
            logger.error("❌ No messages received from queue")
            return False

        msg = msgs[0]
        logger.info("✅ Received message from queue")

        # Parse event
        event = StorageEvent.model_validate_json(msg.data)
        logger.info(f"   Processing: {event.file_path}")

        # Process file (downloads from S3, extracts content, saves resources)
        await worker.process_file(
            event.file_path,
            event.tenant_id,
            event.s3_key
        )

        # Acknowledge message
        await msg.ack()
        logger.info("✅ Successfully processed and acknowledged message")

        return True

    except asyncio.TimeoutError:
        logger.error("❌ Timeout waiting for message")
        return False
    except Exception as e:
        logger.error(f"❌ Error processing message: {e}")
        raise
    finally:
        await worker.cleanup()


async def verify_resources():
    """Verify resources were created in database."""
    logger.info(f"\n📊 Step 5: Verifying resources in database...")

    from p8fs.models.p8 import Resources, Files
    from p8fs.repository import TenantRepository

    # Check file entry
    files_repo = TenantRepository(Files, tenant_id=TENANT_ID)
    files = await files_repo.select(limit=5)
    logger.info(f"✅ Files found: {len(files)}")
    for file in files[:3]:
        logger.info(f"   - {file.uri} ({file.file_size:,} bytes)")

    # Check resource chunks
    resources_repo = TenantRepository(Resources, tenant_id=TENANT_ID)
    resources = await resources_repo.select(limit=10)
    logger.info(f"✅ Resources found: {len(resources)}")
    for resource in resources[:5]:
        content_len = len(resource.content) if resource.content else 0
        logger.info(f"   - {resource.name} ({content_len:,} chars)")

    return len(resources) > 0


async def main():
    """Run complete test flow."""
    logger.info("="*80)
    logger.info("NATS Storage Worker Integration Test")
    logger.info("="*80)
    logger.info(f"Configuration:")
    logger.info(f"  NATS URL: {config.nats_url}")
    logger.info(f"  S3 Endpoint: {config.seaweedfs_s3_endpoint}")
    logger.info(f"  Storage Provider: {config.storage_provider}")
    logger.info(f"  Test Subject: {TEST_SUBJECT}")
    logger.info(f"  Test File: {TEST_FILE}")
    logger.info("="*80)

    # Verify test file exists
    if not TEST_FILE.exists():
        logger.error(f"❌ Test file not found: {TEST_FILE}")
        logger.error(f"   Please run from p8fs-modules root directory")
        return

    try:
        # Step 1: Upload file to S3
        file_info = await upload_test_file()

        # Step 2: Setup NATS stream (before publishing)
        await setup_test_stream()

        # Step 3: Publish event to NATS
        await publish_storage_event(file_info)

        # Step 4: Process from queue
        success = await process_from_queue()

        if not success:
            logger.error("❌ Test failed: Could not process message from queue")
            return

        # Step 5: Verify resources created
        resources_created = await verify_resources()

        if resources_created:
            logger.info("\n" + "="*80)
            logger.info("✅ Test PASSED - Complete workflow successful!")
            logger.info("="*80)
            logger.info("\nWhat happened:")
            logger.info("1. ✅ File uploaded to SeaweedFS S3")
            logger.info("2. ✅ NATS stream created")
            logger.info("3. ✅ Event published to NATS test queue")
            logger.info("4. ✅ Worker consumed message and downloaded from S3")
            logger.info("5. ✅ Content extracted using PDF provider")
            logger.info("6. ✅ Resources saved to database")
            logger.info("\nNext steps:")
            logger.info("- Check database for resources:")
            logger.info(f"  docker exec percolate psql -U postgres -d app -c \"SELECT name, category FROM resources WHERE tenant_id = '{TENANT_ID}' LIMIT 5;\"")
            logger.info("- View file in S3:")
            logger.info(f"  uv run python -m p8fs.cli files list --tenant-id {TENANT_ID} --recursive")
        else:
            logger.error("\n❌ Test FAILED - No resources created")

    except Exception as e:
        logger.error(f"\n❌ Test FAILED with error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
