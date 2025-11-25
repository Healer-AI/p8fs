"""Session message compression and rehydration for efficient context loading."""

from typing import Any
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class MessageCompressor:
    """Compress and decompress session messages with REM lookup keys."""

    def __init__(self, truncate_length: int = 200):
        """
        Initialize message compressor.

        Args:
            truncate_length: Number of characters to keep from start/end (default: 200)
        """
        self.truncate_length = truncate_length
        self.min_length_for_compression = truncate_length * 2

    def compress_message(self, message: dict[str, Any], entity_key: str | None = None) -> dict[str, Any]:
        """
        Compress a message by truncating long content and adding REM lookup key.

        Args:
            message: Message dict with role and content
            entity_key: Optional REM lookup key for full message recovery

        Returns:
            Compressed message dict
        """
        content = message.get("content", "")

        # Don't compress short messages or system messages
        if len(content) <= self.min_length_for_compression or message.get("role") == "system":
            return message.copy()

        # Compress long messages
        n = self.truncate_length
        start = content[:n]
        end = content[-n:]

        # Create compressed content with REM lookup hint
        if entity_key:
            compressed_content = f"{start}\n\n... [Message truncated - REM LOOKUP {entity_key} to recover full content] ...\n\n{end}"
        else:
            compressed_content = f"{start}\n\n... [Message truncated - {len(content) - 2*n} characters omitted] ...\n\n{end}"

        compressed_message = message.copy()
        compressed_message["content"] = compressed_content
        compressed_message["_compressed"] = True
        compressed_message["_original_length"] = len(content)
        if entity_key:
            compressed_message["_entity_key"] = entity_key

        logger.debug(f"Compressed message from {len(content)} to {len(compressed_content)} chars (key={entity_key})")

        return compressed_message

    def decompress_message(self, message: dict[str, Any], full_content: str) -> dict[str, Any]:
        """
        Decompress a message by restoring full content.

        Args:
            message: Compressed message dict
            full_content: Full content to restore

        Returns:
            Decompressed message dict
        """
        decompressed = message.copy()
        decompressed["content"] = full_content
        decompressed.pop("_compressed", None)
        decompressed.pop("_original_length", None)
        decompressed.pop("_entity_key", None)

        return decompressed

    def is_compressed(self, message: dict[str, Any]) -> bool:
        """Check if a message is compressed."""
        return message.get("_compressed", False)

    def get_entity_key(self, message: dict[str, Any]) -> str | None:
        """Get REM lookup key from compressed message."""
        return message.get("_entity_key")


