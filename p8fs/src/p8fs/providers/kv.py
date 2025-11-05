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
    """PostgreSQL-based KV storage using kv_storage table.

    Current Implementation:
    ----------------------
    Uses simple table-based storage with `public.kv_storage` table for KV operations.
    This approach provides:
    - Simple, reliable storage compatible with all PostgreSQL deployments
    - Consistent behavior with TiDB table-based storage (local development parity)
    - No dependency on extension availability

    Future AGE Graph Integration:
    ----------------------------
    PostgreSQL AGE extension provides graph-based entity management functions that can
    be used for more sophisticated KV operations and entity relationships:

    Available AGE Functions (in p8fs/extensions/sql/03_functions.sql):
    - p8.put_kv(key, value, ttl) - Store KV pairs in graph with TTL
    - p8.get_kv(key) - Retrieve values from graph with automatic expiry cleanup
    - p8.scan_kv(prefix, limit) - Scan keys by prefix pattern
    - p8.add_node(key, label, properties) - Add entity nodes to graph
    - p8.get_entities(keys) - Retrieve entities by keys from graph index

    These functions are automatically loaded in fresh database installations via
    docker-entrypoint-initdb.d. They provide:
    - Graph-based entity relationships using Cypher queries
    - Automatic expiry cleanup on read
    - Node-based entity management for complex data structures

    Migration Path:
    --------------
    To switch to AGE graph-based KV storage:
    1. Ensure AGE functions are loaded (see p8fs/extensions/sql/03_functions.sql)
    2. Replace direct SQL queries with p8.put_kv/get_kv/scan_kv function calls
    3. Leverage p8.add_node for entity nodes that need graph relationships
    4. Use p8.get_entities for graph-based entity retrieval

    The table-based approach remains the recommended default for simplicity and
    compatibility. AGE functions provide value when graph relationships and advanced
    entity management are needed.
    """

    def __init__(self, provider):
        """Initialize with parent PostgreSQL provider."""
        self.provider = provider

    def _get_connection(self):
        """Get database connection from parent provider."""
        return self.provider.connect_sync()

    async def put(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """Store key-value using kv_storage table."""
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
                expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

            logger.debug(f"PostgreSQL KV: Storing key={key}, ttl={ttl_seconds}")

            import uuid
            record_id = str(uuid.uuid4())

            # Use INSERT ... ON CONFLICT for upsert
            cursor.execute("""
                INSERT INTO public.kv_storage (id, key, value, expires_at, tenant_id)
                VALUES (%s, %s, %s, %s, 'system')
                ON CONFLICT (key, tenant_id)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
            """, (record_id, key, json_value, expires_at))

            conn.commit()
            cursor.close()

            logger.debug(f"PostgreSQL KV: Stored {key} successfully")
            return True

        except Exception as e:
            logger.error(f"Error storing KV pair {key} in PostgreSQL: {e}")
            logger.error(f"Value type: {type(value)}, Value repr: {repr(value)}")
            return False

    async def get(self, key: str) -> Optional[Any]:
        """Get value from kv_storage table."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT value FROM public.kv_storage
                WHERE key = %s
                AND (expires_at IS NULL OR expires_at > NOW())
                AND tenant_id = 'system'
            """, (key,))

            result = cursor.fetchone()
            cursor.close()

            logger.debug(f"PostgreSQL KV: fetchone() returned: {repr(result)}, type: {type(result)}")

            if result:
                raw_value = result[0]
                value = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
                logger.debug(f"PostgreSQL KV: Retrieved value for {key}")
                if isinstance(value, dict) and len(value) == 1 and "value" in value:
                    return value["value"]
                return value

            logger.debug(f"PostgreSQL KV: No result for key {key}")
            return None

        except Exception as e:
            logger.error(f"Error getting KV pair {key} from PostgreSQL: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """Delete not supported - keys expire via TTL."""
        return True

    async def scan(self, prefix: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Scan keys with prefix in kv_storage table."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT key, value, created_at, expires_at
                FROM public.kv_storage
                WHERE key LIKE %s
                AND (expires_at IS NULL OR expires_at > NOW())
                AND tenant_id = 'system'
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
            logger.error(f"Error scanning KV pairs with prefix {prefix} in PostgreSQL: {e}")
            return []


class TiDBKVProvider(BaseKVProvider):
    """TiDB-based KV storage with TiKV fallback.

    Architecture:
    - Production: Uses native TiKV client (gRPC) when available
    - Development: Falls back to table storage when TiKV cluster not available

    Detection:
    - If P8FS_TIKV_PD_ENDPOINTS is set and reachable → Native TiKV
    - Otherwise → Table storage fallback
    """

    def __init__(self, provider):
        """Initialize with parent TiDB provider."""
        self.provider = provider
        self._tikv_client = None
        self._use_tikv = self._check_tikv_available()

        if self._use_tikv:
            logger.info("TiDB KV: Using native TiKV client")
        else:
            logger.info("TiDB KV: Using table storage fallback (TiKV not available)")

    def _check_tikv_available(self) -> bool:
        """Check if TiKV cluster is available for native client."""
        pd_endpoints = getattr(config, "tikv_pd_endpoints", None)
        if not pd_endpoints:
            return False

        # TODO: Implement native TiKV client connection check
        # try:
        #     import tikv_client
        #     client = tikv_client.RawClient.connect(pd_endpoints)
        #     client.close()
        #     return True
        # except Exception as e:
        #     logger.debug(f"TiKV not available: {e}")
        #     return False

        # For now, always use table storage until native client is implemented
        return False

    def _get_connection(self):
        """Get database connection from parent provider."""
        return self.provider.connect_sync()

    async def put(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """Store key-value using simple table storage."""
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
        """Get value from TiDB table storage."""
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
        """Scan keys with prefix in TiDB table storage."""
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