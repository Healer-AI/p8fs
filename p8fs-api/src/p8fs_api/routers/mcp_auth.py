"""MCP (Model Context Protocol) Authentication Router.

This module provides MCP-specific authentication endpoints that complement the main
OAuth 2.1 implementation in auth.py. It focuses on MCP client discovery and
authentication status reporting.

MCP Specification Reference:
https://modelcontextprotocol.io/specification/draft/basic/authorization

Purpose:
MCP clients (like Claude Desktop, VS Code extensions) need to discover OAuth
endpoints and understand authentication requirements. This router provides:

1. Authentication Status Endpoints
   - /api/mcp/auth/info - For authenticated clients to get current status
   - /api/mcp/auth/login-required - For unauthenticated clients to get instructions

2. Discovery Endpoints
   - /api/mcp/auth/discovery - OAuth configuration for MCP clients
   - /api/mcp/.well-known/openid_configuration - Redirects to main discovery

3. Legacy Support
   - /api/mcp/auth/qr-login - Redirects to standard device flow

Key Differences from Standard OAuth:
- Returns structured login instructions for MCP clients
- Provides both authenticated and unauthenticated discovery paths
- Includes MCP-specific metadata in responses

Integration:
All actual OAuth operations (token issuance, device flow, etc.) are handled by
the main auth.py router. This router provides the MCP-specific wrapper and
discovery layer that MCP clients expect.

Authentication Flow for MCP Clients:
1. Client calls /api/mcp/auth/login-required to discover OAuth endpoints
2. Client initiates device flow via /api/v1/oauth/device_authorization
3. User approves via QR code on mobile device
4. Client polls /api/v1/oauth/token until approval
5. Client uses bearer token for subsequent MCP operations
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic import BaseModel

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from ..middleware import User, get_current_user
from ..controllers.auth_controller import AuthController
from fastapi.responses import RedirectResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["MCP Authentication"])

# Setup Jinja2 templates
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))



class MCPLoginInfo(BaseModel):
    """MCP login information with OAuth discovery."""
    authenticated: bool
    user: User | None = None
    oauth_discovery: Dict[str, Any]
    login_instructions: Dict[str, Any]


class OAuthDiscovery(BaseModel):
    """OAuth 2.1 discovery document."""
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    device_authorization_endpoint: str
    jwks_uri: str
    response_types_supported: list[str]
    grant_types_supported: list[str]
    subject_types_supported: list[str]
    id_token_signing_alg_values_supported: list[str]
    scopes_supported: list[str]
    code_challenge_methods_supported: list[str]


async def _get_oauth_discovery(request: Request) -> Dict[str, Any]:
    """Get OAuth discovery from core auth controller."""
    auth_controller = AuthController()
    return await auth_controller.get_oauth_discovery(request)


def _build_login_instructions(oauth_discovery: Dict[str, Any]) -> Dict[str, Any]:
    """Build detailed login instructions for MCP clients.
    
    MCP Pattern: Client Education
    MCP clients need explicit instructions on how to authenticate since they
    operate in various environments (CLI, desktop apps, VS Code, etc.).
    
    This provides:
    - Recommended authentication method (device flow)
    - Step-by-step API calls with exact parameters
    - Example requests and expected responses
    - How to construct bearer token headers
    
    The device flow is recommended because:
    - No redirect URI needed (works in any environment)
    - User-friendly with QR codes
    - Secure without client secrets
    """
    return {
        "method": "oauth2_device_flow",
        "description": "P8FS uses OAuth 2.1 Device Authorization Flow for secure MCP authentication",
        "instructions": [
            "1. Make a POST request to the device_authorization_endpoint",
            "2. Display the user_code to the user",
            "3. Show the QR code or direct user to verification_uri", 
            "4. Poll the token_endpoint with device_code until authentication completes",
            "5. Use the access_token in Authorization header for MCP requests"
        ],
        "client_registration": {
            "client_id": "mcp_client",
            "client_type": "public",
            "description": "Use 'mcp_client' as the client_id for MCP authentication"
        },
        "example_flow": {
            "step1_device_auth": {
                "method": "POST",
                "url": oauth_discovery["device_authorization_endpoint"],
                "headers": {"Content-Type": "application/x-www-form-urlencoded"},
                "body": "client_id=mcp_client&scope=read write"
            },
            "step2_token_poll": {
                "method": "POST", 
                "url": oauth_discovery["token_endpoint"],
                "headers": {"Content-Type": "application/x-www-form-urlencoded"},
                "body": "grant_type=urn:ietf:params:oauth:grant-type:device_code&client_id=mcp_client&device_code={device_code}"
            },
            "step3_mcp_request": {
                "method": "POST",
                "url": "/api/mcp/{method}",
                "headers": {"Authorization": "Bearer {access_token}"}
            }
        },
        "qr_code_generation": {
            "description": "Generate QR code from verification_uri_complete for easy mobile login",
            "format": "verification_uri_complete should be encoded as QR code",
            "mobile_flow": "User scans QR code, approves on mobile, desktop gets token"
        }
    }


@router.get("/auth/info")
async def get_auth_info(
    request: Request,
    user: User = Depends(get_current_user)
) -> MCPLoginInfo:
    """Authentication status for authenticated MCP clients.
    
    MCP Pattern: Authenticated Discovery
    This endpoint is called by MCP clients that already have a bearer token
    to understand the current authentication context and available operations.
    
    Returns:
    - authenticated: Always true (endpoint requires auth)
    - user: Current user details including tenant and device info
    - oauth_discovery: Full OAuth endpoint configuration
    - login_instructions: How to authenticate other clients
    
    This helps MCP clients understand:
    - Who is currently authenticated
    - How to authenticate additional clients/devices
    - Available OAuth endpoints and capabilities
    """
    oauth_discovery = await _get_oauth_discovery(request)
    login_instructions = _build_login_instructions(oauth_discovery)
    
    return MCPLoginInfo(
        authenticated=True,
        user=user,
        oauth_discovery=oauth_discovery,
        login_instructions=login_instructions
    )


@router.get("/auth/discovery") 
async def get_oauth_discovery(request: Request) -> Dict[str, Any]:
    """OAuth discovery endpoint for MCP clients.
    
    MCP Specification: Authorization Server Discovery
    This provides OAuth configuration without requiring authentication,
    allowing MCP clients to bootstrap the authentication process.
    
    Equivalent to /.well-known/openid-configuration but under MCP namespace.
    Returns the same discovery document with all OAuth endpoints.
    """
    return await _get_oauth_discovery(request)


@router.get("/auth/login-required")
async def login_required(request: Request) -> MCPLoginInfo:
    """Authentication instructions for unauthenticated MCP clients.
    
    MCP Pattern: Unauthenticated Discovery
    This is typically the first endpoint an MCP client calls when it needs
    to authenticate. It provides everything needed to start the auth flow.
    
    Returns:
    - authenticated: Always false (no auth required for this endpoint)
    - user: Always null
    - oauth_discovery: Complete OAuth endpoint configuration
    - login_instructions: Step-by-step guide for device flow authentication
    
    The login_instructions include:
    - Which OAuth flow to use (device flow recommended)
    - Example requests for each step
    - How to poll for completion
    - How to use the resulting bearer token
    """
    oauth_discovery = await _get_oauth_discovery(request)
    login_instructions = _build_login_instructions(oauth_discovery)
    
    return MCPLoginInfo(
        authenticated=False,
        user=None,
        oauth_discovery=oauth_discovery,
        login_instructions=login_instructions
    )


# Removed /auth/qr-login endpoint - MCP clients should use standard OAuth flow:
# 1. POST /api/v1/oauth/device_authorization to get device code
# 2. Direct user to /api/v1/oauth/device for QR code
# 3. Poll /api/v1/oauth/token for completion




# Removed - duplicate of main OAuth router's discovery endpoint
# MCP clients should use /api/v1/oauth/.well-known/openid-configuration directly
# or /api/mcp/auth/discovery for MCP-namespaced access