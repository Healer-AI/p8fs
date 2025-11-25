"""Integration tests for session reloading with message compression."""

import pytest
from datetime import datetime
from p8fs.services.llm.session_messages import MessageCompressor, SessionMessageStore
from p8fs.services.llm.audit_mixin import AuditSessionMixin
from p8fs.models.user_context import UserContext
from p8fs.models.p8 import Session
from p8fs.repository.TenantRepository import TenantRepository


class TestableProxy(AuditSessionMixin):
    """Testable proxy with audit session mixin."""

    pass


@pytest.mark.integration
class TestMessageCompression:
    """Test message compression and decompression."""

    def test_compress_short_message(self):
        """Short messages should not be compressed."""
        compressor = MessageCompressor(truncate_length=200)

        message = {
            "role": "user",
            "content": "Hello, how are you?"
        }

        compressed = compressor.compress_message(message)

        assert compressed["content"] == message["content"]
        assert not compressor.is_compressed(compressed)

    def test_compress_long_message(self):
        """Long messages should be compressed with truncation."""
        compressor = MessageCompressor(truncate_length=200)

        long_content = "This is a very long message. " * 100  # ~3000 chars
        message = {
            "role": "assistant",
            "content": long_content
        }

        entity_key = "test-session-msg-1"
        compressed = compressor.compress_message(message, entity_key)

        assert compressor.is_compressed(compressed)
        assert compressed["_entity_key"] == entity_key
        assert compressed["_original_length"] == len(long_content)
        assert "REM LOOKUP test-session-msg-1" in compressed["content"]
        assert len(compressed["content"]) < len(long_content)

    def test_compress_system_message_never_compressed(self):
        """System messages should never be compressed."""
        compressor = MessageCompressor(truncate_length=200)

        long_content = "System instructions. " * 100
        message = {
            "role": "system",
            "content": long_content
        }

        compressed = compressor.compress_message(message, "test-key")

        assert not compressor.is_compressed(compressed)
        assert compressed["content"] == long_content

    def test_decompress_message(self):
        """Decompression should restore full content."""
        compressor = MessageCompressor(truncate_length=200)

        original_content = "Original message content. " * 100
        message = {"role": "assistant", "content": original_content}

        compressed = compressor.compress_message(message, "test-key")
        decompressed = compressor.decompress_message(compressed, original_content)

        assert decompressed["content"] == original_content
        assert not compressor.is_compressed(decompressed)
        assert "_entity_key" not in decompressed


