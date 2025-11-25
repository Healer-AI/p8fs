"""Test user summary functionality."""

import asyncio
import yaml
from p8fs.models.p8 import Session
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

TENANT_ID = "tenant-test"


async def test_user_summary():
    """Test user summarization with actual session data."""

    logger.info("Testing user summary for tenant: %s", TENANT_ID)

    # Use the convenience method on Session class
    summary = await Session.summarize_user(
        tenant_id=TENANT_ID,
        max_sessions=100,
        max_moments=20,
        max_resources=20,
        max_files=10
    )

    logger.info("User summary generated successfully")

    # Save to YAML file
    with open("user-summary-example.yaml", "w") as f:
        yaml.dump(summary, f, default_flow_style=False, sort_keys=False)

    logger.info("User summary saved to user-summary-example.yaml")

    # Print summary to console
    print("\n" + "="*60)
    print("USER SUMMARY")
    print("="*60)
    print(yaml.dump(summary, default_flow_style=False, sort_keys=False))


if __name__ == "__main__":
    asyncio.run(test_user_summary())
