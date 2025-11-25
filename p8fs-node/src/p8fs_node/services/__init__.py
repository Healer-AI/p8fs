"""Services module for p8fs-node."""

from .embeddings import get_embedding_service

__all__ = [
    "get_embedding_service",
]