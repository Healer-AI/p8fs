"""Routers package."""

from .admin import router as admin_router
from .auth import dev_router as dev_auth_router
from .auth import protected_router as protected_auth_router
from .auth import public_router as public_auth_router
from .chat import protected_router as protected_chat_router
from .chat import public_router as public_chat_router
from .entity.moments import router as moments_router
from .files import router as files_router
from .health import router as health_router
from .icons import router as icons_router
from .mcp_auth import router as mcp_auth_router
from .rem_query import router as rem_query_router
from .slack import router as slack_router

# MCP server is now mounted directly using FastMCP with authentication

__all__ = [
    "admin_router",
    "public_auth_router",
    "protected_auth_router",
    "dev_auth_router",
    "protected_chat_router",
    "public_chat_router",
    "health_router",
    "mcp_auth_router",
    "moments_router",
    "files_router",
    "icons_router",
    "rem_query_router",
    "slack_router",
]