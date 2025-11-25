"""Test session reload and message compression functionality."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from p8fs.models.p8 import Session, SessionType
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.services.llm.session_messages import SessionMessageStore
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

TENANT_ID = "tenant-test"


async def create_test_sessions():
    """Create test sessions with various message lengths to test compression."""

    repo = TenantRepository(model_class=Session, tenant_id=TENANT_ID)
    message_store = SessionMessageStore(tenant_id=TENANT_ID)

    # Session 1: Short messages (no compression)
    session1_id = str(uuid4())
    session1 = Session(
        id=session1_id,
        name=f"test-session-{session1_id}",
        query="What is machine learning?",
        session_type=SessionType.CHAT,
        userid="test-user-1"
    )
    await repo.upsert(session1)

    messages1 = [
        {"role": "user", "content": "What is machine learning?", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "Machine learning is a subset of AI that enables systems to learn from data.", "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    compressed = await message_store.store_session_messages(session_id=session1_id, messages=messages1, compress=True)

    # Update session metadata with compressed messages
    session1.metadata = {"messages": compressed}
    await repo.upsert(session1)
    logger.info(f"Created session 1 with short messages: {session1_id}")

    # Session 2: Long assistant message (compression)
    session2_id = str(uuid4())
    session2 = Session(
        id=session2_id,
        name=f"test-session-{session2_id}",
        query="Explain neural networks in detail",
        session_type=SessionType.CHAT,
        userid="test-user-1"
    )
    await repo.upsert(session2)

    long_response = """Neural networks are computational models inspired by biological neural networks in animal brains. They consist of interconnected nodes (neurons) organized in layers. Each connection has a weight that adjusts as learning proceeds. The basic architecture includes an input layer, one or more hidden layers, and an output layer. During training, the network learns by adjusting weights through backpropagation, which calculates gradients of a loss function with respect to the weights. This process allows the network to minimize prediction errors. Deep learning uses neural networks with many hidden layers, enabling the model to learn complex hierarchical representations of data. Applications include image recognition, natural language processing, and autonomous vehicles."""

    messages2 = [
        {"role": "user", "content": "Explain neural networks in detail", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": long_response, "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    compressed = await message_store.store_session_messages(session_id=session2_id, messages=messages2, compress=True)

    # Update session metadata with compressed messages
    session2.metadata = {"messages": compressed}
    await repo.upsert(session2)
    logger.info(f"Created session 2 with long assistant message: {session2_id}")

    # Session 3: Multiple exchanges
    session3_id = str(uuid4())
    session3 = Session(
        id=session3_id,
        name=f"test-session-{session3_id}",
        query="Tell me about quantum computing",
        session_type=SessionType.CHAT,
        userid="test-user-2"
    )
    await repo.upsert(session3)

    long_quantum_response = """Quantum computing leverages quantum mechanical phenomena to perform computations. Unlike classical bits that are either 0 or 1, quantum bits (qubits) can exist in superposition, representing both states simultaneously. This property, combined with entanglement, allows quantum computers to process vast amounts of information in parallel. Quantum gates manipulate qubit states to perform operations. Key algorithms include Shor's algorithm for factoring large numbers and Grover's algorithm for searching unsorted databases. Current challenges include maintaining quantum coherence (decoherence), error correction, and scaling to practical qubit counts. Applications span cryptography, drug discovery, optimization problems, and materials science."""

    messages3 = [
        {"role": "user", "content": "Tell me about quantum computing", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": long_quantum_response, "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "user", "content": "How does it differ from classical computing?", "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": "Classical computers use bits (0 or 1) and process sequentially. Quantum computers use qubits that can be in superposition, enabling parallel processing of multiple states simultaneously.", "timestamp": datetime.now(timezone.utc).isoformat()}
    ]

    compressed = await message_store.store_session_messages(session_id=session3_id, messages=messages3, compress=True)

    # Update session metadata with compressed messages
    session3.metadata = {"messages": compressed}
    await repo.upsert(session3)
    logger.info(f"Created session 3 with multiple exchanges: {session3_id}")

    return [session1_id, session2_id, session3_id]


async def test_session_reload(session_ids: list[str]):
    """Test reloading sessions with compressed messages."""

    message_store = SessionMessageStore(tenant_id=TENANT_ID)

    for session_id in session_ids:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing reload for session: {session_id}")
        logger.info(f"{'='*60}")

        # Load with compression (shows REM LOOKUP hints)
        messages_compressed = await message_store.load_session_messages(
            session_id=session_id,
            decompress=False
        )

        logger.info(f"\nCompressed messages ({len(messages_compressed)}):")
        for i, msg in enumerate(messages_compressed):
            content = msg.get("content", "")
            logger.info(f"  [{i}] {msg['role']}: {content[:100]}...")

        # Load with decompression (full content)
        messages_full = await message_store.load_session_messages(
            session_id=session_id,
            decompress=True
        )

        logger.info(f"\nDecompressed messages ({len(messages_full)}):")
        for i, msg in enumerate(messages_full):
            content = msg.get("content", "")
            logger.info(f"  [{i}] {msg['role']}: {content[:100]}... (length: {len(content)})")


async def verify_storage():
    """Verify that assistant responses are stored correctly."""

    logger.info(f"\n{'='*60}")
    logger.info("Verifying assistant response storage")
    logger.info(f"{'='*60}")

    repo = TenantRepository(model_class=Session, tenant_id=TENANT_ID)

    # Find all assistant-chat-response sessions
    responses = await repo.select(
        filters={"session_type": SessionType.ASSISTANT_CHAT_RESPONSE.value},
        limit=100
    )

    logger.info(f"\nFound {len(responses)} stored assistant responses:")
    for resp in responses:
        logger.info(f"  - {resp.name}: {len(resp.query)} chars")
        logger.info(f"    Parent session: {resp.parent_session_id}")
        logger.info(f"    Message index: {resp.metadata.get('message_index')}")


async def main():
    """Run all tests."""

    logger.info("Starting session reload and compression tests")

    # Create test sessions
    logger.info("\n1. Creating test sessions with various message types...")
    session_ids = await create_test_sessions()

    # Test reloading
    logger.info("\n2. Testing session reload with compression/decompression...")
    await test_session_reload(session_ids)

    # Verify storage
    logger.info("\n3. Verifying assistant response storage...")
    await verify_storage()

    logger.info("\n✅ All tests completed successfully")


if __name__ == "__main__":
    asyncio.run(main())
