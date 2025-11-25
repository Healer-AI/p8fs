"""CORS middleware configuration."""

from fastapi.middleware.cors import CORSMiddleware
from p8fs_cluster.config.settings import config


def setup_cors(app):
    """Configure CORS middleware."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,  # Use default from centralized config
        allow_methods=["*"],     # Use default from centralized config
        allow_headers=["*"],     # Use default from centralized config
    )