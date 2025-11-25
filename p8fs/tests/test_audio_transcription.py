"""Test audio transcription using OpenAI Whisper API (lightweight, no p8fs-node)."""

import asyncio
import base64
from pathlib import Path

from p8fs.services.llm import MemoryProxy


async def test_audio_transcription():
    """Test that audio transcription works with OpenAI Whisper API."""

    # Create a simple test audio file (1 second of silence as WAV)
    # WAV header for 1 second of silence at 16kHz mono
    wav_header = bytes([
        0x52, 0x49, 0x46, 0x46,  # "RIFF"
        0x24, 0x7D, 0x00, 0x00,  # File size - 8
        0x57, 0x41, 0x56, 0x45,  # "WAVE"
        0x66, 0x6D, 0x74, 0x20,  # "fmt "
        0x10, 0x00, 0x00, 0x00,  # Subchunk size
        0x01, 0x00,              # Audio format (PCM)
        0x01, 0x00,              # Num channels (mono)
        0x80, 0x3E, 0x00, 0x00,  # Sample rate (16000)
        0x00, 0x7D, 0x00, 0x00,  # Byte rate
        0x02, 0x00,              # Block align
        0x10, 0x00,              # Bits per sample
        0x64, 0x61, 0x74, 0x61,  # "data"
        0x00, 0x7D, 0x00, 0x00,  # Data size
    ])
    # Add 1 second of silence (16000 samples * 2 bytes = 32000 bytes)
    silence = bytes([0x00] * 32000)
    test_audio = wav_header + silence

    # Convert to base64
    base64_audio = base64.b64encode(test_audio).decode('utf-8')

    print(f"\n{'=' * 80}")
    print("TESTING AUDIO TRANSCRIPTION (OpenAI Whisper API)")
    print(f"{'=' * 80}\n")

    # Create a test message with audio
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": base64_audio}
    ]

    print("✓ Created test audio file (1 second of silence)")
    print(f"✓ Base64 encoded: {len(base64_audio)} characters\n")

    # Initialize MemoryProxy
    proxy = MemoryProxy()

    try:
        # Process audio messages
        print("Processing audio transcription...")
        processed_messages = await proxy.process_audio_messages(messages, has_audio=True)

        print("✅ Audio transcription completed successfully!\n")
        print("Processed messages:")
        for i, msg in enumerate(processed_messages):
            print(f"  {i+1}. {msg['role']}: {msg['content'][:100]}...")

        print(f"\n{'=' * 80}")
        print("SUCCESS: Audio transcription uses OpenAI Whisper API (no p8fs-node required)")
        print(f"{'=' * 80}\n")

        return True

    except ValueError as e:
        if "p8fs-node" in str(e):
            print(f"❌ FAILED: Still trying to import p8fs-node")
            print(f"   Error: {e}\n")
            return False
        else:
            print(f"❌ FAILED: {e}\n")
            return False
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_audio_transcription())
    exit(0 if success else 1)
