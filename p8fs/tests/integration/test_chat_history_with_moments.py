"""Test chat history with and without moment_id in various combinations."""

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
async def test_chat_history_without_moment_id():
    """Test that chat history works when moment_id is None."""

    class TestAuditProxy(AuditSessionMixin):
        pass

    proxy = TestAuditProxy()
    thread_id = str(uuid4())

    # Create sessions without moment_id
    session1_id = str(uuid4())
    messages1 = [
        {"role": "user", "content": "Hello", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "Hi there!", "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    session1 = Session(
        id=session1_id,
        name=f"session-no-moment-{session1_id[:8]}",
        query="Hello",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user",
        moment_id=None,  # Explicitly no moment
        metadata={"messages": messages1}
    )

    repo = TenantRepository(model_class=Session, tenant_id=TENANT_ID)
    await repo.upsert(session1)

    # Second session, also without moment_id
    session2_id = str(uuid4())
    messages2 = [
        {"role": "user", "content": "How are you?", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "I'm doing well!", "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    session2 = Session(
        id=session2_id,
        name=f"session-no-moment-{session2_id[:8]}",
        query="How are you?",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user",
        moment_id=None,  # Explicitly no moment
        metadata={"messages": messages2}
    )

    await repo.upsert(session2)

    logger.info(f"Created thread {thread_id} with 2 sessions without moment_id")

    # Reload session
    reloaded_session, all_messages = await proxy.reload_session(
        thread_id=thread_id,
        tenant_id=TENANT_ID,
        decompress_messages=False
    )

    # Verify all messages loaded
    assert reloaded_session is not None, "Should reload latest session"
    assert len(all_messages) == 4, f"Expected 4 messages, got {len(all_messages)}"
    assert reloaded_session.moment_id is None, "Session should have no moment_id"

    logger.info("✓ Chat history works without moment_id")

    # Cleanup
    await repo.delete(session1_id)
    await repo.delete(session2_id)


@pytest.mark.asyncio
async def test_chat_history_with_moment_id():
    """Test that chat history works when moment_id is set."""

    class TestAuditProxy(AuditSessionMixin):
        pass

    proxy = TestAuditProxy()
    thread_id = str(uuid4())
    moment_id = str(uuid4())

    # Create sessions with moment_id
    session1_id = str(uuid4())
    messages1 = [
        {"role": "user", "content": "Tell me about the meeting", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "The meeting was productive.", "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    session1 = Session(
        id=session1_id,
        name=f"session-with-moment-{session1_id[:8]}",
        query="Tell me about the meeting",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user",
        moment_id=moment_id,  # Link to moment
        metadata={"messages": messages1}
    )

    repo = TenantRepository(model_class=Session, tenant_id=TENANT_ID)
    await repo.upsert(session1)

    # Second session with same moment_id
    session2_id = str(uuid4())
    messages2 = [
        {"role": "user", "content": "What were the action items?", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "The action items were...", "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    session2 = Session(
        id=session2_id,
        name=f"session-with-moment-{session2_id[:8]}",
        query="What were the action items?",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user",
        moment_id=moment_id,  # Same moment
        metadata={"messages": messages2}
    )

    await repo.upsert(session2)

    logger.info(f"Created thread {thread_id} with 2 sessions linked to moment {moment_id}")

    # Reload session
    reloaded_session, all_messages = await proxy.reload_session(
        thread_id=thread_id,
        tenant_id=TENANT_ID,
        decompress_messages=False
    )

    # Verify all messages loaded
    assert reloaded_session is not None, "Should reload latest session"
    assert len(all_messages) == 4, f"Expected 4 messages, got {len(all_messages)}"
    assert reloaded_session.moment_id == moment_id, f"Session should have moment_id {moment_id}"

    logger.info("✓ Chat history works with moment_id")

    # Cleanup
    await repo.delete(session1_id)
    await repo.delete(session2_id)


@pytest.mark.asyncio
async def test_chat_history_mixed_moments():
    """Test that chat history works with mixed moment_id values (some None, some set)."""

    class TestAuditProxy(AuditSessionMixin):
        pass

    proxy = TestAuditProxy()
    thread_id = str(uuid4())
    moment_id = str(uuid4())

    repo = TenantRepository(model_class=Session, tenant_id=TENANT_ID)

    # Session 1: No moment
    session1_id = str(uuid4())
    messages1 = [
        {"role": "user", "content": "General question", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "General answer", "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    session1 = Session(
        id=session1_id,
        name=f"session-mixed-1-{session1_id[:8]}",
        query="General question",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user",
        moment_id=None,  # No moment
        metadata={"messages": messages1}
    )
    await repo.upsert(session1)

    # Session 2: With moment
    session2_id = str(uuid4())
    messages2 = [
        {"role": "user", "content": "Question about the moment", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "Answer about the moment", "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    session2 = Session(
        id=session2_id,
        name=f"session-mixed-2-{session2_id[:8]}",
        query="Question about the moment",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user",
        moment_id=moment_id,  # With moment
        metadata={"messages": messages2}
    )
    await repo.upsert(session2)

    # Session 3: Back to no moment
    session3_id = str(uuid4())
    messages3 = [
        {"role": "user", "content": "Another general question", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "Another general answer", "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    session3 = Session(
        id=session3_id,
        name=f"session-mixed-3-{session3_id[:8]}",
        query="Another general question",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user",
        moment_id=None,  # No moment
        metadata={"messages": messages3}
    )
    await repo.upsert(session3)

    logger.info(f"Created thread {thread_id} with 3 sessions: mixed moment_id values")

    # Reload session - should get ALL messages regardless of moment_id
    reloaded_session, all_messages = await proxy.reload_session(
        thread_id=thread_id,
        tenant_id=TENANT_ID,
        decompress_messages=False
    )

    # Verify all messages loaded
    assert reloaded_session is not None, "Should reload latest session"
    assert len(all_messages) == 6, f"Expected 6 messages (2 from each session), got {len(all_messages)}"
    assert reloaded_session.id == session3_id, "Should return latest session"
    assert reloaded_session.moment_id is None, "Latest session should have no moment_id"

    # Verify message order (chronological)
    assert all_messages[0]["content"] == "General question", "First message should be from session 1"
    assert all_messages[2]["content"] == "Question about the moment", "Third message should be from session 2"
    assert all_messages[4]["content"] == "Another general question", "Fifth message should be from session 3"

    logger.info("✓ Chat history works with mixed moment_id values")

    # Cleanup
    await repo.delete(session1_id)
    await repo.delete(session2_id)
    await repo.delete(session3_id)


@pytest.mark.asyncio
async def test_chat_history_different_moments_same_thread():
    """Test thread with sessions linked to different moments."""

    class TestAuditProxy(AuditSessionMixin):
        pass

    proxy = TestAuditProxy()
    thread_id = str(uuid4())
    moment_id_1 = str(uuid4())
    moment_id_2 = str(uuid4())

    repo = TenantRepository(model_class=Session, tenant_id=TENANT_ID)

    # Session 1: Moment 1
    session1_id = str(uuid4())
    session1 = Session(
        id=session1_id,
        name=f"session-moment1-{session1_id[:8]}",
        query="Question about first meeting",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user",
        moment_id=moment_id_1,
        metadata={"messages": [
            {"role": "user", "content": "Question about first meeting"},
            {"role": "assistant", "content": "Answer about first meeting"}
        ]}
    )
    await repo.upsert(session1)

    # Session 2: Moment 2
    session2_id = str(uuid4())
    session2 = Session(
        id=session2_id,
        name=f"session-moment2-{session2_id[:8]}",
        query="Question about second meeting",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user",
        moment_id=moment_id_2,
        metadata={"messages": [
            {"role": "user", "content": "Question about second meeting"},
            {"role": "assistant", "content": "Answer about second meeting"}
        ]}
    )
    await repo.upsert(session2)

    logger.info(f"Created thread {thread_id} with 2 sessions linked to different moments")

    # Reload session - should get ALL messages from both moments
    reloaded_session, all_messages = await proxy.reload_session(
        thread_id=thread_id,
        tenant_id=TENANT_ID,
        decompress_messages=False
    )

    # Verify all messages loaded
    assert reloaded_session is not None, "Should reload latest session"
    assert len(all_messages) == 4, f"Expected 4 messages, got {len(all_messages)}"
    assert reloaded_session.moment_id == moment_id_2, "Latest session should have moment_id_2"

    # Verify we got messages from both moments
    message_contents = [msg["content"] for msg in all_messages]
    assert "Question about first meeting" in message_contents, "Should include messages from moment 1"
    assert "Question about second meeting" in message_contents, "Should include messages from moment 2"

    logger.info("✓ Chat history works with different moments in same thread")

    # Cleanup
    await repo.delete(session1_id)
    await repo.delete(session2_id)


@pytest.mark.asyncio
async def test_message_compression_with_moments():
    """Test that message compression works with and without moment_id."""

    thread_id = str(uuid4())
    moment_id = str(uuid4())

    # Session with moment and long message
    session_id = str(uuid4())
    long_response = "A" * 1000  # > 400 chars, should be compressed

    messages = [
        {"role": "user", "content": "Question", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": long_response, "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    session = Session(
        id=session_id,
        name=f"session-compress-{session_id[:8]}",
        query="Question",
        session_type=SessionType.CHAT,
        thread_id=thread_id,
        userid="test-user",
        moment_id=moment_id,  # With moment
        metadata={}
    )

    repo = TenantRepository(model_class=Session, tenant_id=TENANT_ID)
    await repo.upsert(session)

    # Store messages with compression
    message_store = SessionMessageStore(tenant_id=TENANT_ID)
    compressed_messages = await message_store.store_session_messages(
        session_id=session_id,
        messages=messages,
        compress=True
    )

    # Update session with compressed messages
    session.metadata["messages"] = compressed_messages
    await repo.upsert(session)

    # Verify compression worked
    assistant_msg = [m for m in compressed_messages if m.get("role") == "assistant"][0]
    assert assistant_msg.get("_compressed") is True, "Long message should be compressed"
    assert "_entity_key" in assistant_msg, "Compressed message should have entity key"

    # Load with decompression
    decompressed_messages = await message_store.load_session_messages(
        session_id=session_id,
        decompress=True
    )

    # Verify decompression worked
    decompressed_assistant = [m for m in decompressed_messages if m.get("role") == "assistant"][0]
    assert decompressed_assistant["content"] == long_response, "Decompressed content should match original"
    assert "_compressed" not in decompressed_assistant, "Decompressed message should not have _compressed flag"

    logger.info("✓ Message compression works with moment_id")

    # Cleanup
    await repo.delete(session_id)


if __name__ == "__main__":
    asyncio.run(test_chat_history_without_moment_id())
    asyncio.run(test_chat_history_with_moment_id())
    asyncio.run(test_chat_history_mixed_moments())
    asyncio.run(test_chat_history_different_moments_same_thread())
    asyncio.run(test_message_compression_with_moments())
