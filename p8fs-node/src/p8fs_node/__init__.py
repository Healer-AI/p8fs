"""P8FS Node - Core processing unit for content handling and embeddings."""

__version__ = "0.1.0"

from .models import (
    ContentChunk,
    ContentMetadata,
    ContentProcessingResult,
    ContentType,
)
from .providers import (
    ContentProvider,
    auto_register,
    get_content_provider,
    list_content_providers,
    list_supported_content_types,
    register_content_provider,
)

__all__ = [
    # Version
    "__version__",
    # Models
    "ContentType",
    "ContentChunk",
    "ContentMetadata", 
    "ContentProcessingResult",
    # Providers
    "ContentProvider",
    "auto_register",
    "register_content_provider",
    "get_content_provider",
    "list_content_providers",
    "list_supported_content_types",
]