@pytest.mark.integration
class TestSessionMessageStore:
    """Test session message storage and retrieval."""

    @pytest.fixture
    def tenant_id(self):
        return "test-tenant-session-store"

    @pytest.fixture
    def message_store(self, tenant_id):
        return SessionMessageStore(tenant_id=tenant_id)

    async def test_store_and_retrieve_message(self, message_store):
        """Store a message and retrieve it by entity key."""
        session_id = "test-session-1"
        message = {
            "role": "assistant",
            "content": "This is a test message with some content to verify storage and retrieval.",
            "timestamp": datetime.now().isoformat()
        }

        # Store message
        entity_key = await message_store.store_message(session_id, message, message_index=0)

        assert entity_key == f"session-{session_id}-msg-0"

        # Retrieve message
        retrieved_content = await message_store.retrieve_message(entity_key)

        assert retrieved_content == message["content"]

    async def test_store_session_messages_with_compression(self, message_store):
        """Store multiple messages and compress long ones."""
        session_id = "test-session-2"

        short_message = {
            "role": "user",
            "content": "Short question"
        }

        long_message = {
            "role": "assistant",
            "content": "This is a very detailed answer. " * 100  # Long response
        }

        messages = [short_message, long_message]

        # Store with compression
        compressed_messages = await message_store.store_session_messages(
            session_id=session_id,
            messages=messages,
            compress=True
        )

        assert len(compressed_messages) == 2

        # Short message not compressed
        assert compressed_messages[0]["content"] == short_message["content"]

        # Long message compressed
        assert message_store.compressor.is_compressed(compressed_messages[1])
        assert "REM LOOKUP" in compressed_messages[1]["content"]
        assert len(compressed_messages[1]["content"]) < len(long_message["content"])

    async def test_load_session_messages(self, message_store, tenant_id):
        """Load session messages from database."""
        session_id = "test-session-3"

        messages = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1 with details. " * 50},
            {"role": "user", "content": "Question 2"},
        ]

        # Store messages
        compressed_messages = await message_store.store_session_messages(
            session_id=session_id,
            messages=messages,
            compress=True
        )

        # Save to session
        session = Session(
            id=session_id,
            userid=tenant_id,
            metadata={
                "messages": compressed_messages,
                "message_count": len(messages)
            }
        )

        repo = TenantRepository(model_class=Session, tenant_id=tenant_id)
        await repo.upsert(session)

        # Load messages (compressed)
        loaded_messages = await message_store.load_session_messages(
            session_id=session_id,
            decompress=False
        )

        assert len(loaded_messages) == 3
        assert message_store.compressor.is_compressed(loaded_messages[1])

        # Load messages (decompressed)
        decompressed_messages = await message_store.load_session_messages(
            session_id=session_id,
            decompress=True
        )

        assert len(decompressed_messages) == 3
        assert not message_store.compressor.is_compressed(decompressed_messages[1])
        assert decompressed_messages[1]["content"] == messages[1]["content"]


@pytest.mark.integration
class TestAuditSessionReload:
    """Test audit session reload functionality."""

    @pytest.fixture
    def tenant_id(self):
        return "test-tenant-audit-reload"

    @pytest.fixture
    def proxy(self):
        return TestableProxy()

    async def test_reload_session_not_found(self, proxy, tenant_id):
        """Reloading non-existent session returns None."""
        session, messages = await proxy.reload_session(
            session_id="nonexistent-session",
            tenant_id=tenant_id
        )

        assert session is None
        assert messages == []

    async def test_create_and_reload_session(self, proxy, tenant_id):
        """Create a session with messages and reload it."""
        # Start new session
        session = await proxy.start_audit_session(
            tenant_id=tenant_id,
            model="gpt-4.1-mini",
            user_id=tenant_id,
            query="Initial question"
        )

        session_id = session.id

        # Add messages
        messages = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language. " * 100},
            {"role": "user", "content": "Tell me more"},
        ]

        await proxy.save_session_messages(messages, compress=True)

        # End session
        await proxy.end_audit_session()

        # Reload session
        reloaded_session, reloaded_messages = await proxy.reload_session(
            session_id=session_id,
            tenant_id=tenant_id,
            decompress_messages=False
        )

        assert reloaded_session is not None
        assert reloaded_session.id == session_id
        assert len(reloaded_messages) == 3

        # Verify compression
        assert proxy._current_session.metadata["messages"][1].get("_compressed") is True

    async def test_reload_with_decompression(self, proxy, tenant_id):
        """Reload session and decompress messages."""
        # Create session with long message
        session = await proxy.start_audit_session(
            tenant_id=tenant_id,
            model="gpt-4.1-mini"
        )

        session_id = session.id
        long_content = "Detailed explanation. " * 200

        messages = [
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": long_content},
        ]

        await proxy.save_session_messages(messages, compress=True)
        await proxy.end_audit_session()

        # Reload with decompression
        reloaded_session, decompressed_messages = await proxy.reload_session(
            session_id=session_id,
            tenant_id=tenant_id,
            decompress_messages=True
        )

        assert len(decompressed_messages) == 2
        assert decompressed_messages[1]["content"] == long_content
        assert "_compressed" not in decompressed_messages[1]


