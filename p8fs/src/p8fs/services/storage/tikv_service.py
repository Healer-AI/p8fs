"""TiKV service abstraction for HTTP proxy operations.

This service provides a simple interface for TiKV operations using an HTTP proxy
instead of direct gRPC connections. This is useful when running outside the cluster.

HTTP Proxy API: https://p8fs.percolationlabs.ai
"""

import json
from typing import Any, Dict, List, Optional

import httpx
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from tenacity import retry, stop_after_attempt, wait_fixed

logger = get_logger(__name__)

# HTTP Proxy endpoint for TiKV operations
TIKV_HTTP_PROXY = "https://p8fs.percolationlabs.ai"


class TiKVService:
    """TiKV service for key-value operations via HTTP proxy."""

    def __init__(self, proxy_url: str = TIKV_HTTP_PROXY):
        """Initialize TiKV service with HTTP proxy URL."""
        self.proxy_url = proxy_url
        self.client = httpx.Client(timeout=30.0)

    def _format_key(self, key: str, tenant_id: str) -> str:
        """Format key with tenant isolation."""
        return f"{tenant_id}/{key}"

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def get(self, key: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get value by key with tenant isolation."""
        formatted_key = self._format_key(key, tenant_id)
        try:
            response = self.client.get(f"{self.proxy_url}/kv/{formatted_key}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return json.loads(data["value"]) if data.get("value") else None
        except Exception as e:
            logger.error(f"Failed to get key {formatted_key}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def put(self, key: str, value: Any, tenant_id: str, ttl_seconds: Optional[int] = None) -> None:
        """Put key-value pair with tenant isolation and optional TTL."""
        formatted_key = self._format_key(key, tenant_id)
        try:
            payload = {
                "key": formatted_key,
                "value": json.dumps(value)
            }
            if ttl_seconds:
                payload["ttl"] = ttl_seconds
            
            response = self.client.put(f"{self.proxy_url}/kv", json=payload)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to put key {formatted_key}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def scan(self, prefix: str, tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Scan keys by prefix with tenant isolation."""
        formatted_prefix = self._format_key(prefix, tenant_id)
        try:
            params = {"prefix": formatted_prefix, "limit": limit}
            response = self.client.get(f"{self.proxy_url}/kv/scan", params=params)
            response.raise_for_status()
            results = []
            for item in response.json():
                if item.get("value"):
                    results.append({
                        "key": item["key"].replace(f"{tenant_id}/", "", 1),
                        "value": json.loads(item["value"])
                    })
            return results
        except Exception as e:
            logger.error(f"Failed to scan prefix {formatted_prefix}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def delete(self, key: str, tenant_id: str) -> None:
        """Delete key with tenant isolation."""
        formatted_key = self._format_key(key, tenant_id)
        try:
            response = self.client.delete(f"{self.proxy_url}/kv/{formatted_key}")
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to delete key {formatted_key}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def batch_get(self, keys: List[str], tenant_id: str) -> Dict[str, Any]:
        """Get multiple keys in a single request."""
        formatted_keys = [self._format_key(k, tenant_id) for k in keys]
        try:
            response = self.client.post(
                f"{self.proxy_url}/kv/batch",
                json={"keys": formatted_keys}
            )
            response.raise_for_status()
            results = {}
            for item in response.json():
                if item.get("value"):
                    key = item["key"].replace(f"{tenant_id}/", "", 1)
                    results[key] = json.loads(item["value"])
            return results
        except Exception as e:
            logger.error(f"Failed to batch get keys: {e}")
            raise

    def close(self):
        """Close HTTP client connection."""
        self.client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class TiKVReverseMapping:
    """TiKV reverse mapping system for bidirectional lookups."""

    def __init__(self, tikv_service: TiKVService):
        """Initialize with TiKV service."""
        self.tikv = tikv_service

    def store_reverse_mapping(
        self,
        name: str,
        entity_type: str,
        entity_key: str,
        table_name: str,
        tenant_id: str
    ) -> None:
        """Store reverse mapping for entity lookups.
        
        Creates three key patterns:
        1. Name mapping: "{name}/{entity_type}" -> entity reference
        2. Entity reference: "{entity_type}/{name}" -> TiDB info
        3. Reverse mapping: "reverse/{entity_key}/{entity_type}" -> reverse lookup
        """
        # Name-based lookup
        name_key = f"{name}/{entity_type}"
        name_value = {
            "entity_type": entity_type,
            "entity_name": name,
            "entity_key": entity_key
        }
        self.tikv.put(name_key, name_value, tenant_id)
        
        # Entity reference
        entity_ref_key = f"{entity_type}/{name}"
        entity_ref_value = {
            "entity_key": entity_key,
            "table_name": table_name,
            "tenant_id": tenant_id,
            "entity_type": entity_type,
            "name": name
        }
        self.tikv.put(entity_ref_key, entity_ref_value, tenant_id)
        
        # Reverse mapping
        reverse_key = f"reverse/{entity_key}/{entity_type}"
        reverse_value = {
            "name": name,
            "entity_type": entity_type,
            "table_name": table_name
        }
        self.tikv.put(reverse_key, reverse_value, tenant_id)

    def lookup_by_name(self, name: str, entity_type: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Lookup entity by name and type."""
        key = f"{name}/{entity_type}"
        return self.tikv.get(key, tenant_id)

    def lookup_entity_reference(self, entity_type: str, name: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get full entity reference including TiDB table info."""
        key = f"{entity_type}/{name}"
        return self.tikv.get(key, tenant_id)

    def reverse_lookup(self, entity_key: str, entity_type: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Reverse lookup from entity key to original info."""
        key = f"reverse/{entity_key}/{entity_type}"
        return self.tikv.get(key, tenant_id)

    def find_entities_by_type(self, entity_type: str, tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Find all entities of a given type."""
        prefix = f"{entity_type}/"
        return self.tikv.scan(prefix, tenant_id, limit)