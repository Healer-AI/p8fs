"""OpenAPI service package for P8FS

This package provides OpenAPI specification parsing and REST API invocation
capabilities for the P8FS system. It includes:

- OpenApiService: Main service for invoking REST APIs
- OpenApiSpec: Parser for OpenAPI specifications
- ApiTokenCache: KV-based token storage
- map_openapi_to_function: Utility for converting OpenAPI specs to function definitions

The service integrates with P8FS's KV store for token management and can
store Function entities for use with the LLM system.
"""

from .cache import ApiTokenCache, get_token_cache, set_token_cache
from .service import OpenApiService, OpenApiServiceFactory
from .spec import OpenApiSpec
from .utils import generate_short_name, map_openapi_to_function, normalize_operation_id

__all__ = [
    "OpenApiService",
    "OpenApiServiceFactory",
    "OpenApiSpec",
    "ApiTokenCache",
    "get_token_cache",
    "set_token_cache",
    "map_openapi_to_function",
    "normalize_operation_id",
    "generate_short_name",
]