"""
Simulation utilities for testing and demos.

These utilities generate mock responses instead of calling real LLMs,
useful for testing, demos, and development.
"""

import json
import uuid
import asyncio
from typing import AsyncGenerator, Any
from datetime import datetime


async def build_simulation_response(question: str, model: str) -> dict[str, Any]:
    """
    Build a complete simulation response for non-streaming mode.
    
    Args:
        question: The user's question
        model: The model name to simulate
        
    Returns:
        OpenAI-compatible chat completion response
    """
    # Generate simulated content based on question
    content = _generate_simulation_content(question)
    
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": len(question.split()),
            "completion_tokens": len(content.split()),
            "total_tokens": len(question.split()) + len(content.split())
        }
    }


async def stream_simulation_response(question: str, model: str) -> AsyncGenerator[str, None]:
    """
    Stream a simulation response for streaming mode.
    
    Args:
        question: The user's question
        model: The model name to simulate
        
    Yields:
        JSON strings representing streaming chunks
    """
    content = _generate_simulation_content(question)
    words = content.split()
    
    # Initial chunk
    yield json.dumps({
        "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
        "object": "chat.completion.chunk",
        "created": int(datetime.now().timestamp()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None
            }
        ]
    })
    
    # Stream words with slight delay
    for i, word in enumerate(words):
        await asyncio.sleep(0.05)  # Simulate streaming delay
        
        chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
            "object": "chat.completion.chunk", 
            "created": int(datetime.now().timestamp()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": f"{word} " if i < len(words) - 1 else word},
                    "finish_reason": None
                }
            ]
        }
        yield json.dumps(chunk)
    
    # Final chunk with finish reason
    yield json.dumps({
        "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
        "object": "chat.completion.chunk",
        "created": int(datetime.now().timestamp()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }
        ]
    })


def _generate_simulation_content(question: str) -> str:
    """Generate simulated response content based on the question."""
    question_lower = question.lower()
    
    # Simple pattern matching for different response types
    if any(word in question_lower for word in ["hello", "hi", "hey"]):
        return "Hello! I'm a simulated AI assistant. How can I help you today?"
    
    elif any(word in question_lower for word in ["code", "program", "function"]):
        return """Here's a simple Python example:

                ```python
                def greet(name):
                    return f"Hello, {name}!"

                # Usage
                message = greet("World")
                print(message)
                ```

This function demonstrates basic string formatting in Python."""
    
    elif any(word in question_lower for word in ["table", "data", "comparison"]):
        return """Here's a comparison table:

                | Feature | Option A | Option B |
                |---------|----------|----------|
                | Speed   | Fast     | Moderate |
                | Cost    | High     | Low      |
                | Quality | Excellent| Good     |

                This table shows the key differences between the options."""
    
    elif any(word in question_lower for word in ["list", "steps", "how to"]):
        return """Here are the key steps:

                    1. **Planning Phase**: Define your objectives clearly
                    2. **Implementation Phase**: Execute your plan systematically
                    3. **Testing Phase**: Verify everything works as expected
                    4. **Deployment Phase**: Launch and monitor the results

                    Each phase is important for successful completion."""
    
    else:
        return f"Thank you for your question about '{question}'. This is a simulated response generated for testing purposes. In a real system, this would be processed by an actual language model."