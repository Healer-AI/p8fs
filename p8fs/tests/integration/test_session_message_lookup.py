"""Test REM LOOKUP for session messages from sessions.yaml."""

import asyncio
from p8fs.models.p8 import Session, SessionType
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.services.llm.session_messages import SessionMessageStore
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

TENANT_ID = "tenant-test"


async def test_session_message_lookup():
    """Test REM LOOKUP for compressed session messages."""

    # Test the REM LOOKUP keys from sessions.yaml
    test_keys = [
        "session-f880332c-8333-4753-927f-16e2542366b1-msg-1",  # Quantum computing
        "session-3317bade-4b11-49c0-99cb-2b1c5f692256-msg-1",  # Neural networks
    ]

    message_store = SessionMessageStore(tenant_id=TENANT_ID)

    logger.info("\n" + "="*60)
    logger.info("Testing Session Message REM LOOKUP")
    logger.info("="*60)

    for entity_key in test_keys:
        logger.info(f"\n📍 Looking up: {entity_key}")

        # Use retrieve_message to get full content
        full_content = await message_store.retrieve_message(entity_key)

        if full_content:
            logger.info(f"✅ Retrieved full message ({len(full_content)} chars):")
            logger.info(f"   First 100 chars: {full_content[:100]}...")
            logger.info(f"   Last 100 chars: ...{full_content[-100:]}")
        else:
            logger.error(f"❌ Failed to retrieve message for key: {entity_key}")


async def test_full_session_reload():
    """Test reloading a full session with decompression."""

    logger.info("\n" + "="*60)
    logger.info("Testing Full Session Reload with Decompression")
    logger.info("="*60)

    session_id = "f880332c-8333-4753-927f-16e2542366b1"  # Quantum computing session

    message_store = SessionMessageStore(tenant_id=TENANT_ID)

    # Load compressed
    logger.info(f"\n📍 Loading session {session_id} (compressed)")
    messages_compressed = await message_store.load_session_messages(
        session_id=session_id,
        decompress=False
    )

    logger.info(f"Compressed: {len(messages_compressed)} messages")
    for i, msg in enumerate(messages_compressed):
        content = msg.get("content", "")
        is_compressed = msg.get("_compressed", False)
        logger.info(f"  [{i}] {msg['role']}: {len(content)} chars {'(COMPRESSED)' if is_compressed else ''}")

    # Load decompressed
    logger.info(f"\n📍 Loading session {session_id} (decompressed)")
    messages_full = await message_store.load_session_messages(
        session_id=session_id,
        decompress=True
    )

    logger.info(f"Decompressed: {len(messages_full)} messages")
    for i, msg in enumerate(messages_full):
        content = msg.get("content", "")
        logger.info(f"  [{i}] {msg['role']}: {len(content)} chars (FULL)")
        if msg['role'] == 'assistant' and len(content) > 400:
            logger.info(f"      Preview: {content[:100]}...")


async def main():
    """Run all tests."""
    await test_session_message_lookup()
    await test_full_session_reload()

    logger.info("\n" + "="*60)
    logger.info("✅ All REM LOOKUP tests completed")
    logger.info("="*60)


if __name__ == "__main__":
    asyncio.run(main())