@pytest.mark.integration
class TestUserContext:
    """Test user context loading and storage."""

    @pytest.fixture
    def tenant_id(self):
        return "test-tenant-user-context"

    async def test_load_or_create_new_user(self, tenant_id):
        """Create new user context if not exists."""
        user_context = await UserContext.load_or_create(tenant_id)

        assert user_context.tenant_id == tenant_id
        assert user_context.id == f"user-{tenant_id}"
        assert user_context.total_sessions == 0

    async def test_update_session_stats(self, tenant_id):
        """Update user session statistics."""
        user_context = await UserContext.load_or_create(tenant_id)

        initial_sessions = user_context.total_sessions
        initial_tokens = user_context.total_tokens_used

        await user_context.update_session_stats(tokens_used=1500)

        assert user_context.total_sessions == initial_sessions + 1
        assert user_context.total_tokens_used == initial_tokens + 1500
        assert user_context.last_session_at is not None

    async def test_user_context_to_message(self, tenant_id):
        """Convert user context to system message."""
        user_context = await UserContext.load_or_create(tenant_id)
        user_context.facts = ["User prefers Python", "User works on AI projects"]
        user_context.goals = ["Learn advanced Python", "Build AI applications"]

        message = user_context.to_context_message()

        assert message["role"] == "system"
        assert f"REM LOOKUP user-{tenant_id}" in message["content"]
        assert "User prefers Python" in message["content"]
        assert "Learn advanced Python" in message["content"]
        assert str(user_context.total_sessions) in message["content"]


@pytest.mark.integration
class TestEndToEndSessionReload:
    """End-to-end test of session reload workflow."""

    @pytest.fixture
    def tenant_id(self):
        return "test-tenant-e2e"

    @pytest.fixture
    def proxy(self):
        return TestableProxy()

    async def test_complete_session_lifecycle(self, proxy, tenant_id):
        """Test complete session lifecycle with reload."""
        # 1. Start session
        session = await proxy.start_audit_session(
            tenant_id=tenant_id,
            model="gpt-4.1-mini",
            user_id=tenant_id,
            query="Initial query"
        )

        session_id = session.id

        # 2. Simulate conversation
        conversation = [
            {"role": "user", "content": "What is machine learning?"},
            {"role": "assistant", "content": "Machine learning is a subset of artificial intelligence. " * 100},
            {"role": "user", "content": "Can you explain neural networks?"},
            {"role": "assistant", "content": "Neural networks are computing systems inspired by biological neural networks. " * 150},
        ]

        # 3. Save conversation with compression
        await proxy.save_session_messages(conversation, compress=True)

        # 4. Track some usage
        await proxy.track_usage(prompt_tokens=500, completion_tokens=1500)

        # 5. End session
        ended_session = await proxy.end_audit_session()

        assert ended_session.metadata["total_tokens"] == 2000

        # 6. Load user context
        user_context = await UserContext.load_or_create(tenant_id)
        await user_context.update_session_stats(tokens_used=2000)

        # 7. Reload session in new conversation
        reloaded_session, historical_messages = await proxy.reload_session(
            session_id=session_id,
            tenant_id=tenant_id,
            decompress_messages=False  # Keep compressed
        )

        assert reloaded_session is not None
        assert len(historical_messages) == 4

        # 8. Verify compression
        assert "REM LOOKUP" in historical_messages[1]["content"]  # First assistant message
        assert "REM LOOKUP" in historical_messages[3]["content"]  # Second assistant message

        # 9. Add user context message
        user_context_msg = user_context.to_context_message()
        full_context = [user_context_msg] + historical_messages

        assert full_context[0]["role"] == "system"
        assert f"REM LOOKUP user-{tenant_id}" in full_context[0]["content"]
        assert len(full_context) == 5  # 1 system + 4 historical

        # 10. Verify we can continue the conversation
        new_message = {"role": "user", "content": "Tell me more about deep learning"}
        full_context.append(new_message)

        assert len(full_context) == 6
        assert full_context[-1]["content"] == "Tell me more about deep learning"
