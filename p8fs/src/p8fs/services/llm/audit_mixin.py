"""Audit session mixin for LLM services."""

import asyncio
from typing import Optional, Dict, Any

from p8fs_cluster.logging import get_logger
from datetime import datetime
from uuid import uuid4
from p8fs.models.p8 import Session
from p8fs.models.audit_session import TokenUsageCalculator

logger = get_logger(__name__)


class AuditSessionMixin:
    """Mixin to add audit session tracking to LLM services."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_session: Optional[Session] = None
        self._session_lock = asyncio.Lock()
        self._current_tenant_id: Optional[str] = None

    async def start_audit_session(
        self,
        tenant_id: str,
        model: str,
        provider: str = "openai",
        streaming: bool = False,
        user_id: Optional[str] = None,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        query: Optional[str] = None,
        moment_id: Optional[str] = None,
        session_type: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """Start new audit session for tracking token usage.

        Note: session_id here is the PARENT/THREAD session ID for grouping,
        not the actual Session.id which is always a new UUID.
        """
        async with self._session_lock:
            self._current_tenant_id = tenant_id

            try:
                # Always create new session with new UUID
                # session_id from header goes into thread_id for grouping
                self._current_session = Session(
                    id=str(uuid4()),
                    thread_id=session_id,  # Group sessions by thread/conversation
                    userid=user_id,
                    query=query,  # Set the query field
                    moment_id=moment_id,  # Link to moment if provided
                    session_type=session_type,  # Set session type (chat, dreaming, etc.)
                    metadata={
                        "model": model,
                        "provider": provider,
                        "streaming": streaming,
                        "system_message": system_message,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "estimated_cost": 0.0,
                        "function_calls": 0,
                        "started_at": datetime.now().isoformat(),
                    },
                )

                # Save the session
                from p8fs.repository.TenantRepository import TenantRepository

                repo = TenantRepository(model_class=Session, tenant_id=tenant_id)
                await repo.upsert(self._current_session)

                logger.debug(f"Started audit session {self._current_session.id}")
                return self._current_session
            except Exception as e:
                logger.error(f"Failed to create audit session: {e}")
                # Create in-memory session as fallback
                self._current_session = Session(
                    id=str(uuid4()),
                    thread_id=session_id,  # Group sessions by thread/conversation
                    userid=user_id,
                    query=query,  # Set the query field
                    moment_id=moment_id,  # Link to moment if provided
                    session_type=session_type,  # Set session type (chat, dreaming, etc.)
                    metadata={
                        "model": model,
                        "provider": provider,
                        "streaming": streaming,
                        "system_message": system_message,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "estimated_cost": 0.0,
                        "function_calls": 0,
                        "started_at": datetime.now().isoformat(),
                    },
                )
                return self._current_session

    async def track_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> None:
        """Track token usage in current session."""
        if not self._current_session:
            logger.warning("No active audit session for token tracking")
            return

        # Calculate cost
        model_name = model or self._current_session.metadata.get("model", "")
        provider_name = provider or self._current_session.metadata.get(
            "provider", "openai"
        )

        estimated_cost = TokenUsageCalculator.calculate_cost(
            provider=provider_name,
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        # Update session metadata
        self._current_session.metadata["prompt_tokens"] = (
            self._current_session.metadata.get("prompt_tokens", 0) + prompt_tokens
        )
        self._current_session.metadata["completion_tokens"] = (
            self._current_session.metadata.get("completion_tokens", 0)
            + completion_tokens
        )
        self._current_session.metadata["total_tokens"] = (
            self._current_session.metadata["prompt_tokens"]
            + self._current_session.metadata["completion_tokens"]
        )
        self._current_session.metadata["estimated_cost"] = (
            self._current_session.metadata.get("estimated_cost", 0.0) + estimated_cost
        )

        logger.debug(
            f"Session {self._current_session.id}: "
            f"+{prompt_tokens}p +{completion_tokens}c "
            f"(${estimated_cost:.4f}) "
            f"Total: {self._current_session.metadata['total_tokens']} tokens, "
            f"${self._current_session.metadata['estimated_cost']:.4f}"
        )

        # Update in database (async, don't await)
        asyncio.create_task(self._update_session_async())

    async def track_function_call(self) -> None:
        """Track function call in current session."""
        if self._current_session:
            self._current_session.metadata["function_calls"] = (
                self._current_session.metadata.get("function_calls", 0) + 1
            )
            logger.debug(
                f"Session {self._current_session.id}: "
                f"Function call #{self._current_session.metadata.get('function_calls', 0)}"
            )
            # Update in database (async, don't await)
            asyncio.create_task(self._update_session_async())

    async def end_audit_session(self) -> Optional[Session]:
        """End current audit session and return final stats."""
        async with self._session_lock:
            if not self._current_session:
                return None

            self._current_session.metadata["ended_at"] = datetime.now().isoformat()
            self._current_session.session_completed_at = datetime.now()

            # Calculate duration
            started_at = datetime.fromisoformat(
                self._current_session.metadata.get(
                    "started_at", datetime.now().isoformat()
                )
            )
            ended_at = datetime.fromisoformat(
                self._current_session.metadata.get(
                    "ended_at", datetime.now().isoformat()
                )
            )
            duration_seconds = (ended_at - started_at).total_seconds()

            logger.info(
                f"Ended audit session {self._current_session.id}: "
                f"{self._current_session.metadata.get('total_tokens', 0)} tokens, "
                f"{self._current_session.metadata.get('function_calls', 0)} function calls, "
                f"${self._current_session.metadata.get('estimated_cost', 0.0):.4f}, "
                f"{duration_seconds:.2f}s"
            )

            # Final update to database
            try:
                await self._update_session_async()
            except Exception as e:
                logger.error(f"Failed to update audit session: {e}")

            session = self._current_session
            self._current_session = None
            return session

    async def _update_session_async(self) -> None:
        """Update session in database asynchronously."""
        if self._current_session:
            try:
                from p8fs.repository.TenantRepository import TenantRepository

                repo = TenantRepository(
                    model_class=Session, tenant_id=self._current_tenant_id
                )
                await repo.upsert(self._current_session)
            except Exception as e:
                logger.debug(f"Failed to update audit session: {e}")

    def extract_usage_from_response(self, response: Dict[str, Any]) -> tuple[int, int]:
        """Extract token usage from LLM response."""
        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        return prompt_tokens, completion_tokens

    @property
    def current_session(self) -> Optional[Session]:
        """Get current audit session."""
        return self._current_session

    def _calculate_duration(self) -> float:
        """Calculate session duration in seconds."""
        if (
            not self._current_session
            or "started_at" not in self._current_session.metadata
        ):
            return 0.0

        started_at = datetime.fromisoformat(
            self._current_session.metadata["started_at"]
        )
        ended_at = datetime.fromisoformat(
            self._current_session.metadata.get("ended_at", datetime.now().isoformat())
        )
        return (ended_at - started_at).total_seconds()

    @property
    def session_stats(self) -> Dict[str, Any]:
        """Get current session statistics."""
        if not self._current_session:
            return {}

        # Calculate duration if session has started
        duration_seconds = 0.0
        if "started_at" in self._current_session.metadata:
            started_at = datetime.fromisoformat(
                self._current_session.metadata["started_at"]
            )
            ended_at = datetime.fromisoformat(
                self._current_session.metadata.get(
                    "ended_at", datetime.now().isoformat()
                )
            )
            duration_seconds = (ended_at - started_at).total_seconds()

        return {
            "session_id": self._current_session.id,
            "tenant_id": self._current_tenant_id,
            "model": self._current_session.metadata.get("model", ""),
            "provider": self._current_session.metadata.get("provider", "openai"),
            "total_tokens": self._current_session.metadata.get("total_tokens", 0),
            "prompt_tokens": self._current_session.metadata.get("prompt_tokens", 0),
            "completion_tokens": self._current_session.metadata.get(
                "completion_tokens", 0
            ),
            "function_calls": self._current_session.metadata.get("function_calls", 0),
            "estimated_cost": self._current_session.metadata.get("estimated_cost", 0.0),
            "duration_seconds": duration_seconds,
            "streaming": self._current_session.metadata.get("streaming", False),
        }

    async def audit_session(
        self,
        tenant_id: str,
        model: str,
        provider: str = "openai",
        streaming: bool = False,
        temperature: float = 0.7,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        messages: Optional[list] = None,
        completion_tokens: int = 0,
        prompt_tokens: int = 0,
        **kwargs,
    ) -> Optional[Session]:
        """
        Convenience method to audit a complete session interaction.

        This creates a session, tracks usage, and ends it in a single call.
        Useful for simple request-response interactions.

        Args:
            tenant_id: Tenant identifier
            model: Model name used
            provider: Provider name (openai, anthropic, etc.)
            streaming: Whether streaming was used
            temperature: Model temperature
            user_id: Optional user identifier
            session_id: Optional session identifier
            messages: Optional list of messages in the interaction
            completion_tokens: Number of completion tokens used
            prompt_tokens: Number of prompt tokens used
            **kwargs: Additional parameters

        Returns:
            The completed audit session or None if creation failed
        """
        try:
            # Start audit session
            # Extract query from messages if provided
            query = None
            if messages:
                for msg in messages:
                    if msg.get("role") == "user":
                        query = msg.get("content")
                        break

            session = await self.start_audit_session(
                tenant_id=tenant_id,
                model=model,
                provider=provider,
                streaming=streaming,
                user_id=user_id,
                temperature=temperature,
                query=query,
            )

            # Track usage if provided
            if prompt_tokens > 0 or completion_tokens > 0:
                await self.track_usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    model=model,
                    provider=provider,
                )

            # End session and return final stats
            return await self.end_audit_session()

        except Exception as e:
            logger.error(f"Failed to audit session: {e}")
            return None

    async def reload_session(
        self,
        thread_id: str,
        tenant_id: str,
        decompress_messages: bool = False
    ) -> tuple[Session | None, list[dict]]:
        """
        Reload all sessions in a thread and their message history.

        Args:
            thread_id: Thread/conversation identifier (from X-Session-ID header)
            tenant_id: Tenant identifier
            decompress_messages: Whether to decompress long messages (default: False)

        Returns:
            Tuple of (latest_session, all_messages) or (None, []) if not found
        """
        from p8fs.repository.TenantRepository import TenantRepository
        from p8fs.services.llm.session_messages import SessionMessageStore

        try:
            # Load ALL sessions in this thread
            repo = TenantRepository(model_class=Session, tenant_id=tenant_id)
            sessions = await repo.select(
                filters={"thread_id": thread_id},
                order_by=["created_at"],  # Chronological order
            )

            if not sessions:
                logger.warning(f"No sessions found for thread: {thread_id}")
                return None, []

            # Set latest session as current
            latest_session = sessions[-1]
            async with self._session_lock:
                self._current_session = latest_session
                self._current_tenant_id = tenant_id

            # Load and combine messages from all sessions in thread
            message_store = SessionMessageStore(tenant_id=tenant_id)
            all_messages = []

            for session in sessions:
                session_messages = await message_store.load_session_messages(
                    session_id=session.id,
                    decompress=decompress_messages
                )
                all_messages.extend(session_messages)

            logger.info(
                f"Reloaded thread {thread_id}: "
                f"{len(sessions)} sessions, "
                f"{len(all_messages)} total messages"
            )

            return latest_session, all_messages

        except Exception as e:
            logger.error(f"Failed to reload thread {thread_id}: {e}")
            return None, []

    async def save_session_messages(
        self,
        messages: list[dict],
        compress: bool = True
    ) -> None:
        """
        Save session messages with optional compression.

        Args:
            messages: List of messages to save
            compress: Whether to compress long messages (default: True)
        """
        if not self._current_session:
            logger.warning("No active session to save messages")
            return

        from p8fs.services.llm.session_messages import SessionMessageStore

        try:
            message_store = SessionMessageStore(tenant_id=self._current_tenant_id)

            # Store and compress messages
            compressed_messages = await message_store.store_session_messages(
                session_id=self._current_session.id,
                messages=messages,
                compress=compress
            )

            # Update session with compressed messages
            self._current_session.metadata["messages"] = compressed_messages
            self._current_session.metadata["message_count"] = len(messages)

            # Save to database
            await self._update_session_async()

            logger.debug(
                f"Saved {len(messages)} messages for session {self._current_session.id} "
                f"(compressed: {compress})"
            )

        except Exception as e:
            logger.error(f"Failed to save session messages: {e}")
