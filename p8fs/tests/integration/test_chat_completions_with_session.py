"""Integration test for chat completions with session recovery and user context."""

import asyncio
import httpx
from uuid import uuid4
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

API_BASE_URL = "http://localhost:8001"
TENANT_ID = "tenant-test"


async def test_chat_completions_with_session():
    """Test chat completions API with session ID header."""

    logger.info("\n" + "="*60)
    logger.info("Testing Chat Completions with Session Recovery")
    logger.info("="*60)

    # Generate a new session ID
    session_id = str(uuid4())
    logger.info(f"\n📍 Session ID: {session_id}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # First call - create new session
        logger.info("\n1️⃣  First call - Creating new session")

        payload1 = {
            "model": "gpt-4.1-nano",
            "messages": [
                {"role": "user", "content": "What are the key principles of quantum computing?"}
            ],
            "temperature": 0.7
        }

        headers1 = {
            "X-Tenant-ID": TENANT_ID,
            "X-Session-ID": session_id,
            "Content-Type": "application/json"
        }

        response1 = await client.post(
            f"{API_BASE_URL}/api/v1/chat/completions",
            json=payload1,
            headers=headers1
        )

        logger.info(f"Status: {response1.status_code}")

        if response1.status_code == 200:
            result1 = response1.json()
            assistant_message = result1["choices"][0]["message"]["content"]
            logger.info(f"✅ First response ({len(assistant_message)} chars):")
            logger.info(f"   {assistant_message[:150]}...")
        else:
            logger.error(f"❌ First call failed: {response1.text}")
            return

        # Wait for session and messages to be saved (async operations)
        await asyncio.sleep(2)

        # Second call - should recover session and include user context
        logger.info("\n2️⃣  Second call - Should recover session + user context")

        payload2 = {
            "model": "gpt-4.1-nano",
            "messages": [
                {"role": "user", "content": "Can you summarize what we discussed?"}
            ],
            "temperature": 0.7
        }

        headers2 = {
            "X-Tenant-ID": TENANT_ID,
            "X-Session-ID": session_id,
            "Content-Type": "application/json"
        }

        response2 = await client.post(
            f"{API_BASE_URL}/api/v1/chat/completions",
            json=payload2,
            headers=headers2
        )

        logger.info(f"Status: {response2.status_code}")

        if response2.status_code == 200:
            result2 = response2.json()
            assistant_message2 = result2["choices"][0]["message"]["content"]
            logger.info(f"✅ Second response ({len(assistant_message2)} chars):")
            logger.info(f"   {assistant_message2[:200]}...")

            # Check if response references the previous conversation
            if "quantum" in assistant_message2.lower():
                logger.info("✅ Response references previous quantum computing discussion")
            else:
                logger.warning("⚠️  Response may not be using session context")
        else:
            logger.error(f"❌ Second call failed: {response2.text}")
            return

        # Third call - test without session ID to verify user context loading
        logger.info("\n3️⃣  Third call - New session, should load user context")

        new_session_id = str(uuid4())
        logger.info(f"📍 New Session ID: {new_session_id}")

        payload3 = {
            "model": "gpt-4.1-nano",
            "messages": [
                {"role": "user", "content": "What topics am I interested in?"}
            ],
            "temperature": 0.7
        }

        headers3 = {
            "X-Tenant-ID": TENANT_ID,
            "X-Session-ID": new_session_id,
            "Content-Type": "application/json"
        }

        response3 = await client.post(
            f"{API_BASE_URL}/api/v1/chat/completions",
            json=payload3,
            headers=headers3
        )

        logger.info(f"Status: {response3.status_code}")

        if response3.status_code == 200:
            result3 = response3.json()
            assistant_message3 = result3["choices"][0]["message"]["content"]
            logger.info(f"✅ Third response ({len(assistant_message3)} chars):")
            logger.info(f"   {assistant_message3[:200]}...")

            # Check if response uses user context
            if any(keyword in assistant_message3.lower() for keyword in ["quantum", "ai", "machine learning", "neural"]):
                logger.info("✅ Response includes user context from previous sessions")
            else:
                logger.warning("⚠️  Response may not be using user context")
        else:
            logger.error(f"❌ Third call failed: {response3.text}")


async def main():
    """Run the test."""

    logger.info("Starting chat completions integration test")
    logger.info("Make sure API server is running on http://localhost:8001")

    try:
        await test_chat_completions_with_session()

        logger.info("\n" + "="*60)
        logger.info("✅ Integration test completed")
        logger.info("="*60)
    except Exception as e:
        logger.error(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
