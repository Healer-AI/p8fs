"""Content processor delegation system."""

from .document_processor import DocumentProcessor, ProcessorRegistry

__all__ = ["DocumentProcessor", "ProcessorRegistry"]