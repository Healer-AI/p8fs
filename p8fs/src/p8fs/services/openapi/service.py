"""OpenAPI service for P8FS

This module provides the main OpenApiService class for invoking REST APIs
from Function entities stored in the P8FS KV store. The service can also
load and manage Function entities through an internal FunctionManager.
"""

from typing import TYPE_CHECKING, Any, Optional

import requests

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
from io import BytesIO

from p8fs_cluster.logging import get_logger
from p8fs.models.p8 import Function

from .cache import ApiTokenCache, get_token_cache
from .spec import OpenApiSpec

if TYPE_CHECKING:
    from p8fs.repository.BaseRepository import BaseRepository

    from .manager import FunctionManager

logger = get_logger(__name__)


class OpenApiService:
    """Service for invoking REST APIs from Function entities

    This service can invoke REST API endpoints defined in Function entities
    that are stored in the P8FS KV store. It handles authentication, request
    formatting, and response parsing.
    """

    def __init__(
        self,
        uri: str,
        token_or_key: str | None = None,
        spec: OpenApiSpec | None = None,
        token_cache: ApiTokenCache | None = None,
        repository: Optional["BaseRepository"] = None,
    ):
        """Initialize OpenAPI service

        Args:
            uri: Base URI for the API
            token_or_key: API token or key for authentication
            spec: Optional OpenApiSpec instance
            token_cache: Optional ApiTokenCache instance
            repository: Optional repository for Function management
        """
        self.uri = uri.rstrip("/")
        self.spec = spec
        self.token_cache = token_cache or get_token_cache()
        self.repository = repository
        self._function_manager: FunctionManager | None = None

        # Try to get token from cache if not provided
        if token_or_key:
            self.token = token_or_key
        elif self.token_cache:
            # This will be resolved asynchronously in invoke method
            self.token = None
        else:
            self.token = None

    async def _get_token(self) -> str | None:
        """Get API token from cache or direct assignment

        Returns:
            API token if available
        """
        if self.token:
            return self.token

        if self.token_cache:
            return await self.token_cache.get(self.uri)

        return None

    def _get_function_manager(self) -> "FunctionManager":
        """Get or create FunctionManager instance

        Returns:
            FunctionManager instance

        Raises:
            ValueError: If no repository is available
        """
        if self._function_manager is None:
            if self.repository is None:
                raise ValueError("Cannot create FunctionManager without repository")

            # Import here to avoid circular dependencies
            from .manager import FunctionManager

            self._function_manager = FunctionManager(self.repository)

        return self._function_manager

    async def register_api_from_spec(
        self,
        spec_uri: str,
        token: str | None = None,
        name: str | None = None,
        verbs: list[str] | None = None,
        filter_ops: list[str] | None = None,
    ) -> list[Function]:
        """Register API functions from OpenAPI specification

        Args:
            spec_uri: URI to OpenAPI specification
            token: Optional API token
            name: Optional friendly name for the API
            verbs: HTTP verbs to include (default: all)
            filter_ops: Operation IDs to include (default: all)

        Returns:
            List of registered Function entities
        """
        manager = self._get_function_manager()
        return await manager.register_api_from_spec(
            spec_uri=spec_uri,
            token=token,
            name=name,
            verbs=verbs,
            filter_ops=filter_ops,
        )

    async def list_functions(
        self, proxy_uri: str | None = None
    ) -> list[dict[str, Any]]:
        """List available functions

        Args:
            proxy_uri: Optional filter by proxy URI

        Returns:
            List of function summaries
        """
        manager = self._get_function_manager()
        return await manager.list_functions(proxy_uri)

    async def search_functions(self, query: str) -> list[Function]:
        """Search functions by description

        Args:
            query: Search query

        Returns:
            List of matching Function entities
        """
        manager = self._get_function_manager()
        return await manager.search_functions(query)

    async def get_function(self, name: str) -> Function | None:
        """Get Function entity by name

        Args:
            name: Function name

        Returns:
            Function entity or None if not found
        """
        manager = self._get_function_manager()
        return await manager.get_function(name)

    async def invoke_function(
        self, name: str, request_body: dict[str, Any] | None = None, **kwargs
    ) -> Any:
        """Invoke a Function entity

        Args:
            name: Function name
            request_body: Optional request body
            **kwargs: Additional parameters

        Returns:
            Function invocation result
        """
        manager = self._get_function_manager()
        return await manager.invoke_function(name, request_body, **kwargs)

    async def invoke(
        self,
        function: Function,
        request_body: dict[str, Any] | None = None,
        p8_return_raw_response: bool = False,
        p8_full_detail_on_error: bool = False,
        **kwargs,
    ) -> Any:
        """Invoke a Function entity as a REST API call

        Args:
            function: Function entity containing endpoint information
            request_body: Optional request body for POST/PUT requests
            p8_return_raw_response: Return raw response object for debugging
            p8_full_detail_on_error: Include full error details in response
            **kwargs: Additional parameters for the API call

        Returns:
            API response data (JSON, image, or text)

        Raises:
            Exception: If the API call fails
        """
        try:
            # Get authentication token
            token = await self._get_token()

            # Build request URL
            endpoint = function.endpoint
            if endpoint and kwargs:
                # Format endpoint with path parameters
                endpoint = endpoint.format(**kwargs)

            url = f"{self.uri}/{endpoint.lstrip('/')}" if endpoint else self.uri

            # Build headers
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            # Select HTTP method
            method = (function.verb or "GET").upper()
            http_method = getattr(requests, method.lower())

            # Build request parameters
            request_params = {
                "url": url,
                "headers": headers,
                "params": kwargs,  # Query parameters
                "timeout": 30,
            }

            # Add request body for POST/PUT/PATCH
            if request_body and method in ["POST", "PUT", "PATCH"]:
                if isinstance(request_body, dict):
                    request_params["json"] = request_body
                else:
                    request_params["data"] = request_body

            # Make the API call
            logger.debug(f"Making {method} request to {url}")
            response = http_method(**request_params)

            # Handle response
            if p8_return_raw_response:
                return response

            # Raise for HTTP errors
            response.raise_for_status()

            # Parse response based on content type
            content_type = response.headers.get("Content-Type", "text/plain").lower()

            if "json" in content_type:
                return response.json()
            elif content_type.startswith("image/"):
                if PIL_AVAILABLE:
                    return Image.open(BytesIO(response.content))
                else:
                    # Return raw bytes if PIL not available
                    return response.content
            else:
                # Return text content
                content = response.content
                return (
                    content.decode("utf-8") if isinstance(content, bytes) else content
                )

        except requests.exceptions.RequestException as e:
            error_msg = f"API request failed: {str(e)}"

            if p8_full_detail_on_error and hasattr(e, "response") and e.response:
                try:
                    error_data = e.response.json()
                except:
                    error_data = e.response.text

                return {
                    "error": error_msg,
                    "status_code": e.response.status_code,
                    "response_data": error_data,
                    "response_headers": dict(e.response.headers),
                    "requested_url": url,
                    "function_info": {
                        "name": function.name,
                        "endpoint": function.endpoint,
                        "verb": function.verb,
                    },
                }
            else:
                raise Exception(error_msg)

        except Exception as e:
            error_msg = f"Unexpected error invoking function {function.name}: {str(e)}"

            if p8_full_detail_on_error:
                return {
                    "error": error_msg,
                    "exception_type": type(e).__name__,
                    "requested_url": url,
                    "function_info": {
                        "name": function.name,
                        "endpoint": function.endpoint,
                        "verb": function.verb,
                    },
                }
            else:
                raise Exception(error_msg)

    def create_function_from_spec(
        self, operation_id: str, spec: OpenApiSpec | None = None
    ) -> Function | None:
        """Create Function entity from OpenAPI spec

        Args:
            operation_id: OpenAPI operation ID
            spec: Optional OpenApiSpec instance (uses self.spec if not provided)

        Returns:
            Function entity or None if operation not found
        """
        target_spec = spec or self.spec
        if not target_spec:
            raise ValueError("No OpenAPI spec available")

        return target_spec.get_function_by_name(operation_id)

    async def test_connectivity(self) -> dict[str, Any]:
        """Test connectivity to the API

        Returns:
            Dictionary with connectivity test results
        """
        try:
            # Try to get token
            token = await self._get_token()

            # Make a simple HEAD request to the base URI
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            response = requests.head(self.uri, headers=headers, timeout=10)

            return {
                "status": "success",
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "has_token": bool(token),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "has_token": bool(await self._get_token()),
            }

    def __repr__(self) -> str:
        return f"OpenApiService(uri='{self.uri}')"