class SessionMessageStore:
    """Store and retrieve session messages with compression."""

    def __init__(self, tenant_id: str, compressor: MessageCompressor | None = None):
        """
        Initialize session message store.

        Args:
            tenant_id: Tenant identifier
            compressor: Optional message compressor (creates default if None)
        """
        self.tenant_id = tenant_id
        self.compressor = compressor or MessageCompressor()

    async def store_message(
        self,
        session_id: str,
        message: dict[str, Any],
        message_index: int
    ) -> str:
        """
        Store a long assistant message as a Session entity for REM lookup.

        Args:
            session_id: Parent session identifier
            message: Message dict to store
            message_index: Index of message in conversation

        Returns:
            Entity key for REM lookup
        """
        from p8fs.models.p8 import Session, SessionType
        from p8fs.repository.TenantRepository import TenantRepository
        from uuid import uuid4

        # Generate UUID for assistant response session
        response_id = str(uuid4())

        # Create entity key for REM LOOKUP: session-{session_id}-msg-{index}
        entity_key = f"session-{session_id}-msg-{message_index}"

        # Create session entity for assistant response
        # query field stores the primary content of the session
        response_session = Session(
            id=response_id,  # Use UUID
            name=entity_key,  # Use entity key as name for REM LOOKUP
            query=message.get("content", ""),  # Store assistant message content
            session_type=SessionType.ASSISTANT_CHAT_RESPONSE,
            parent_session_id=session_id,
            userid=None,  # Inherit from parent session if needed
            metadata={
                "message_index": message_index,
                "role": message.get("role"),
                "timestamp": message.get("timestamp"),
                "entity_key": entity_key,  # Store entity key for lookup
            }
        )

        # Store in database
        repo = TenantRepository(model_class=Session, tenant_id=self.tenant_id)
        await repo.upsert(response_session)

        logger.debug(f"Stored assistant response: {entity_key}")
        return entity_key

    async def retrieve_message(self, entity_key: str) -> str | None:
        """
        Retrieve full message content by REM lookup key.

        Args:
            entity_key: REM lookup key (session-{id}-msg-{index})

        Returns:
            Full message content or None if not found
        """
        from p8fs.models.p8 import Session, SessionType
        from p8fs.repository.TenantRepository import TenantRepository

        try:
            repo = TenantRepository(model_class=Session, tenant_id=self.tenant_id)

            # Find session by name (which stores the entity_key)
            # and session_type=assistant-chat-response
            results = await repo.select(
                filters={"name": entity_key, "session_type": SessionType.ASSISTANT_CHAT_RESPONSE.value},
                limit=1
            )

            if results and len(results) > 0:
                response_session = results[0]
                logger.debug(f"Retrieved assistant response: {entity_key}")
                return response_session.query  # Content is stored in query field

            logger.warning(f"Assistant response not found: {entity_key}")
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve assistant response {entity_key}: {e}")
            return None

    async def store_session_messages(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        compress: bool = True
    ) -> list[dict[str, Any]]:
        """
        Store all session messages and return compressed versions.

        Args:
            session_id: Session identifier
            messages: List of messages to store
            compress: Whether to compress messages (default: True)

        Returns:
            List of compressed messages with REM lookup keys
        """
        compressed_messages = []

        for idx, message in enumerate(messages):
            content = message.get("content", "")

            # Only store and compress long assistant responses (> min_length_for_compression)
            if (message.get("role") == "assistant" and
                len(content) > self.compressor.min_length_for_compression):

                # Store full message as separate Session entity
                entity_key = await self.store_message(session_id, message, idx)

                if compress:
                    compressed_msg = self.compressor.compress_message(message, entity_key)
                    compressed_messages.append(compressed_msg)
                else:
                    msg_copy = message.copy()
                    msg_copy["_entity_key"] = entity_key
                    compressed_messages.append(msg_copy)
            else:
                # Short assistant messages, user messages, and system messages stored as-is
                compressed_messages.append(message.copy())

        return compressed_messages

    async def load_session_messages(
        self,
        session_id: str,
        decompress: bool = False
    ) -> list[dict[str, Any]]:
        """
        Load session messages from Session entity.

        Args:
            session_id: Session identifier
            decompress: Whether to decompress messages (default: False)

        Returns:
            List of session messages
        """
        from p8fs.models.p8 import Session
        from p8fs.repository.TenantRepository import TenantRepository

        try:
            repo = TenantRepository(model_class=Session, tenant_id=self.tenant_id)
            session = await repo.get(session_id)

            if not session:
                logger.warning(f"Session not found: {session_id}")
                return []

            messages = session.metadata.get("messages", [])

            # Decompress if requested
            if decompress:
                decompressed_messages = []
                for message in messages:
                    if self.compressor.is_compressed(message):
                        entity_key = self.compressor.get_entity_key(message)
                        if entity_key:
                            full_content = await self.retrieve_message(entity_key)
                            if full_content:
                                decompressed_messages.append(
                                    self.compressor.decompress_message(message, full_content)
                                )
                            else:
                                # Fallback to compressed version if retrieval fails
                                decompressed_messages.append(message)
                        else:
                            decompressed_messages.append(message)
                    else:
                        decompressed_messages.append(message)

                return decompressed_messages

            return messages

        except Exception as e:
            logger.error(f"Failed to load session messages: {e}")
            return []
