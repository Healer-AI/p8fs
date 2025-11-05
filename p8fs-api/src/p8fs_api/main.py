"""P8FS API main application."""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging.setup import get_logger, setup_service_logging

from . import __version__
from .middleware import setup_cors, setup_rate_limiting, setup_request_context
from .models import ErrorResponse
from .routers import (
    dev_auth_router,
    health_router,
    icons_router,
    mcp_auth_router,
    moments_router,
    protected_auth_router,
    protected_chat_router,
    public_auth_router,
    public_chat_router,
)

# Setup logging for API service
setup_service_logging("p8fs-api")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting P8FS API", version=__version__)
    
    # Initialize repository for p8fs-auth
    from p8fs_auth.models.repository import set_repository

    from .repositories.auth_repository import P8FSAuthRepository
    
    logger.info("Initializing auth repository")
    auth_repo = P8FSAuthRepository()
    set_repository(auth_repo)
    
    # TODO: Initialize other service connections
    # - p8fs-node client
    # - Observability setup
    
    yield
    
    # Shutdown
    logger.info("Shutting down P8FS API")
    # TODO: Cleanup connections


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    
    # Create MCP app early to get its lifespan
    mcp_app = None
    try:
        from .routers.mcp_server import create_secure_mcp_server
        mcp = create_secure_mcp_server()
        mcp_app = mcp.http_app()
    except Exception as e:
        logger.error(f"Error creating MCP server: {e}")
    
    # Combine lifespans if MCP app was created successfully
    if mcp_app:
        @asynccontextmanager
        async def combined_lifespan(app: FastAPI):
            async with lifespan(app):
                async with mcp_app.lifespan(mcp_app):
                    yield
        app_lifespan = combined_lifespan
    else:
        app_lifespan = lifespan
    
    app = FastAPI(
        title="P8FS API",
        description="REST API, CLI, and MCP interfaces for the P8FS smart content management system",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=app_lifespan
    )
    
    # Security middleware
    app.add_middleware(
        TrustedHostMiddleware, 
        allowed_hosts=["*"] if config.debug else ["localhost", "127.0.0.1", "*.p8fs.com", "testserver"]
    )
    
    # CORS middleware
    setup_cors(app)

    # Rate limiting middleware
    setup_rate_limiting(app)

    # Request context middleware (for X-Moment-Id, etc.)
    setup_request_context(app)
    
    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        # Skip logging for health check endpoints
        if request.url.path in ["/health", "/health/ready", "/health/live"]:
            return await call_next(request)

        start_time = time.time()

        # Generate request ID
        request_id = f"req_{int(time.time() * 1000000)}"

        # Add request context
        logger.info(
            "Request started",
            method=request.method,
            url=str(request.url),
            client_ip=request.client.host if request.client else None,
            request_id=request_id
        )

        try:
            response = await call_next(request)

            process_time = time.time() - start_time
            logger.info(
                "Request completed",
                status_code=response.status_code,
                process_time=round(process_time, 4),
                request_id=request_id
            )

            # Add response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(round(process_time, 4))

            return response

        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                "Request failed",
                error=str(e),
                process_time=round(process_time, 4),
                exc_info=True,
                request_id=request_id
            )
            raise
    
    # Security headers middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        if not config.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response
    
    # Exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=f"http_error_{exc.status_code}",
                message=exc.detail,
                request_id=getattr(request.state, 'request_id', None)
            ).model_dump()
        )
    
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        logger.error("Validation error", error=str(exc))
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error="validation_error",
                message=str(exc),
                request_id=getattr(request.state, 'request_id', None)
            ).model_dump()
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Internal server error: {exc}", exc_info=True)
        
        # In debug mode, include the actual error details
        if config.debug:
            error_details = {
                "type": type(exc).__name__,
                "message": str(exc),
                "path": str(request.url.path)
            }
            message = f"{type(exc).__name__}: {str(exc)}"
        else:
            error_details = None
            message = "An unexpected error occurred"
            
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="internal_server_error",
                message=message,
                details=error_details,
                request_id=getattr(request.state, 'request_id', None)
            ).model_dump()
        )
    
    # Include routers with clear JWT protection levels
    
    # Public routers (no JWT auth required)
    app.include_router(health_router)                    # Health endpoints
    app.include_router(public_auth_router)              # OAuth token exchange, device registration
    app.include_router(public_chat_router, prefix="/api")  # Model listing endpoints (/api/v1/models)
    app.include_router(dev_auth_router)                 # Dev endpoints (dev token auth)
    app.include_router(mcp_auth_router)                 # MCP OAuth discovery endpoints
    app.include_router(icons_router)                    # Icon serving for email templates
    
    # Protected routers (JWT auth required at router level)
    app.include_router(protected_auth_router)           # OAuth authorize, userinfo
    app.include_router(protected_chat_router, prefix="/api")  # Chat completions, agent endpoints
    app.include_router(moments_router)                  # Moments entity endpoints
    # Mount MCP server if it was created successfully
    if mcp_app:
        # Mount at /api so the MCP server is accessible at /api/mcp
        app.mount("/api", mcp_app)
        logger.info("FastMCP server mounted successfully at /api (accessible at /api/mcp)")
    else:
        logger.warning("MCP server not mounted due to initialization error")
    
    # Root-level OAuth discovery endpoints (standard location)
    # Excluded from OpenAPI schema to avoid duplicates with /oauth/* endpoints
    @app.get("/.well-known/openid-configuration", include_in_schema=False)
    async def root_openid_configuration(request: Request):
        """OpenID Connect discovery document at standard location."""
        from .controllers.auth_controller import AuthController
        auth_controller = AuthController()
        return await auth_controller.get_oauth_discovery(request)

    @app.get("/.well-known/oauth-authorization-server", include_in_schema=False)
    async def root_oauth_authorization_server(request: Request):
        """OAuth 2.1 authorization server metadata at root level."""
        from .controllers.auth_controller import AuthController
        auth_controller = AuthController()
        return await auth_controller.get_oauth_discovery(request)

    @app.get("/.well-known/jwks.json", include_in_schema=False)
    async def root_jwks():
        """JSON Web Key Set at standard location."""
        from p8fs_auth.services.jwt_key_manager import JWTKeyManager
        jwt_manager = JWTKeyManager()
        return jwt_manager.get_jwks()

    @app.post("/register", include_in_schema=False)
    async def root_register_client(request: Request):
        """OAuth 2.1 dynamic client registration at root level."""
        # Get registration data from request body
        registration_data = await request.json()
        
        # Default client registration response for MCP clients
        client_id = registration_data.get("client_name", "mcp_client")
        
        # Build response with only non-null fields
        response = {
            "client_id": client_id,
            "client_secret": "",  # Empty string for public client
            "client_id_issued_at": 1732320000,
            "client_secret_expires_at": 0,  # Never expires
            "redirect_uris": registration_data.get("redirect_uris", []),
            "grant_types": ["authorization_code", "refresh_token", "urn:ietf:params:oauth:grant-type:device_code"],
            "response_types": ["code"],
            "client_name": registration_data.get("client_name", "MCP Client"),
            "scope": registration_data.get("scope", "read write"),
            "contacts": registration_data.get("contacts", []),
            "token_endpoint_auth_method": "none",  # Public client
        }
        
        # Add optional fields only if provided
        if "client_uri" in registration_data:
            response["client_uri"] = registration_data["client_uri"]
        if "logo_uri" in registration_data:
            response["logo_uri"] = registration_data["logo_uri"]
        if "tos_uri" in registration_data:
            response["tos_uri"] = registration_data["tos_uri"]
        if "policy_uri" in registration_data:
            response["policy_uri"] = registration_data["policy_uri"]
        if "software_id" in registration_data:
            response["software_id"] = registration_data["software_id"]
        if "software_version" in registration_data:
            response["software_version"] = registration_data["software_version"]
            
        return response
    
    # Root endpoint
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name": "P8FS API",
            "version": __version__,
            "description": "REST API, CLI, and MCP interfaces for P8FS",
            "docs": "/docs",
            "health": "/health"
        }
    
    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.debug,  # Use debug flag instead of separate reload flag
        log_level=config.log_level.lower()
    )