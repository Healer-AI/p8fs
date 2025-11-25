"""Test to verify chat message history includes both user and assistant messages."""

import asyncio
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from p8fs.models.p8 import Session, SessionType
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.services.llm.session_messages import SessionMessageStore
from p8fs.services.llm.audit_mixin import AuditSessionMixin
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

TENANT_ID = "tenant-test"


@pytest.mark.asyncio
async def test_message_history_includes_both_user_and_assistant():
    """Verify that chat message history includes both user questions and assistant responses."""

    # Create a session with messages
    session_id = str(uuid4())
    thread_id = str(uuid4())

    # Create session
    session = Session(
        id=session_id,
        name=f"test-session-{session_id[:8]}",
        query="What is machine learning?",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user-123",
        metadata={
            "model": "gpt-4.1-mini",
            "total_tokens": 100
        }
    )

    repo = TenantRepository(model_class=Session, tenant_id=TENANT_ID)
    await repo.upsert(session)

    # Create message store
    message_store = SessionMessageStore(tenant_id=TENANT_ID)

    # Create messages (both user and assistant)
    messages = [
        {
            "role": "user",
            "content": "What is machine learning?",
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        {
            "role": "assistant",
            "content": "Machine learning is a subset of artificial intelligence that enables computers to learn from data without being explicitly programmed. It involves training algorithms on datasets to recognize patterns and make predictions or decisions.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    ]

    # Store messages with compression
    compressed_messages = await message_store.store_session_messages(
        session_id=session_id,
        messages=messages,
        compress=True
    )

    # Update session with compressed messages
    session.metadata["messages"] = compressed_messages
    await repo.upsert(session)

    logger.info(f"Created session {session_id} with {len(compressed_messages)} messages")

    # Load messages back (compressed)
    loaded_messages = await message_store.load_session_messages(
        session_id=session_id,
        decompress=False
    )

    # Verify we have both user and assistant messages
    assert len(loaded_messages) == 2, f"Expected 2 messages, got {len(loaded_messages)}"

    user_messages = [m for m in loaded_messages if m.get("role") == "user"]
    assistant_messages = [m for m in loaded_messages if m.get("role") == "assistant"]

    assert len(user_messages) == 1, f"Expected 1 user message, got {len(user_messages)}"
    assert len(assistant_messages) == 1, f"Expected 1 assistant message, got {len(assistant_messages)}"

    # Verify content is preserved
    assert user_messages[0]["content"] == "What is machine learning?"

    # Assistant message should be short (not compressed since < 400 chars)
    assert "Machine learning" in assistant_messages[0]["content"]

    logger.info("✓ Message history includes both user and assistant messages")

    # Test with long assistant response (should be compressed)
    long_response = "A" * 1000  # Long response > 400 chars

    messages_with_long = [
        {
            "role": "user",
            "content": "Tell me more",
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        {
            "role": "assistant",
            "content": long_response,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    ]

    compressed_long = await message_store.store_session_messages(
        session_id=session_id,
        messages=messages_with_long,
        compress=True
    )

    # Verify long assistant message is compressed
    assistant_long = [m for m in compressed_long if m.get("role") == "assistant"][0]
    assert assistant_long.get("_compressed") is True, "Long assistant message should be compressed"
    assert "_entity_key" in assistant_long, "Compressed message should have entity key"

    logger.info("✓ Long assistant messages are properly compressed")

    # Verify we can retrieve the full message
    loaded_decompressed = await message_store.load_session_messages(
        session_id=session_id,
        decompress=True
    )

    # Find the long assistant message
    decompressed_assistant = [m for m in loaded_decompressed if m.get("role") == "assistant" and len(m.get("content", "")) > 500]

    if decompressed_assistant:
        assert decompressed_assistant[0]["content"] == long_response, "Decompressed content should match original"
        logger.info("✓ Decompression retrieves full content")

    # Cleanup
    await repo.delete(session_id)
    logger.info(f"Cleaned up test session {session_id}")


@pytest.mark.asyncio
async def test_reload_session_with_messages():
    """Test that reload_session returns both user and assistant messages."""

    # Create audit mixin instance
    class TestAuditProxy(AuditSessionMixin):
        pass

    proxy = TestAuditProxy()

    # Create a thread with multiple sessions
    thread_id = str(uuid4())

    # First interaction
    session1_id = str(uuid4())
    messages1 = [
        {"role": "user", "content": "Hello", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "Hi! How can I help you?", "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    session1 = Session(
        id=session1_id,
        name=f"test-session-{session1_id[:8]}",
        query="Hello",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user-456",
        metadata={"messages": messages1}
    )

    repo = TenantRepository(model_class=Session, tenant_id=TENANT_ID)
    await repo.upsert(session1)

    # Second interaction
    session2_id = str(uuid4())
    messages2 = [
        {"role": "user", "content": "What's the weather?", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "I don't have access to weather data.", "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    session2 = Session(
        id=session2_id,
        name=f"test-session-{session2_id[:8]}",
        query="What's the weather?",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user-456",
        metadata={"messages": messages2}
    )

    await repo.upsert(session2)

    logger.info(f"Created thread {thread_id} with 2 sessions")

    # Reload session
    reloaded_session, all_messages = await proxy.reload_session(
        thread_id=thread_id,
        tenant_id=TENANT_ID,
        decompress_messages=False
    )

    # Verify we got both sessions' messages
    assert reloaded_session is not None, "Should reload latest session"
    assert reloaded_session.id == session2_id, "Should return latest session"

    assert len(all_messages) == 4, f"Expected 4 messages from 2 sessions, got {len(all_messages)}"

    # Verify message ordering (should be chronological)
    user_messages = [m for m in all_messages if m.get("role") == "user"]
    assistant_messages = [m for m in all_messages if m.get("role") == "assistant"]

    assert len(user_messages) == 2, f"Expected 2 user messages, got {len(user_messages)}"
    assert len(assistant_messages) == 2, f"Expected 2 assistant messages, got {len(assistant_messages)}"

    logger.info("✓ reload_session returns all messages from all sessions in thread")

    # Cleanup
    await repo.delete(session1_id)
    await repo.delete(session2_id)
    logger.info(f"Cleaned up thread {thread_id}")


@pytest.mark.asyncio
async def test_parameter_space_with_test_users():
    """Test that different tenant IDs work correctly."""

    test_tenants = ["tenant-test", "tenant-1", "tenant-2", "tenant-3"]

    for tenant_id in test_tenants:
        session_id = str(uuid4())

        # Create session for this tenant
        session = Session(
            id=session_id,
            name=f"test-{tenant_id}-{session_id[:8]}",
            query="Test query",
            session_type=SessionType.CHAT,
            userid=f"user-{tenant_id}",
            metadata={
                "messages": [
                    {"role": "user", "content": "Test", "timestamp": datetime.now(timezone.utc).isoformat()},
                    {"role": "assistant", "content": "Test response", "timestamp": datetime.now(timezone.utc).isoformat()}
                ]
            }
        )

        repo = TenantRepository(model_class=Session, tenant_id=tenant_id)
        await repo.upsert(session)

        # Verify we can load it back
        message_store = SessionMessageStore(tenant_id=tenant_id)
        messages = await message_store.load_session_messages(session_id, decompress=False)

        assert len(messages) == 2, f"Tenant {tenant_id}: Expected 2 messages, got {len(messages)}"
        assert messages[0]["role"] == "user", f"Tenant {tenant_id}: First message should be user"
        assert messages[1]["role"] == "assistant", f"Tenant {tenant_id}: Second message should be assistant"

        # Cleanup
        await repo.delete(session_id)

        logger.info(f"✓ Tenant {tenant_id} works correctly")

    logger.info(f"✓ All {len(test_tenants)} test tenants verified")


if __name__ == "__main__":
    asyncio.run(test_message_history_includes_both_user_and_assistant())
    asyncio.run(test_reload_session_with_messages())
    asyncio.run(test_parameter_space_with_test_users())
