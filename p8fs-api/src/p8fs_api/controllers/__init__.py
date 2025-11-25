"""Controllers package."""

from .auth_controller import AuthController
from .rem_query_controller import REMQueryController

# Use simple controller for testing without dependencies
try:
    from .chat_controller import ChatController
except ImportError:
    from .chat_controller_simple import ChatController

__all__ = ["AuthController", "ChatController", "REMQueryController"]