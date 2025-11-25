"""API Token Cache for OpenAPI service

This module provides KV-based token storage for OpenAPI services.
Tokens are stored in the P8FS KV store with tenant isolation.
"""

import asyncio
from typing import TYPE_CHECKING

from p8fs_cluster.logging import get_logger
from p8fs.models.p8 import ApiProxy

if TYPE_CHECKING:
    from p8fs.repository import TenantRepository, SystemRepository
    from p8fs.providers.kv import BaseKVProvider

logger = get_logger(__name__)


class ApiTokenCache:
    """Cache for API tokens stored in P8FS KV store

    This class provides a simple cache for API tokens that are stored
    in the P8FS KV store as ApiProxy entities. The cache supports
    tenant isolation and automatic token refresh.
    """

    def __init__(self, repository: "TenantRepository | SystemRepository"):
        """Initialize the token cache

        Args:
            repository: Repository instance for KV operations
        """
        self.repository = repository
        self.kv_provider: BaseKVProvider = repository.kv
        self.cache: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        """Get API token for the given key

        Args:
            key: The API proxy URI or key

        Returns:
            The API token if found, None otherwise
        """
        async with self._lock:
            # Check cache first
            if key in self.cache:
                return self.cache[key]

            try:
                # Try to fetch from KV store
                api_proxy_data = await self.kv_provider.get(f"ApiProxy/{key}")
                if api_proxy_data:
                    # Parse as ApiProxy model
                    api_proxy = ApiProxy(**api_proxy_data)
                    if api_proxy.token:
                        self.cache[key] = api_proxy.token
                        return api_proxy.token

                # Also try to find by proxy_uri using repository
                if isinstance(self.repository, type) and issubclass(self.repository.model_class, ApiProxy):
                    results = await self.repository.select(
                        filters={"proxy_uri": key},
                        limit=1
                    )
                    if results:
                        proxy = results[0]
                        if proxy.token:
                            self.cache[key] = proxy.token
                            return proxy.token

            except Exception as e:
                logger.warning(f"Failed to fetch token for {key}: {e}")

            return None

    async def set(self, key: str, token: str, name: str | None = None) -> bool:
        """Store API token in the cache and KV store

        Args:
            key: The API proxy URI or key
            token: The API token to store
            name: Optional friendly name for the API

        Returns:
            True if successful, False otherwise
        """
        async with self._lock:
            try:
                # Create ApiProxy entity
                api_proxy = ApiProxy(proxy_uri=key, token=token, name=name or key)

                # Store in KV store with encryption
                await self.kv_provider.put(
                    key=f"ApiProxy/{api_proxy.id}",
                    value=api_proxy.model_dump(),
                    ttl_seconds=None  # No expiration for API tokens
                )

                # Also store in repository if it handles ApiProxy
                if isinstance(self.repository, type) and issubclass(self.repository.model_class, ApiProxy):
                    await self.repository.upsert(api_proxy)

                # Update cache
                self.cache[key] = token
                return True

            except Exception as e:
                logger.error(f"Failed to store token for {key}: {e}")
                return False

    async def remove(self, key: str) -> bool:
        """Remove API token from cache and KV store

        Args:
            key: The API proxy URI or key

        Returns:
            True if successful, False otherwise
        """
        async with self._lock:
            try:
                # Remove from cache
                self.cache.pop(key, None)

                # Remove from KV store
                await self.kv_provider.delete(f"ApiProxy/{key}")

                # Also find and remove by proxy_uri from repository
                if isinstance(self.repository, type) and issubclass(self.repository.model_class, ApiProxy):
                    results = await self.repository.select(
                        filters={"proxy_uri": key},
                        limit=1
                    )
                    for proxy in results:
                        await self.kv_provider.delete(f"ApiProxy/{proxy.id}")

                return True

            except Exception as e:
                logger.error(f"Failed to remove token for {key}: {e}")
                return False

    def clear_cache(self):
        """Clear the in-memory cache"""
        self.cache.clear()

    async def list_apis(self) -> dict[str, ApiProxy]:
        """List all stored API proxies

        Returns:
            Dictionary mapping proxy URIs to ApiProxy instances
        """
        try:
            # Scan KV store for ApiProxy entries
            kv_results = await self.kv_provider.scan("ApiProxy/", limit=1000)
            
            result = {}
            for kv_entry in kv_results:
                if kv_entry and "value" in kv_entry:
                    try:
                        proxy = ApiProxy(**kv_entry["value"])
                        result[proxy.proxy_uri] = proxy
                    except Exception as e:
                        logger.warning(f"Failed to parse ApiProxy: {e}")
            
            return result

        except Exception as e:
            logger.error(f"Failed to list APIs: {e}")
            return {}


# Global cache instance (will be initialized by the service)
_global_cache: ApiTokenCache | None = None


def get_token_cache() -> ApiTokenCache | None:
    """Get the global token cache instance

    Returns:
        The global ApiTokenCache instance or None if not initialized
    """
    return _global_cache


def set_token_cache(cache: ApiTokenCache):
    """Set the global token cache instance

    Args:
        cache: The ApiTokenCache instance to use globally
    """
    global _global_cache
    _global_cache = cache