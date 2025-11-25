"""Key-Value storage providers for temporary data like device authorization flows.

This module provides KV storage abstractions that work with different backends:
- TiKV for TiDB deployments (production)
- PostgreSQL JSON storage for development/testing
- RocksDB for embedded scenarios

The KV provider is accessed via provider.kv.put/get/scan methods.
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging.setup import get_logger

logger = get_logger(__name__)


class BaseKVProvider(ABC):
    """Abstract base class for key-value storage providers."""
    
    @abstractmethod
    async def put(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """Store a key-value pair with optional TTL.
        
        Args:
            key: Storage key
            value: Any JSON-serializable value to store
            ttl_seconds: Time to live in seconds (None for no expiration)
            
        Returns:
            True if stored successfully
        """
        pass
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value by key.
        
        Args:
            key: Storage key
            
        Returns:
            Dictionary value or None if not found/expired
        """
        pass
    
    # Delete functionality not implemented - keys expire via TTL only
    
    @abstractmethod
    async def scan(self, prefix: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Scan for keys with given prefix.
        
        Args:
            prefix: Key prefix to search for
            limit: Maximum number of results
            
        Returns:
            List of matching key-value pairs
        """
        pass
    
    async def find_by_field(self, field: str, value: str, prefix: str = "", limit: int = 100) -> Optional[Dict[str, Any]]:
        """Find first record where field equals value.
        
        Args:
            field: Field name to search in
            value: Value to search for
            prefix: Key prefix to limit search scope
            limit: Maximum records to scan
            
        Returns:
            First matching record or None
        """
        records = await self.scan(prefix, limit)
        for record in records:
            if record.get("value", {}).get(field) == value:
                return record.get("value")
        return None


class PostgreSQLKVProvider(BaseKVProvider):
    """PostgreSQL-based KV storage using AGE graph functions.

    Implementation:
    --------------
    Uses PostgreSQL AGE extension graph functions for KV operations:
    - p8.put_kv(key, value, ttl_seconds, userid) - Store KV pairs with TTL
    - p8.get_kv(key, userid) - Retrieve values with automatic expiry cleanup
    - p8.scan_kv(prefix, limit, userid) - Scan keys by prefix pattern

    Features:
    - Graph-based storage using AGE extension (Apache AGE)
    - Automatic TTL-based expiration on read
    - Tenant isolation via key prefixing
    - Support for device authorization flows and entity indexing

    Functions are defined in p8fs/extensions/sql/03_functions.sql and loaded
    automatically via docker-entrypoint-initdb.d in fresh installations.

    Note: Table-based fallback (kv_storage) is deprecated for PostgreSQL.
    Use TiDB provider for table-based KV with TiKV fallback.
    """

    def __init__(self, provider):
        """Initialize with parent PostgreSQL provider."""
        self.provider = provider

    def _get_connection(self):
        """Get database connection from parent provider."""
        return self.provider.connect_sync()

    async def put(self, key: str, value: Any, ttl_seconds: Optional[int] = None, tenant_id: Optional[str] = None) -> bool:
        """Store key-value using AGE graph p8.put_kv() function.

        Args:
            key: Storage key (may contain tenant prefix)
            value: Value to store (will be converted to JSONB)
            ttl_seconds: Optional TTL in seconds
            tenant_id: Optional tenant ID (for logging only, key should include tenant prefix)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            from datetime import datetime, date

            class DateTimeEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    return super().default(obj)

            # Convert value to JSONB format
            if not isinstance(value, dict):
                value = {"value": value}

            json_value = json.dumps(value, cls=DateTimeEncoder, ensure_ascii=False)

            logger.debug(f"PostgreSQL AGE KV: Storing key={key}, ttl={ttl_seconds}")

            # Call p8.put_kv() AGE graph function
            cursor.execute(
                "SELECT p8.put_kv(%s, %s::jsonb, %s)",
                (key, json_value, ttl_seconds)
            )

            result = cursor.fetchone()
            conn.commit()
            cursor.close()

            success = result[0] if result else False
            if success:
                logger.debug(f"PostgreSQL AGE KV: Stored {key} successfully")
            else:
                logger.warning(f"PostgreSQL AGE KV: Failed to store {key}")

            return success

        except Exception as e:
            logger.error(f"Error storing KV pair {key} in PostgreSQL AGE: {e}")
            logger.error(f"Value type: {type(value)}, Value repr: {repr(value)}")
            return False

    async def get(self, key: str) -> Optional[Any]:
        """Get value from AGE graph using p8.get_kv() function.

        Args:
            key: Storage key (may contain tenant prefix)

        Returns:
            Stored value or None if not found/expired
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            logger.debug(f"PostgreSQL AGE KV: Retrieving key={key}")

            # Call p8.get_kv() AGE graph function
            cursor.execute("SELECT p8.get_kv(%s)", (key,))

            result = cursor.fetchone()
            cursor.close()

            logger.debug(f"PostgreSQL AGE KV: fetchone() returned: {repr(result)}, type: {type(result)}")

            if result and result[0]:
                value = result[0]
                # p8.get_kv returns JSONB, convert if needed
                if isinstance(value, str):
                    value = json.loads(value)

                logger.debug(f"PostgreSQL AGE KV: Retrieved value for {key}")

                # Unwrap single-value wrapper if present
                if isinstance(value, dict) and len(value) == 1 and "value" in value:
                    return value["value"]
                return value

            logger.debug(f"PostgreSQL AGE KV: No result for key {key}")
            return None

        except Exception as e:
            logger.error(f"Error getting KV pair {key} from PostgreSQL AGE: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """Delete not supported - keys expire via TTL."""
        return True

    async def scan(self, prefix: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Scan keys with prefix using AGE graph p8.scan_kv() function.

        Args:
            prefix: Key prefix to scan (may contain tenant prefix)
            limit: Maximum number of results

        Returns:
            List of matching key-value pairs
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            logger.debug(f"PostgreSQL AGE KV scan: prefix={prefix}, limit={limit}")

            # Call p8.scan_kv() AGE graph function
            # Returns TABLE(key text, value jsonb, created_at text, expires_at text)
            cursor.execute(
                "SELECT key, value, created_at, expires_at FROM p8.scan_kv(%s, %s)",
                (prefix, limit)
            )

            rows = cursor.fetchall()
            cursor.close()

            logger.debug(f"PostgreSQL AGE KV scan found {len(rows)} rows")

            return [
                {
                    "key": row[0],
                    "value": row[1] if isinstance(row[1], dict) else json.loads(row[1]) if row[1] else {},
                    "created_at": row[2],
                    "expires_at": row[3]
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Error scanning KV pairs with prefix {prefix} in PostgreSQL AGE: {e}")
            return []


class TiDBKVProvider(BaseKVProvider):
    """TiDB-based KV storage with TiKV fallback.

    Architecture:
    - Production: Uses native TiKV async client (gRPC) when available
    - Development: Falls back to table storage when TiKV cluster not available

    Detection:
    - If P8FS_TIKV_ENDPOINTS is set and tikv-client installed → Native TiKV
    - Otherwise → Table storage fallback

    TTL Limitations:
    - TiKV Python client doesn't support native TTL
    - Operations with TTL automatically fall back to table storage
    - Table storage handles TTL via database-native expiry (expires_at column)
    """

    def __init__(self, provider):
        """Initialize with parent TiDB provider."""
        self.provider = provider
        self._async_tikv_client = None
        self._async_client_lock = None
        self._use_tikv = False
        self._tikv_available = None  # Cache availability check result

        # Check if TiKV is potentially available (lazy actual connection)
        tikv_endpoints = getattr(config, "tikv_endpoints", None)
        if tikv_endpoints:
            try:
                # Just check if the module exists, don't connect yet
                import tikv_client.asynchronous
                self._use_tikv = True
                logger.debug(
                    f"TiDB KV: TiKV client available, will use native client for operations without TTL. "
                    f"Endpoints: {tikv_endpoints}"
                )
            except ImportError:
                logger.warning(
                    "TiDB KV: tikv-client package not installed. "
                    "Install with: pip install 'p8fs[tikv]' for better performance"
                )
        else:
            logger.debug("TiKV endpoints not configured (P8FS_TIKV_ENDPOINTS not set)")

    async def _get_async_tikv_client(self):
        """Get or create async TiKV client (lazy initialization with retry)."""
        if self._async_tikv_client is None:
            # Initialize lock if needed
            if self._async_client_lock is None:
                import asyncio
                self._async_client_lock = asyncio.Lock()

            async with self._async_client_lock:
                if self._async_tikv_client is None:
                    from tikv_client.asynchronous import RawClient as AsyncRawClient
                    tikv_endpoints = getattr(config, "tikv_endpoints", [])

                    try:
                        self._async_tikv_client = await AsyncRawClient.connect(tikv_endpoints)
                        logger.info(f"TiKV async client connected to {tikv_endpoints}")
                    except Exception as e:
                        logger.error(f"Failed to connect to TiKV: {e}")
                        raise

        return self._async_tikv_client

    def _get_connection(self):
        """Get database connection from parent provider."""
        return self.provider.connect_sync()

    async def put(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """Store key-value using TiKV client or table storage fallback.

        Note: TiKV Python client doesn't support TTL.
        Operations with TTL automatically use table storage.
        """
        # If TTL is requested, must use table storage (TiKV doesn't support TTL)
        if ttl_seconds is not None:
            logger.debug(f"TTL requested ({ttl_seconds}s), using table storage for key={key}")
            return await self._put_table(key, value, ttl_seconds)

        # Try TiKV if available
        if self._use_tikv:
            try:
                return await self._put_tikv(key, value)
            except Exception as e:
                logger.warning(f"TiKV put failed, falling back to table storage: {e}")
                return await self._put_table(key, value, ttl_seconds)

        # Default to table storage
        return await self._put_table(key, value, ttl_seconds)

    async def _put_tikv(self, key: str, value: Any) -> bool:
        """Store key-value using native TiKV async client with retry logic."""
        if not isinstance(value, dict):
            value = {"value": value}

        from datetime import datetime, date
        class DateTimeEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                return super().default(obj)

        json_value = json.dumps(value, cls=DateTimeEncoder, ensure_ascii=False)

        # Retry logic for region errors (based on working TiKV example)
        max_retries = 3
        base_delay = 0.1

        for attempt in range(max_retries):
            try:
                client = await self._get_async_tikv_client()
                await client.put(key.encode(), json_value.encode())
                logger.debug(f"TiKV: Stored key={key}")
                return True
            except Exception as e:
                error_msg = str(e).lower()
                is_region_error = any(keyword in error_msg for keyword in [
                    'region not found', 'region error', 'not_leader',
                    'epoch_not_match', 'key_not_in_region'
                ])

                if is_region_error and attempt < max_retries - 1:
                    # Exponential backoff for region errors
                    import asyncio
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"TiKV region error (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    # Force refresh of client connection
                    self._async_tikv_client = None
                    continue
                else:
                    # Final attempt failed or non-region error
                    logger.error(f"TiKV put operation failed for key {key}: {e}")
                    raise

    async def _put_table(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """Store key-value using table storage fallback."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            from datetime import datetime, date

            class DateTimeEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    return super().default(obj)

            if not isinstance(value, dict):
                value = {"value": value}

            json_value = json.dumps(value, cls=DateTimeEncoder, ensure_ascii=False)

            expires_at = None
            if ttl_seconds:
                from datetime import datetime, timedelta
                expires_at = (datetime.utcnow() + timedelta(seconds=ttl_seconds)).strftime('%Y-%m-%d %H:%M:%S')

            logger.debug(f"TiDB KV: Storing key={key}, ttl={ttl_seconds}")

            import uuid
            record_id = str(uuid.uuid4())

            cursor.execute("""
                INSERT INTO public.kv_storage (id, `key`, value, expires_at, tenant_id)
                VALUES (%s, %s, %s, %s, 'system')
                ON DUPLICATE KEY UPDATE
                    value = VALUES(value),
                    expires_at = VALUES(expires_at),
                    updated_at = NOW()
            """, (record_id, key, json_value, expires_at))

            conn.commit()
            cursor.close()

            logger.debug(f"TiDB KV: Stored {key} successfully")
            return True

        except Exception as e:
            logger.error(f"Error storing KV pair {key} in TiDB: {e}")
            logger.error(f"Value type: {type(value)}, Value repr: {repr(value)}")
            return False

    async def get(self, key: str) -> Optional[Any]:
        """Get value from TiKV client or table storage.

        Since TTL-based values are stored in table storage (TiKV doesn't support TTL),
        we must check table storage first, then fall back to TiKV native storage.
        This ensures round-trip consistency for all put/get operations.
        """
        try:
            result = await self._get_table(key)
            if result is not None:
                return result
        except Exception as e:
            logger.debug(f"Table storage get failed, trying TiKV: {e}")

        if self._use_tikv:
            try:
                return await self._get_tikv(key)
            except Exception as e:
                logger.warning(f"TiKV get also failed: {e}")
                return None

        return None

    async def _get_tikv(self, key: str) -> Optional[Any]:
        """Get value from native TiKV async client with retry logic."""
        max_retries = 3
        base_delay = 0.1

        for attempt in range(max_retries):
            try:
                client = await self._get_async_tikv_client()
                raw_value = await client.get(key.encode())
                if raw_value:
                    value = json.loads(raw_value.decode())
                    logger.debug(f"TiKV: Retrieved value for {key}")
                    if isinstance(value, dict) and len(value) == 1 and "value" in value:
                        return value["value"]
                    return value

                logger.debug(f"TiKV: No result for key {key}")
                return None
            except Exception as e:
                error_msg = str(e).lower()
                is_region_error = any(keyword in error_msg for keyword in [
                    'region not found', 'region error', 'not_leader',
                    'epoch_not_match', 'key_not_in_region'
                ])

                if is_region_error and attempt < max_retries - 1:
                    import asyncio
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"TiKV region error (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    # Force refresh of client connection
                    self._async_tikv_client = None
                    continue
                else:
                    # Final attempt failed or non-region error
                    logger.error(f"TiKV get operation failed for key {key}: {e}")
                    raise

    async def _get_table(self, key: str) -> Optional[Any]:
        """Get value from table storage fallback."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT value FROM public.kv_storage
                WHERE `key` = %s
                AND (expires_at IS NULL OR expires_at > NOW())
            """, (key,))

            result = cursor.fetchone()
            cursor.close()

            logger.debug(f"TiDB KV: fetchone() returned: {repr(result)}, type: {type(result)}")

            if result:
                raw_value = result.get('value') if isinstance(result, dict) else result[0]
                value = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
                logger.debug(f"TiDB KV: Retrieved value for {key}")
                if isinstance(value, dict) and len(value) == 1 and "value" in value:
                    return value["value"]
                return value

            logger.debug(f"TiDB KV: No result for key {key}")
            return None

        except Exception as e:
            import traceback
            logger.error(f"Error getting KV pair {key} from TiDB: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception args: {e.args}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def scan(self, prefix: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Scan keys with prefix using TiKV client or table storage fallback."""
        # Try TiKV if available
        if self._use_tikv:
            try:
                return await self._scan_tikv(prefix, limit)
            except Exception as e:
                logger.warning(f"TiKV scan failed, falling back to table storage: {e}")
                return await self._scan_table(prefix, limit)

        # Default to table storage
        return await self._scan_table(prefix, limit)

    async def _scan_tikv(self, prefix: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Scan keys with prefix using native TiKV async client with retry logic."""
        max_retries = 3
        base_delay = 0.1

        for attempt in range(max_retries):
            try:
                client = await self._get_async_tikv_client()
                results = []
                start_key = prefix.encode()
                end_key = (prefix + "\xff").encode()

                # The async scan returns a list of tuples, not an iterator
                pairs = await client.scan(start_key, end=end_key, limit=limit)

                for key_bytes, value_bytes in pairs:
                    key = key_bytes.decode()
                    value = json.loads(value_bytes.decode())
                    results.append({
                        "key": key,
                        "value": value
                    })

                logger.debug(f"TiKV: Scanned {len(results)} keys with prefix {prefix}")
                return results
            except Exception as e:
                error_msg = str(e).lower()
                is_region_error = any(keyword in error_msg for keyword in [
                    'region not found', 'region error', 'not_leader',
                    'epoch_not_match', 'key_not_in_region'
                ])

                if is_region_error and attempt < max_retries - 1:
                    import asyncio
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"TiKV region error (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    # Force refresh of client connection
                    self._async_tikv_client = None
                    continue
                else:
                    # Final attempt failed or non-region error
                    logger.error(f"TiKV scan operation failed for prefix {prefix}: {e}")
                    raise

    async def _scan_table(self, prefix: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Scan keys with prefix in table storage fallback."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT `key`, value, created_at, expires_at
                FROM public.kv_storage
                WHERE `key` LIKE %s
                AND (expires_at IS NULL OR expires_at > NOW())
                LIMIT %s
            """, (f"{prefix}%", limit))

            rows = cursor.fetchall()
            cursor.close()

            return [
                {
                    "key": row[0],
                    "value": json.loads(row[1]) if isinstance(row[1], str) else row[1],
                    "created_at": row[2],
                    "expires_at": row[3]
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Error scanning KV pairs with prefix {prefix} in TiDB: {e}")
            return []

    async def delete(self, key: str) -> bool:
        """Delete key using TiKV client or table storage fallback."""
        # Try TiKV if available
        if self._use_tikv:
            try:
                return await self._delete_tikv(key)
            except Exception as e:
                logger.warning(f"TiKV delete failed, falling back to table storage: {e}")
                return await self._delete_table(key)

        # Default to table storage
        return await self._delete_table(key)

    async def _delete_tikv(self, key: str) -> bool:
        """Delete key using native TiKV async client with retry logic."""
        max_retries = 3
        base_delay = 0.1

        for attempt in range(max_retries):
            try:
                client = await self._get_async_tikv_client()
                await client.delete(key.encode())
                logger.debug(f"TiKV: Deleted key={key}")
                return True
            except Exception as e:
                error_msg = str(e).lower()
                is_region_error = any(keyword in error_msg for keyword in [
                    'region not found', 'region error', 'not_leader',
                    'epoch_not_match', 'key_not_in_region'
                ])

                if is_region_error and attempt < max_retries - 1:
                    import asyncio
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"TiKV region error (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    # Force refresh of client connection
                    self._async_tikv_client = None
                    continue
                else:
                    # Final attempt failed or non-region error
                    logger.error(f"TiKV delete operation failed for key {key}: {e}")
                    raise

    async def _delete_table(self, key: str) -> bool:
        """Delete key using table storage fallback."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM public.kv_storage
                WHERE `key` = %s
            """, (key,))

            conn.commit()
            cursor.close()

            logger.debug(f"TiDB: Deleted key={key}")
            return True
        except Exception as e:
            logger.error(f"Error deleting KV pair {key} from TiDB: {e}")
            return False


class TiKVProvider(BaseKVProvider):
    """TiKV-based KV storage for production."""

    def __init__(self, pd_endpoints: List[str]):
        self.pd_endpoints = pd_endpoints
        self._client = None
        self._http_client = None
        self._use_http = config.tikv_use_http_proxy
    
    async def _get_client(self):
        """Get TiKV client - either HTTP proxy or native client."""
        # TiKV HTTP client not implemented - TiDB should use PostgreSQLKVProvider instead
        logger.error("TiKVProvider is deprecated - use PostgreSQLKVProvider for TiDB")
        raise NotImplementedError(
            "TiKV HTTP client not available. For TiDB, use PostgreSQLKVProvider via "
            "get_kv_provider(provider_type='tidb', ...) which uses PostgreSQL-compatible storage."
        )
    
    async def put(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> bool:
        """Store key-value in TiKV."""
        try:
            client = await self._get_client()
            
            # Add metadata for expiry
            storage_value = {
                "data": value,
                "expires_at": (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds else None,
                "created_at": datetime.utcnow().isoformat()
            }
            
            if self._use_http:
                # Use HTTP client with system tenant for auth flows
                tenant_id = "system"  # System tenant for auth operations
                return await client.aput(key, storage_value, tenant_id)
            else:
                # Native TiKV implementation
                # await client.put(key.encode(), json.dumps(storage_value).encode())
                logger.info(f"TiKV put stub: {key} = {storage_value}")
                return True
            
        except Exception as e:
            logger.error(f"Error storing KV pair {key} in TiKV: {e}")
            return False
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value from TiKV."""
        try:
            client = await self._get_client()
            
            if self._use_http:
                # Use HTTP client with system tenant
                tenant_id = "system"
                result = await client.aget(key, tenant_id)
                if result:
                    # HTTP client returns the full storage value
                    storage_value = result
                    
                    # Check expiry
                    if storage_value.get("expires_at"):
                        expires_at = datetime.fromisoformat(storage_value["expires_at"])
                        if datetime.utcnow() > expires_at:
                            await client.adelete(key, tenant_id)
                            return None
                    
                    return storage_value.get("data")
                return None
            else:
                # Native TiKV implementation
                # raw_value = await client.get(key.encode())
                # if raw_value:
                #     storage_value = json.loads(raw_value.decode())
                #     ...
                logger.info(f"TiKV get stub: {key}")
                return None
            
        except Exception as e:
            logger.error(f"Error getting KV pair {key} from TiKV: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete key from TiKV."""
        try:
            client = await self._get_client()
            
            if self._use_http:
                tenant_id = "system"
                return await client.adelete(key, tenant_id)
            else:
                # Native implementation would delete the key
                return True
        except Exception as e:
            logger.error(f"Error deleting KV pair {key} from TiKV: {e}")
            return False
    
    async def scan(self, prefix: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Scan keys with prefix in TiKV."""
        try:
            client = await self._get_client()
            
            if self._use_http:
                tenant_id = "system"
                results = await client.ascan(prefix, limit, tenant_id)
                
                # Process results and check expiry
                valid_results = []
                for key, storage_value in results:
                    if storage_value.get("expires_at"):
                        expires_at = datetime.fromisoformat(storage_value["expires_at"])
                        if datetime.utcnow() > expires_at:
                            await client.adelete(key, tenant_id)
                            continue
                    
                    valid_results.append({
                        "key": key,
                        "value": storage_value.get("data")
                    })
                
                return valid_results
            else:
                # Native TiKV implementation
                logger.info(f"TiKV scan stub: {prefix} (limit: {limit})")
                return []
            
        except Exception as e:
            logger.error(f"Error scanning KV pairs with prefix {prefix} in TiKV: {e}")
            return []


class RocksDBKVProvider(BaseKVProvider):
    """RocksDB-based KV storage for embedded scenarios."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db = None
    
    async def _get_db(self):
        """Get RocksDB instance."""
        if not self._db:
            # TODO: Implement RocksDB connection
            # import rocksdb
            # self._db = rocksdb.DB(self.db_path, rocksdb.Options(create_if_missing=True))
            logger.warning("RocksDB client not implemented yet - using stub")
        return self._db
    
    async def put(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> bool:
        """Store key-value in RocksDB."""
        try:
            db = await self._get_db()
            
            storage_value = {
                "data": value,
                "expires_at": (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds else None,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # TODO: Implement RocksDB storage
            # db.put(key.encode(), json.dumps(storage_value).encode())
            logger.info(f"RocksDB put stub: {key} = {storage_value}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing KV pair {key} in RocksDB: {e}")
            return False
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value from RocksDB."""
        try:
            db = await self._get_db()
            
            # TODO: Implement RocksDB retrieval
            logger.info(f"RocksDB get stub: {key}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting KV pair {key} from RocksDB: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete not supported - keys expire via TTL."""
        # RocksDB delete stub - keys expire via TTL
        return True
    
    async def scan(self, prefix: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Scan keys with prefix in RocksDB."""
        try:
            db = await self._get_db()
            
            # TODO: Implement RocksDB scan
            logger.info(f"RocksDB scan stub: {prefix} (limit: {limit})")
            return []
            
        except Exception as e:
            logger.error(f"Error scanning KV pairs with prefix {prefix} in RocksDB: {e}")
            return []


def get_kv_provider(provider_type: str, connection_config: Dict[str, Any]) -> BaseKVProvider:
    """Factory function to create appropriate KV provider.

    Args:
        provider_type: "postgresql", "tidb", or "rocksdb"
        connection_config: Provider-specific connection configuration

    Returns:
        KV provider instance
    """
    if provider_type == "postgresql":
        return PostgreSQLKVProvider(connection_config["provider"])
    elif provider_type == "tidb":
        return TiDBKVProvider(connection_config["provider"])
    elif provider_type == "rocksdb":
        return RocksDBKVProvider(connection_config["db_path"])
    else:
        raise ValueError(f"Unsupported KV provider type: {provider_type}")