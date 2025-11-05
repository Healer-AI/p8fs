"""Function manager for OpenAPI services

This module provides a FunctionManager that can load Function entities from
the P8FS KV store and invoke them using the OpenAPI service.
"""

from typing import TYPE_CHECKING, Any

from p8fs_cluster.logging import get_logger
from p8fs.models.p8 import Function
from p8fs.repository import TenantRepository, SystemRepository

if TYPE_CHECKING:
    from p8fs.repository.BaseRepository import BaseRepository

from .cache import ApiTokenCache, set_token_cache
from .service import OpenApiService
from .spec import OpenApiSpec

logger = get_logger(__name__)


class FunctionManager:
    """Manager for Function entities and OpenAPI service invocation

    This class provides a high-level interface for managing Function entities
    stored in the P8FS KV store and invoking them via OpenAPI services.
    """

    def __init__(self, repository: "BaseRepository", function_repository: "BaseRepository | None" = None):
        """Initialize function manager

        Args:
            repository: Repository instance for general operations
            function_repository: Optional separate repository for Function entities
        """
        self.repository = repository
        self.function_repository = function_repository or TenantRepository(Function)
        self.token_cache = ApiTokenCache(repository)
        self.services: dict[str, OpenApiService] = {}
        self.functions: dict[str, Function] = {}

        # Set global token cache
        set_token_cache(self.token_cache)

    async def load_functions(self, proxy_uri: str | None = None) -> list[Function]:
        """Load Function entities from repository

        Args:
            proxy_uri: Optional filter by proxy URI

        Returns:
            List of Function entities
        """
        try:
            # Use repository to select functions
            filters = {"proxy_uri": proxy_uri} if proxy_uri else None
            functions = await self.function_repository.select(filters=filters)

            # Update local cache
            for function in functions:
                self.functions[function.name] = function

            logger.info(f"Loaded {len(functions)} functions from repository")
            return functions

        except Exception as e:
            logger.error(f"Failed to load functions: {e}")
            return []

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
        try:
            # Load and parse OpenAPI spec
            spec = OpenApiSpec(spec_uri, token_key=token)

            # Store API token if provided
            if token:
                await self.token_cache.set(spec.host_uri, token, name)

            # Generate Function entities from spec
            functions = []
            for function in spec.iterate_functions(verbs=verbs, filter_ops=filter_ops):
                # Store function using repository
                await self.function_repository.upsert(function)

                functions.append(function)
                self.functions[function.name] = function

            logger.info(f"Registered {len(functions)} functions from {spec_uri}")
            return functions

        except Exception as e:
            logger.error(f"Failed to register API from spec {spec_uri}: {e}")
            return []

    async def get_function(self, name: str) -> Function | None:
        """Get Function entity by name

        Args:
            name: Function name

        Returns:
            Function entity or None if not found
        """
        # Check local cache first
        if name in self.functions:
            return self.functions[name]

        # Try to load from repository
        try:
            results = await self.function_repository.select(
                filters={"name": name},
                limit=1
            )
            if results:
                function = results[0]
                self.functions[name] = function
                return function
        except Exception as e:
            logger.error(f"Failed to get function {name}: {e}")

        return None

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
        # Get function
        function = await self.get_function(name)
        if not function:
            raise ValueError(f"Function {name} not found")

        # Get or create OpenAPI service
        service = await self._get_service(function.proxy_uri)

        # Invoke function
        return await service.invoke(function, request_body=request_body, **kwargs)

    async def _get_service(self, proxy_uri: str) -> OpenApiService:
        """Get or create OpenAPI service for proxy URI

        Args:
            proxy_uri: Proxy URI

        Returns:
            OpenApiService instance
        """
        if proxy_uri not in self.services:
            self.services[proxy_uri] = OpenApiService(
                uri=proxy_uri, 
                token_cache=self.token_cache,
                repository=self.repository
            )

        return self.services[proxy_uri]

    async def list_functions(
        self, proxy_uri: str | None = None
    ) -> list[dict[str, Any]]:
        """List available functions

        Args:
            proxy_uri: Optional filter by proxy URI

        Returns:
            List of function summaries
        """
        functions = await self.load_functions(proxy_uri)

        return [
            {
                "name": func.name,
                "description": func.description,
                "proxy_uri": func.proxy_uri,
                "verb": func.verb,
                "endpoint": func.endpoint,
                "parameters": func.function_spec.get("parameters", {}).get(
                    "properties", {}
                ),
            }
            for func in functions
        ]

    async def search_functions(self, query: str) -> list[Function]:
        """Search functions by description

        Args:
            query: Search query

        Returns:
            List of matching Function entities
        """
        # Use repository's semantic search if available
        if hasattr(self.function_repository, "semantic_search"):
            results = self.function_repository.semantic_search(
                query=query,
                limit=20,
                field_name="description"
            )
            return [Function(**result) for result in results]
        
        # Fallback to loading all and filtering
        functions = await self.load_functions()
        query_lower = query.lower()

        matches = []
        for function in functions:
            if (
                query_lower in function.description.lower()
                or query_lower in function.name.lower()
                or any(
                    query_lower in tag.lower()
                    for tag in function.function_spec.get("tags", [])
                )
            ):
                matches.append(function)

        return matches

    async def test_function(self, name: str) -> dict[str, Any]:
        """Test a function's connectivity

        Args:
            name: Function name

        Returns:
            Test results
        """
        function = await self.get_function(name)
        if not function:
            return {"status": "error", "error": f"Function {name} not found"}

        service = await self._get_service(function.proxy_uri)
        return await service.test_connectivity()

    async def remove_function(self, name: str) -> bool:
        """Remove a function from the repository

        Args:
            name: Function name

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get function to find its ID
            function = await self.get_function(name)
            if not function:
                return False
                
            # Remove from repository using filters
            results = await self.function_repository.select(
                filters={"name": name},
                limit=1
            )
            
            # Note: Repository doesn't have delete method, would need to add
            # For now, just remove from cache
            self.functions.pop(name, None)
            
            logger.warning("Function removal not fully implemented - removed from cache only")
            return True
        except Exception as e:
            logger.error(f"Failed to remove function {name}: {e}")
            return False

    async def update_function(self, function: Function) -> bool:
        """Update a function in the repository

        Args:
            function: Function entity to update

        Returns:
            True if successful, False otherwise
        """
        try:
            await self.function_repository.upsert(function)
            self.functions[function.name] = function
            return True
        except Exception as e:
            logger.error(f"Failed to update function {function.name}: {e}")
            return False

    def clear_cache(self):
        """Clear all caches"""
        self.functions.clear()
        self.services.clear()
        self.token_cache.clear_cache()