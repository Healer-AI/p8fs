"""Test REM LOOKUP functionality with moments, resources, and files."""

import asyncio
from p8fs.models.p8 import Moment, Resources, Files
from p8fs.repository.TenantRepository import TenantRepository
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

TENANT_ID = "tenant-test"


async def test_moment_lookup():
    """Test looking up a moment by name."""

    logger.info("\n" + "="*60)
    logger.info("Testing Moment REM LOOKUP")
    logger.info("="*60)

    repo = TenantRepository(model_class=Moment, tenant_id=TENANT_ID)

    # Get one moment to test lookup
    moments = await repo.select(filters={}, limit=1)

    if not moments:
        logger.error("No moments found to test")
        return

    moment = moments[0]
    logger.info(f"\nLooking up moment by name: '{moment.name}'")

    # Test lookup by name using select with filters
    results = await repo.select(filters={"name": moment.name}, limit=1)

    if results:
        found = results[0]
        logger.info(f"✅ Found moment: {found.name}")
        logger.info(f"   Summary: {found.summary}")
        logger.info(f"   Content: {found.content[:100]}...")
    else:
        logger.error(f"❌ Moment not found by name lookup")


async def test_resource_lookup():
    """Test looking up a resource by name."""

    logger.info("\n" + "="*60)
    logger.info("Testing Resource REM LOOKUP")
    logger.info("="*60)

    repo = TenantRepository(model_class=Resources, tenant_id=TENANT_ID)

    # Get one resource to test lookup
    resources = await repo.select(filters={}, limit=1)

    if not resources:
        logger.error("No resources found to test")
        return

    resource = resources[0]
    logger.info(f"\nLooking up resource by name: '{resource.name}'")

    # Test lookup by name
    results = await repo.select(filters={"name": resource.name}, limit=1)

    if results:
        found = results[0]
        logger.info(f"✅ Found resource: {found.name}")
        logger.info(f"   Category: {found.category}")
        logger.info(f"   Content: {found.content[:100]}...")
    else:
        logger.error(f"❌ Resource not found by name lookup")


async def test_file_lookup():
    """Test looking up a file by URI."""

    logger.info("\n" + "="*60)
    logger.info("Testing File REM LOOKUP")
    logger.info("="*60)

    repo = TenantRepository(model_class=Files, tenant_id=TENANT_ID)

    # Get files
    files = await repo.select(filters={}, limit=1)

    if not files:
        logger.warning("No files found - this is expected for now")
        logger.info("File lookup would work with filters={'uri': file_uri}")
        return

    file = files[0]
    logger.info(f"\nLooking up file by URI: '{file.uri}'")

    # Test lookup by URI
    results = await repo.select(filters={"uri": file.uri}, limit=1)

    if results:
        found = results[0]
        logger.info(f"✅ Found file: {found.uri}")
        logger.info(f"   Name: {found.name}")
    else:
        logger.error(f"❌ File not found by URI lookup")


async def main():
    """Run all REM LOOKUP tests."""

    logger.info("Testing REM LOOKUP functionality\n")

    await test_moment_lookup()
    await test_resource_lookup()
    await test_file_lookup()

    logger.info("\n" + "="*60)
    logger.info("REM LOOKUP Tests Complete")
    logger.info("="*60)


if __name__ == "__main__":
    asyncio.run(main())
