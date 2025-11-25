"""Generate sample session history output."""

import asyncio
import yaml
from datetime import datetime, timezone
from uuid import uuid4

from p8fs.models.p8 import Session, SessionType
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.services.llm.session_messages import SessionMessageStore
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

TENANT_ID = "tenant-test"


async def generate_session_history():
    """Generate session history with compressed messages."""

    repo = TenantRepository(model_class=Session, tenant_id=TENANT_ID)

    # Get recent chat sessions only (exclude internal sessions like assistant-chat-response)
    sessions = await repo.select(
        filters={"session_type": SessionType.CHAT.value},
        order_by=["-created_at"],
        limit=5
    )

    message_store = SessionMessageStore(tenant_id=TENANT_ID)

    session_history = []

    for session in sessions:
        # Load messages (compressed version)
        messages_compressed = await message_store.load_session_messages(
            session_id=session.id,
            decompress=False
        )

        session_data = {
            "session_id": session.id,
            "date": session.created_at.isoformat() if session.created_at else "unknown",
            "query": session.query or "No query",
            "session_type": session.session_type,
            "messages": messages_compressed,
            "metadata": {
                "message_count": len(messages_compressed),
                "total_tokens": session.metadata.get("total_tokens", 0) if session.metadata else 0,
                "model": session.metadata.get("model", "unknown") if session.metadata else "unknown"
            }
        }

        session_history.append(session_data)

    # Save to YAML
    with open("sessions.yaml", "w") as f:
        yaml.dump(session_history, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Generated session history with {len(session_history)} sessions")
    logger.info("Saved to sessions.yaml")

    # Print to console
    print("\n" + "="*60)
    print("SESSION HISTORY")
    print("="*60)
    print(yaml.dump(session_history, default_flow_style=False, sort_keys=False))


async def main():
    """Generate session history."""
    await generate_session_history()


if __name__ == "__main__":
    asyncio.run(main())