class OpenApiServiceFactory:
    """Factory for creating OpenApiService instances

    This factory can create OpenApiService instances from various sources
    including OpenAPI specifications and Function entities.
    """

    @staticmethod
    def from_spec(
        spec: OpenApiSpec,
        token_cache: ApiTokenCache | None = None,
        repository: Optional["BaseRepository"] = None,
    ) -> OpenApiService:
        """Create OpenApiService from OpenAPI specification

        Args:
            spec: OpenApiSpec instance
            token_cache: Optional ApiTokenCache instance
            repository: Optional repository for Function management

        Returns:
            OpenApiService instance
        """
        return OpenApiService(
            uri=spec.host_uri,
            token_or_key=spec.token_key,
            spec=spec,
            token_cache=token_cache,
            repository=repository,
        )

    @staticmethod
    def from_function(
        function: Function,
        token_cache: ApiTokenCache | None = None,
        repository: Optional["BaseRepository"] = None,
    ) -> OpenApiService:
        """Create OpenApiService from Function entity

        Args:
            function: Function entity
            token_cache: Optional ApiTokenCache instance
            repository: Optional repository for Function management

        Returns:
            OpenApiService instance
        """
        return OpenApiService(
            uri=function.proxy_uri, token_cache=token_cache, repository=repository
        )

    @staticmethod
    def from_uri(
        uri: str,
        token: str | None = None,
        token_cache: ApiTokenCache | None = None,
        repository: Optional["BaseRepository"] = None,
    ) -> OpenApiService:
        """Create OpenApiService from URI

        Args:
            uri: Base API URI
            token: Optional API token
            token_cache: Optional ApiTokenCache instance
            repository: Optional repository for Function management

        Returns:
            OpenApiService instance
        """
        return OpenApiService(
            uri=uri, token_or_key=token, token_cache=token_cache, repository=repository
        )

    @staticmethod
    def from_repository(
        repository: "BaseRepository", uri: str, token: str | None = None
    ) -> OpenApiService:
        """Create OpenApiService with full Function management capabilities

        Args:
            repository: Repository instance
            uri: Base API URI
            token: Optional API token

        Returns:
            OpenApiService instance with Function management
        """
        return OpenApiService(uri=uri, token_or_key=token, repository=repository)