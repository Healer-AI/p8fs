"""
Simple chat controller for testing.
"""

from typing import Optional, AsyncGenerator, Dict, Any
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class ChatController:
    """Simple chat controller that delegates to the router."""
    
    def __init__(self):
        """Initialize chat controller."""
        logger.info("Initialized simple ChatController")
    
    async def chat_completion(
        self,
        messages: list[dict],
        model: str = "gpt-4",
        stream: bool = False,
        **kwargs
    ) -> AsyncGenerator[str, None] | dict:
        """
        Handle chat completion requests.
        
        This is a placeholder that the router can use or ignore.
        The actual logic is in the router.
        """
        if stream:
            async def generate():
                yield '{"message": "This is handled by the router"}'
            return generate()
        else:
            return {"message": "This is handled by the router"}
    
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a chat request."""
        return {"status": "processed", "request": request}