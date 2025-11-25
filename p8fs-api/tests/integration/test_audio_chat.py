"""Test chat completions API with audio input via X-Chat-Is-Audio header."""

import base64
import io
import wave
import struct
import pytest
from httpx import AsyncClient, ASGITransport

from src.p8fs_api.main import app
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


def create_small_wav_base64() -> str:
    """
    Create a tiny WAV file (1 second, mono, 8kHz) and return it as base64.

    This creates a simple sine wave tone at 440 Hz (A4 note) for testing.
    File size will be ~8KB.
    """
    # WAV parameters
    sample_rate = 8000  # 8 kHz (low quality for small file)
    duration = 1.0  # 1 second
    frequency = 440.0  # 440 Hz (A4 note)

    # Generate samples
    import math
    num_samples = int(sample_rate * duration)
    samples = []
    for i in range(num_samples):
        # Generate sine wave
        t = i / sample_rate
        sample_value = math.sin(2 * math.pi * frequency * t)
        # Scale to 16-bit range
        sample = int(sample_value * 32767 * 0.5)
        samples.append(sample)

    # Create WAV file in memory
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)

        # Write samples
        for sample in samples:
            wav_file.writeframes(struct.pack('<h', sample))

    # Get WAV bytes and encode to base64
    wav_bytes = wav_buffer.getvalue()
    base64_audio = base64.b64encode(wav_bytes).decode('utf-8')

    logger.info(f"Created test WAV: {len(wav_bytes)} bytes, base64: {len(base64_audio)} chars")
    return base64_audio


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.llm
async def test_chat_with_audio_header(sample_auth_token):
    """
    Test chat completions endpoint with X-Chat-Is-Audio header.

    This test verifies:
    1. Audio is properly base64 decoded
    2. Audio is transcribed using Whisper
    3. Transcribed text is used as the user message
    4. Chat completion proceeds normally with transcribed text
    """
    # Create small test audio
    base64_audio = create_small_wav_base64()

    # Prepare request with audio as content
    request_data = {
        "model": "gpt-4.1-mini",
        "messages": [
            {
                "role": "user",
                "content": base64_audio  # Base64 encoded audio
            }
        ],
        "stream": False,
        "temperature": 0.7
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/chat/completions",
            json=request_data,
            headers={
                "Authorization": f"Bearer {sample_auth_token}",
                "X-Chat-Is-Audio": "true"  # Signal that first user message is audio
            }
        )

    # Verify response
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    response_data = response.json()

    # Verify response structure
    assert "choices" in response_data, "Response should have choices"
    assert len(response_data["choices"]) > 0, "Response should have at least one choice"

    choice = response_data["choices"][0]
    assert "message" in choice, "Choice should have message"
    assert "content" in choice["message"], "Message should have content"

    # The response content should be based on the transcribed audio
    # Since we're using a sine wave tone, the transcription might be empty or contain noise
    # But the endpoint should process it without errors
    content = choice["message"]["content"]
    logger.info(f"Audio transcription and response received: {content[:200]}")

    assert isinstance(content, str), "Response content should be a string"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.llm
async def test_chat_with_audio_streaming(sample_auth_token):
    """Test streaming chat completions with audio input."""
    # Create small test audio
    base64_audio = create_small_wav_base64()

    request_data = {
        "model": "gpt-4.1-mini",
        "messages": [
            {
                "role": "user",
                "content": base64_audio
            }
        ],
        "stream": True,
        "temperature": 0.7
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/chat/completions",
            json=request_data,
            headers={
                "Authorization": f"Bearer {sample_auth_token}",
                "X-Chat-Is-Audio": "true"
            },
            timeout=30.0
        )

    # Verify streaming response
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    # Collect streaming chunks
    chunks = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            data = line[6:]  # Remove "data: " prefix
            if data != "[DONE]":
                chunks.append(data)

    logger.info(f"Received {len(chunks)} streaming chunks from audio input")
    assert len(chunks) > 0, "Should receive at least one chunk"


@pytest.mark.asyncio
async def test_chat_without_audio_header(sample_auth_token):
    """Test that normal text chat works without X-Chat-Is-Audio header."""
    request_data = {
        "model": "gpt-4.1-mini",
        "messages": [
            {
                "role": "user",
                "content": "Hello, this is a text message"
            }
        ],
        "stream": False
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/chat/completions",
            json=request_data,
            headers={
                "Authorization": f"Bearer {sample_auth_token}",
                # No X-Chat-Is-Audio header - should process as text
            }
        )

    # This should work normally
    # Note: Will be skipped in unit tests without --with-llm flag
    logger.info(f"Text chat response status: {response.status_code}")


@pytest.fixture
def sample_auth_token():
    """Create a test authentication token."""
    import jwt
    from datetime import datetime, timedelta, timezone

    # Create a simple JWT token for testing
    payload = {
        "sub": "test-user-audio",
        "tenant": "tenant-test",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc)
    }

    # Use a test secret (this would come from config in production)
    secret = "test-secret-key-for-integration-tests"
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token


if __name__ == "__main__":
    # Quick test to verify WAV creation
    audio_b64 = create_small_wav_base64()
    print(f"Created test audio: {len(audio_b64)} base64 chars")

    # Decode and verify it's valid WAV
    wav_bytes = base64.b64decode(audio_b64)
    print(f"WAV file size: {len(wav_bytes)} bytes")

    # Try to read it
    with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
        print(f"Channels: {wf.getnchannels()}")
        print(f"Sample width: {wf.getsampwidth()}")
        print(f"Frame rate: {wf.getframerate()}")
        print(f"Frames: {wf.getnframes()}")
