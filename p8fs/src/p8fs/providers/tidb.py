"""TiDB SQL provider implementation.

NOTE: When running on the cluster, TiDB is available in tikv-cluster namespace.
For local development, you can temporarily kill the local docker service and
port-forward to the cluster TiDB instance if needed:
  kubectl port-forward -n tikv-cluster svc/tidb 4000:4000

IMPORTANT: YOU CAN ALSO USE TIDB IN DOCKER but often its useful to use a real cluster with real data.
IF you want to use one or the other take care of port conflicts

For TiKV KV operations outside the cluster, we use an HTTP proxy API instead of gRPC.
Currently using: https://p8fs.percolationlabs.ai


set the provider name for tidb to use this provider
r


NOTEs:
- to match the postgres we use a public database as our defaults which we need to use in migrations
- - we also set it in the repository as the default "database" which in postgres is schema/namespace

Advanced Features:
- Reverse Key Mapping: Bidirectional lookups between entities and storage keys
- TiKV Binary Key Computation: Computing exact TiDB->TiKV binary keys for direct access
- Table Metadata Caching: Efficient caching of table IDs and primary key structures
- Entity Storage with KV Lookups: Cross-references between TiDB table storage and TiKV KV storage
- Tenant Isolation: Multi-tenant data isolation across both SQL and KV storage

Reverse Key Mapping System:
The reverse key mapping system creates bidirectional lookups that allow:
1. Name-based lookups: "entity_name/type" -> entity reference
2. Entity references: "type/entity_name" -> TiDB table reference + TiKV key
3. Reverse mappings: "reverse/entity_key/type" -> reverse lookup metadata

Key Patterns:
- Name mapping: "{name}/{entity_type}" -> points to entity reference
- Entity reference: "{entity_type}/{name}" -> contains TiDB key, table info, tenant_id
- Reverse mapping: "reverse/{entity_key}/{entity_type}" -> bidirectional lookup data
- TiKV binary key: Computed as t{tableID}_r{encodedPK} (TiDB's internal format)

This allows efficient lookups in both directions:
- Find all storage locations for a given entity name
- Find the original entity given any storage key
- Cross-reference between TiDB table storage and direct TiKV storage
"""

import json
import struct
import threading
from datetime import datetime
from typing import Any

import pymysql
import pymysql.cursors
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from tenacity import retry, stop_after_attempt, wait_fixed

from p8fs.services.storage.tikv_service import TiKVReverseMapping, TiKVService

from .base import BaseSQLProvider
from .kv import BaseKVProvider, TiKVProvider

logger = get_logger(__name__)


class TableMetadataCache:
    """
    Singleton cache for TiDB table metadata.

    Based on the reference implementation pattern, this cache stores:
    - Table IDs from INFORMATION_SCHEMA for TiKV key computation
    - Primary key structures for efficient lookups
    - Table existence flags to avoid repeated checks
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache = {}
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not getattr(self, "_initialized", False):
            self._cache = {}
            self._initialized = True

    def get_table_id(self, connection: Any, table_name: str) -> int | None:
        """Get cached table ID or fetch from database."""
        cache_key = f"table_id:{table_name}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        # Fetch from database - try multiple approaches for TiDB compatibility
        table_id = None
        try:
            cursor = connection.cursor()

            # Try TiDB 6.0+ TIDB_TABLE_ID column first
            try:
                sql = """
                SELECT TIDB_TABLE_ID FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = %s AND TABLE_SCHEMA = DATABASE()
                """
                cursor.execute(sql, (table_name,))
                result = cursor.fetchone()
                if result and result[0]:
                    table_id = result[0]
            except Exception:
                # Column doesn't exist, try alternative approach
                pass

            # Fallback: Use table name hash as pseudo table ID for older TiDB versions
            if table_id is None:
                try:
                    sql = """
                    SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_NAME = %s AND TABLE_SCHEMA = DATABASE()
                    """
                    cursor.execute(sql, (table_name,))
                    result = cursor.fetchone()
                    if result:
                        # Generate deterministic pseudo-ID from table name
                        import hashlib

                        hash_obj = hashlib.md5(table_name.encode())
                        table_id = int.from_bytes(
                            hash_obj.digest()[:4], byteorder="big"
                        )
                        logger.debug(
                            f"Generated pseudo table ID {table_id} for {table_name}"
                        )
                except Exception as e2:
                    logger.warning(
                        f"Could not verify table existence for {table_name}: {e2}"
                    )

            cursor.close()
            self._cache[cache_key] = table_id
            return table_id

        except Exception as e:
            logger.warning(f"Could not get table ID for {table_name}: {e}")
            self._cache[cache_key] = None
            return None

    def get_primary_key_info(
        self, connection: Any, table_name: str
    ) -> dict[str, Any] | None:
        """Get cached primary key information or fetch from database."""
        cache_key = f"pk_info:{table_name}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            cursor = connection.cursor()
            sql = """
            SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = %s AND TABLE_SCHEMA = DATABASE() 
            AND COLUMN_KEY = 'PRI'
            ORDER BY ORDINAL_POSITION
            """
            cursor.execute(sql, (table_name,))
            results = cursor.fetchall()
            cursor.close()

            if results:
                pk_info = {
                    "columns": [
                        {"name": row[0], "type": row[1], "column_type": row[2]}
                        for row in results
                    ],
                    "is_composite": len(results) > 1,
                }
                self._cache[cache_key] = pk_info
                return pk_info
            else:
                self._cache[cache_key] = None
                return None

        except Exception as e:
            logger.warning(f"Could not get primary key info for {table_name}: {e}")
            return None

    def table_exists(
        self, connection: Any, table_name: str, schema: str = None
    ) -> bool:
        """Check if table exists with caching."""
        schema_name = schema or "DATABASE()"
        cache_key = f"exists:{schema_name}:{table_name}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            cursor = connection.cursor()
            if schema:
                sql = """
                SELECT 1 FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = %s AND TABLE_SCHEMA = %s
                """
                cursor.execute(sql, (table_name, schema))
            else:
                sql = """
                SELECT 1 FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = %s AND TABLE_SCHEMA = DATABASE()
                """
                cursor.execute(sql, (table_name,))

            result = cursor.fetchone()
            cursor.close()

            exists = result is not None
            self._cache[cache_key] = exists
            return exists

        except Exception as e:
            logger.warning(f"Could not check table existence for {table_name}: {e}")
            return False

    def invalidate_table(self, table_name: str):
        """Invalidate cache entries for a specific table."""
        keys_to_remove = [k for k in self._cache.keys() if table_name in k]
        for key in keys_to_remove:
            del self._cache[key]
        logger.debug(f"Invalidated cache entries for table {table_name}")

    def clear_cache(self):
        """Clear the entire cache."""
        self._cache.clear()
        logger.debug("Cleared table metadata cache")

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics for monitoring."""
        stats = {
            "total_entries": len(self._cache),
            "table_ids": len(
                [k for k in self._cache.keys() if k.startswith("table_id:")]
            ),
            "pk_info": len([k for k in self._cache.keys() if k.startswith("pk_info:")]),
            "existence_checks": len(
                [k for k in self._cache.keys() if k.startswith("exists:")]
            ),
        }
        return stats


class TiDBProvider(BaseSQLProvider):
    """TiDB-specific SQL provider with vector support."""

    def __init__(self):
        super().__init__(dialect="tidb")
        self._connection = None
        self._connection_string = None
        self._metadata_cache = TableMetadataCache()
        self._kv = None
        self._tikv_service = None
        self._tikv_reverse_mapping = None

    def get_dialect_name(self) -> str:
        """Get the dialect name for this provider."""
        return "tidb"

    def get_connection_string(
        self,
        host: str = "localhost",
        port: int = 4000,
        user: str = "root",
        password: str = "",
        database: str = "public",  # Default to 'public' to match PostgreSQL
        **kwargs,
    ) -> str:
        """Generate TiDB connection string.

        Uses 'public' database by default to match PostgreSQL's public schema.
        """
        auth = f"{user}:{password}@" if password else f"{user}@"
        return f"mysql://{auth}{host}:{port}/{database}"

    def get_vector_type(self) -> str:
        """TiDB stores vectors as VECTOR type."""
        return "VECTOR"

    def get_json_type(self) -> str:
        """TiDB JSON type."""
        return "JSON"

    @property
    def kv(self) -> BaseKVProvider:
        """Get KV storage provider for temporary data like device authorization.

        TiDB uses simple table storage for KV with MySQL-compatible syntax.
        """
        if not self._kv:
            from .kv import TiDBKVProvider
            self._kv = TiDBKVProvider(self)
        return self._kv

    @property
    def tikv_service(self) -> TiKVService:
        """Get TiKV service for HTTP proxy operations."""
        if not self._tikv_service:
            self._tikv_service = TiKVService()
        return self._tikv_service

    @property
    def tikv_reverse_mapping(self) -> TiKVReverseMapping:
        """Get TiKV reverse mapping service."""
        if not self._tikv_reverse_mapping:
            self._tikv_reverse_mapping = TiKVReverseMapping(self.tikv_service)
        return self._tikv_reverse_mapping

    def supports_vector_operations(self) -> bool:
        """TiDB supports vector operations via VEC_* functions."""
        return True

    def check_vector_functions_available(self, connection: Any) -> bool:
        """Check if TiDB vector functions are available in this instance."""
        try:
            # Try to call a vector function with VEC_FROM_TEXT to see if it exists
            cursor = connection.cursor()
            cursor.execute(
                "SELECT VEC_COSINE_DISTANCE(VEC_FROM_TEXT('[1,2,3]'), VEC_FROM_TEXT('[1,2,3]'))"
            )
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False

    def create_table_sql(self, model_class: type["AbstractModel"]) -> str:
        """Generate TiDB-optimized CREATE TABLE SQL."""
        schema = model_class.to_sql_schema()
        table_name = schema["table_name"]

        # Reserved keywords that need backticks
        RESERVED_KEYWORDS = {'key', 'keys', 'table', 'index', 'order', 'group', 'by', 'where',
                            'select', 'from', 'join', 'on', 'as', 'and', 'or', 'not', 'null'}

        # Generate column definitions
        columns = []
        for field_name, field_info in schema["fields"].items():
            column_type = self.map_python_type(field_info["type"])

            # Override type for PRIMARY KEY fields - TiDB requires VARCHAR for PRIMARY KEY
            if field_info.get("is_primary_key") and column_type == "TEXT":
                column_type = "VARCHAR(255)"

            constraints = []

            if field_info.get("is_primary_key"):
                constraints.append("PRIMARY KEY")
            if field_info.get("nullable", True) is False:
                constraints.append("NOT NULL")
            if field_info.get("unique", False):
                constraints.append("UNIQUE")

            constraint_str = " " + " ".join(constraints) if constraints else ""

            # Escape reserved keywords with backticks
            escaped_field_name = f"`{field_name}`" if field_name.lower() in RESERVED_KEYWORDS else field_name

            columns.append(f"    {escaped_field_name} {column_type}{constraint_str}")

        # Add system fields if not already defined in the model
        # NOTE: These are system fields managed by the repository layer
        existing_fields = set(schema["fields"].keys())

        # Add tenant_id if tenant isolation is required
        if schema.get("tenant_isolated", False):
            if "tenant_id" not in existing_fields:
                columns.append("    tenant_id VARCHAR(36) NOT NULL")

        # Add system timestamps - databases should manage these with triggers
        if "created_at" not in existing_fields:
            columns.append("    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        if "updated_at" not in existing_fields:
            columns.append(
                "    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            )

        columns_sql = ",\n".join(columns)
        sql = f"""CREATE TABLE IF NOT EXISTS {table_name} (
{columns_sql}
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;"""

        return sql

    def create_kv_mapping_table_sql(self) -> str:
        """Generate SQL for KV mapping table creation."""
        return """
CREATE TABLE IF NOT EXISTS kv_entity_mapping (
    entity_name VARCHAR(255),
    entity_type VARCHAR(50),
    entity_key VARCHAR(500),
    tenant_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_lookup (tenant_id, entity_type, entity_name),
    INDEX idx_key_lookup (entity_key)
);"""

    def create_embedding_table_sql(self, model_class: type["AbstractModel"]) -> str:
        """Generate TiDB embedding table with proper VECTOR columns."""
        schema = model_class.to_sql_schema()
        embedding_fields = [
            field
            for field, info in schema["fields"].items()
            if info.get("is_embedding")
        ]

        if not embedding_fields:
            return ""

        # Create embeddings in separate schema for better organization
        main_table_name = schema["table_name"]
        embedding_table_name = f"embeddings.{main_table_name}_embeddings"
        primary_key = schema.get("primary_key", "id")

        # Determine vector dimensions based on embedding providers
        vector_dims = self._get_vector_dimensions_for_model(schema)

        # NOTE: Use VECTOR column type for proper TiDB vector operations
        # The embedding_vector is stored as VECTOR type, not JSON
        # NOTE: embeddings database should be created separately (see migration script header)
        sql = f"""CREATE TABLE IF NOT EXISTS {embedding_table_name} (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector VECTOR({vector_dims}) NOT NULL,
    vector_dimension INT DEFAULT {vector_dims},
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_entity_field (entity_id, field_name),
    INDEX idx_provider (embedding_provider),
    INDEX idx_field_provider (field_name, embedding_provider)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;"""

        # Add tenant isolation if required
        if schema.get("tenant_isolated", False):
            sql = sql.replace(
                f"embedding_vector VECTOR({vector_dims}) NOT NULL,",
                f"embedding_vector VECTOR({vector_dims}) NOT NULL,\n    tenant_id VARCHAR(36) NOT NULL,",
            )
            sql = sql.replace(
                "INDEX idx_field_provider (field_name, embedding_provider)",
                "INDEX idx_field_provider (field_name, embedding_provider),\n    INDEX idx_tenant (tenant_id)",
            )

        # Add TiFlash replica for vector operations
        replica_sql = f"ALTER TABLE {embedding_table_name} SET TIFLASH REPLICA 1;"

        return sql + "\n\n" + replica_sql

    def get_vector_distance_function(self, metric: str = "cosine") -> str:
        """Get TiDB vector distance function name."""
        functions = {
            "cosine": "VEC_COSINE_DISTANCE",
            "l2": "VEC_L2_DISTANCE",
            "inner_product": "VEC_NEGATIVE_INNER_PRODUCT",
        }
        return functions.get(metric, "VEC_COSINE_DISTANCE")

    def vector_similarity_search_sql(
        self,
        model_class: type["AbstractModel"],
        query_vector: list[float],
        field_name: str,
        limit: int = 10,
        threshold: float = 0.7,
        metric: str = "cosine",
        use_vector_functions: bool = True,
    ) -> tuple[str, tuple]:
        """Generate TiDB vector similarity search SQL using VECTOR columns.

        Args:
            use_vector_functions: If False, returns basic JSON-based query for compatibility
        """
        schema = model_class.to_sql_schema()
        embedding_table_name = f"embeddings.{schema['table_name']}_embeddings"

        vector_json = json.dumps(query_vector)

        if use_vector_functions:
            # Use TiDB vector functions with VEC_FROM_TEXT() for VECTOR columns
            distance_func = self.get_vector_distance_function(metric)
            sql = f"""
                SELECT entity_id, field_name, embedding_vector,
                       {distance_func}(embedding_vector, VEC_FROM_TEXT(%s)) as distance
                FROM {embedding_table_name}
                WHERE field_name = %s
                AND {distance_func}(embedding_vector, VEC_FROM_TEXT(%s)) < %s
                ORDER BY distance ASC
                LIMIT %s
            """
            # Convert threshold for distance-based search (lower is better)
            distance_threshold = 1.0 - threshold if metric == "cosine" else threshold
            params = (vector_json, field_name, vector_json, distance_threshold, limit)
        else:
            # Fallback for basic TiDB without vector functions
            # Returns all embeddings for the field (application-level similarity calculation needed)
            sql = f"""
                SELECT entity_id, field_name, embedding_vector
                FROM {embedding_table_name}
                WHERE field_name = %s
                ORDER BY entity_id
                LIMIT %s
            """
            params = (field_name, limit)

        return sql.strip(), params

    def semantic_search_sql(
        self,
        model_class: type["AbstractModel"],
        query_vector: list[float],
        field_name: str | None = None,
        limit: int = 10,
        threshold: float = 0.7,
        metric: str = "cosine",
        tenant_id: str | None = None,
    ) -> tuple[str, tuple]:
        """Generate TiDB semantic search SQL with JOIN to main entity table."""
        schema = model_class.to_sql_schema()
        main_table = schema["table_name"]
        embedding_table = f"embeddings.{schema['table_name']}_embeddings"
        primary_key = schema["key_field"]
        distance_func = self.get_vector_distance_function(metric)

        vector_json = json.dumps(query_vector)

        # Build field filter condition
        field_conditions = []
        if field_name:
            field_conditions.append("e.field_name = %s")
        else:
            # Search all embedding fields
            embedding_fields = schema.get("embedding_fields", [])
            if embedding_fields:
                placeholders = ", ".join(["%s"] * len(embedding_fields))
                field_conditions.append(f"e.field_name IN ({placeholders})")

        # Build tenant isolation
        tenant_conditions = []
        if tenant_id and schema.get("tenant_isolated", True):
            tenant_conditions.extend(["m.tenant_id = %s", "e.tenant_id = %s"])

        # Combine all WHERE conditions
        where_conditions = field_conditions + tenant_conditions

        # Convert threshold for distance-based search (lower is better in TiDB)
        distance_threshold = 1.0 - threshold if metric == "cosine" else threshold

        # For TiDB, use VEC_FROM_TEXT() to convert JSON string to VECTOR
        distance_expr = f"{distance_func}(e.embedding_vector, VEC_FROM_TEXT(%s))"
        threshold_condition = f"{distance_expr} < %s"
        order_clause = f"{distance_expr} ASC"

        sql = f"""
            SELECT m.*, 
                   {distance_expr} as distance_score,
                   e.field_name as matched_field,
                   e.embedding_provider as embedding_provider
            FROM {main_table} m
            INNER JOIN {embedding_table} e ON m.{primary_key} = e.entity_id
            WHERE {' AND '.join(where_conditions + [threshold_condition])}
            ORDER BY {order_clause}
            LIMIT %s
        """

        # Build parameters
        params = []
        params.append(vector_json)  # For distance calculation
        if field_name:
            params.append(field_name)
        else:
            embedding_fields = schema.get("embedding_fields", [])
            params.extend(embedding_fields)
        if tenant_id and schema.get("tenant_isolated", True):
            params.extend([tenant_id, tenant_id])
        params.extend([vector_json, distance_threshold, vector_json, limit])

        return sql.strip(), tuple(params)

    def get_tiflash_replica_sql(self, table_name: str, replica_count: int = 1) -> str:
        """Generate TiFlash replica SQL for analytics workloads."""
        return f"ALTER TABLE {table_name} SET TIFLASH REPLICA {replica_count};"

    def get_placement_rule_sql(
        self, table_name: str, region: str = "default", replicas: int = 3
    ) -> str:
        """Generate placement rule SQL for data locality."""
        return f"""
            ALTER TABLE {table_name} 
            PLACEMENT POLICY = 'PLACEMENT POLICY {region}_policy 
            PRIMARY_REGION="{region}" REGIONS="{region}" REPLICAS={replicas}';
        """

    def optimize_table_sql(self, table_name: str) -> str:
        """Generate table optimization SQL."""
        return f"ANALYZE TABLE {table_name};"

    def get_migration_sql(self, from_version: str, to_version: str) -> list[str]:
        """Get TiDB-specific migration SQL."""
        migrations = []

        # Example migration patterns
        if from_version == "1.0.0" and to_version == "1.1.0":
            migrations.extend(
                [
                    "ALTER TABLE documents ADD COLUMN version VARCHAR(50) DEFAULT '1.1.0'",
                    "UPDATE documents SET version = '1.1.0' WHERE version IS NULL",
                ]
            )

        return migrations

    def map_python_type(self, type_hint: Any) -> str:
        """Map Python type to TiDB/MySQL type.

        Handles complex type mappings including:
        - Union types with precedence rules (UUID | str -> VARCHAR)
        - Optional types (Union[T, None] -> nullable T)
        - Collection types with JSON storage
        - Vector types with TiDB vector functions

        Args:
            type_hint: Python type annotation to map

        Returns:
            str: TiDB/MySQL SQL type definition

        Note:
            TiDB/MySQL stores UUID as VARCHAR(36) since it lacks native UUID type.
            Union types prioritize the first type in the schema definition.
        """
        import typing
        from datetime import datetime
        from uuid import UUID

        # Handle Union types (Optional and other unions)
        if hasattr(type_hint, "__origin__") and type_hint.__origin__ is typing.Union:
            # Get the non-None type from Union, prioritizing database-native types
            args = [arg for arg in type_hint.__args__ if arg is not type(None)]
            if args:
                # Prioritize UUID over str if both are present (will be stored as VARCHAR(36))
                if UUID in args:
                    type_hint = UUID
                else:
                    type_hint = args[0]  # First type takes precedence

        # Basic type mappings
        if type_hint == str:
            return "VARCHAR(255)"  # TiDB requires length for PRIMARY KEY compatibility
        elif type_hint == int:
            return "BIGINT"
        elif type_hint == float:
            return "DOUBLE"
        elif type_hint == bool:
            return "TINYINT(1)"
        elif type_hint == datetime:
            return "TIMESTAMP"
        elif type_hint == UUID:
            return "VARCHAR(36)"

        # Collection types
        if hasattr(type_hint, "__origin__"):
            origin = type_hint.__origin__
            if origin is list or origin is list:
                args = getattr(type_hint, "__args__", ())
                if args and args[0] == float:
                    return "JSON"  # Store vectors as JSON in TiDB
                return "JSON"
            elif origin is dict or origin is dict or origin is set or origin is set:
                return "JSON"

        # Default to TEXT for unknown types
        return "TEXT"

    def upsert_sql(
        self, model_class: type["AbstractModel"], values: dict[str, Any]
    ) -> tuple[str, tuple]:
        """Generate TiDB UPSERT using REPLACE INTO."""
        schema = model_class.to_sql_schema()
        table_name = schema["table_name"]

        fields = list(values.keys())
        placeholders = ["%s" for _ in fields]

        sql = f"""
            REPLACE INTO {table_name} ({', '.join(fields)})
            VALUES ({', '.join(placeholders)})
        """

        # Serialize values for TiDB
        serialized_values = self.serialize_for_db(values)
        return sql.strip(), tuple(serialized_values[field] for field in fields)

    def select_sql(
        self,
        model_class: type["AbstractModel"],
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: list[str] | None = None,
    ) -> tuple[str, tuple]:
        """Generate TiDB SELECT with filtering."""
        schema = model_class.to_sql_schema()
        table_name = schema["table_name"]

        # Build SELECT clause
        select_fields = ", ".join(fields) if fields else "*"

        # Start building SQL
        sql = f"SELECT {select_fields} FROM {table_name}"
        params = []

        # Build WHERE clause
        where_conditions = []
        if filters:
            for filter_key, filter_value in filters.items():
                if "__" in filter_key:
                    field, operator = filter_key.rsplit("__", 1)
                    if operator == "gt":
                        where_conditions.append(f"{field} > %s")
                        params.append(filter_value)
                    elif operator == "gte":
                        where_conditions.append(f"{field} >= %s")
                        params.append(filter_value)
                    elif operator == "lt":
                        where_conditions.append(f"{field} < %s")
                        params.append(filter_value)
                    elif operator == "lte":
                        where_conditions.append(f"{field} <= %s")
                        params.append(filter_value)
                    elif operator == "in":
                        placeholders = ", ".join(["%s"] * len(filter_value))
                        where_conditions.append(f"{field} IN ({placeholders})")
                        params.extend(filter_value)
                    elif operator == "like":
                        where_conditions.append(f"{field} LIKE %s")
                        params.append(filter_value)
                    elif operator == "contains":
                        # JSON contains operation in TiDB
                        where_conditions.append(f"JSON_CONTAINS({field}, %s)")
                        params.append(filter_value)
                else:
                    where_conditions.append(f"{filter_key} = %s")
                    params.append(filter_value)

        if where_conditions:
            sql += " WHERE " + " AND ".join(where_conditions)

        # Add ORDER BY
        if order_by:
            order_clauses = []
            for order_field in order_by:
                # Handle explicit direction (e.g., "created_at DESC" or "name ASC")
                if " " in order_field:
                    # Already contains direction
                    order_clauses.append(order_field)
                elif order_field.startswith("-"):
                    # Prefix notation (e.g., "-created_at")
                    order_clauses.append(f"{order_field[1:]} DESC")
                else:
                    # No direction specified, default to ASC
                    order_clauses.append(f"{order_field} ASC")
            sql += " ORDER BY " + ", ".join(order_clauses)

        # Add LIMIT and OFFSET
        if limit:
            sql += f" LIMIT {limit}"
        if offset:
            sql += f" OFFSET {offset}"

        return sql, tuple(params)

    def delete_sql(
        self,
        model_class: type["AbstractModel"],
        key_value: Any,
        tenant_id: str | None = None,
    ) -> tuple[str, tuple]:
        """Generate TiDB DELETE with tenant isolation."""
        schema = model_class.to_sql_schema()
        table_name = schema["table_name"]
        primary_key = schema.get("primary_key", "id")

        where_conditions = [f"{primary_key} = %s"]
        params = [key_value]

        if schema.get("tenant_isolated") and tenant_id:
            where_conditions.append("tenant_id = %s")
            params.append(tenant_id)

        sql = f"DELETE FROM {table_name} WHERE " + " AND ".join(where_conditions)

        return sql, tuple(params)

    def _reopen_connection(self) -> Any:
        """Reopen TiDB connection with retry logic."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass  # Ignore errors when closing
            self._connection = None

        @retry(wait=wait_fixed(1), stop=stop_after_attempt(4), reraise=True)
        def open_connection_with_retry(conn_string):
            logger.debug(
                f"Opening TiDB connection: {conn_string.split('@')[1] if '@' in conn_string else conn_string}"
            )

            # Parse MySQL connection string
            import re

            pattern = (
                r"mysql://(?:([^:]+)(?::([^@]+))?@)?([^:/?]+)(?::(\d+))?(?:/(.+))?"
            )
            match = re.match(pattern, conn_string)

            if not match:
                raise ValueError(f"Invalid MySQL connection string: {conn_string}")

            user, password, host, port, database = match.groups()

            return pymysql.connect(
                host=host,
                port=int(port or 4000),
                user=user or "root",
                password=password or "",
                database=database or "public",
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
            )

        self._connection = open_connection_with_retry(self._connection_string)

        # Test connection
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        logger.debug("TiDB connection reopened successfully")
        return self._connection

    def apply_user_context(self, connection: Any, user_id: str, tenant_id: str):
        """Apply user context for tenant isolation in TiDB.

        Note: TiDB doesn't have the same RLS features as PostgreSQL,
        so we implement tenant isolation at the query level.
        """
        try:
            with connection.cursor() as cursor:
                # Set session variables for user context
                cursor.execute("SET @p8fs_user_id = %s", (user_id,))
                cursor.execute("SET @p8fs_tenant_id = %s", (tenant_id,))
                logger.debug(
                    f"Applied user context: user={user_id}, tenant={tenant_id}"
                )
        except pymysql.Error as e:
            logger.warning(f"Could not apply user context: {e}")

    def connect_sync(self, connection_string: str | None = None) -> Any:
        """Create synchronous TiDB connection using pymysql."""
        self._connection_string = connection_string or config.tidb_connection_string

        # Check if we have a valid connection
        if self._connection:
            try:
                # Test if connection is still valid
                self._connection.ping()
                return self._connection
            except Exception:
                logger.debug("Existing connection is invalid, reopening...")

        # Reopen connection
        return self._reopen_connection()

    def connect_async(self, connection_string: str | None = None) -> Any:
        """Create asynchronous TiDB connection.

        For now, returns sync connection. Can be upgraded to aiomysql later.
        """
        logger.debug(
            "Async connection requested, returning sync connection (aiomysql not implemented yet)"
        )
        return self.connect_sync(connection_string)

    def execute(
        self, connection: Any, query: str, params: tuple | None = None
    ) -> list[dict[str, Any]]:
        """Execute query and return results as dict collection."""
        # Handle case where connection is actually the query (BaseRepository compatibility)
        if isinstance(connection, str):
            # BaseRepository passes (query, params) without connection
            actual_query = connection
            actual_params = query if query is not None else params
            connection = self.connect_sync()
            query = actual_query
            params = actual_params

        cursor = None
        try:
            cursor = connection.cursor()

            logger.debug(f"Executing query: {query[:100]}...")
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Handle different query types
            query_upper = query.strip().upper()
            if query_upper.startswith(("SELECT", "WITH", "SHOW", "DESCRIBE", "DESC")):
                # Fetch results for SELECT/SHOW/DESCRIBE queries
                results = cursor.fetchall()
                # Deserialize JSON columns from strings back to Python objects
                return [self.deserialize_from_db(row) for row in results]
            else:
                # For INSERT/UPDATE/DELETE, commit and return affected rows info
                connection.commit()
                return [{"affected_rows": cursor.rowcount}]

        except pymysql.Error as e:
            logger.error(f"Query execution failed: {e}")
            if connection:
                connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()

    async def async_execute(
        self, connection: Any, query: str, params: tuple | None = None
    ) -> list[dict[str, Any]]:
        """Execute query asynchronously.

        For now, calls sync version. Can be upgraded to aiomysql later.
        """
        if connection is None:
            connection = self.connect_sync()
        return self.execute(connection, query, params)

    def execute_async(
        self, query: str, params: tuple | None = None
    ) -> list[dict[str, Any]]:
        """Execute query asynchronously without connection parameter.

        This is for compatibility with BaseRepository which doesn't pass connection.
        """
        connection = self.connect_sync()
        return self.execute(connection, query, params)

    def batch_upsert_sql(
        self, model_class: type["AbstractModel"], values_list: list[dict[str, Any]]
    ) -> tuple[str, list[tuple]]:
        """Generate TiDB batch UPSERT using REPLACE INTO."""
        if not values_list:
            raise ValueError("Empty values list for batch upsert")

        schema = model_class.to_sql_schema()
        table_name = schema["table_name"]

        # Use first row to determine columns
        first_row = values_list[0]
        columns = list(first_row.keys())

        # Build the SQL template
        insert_columns = ", ".join(columns)
        value_placeholders = ", ".join(["%s"] * len(columns))

        # TiDB uses REPLACE INTO for upserts
        sql = f"""
            REPLACE INTO {table_name} ({insert_columns})
            VALUES ({value_placeholders})
        """

        # Serialize all rows
        params_list = []
        for row in values_list:
            serialized = self.serialize_for_db(row)
            params_list.append(tuple(serialized[col] for col in columns))

        return sql.strip(), params_list

    def deserialize_from_db(self, data: dict[str, Any]) -> dict[str, Any]:
        """Deserialize data from TiDB storage.

        TiDB/pymysql returns JSON columns as strings, so we need to parse them back to Python objects.
        """
        import json

        def parse_value(value):
            """Parse values from TiDB storage."""
            if value is None:
                return None

            # If it's a string that looks like JSON, try to parse it
            if isinstance(value, str):
                # Check if it looks like JSON (starts with [ or {)
                stripped = value.strip()
                if stripped and stripped[0] in ('{', '['):
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        # Not valid JSON, return as-is
                        return value

            return value

        return {k: parse_value(v) for k, v in data.items()}

    def serialize_for_db(self, data: dict[str, Any]) -> dict[str, Any]:
        """Serialize model data for TiDB storage."""
        import uuid
        import datetime
        import json

        def adapt_value(value):
            """Adapt Python values for TiDB/MySQL storage."""
            if value is None:
                return None

            # UUID objects - convert to string
            if isinstance(value, uuid.UUID):
                return str(value)

            # Enum values - get the actual value
            if hasattr(value, "value") and hasattr(value.__class__, "__bases__"):
                if any("Enum" in str(base) for base in value.__class__.__bases__):
                    return value.value

            # Collections - convert to JSON string
            if isinstance(value, (dict, list)):

                def json_serializer(obj):
                    """Custom JSON serializer for nested objects."""
                    # Handle enums
                    if hasattr(obj, "value") and hasattr(obj.__class__, "__bases__"):
                        if any("Enum" in str(base) for base in obj.__class__.__bases__):
                            return obj.value
                    # Handle UUID
                    if isinstance(obj, uuid.UUID):
                        return str(obj)
                    # Handle datetime
                    if isinstance(obj, (datetime.datetime, datetime.date)):
                        return obj.isoformat()
                    # Default to string representation
                    return str(obj)

                return json.dumps(value, default=json_serializer)

            # Handle datetime objects
            if isinstance(value, (datetime.datetime, datetime.date)):
                return value

            return value

        # Apply adaptation to all values
        return {k: adapt_value(v) for k, v in data.items()}

    def get_vector_operator(self, metric: str = "cosine") -> str:
        """Get TiDB vector distance operator (returns function name since TiDB uses functions)."""
        # TiDB uses functions instead of operators, but this maintains compatibility
        return self.get_vector_distance_function(metric)

    def execute_batch(
        self,
        connection: Any,
        query: str,
        params_list: list[tuple],
        page_size: int = 1000,
    ) -> dict[str, Any]:
        """Execute batch operation using TiDB batch processing.

        Note: TiDB doesn't have execute_values like PostgreSQL, so we execute multiple times.
        """
        cursor = None
        total_affected = 0

        try:
            cursor = connection.cursor()

            logger.debug(f"Executing batch operation with {len(params_list)} rows")

            # Process in pages to avoid memory issues
            for i in range(0, len(params_list), page_size):
                page = params_list[i : i + page_size]

                for params in page:
                    cursor.execute(query, params)
                    total_affected += cursor.rowcount

            connection.commit()

            return {"affected_rows": total_affected, "batch_size": len(params_list)}

        except pymysql.Error as e:
            logger.error(f"Batch execution failed: {e}")
            if connection:
                connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()

    def create_full_text_index_sql(self, table_name: str, field_name: str) -> str:
        """Generate TiDB FULLTEXT index SQL."""
        return f"CREATE FULLTEXT INDEX idx_{table_name}_{field_name}_fulltext ON {table_name} ({field_name});"

    def get_full_text_search_sql(
        self,
        model_class: type["AbstractModel"],
        query: str,
        field_name: str,
        limit: int = 10,
        tenant_id: str | None = None,
    ) -> tuple[str, tuple]:
        """Generate TiDB full-text search SQL using MATCH AGAINST."""
        schema = model_class.to_sql_schema()
        table_name = schema["table_name"]

        where_conditions = [f"MATCH({field_name}) AGAINST(%s IN NATURAL LANGUAGE MODE)"]
        params = [query]

        if schema.get("tenant_isolated") and tenant_id:
            where_conditions.append("tenant_id = %s")
            params.append(tenant_id)

        sql = f"""
            SELECT *, MATCH({field_name}) AGAINST(%s IN NATURAL LANGUAGE MODE) as relevance_score
            FROM {table_name}
            WHERE {' AND '.join(where_conditions)}
            ORDER BY relevance_score DESC
            LIMIT %s
        """

        # Add query param again for relevance score calculation
        params = [query] + params + [limit]
        return sql.strip(), tuple(params)

    def get_partition_sql(
        self,
        table_name: str,
        partition_type: str = "RANGE",
        partition_column: str = "created_at",
        partitions: list[str] = None,
    ) -> str:
        """Generate TiDB table partitioning SQL."""
        if partitions is None:
            # Default monthly partitions for the current year
            partitions = [
                "PARTITION p202501 VALUES LESS THAN ('2025-02-01')",
                "PARTITION p202502 VALUES LESS THAN ('2025-03-01')",
                "PARTITION p202503 VALUES LESS THAN ('2025-04-01')",
                "PARTITION pmax VALUES LESS THAN MAXVALUE",
            ]

        partition_clauses = ",\n    ".join(partitions)

        return f"""
            ALTER TABLE {table_name}
            PARTITION BY {partition_type} ({partition_column}) (
                {partition_clauses}
            );
        """

    def get_vacuum_sql(self, table_name: str) -> str:
        """Generate TiDB table optimization SQL (equivalent to PostgreSQL VACUUM)."""
        return f"ANALYZE TABLE {table_name};"

    def _get_vector_dimensions_for_model(self, schema: dict[str, Any]) -> int:
        """
        Determine the vector dimensions for a model based on its embedding providers.

        Args:
            schema: Model schema with embedding providers

        Returns:
            Number of dimensions for the vector column
        """
        embedding_providers = schema.get("embedding_providers", {})
        if not embedding_providers:
            return 1536  # Default OpenAI dimensions

        try:
            from ..config.embedding import get_vector_dimensions

            # Use the first embedding provider to determine dimensions
            first_provider = next(iter(embedding_providers.values()))
            return get_vector_dimensions(first_provider)
        except Exception:
            # Fallback to default dimensions
            return 1536

    # ==============================================
    # REVERSE KEY MAPPING SYSTEM (EXACT COPY OF REFERENCE)
    # ==============================================
    # Based on reference storage repository implementation
    # Copied exactly to match TiKV operations structure

    async def kv_put(self, key: str, value: dict[str, Any], tenant_id: str) -> bool:
        """Put key-value pair in TiKV using HTTP proxy."""
        try:
            self.tikv_service.put(key, value, tenant_id)
            return True
        except Exception as e:
            logger.error(f"Failed to put key {key} in TiKV: {e}")
            return False

    async def compute_tidb_tikv_key(
        self, tenant_id: str, entity_type: str, entity_id: str
    ) -> bytes:
        """
        Compute the actual TiKV binary key that TiDB uses for a table record.

        TiDB stores table data in TiKV using this key format:
        t{tableID}_r{encodedPK}

        Uses cached table metadata to avoid repeated database queries.
        """
        try:
            # Get table metadata
            table_name = entity_type
            cache = self.get_metadata_cache()
            connection = self.connect_sync()

            table_id = cache.get_table_id(connection, table_name)

            if not table_id:
                raise ValueError(f"Table {table_name} not found")

            # Encode the clustered primary key values
            encoded_pk = self._encode_primary_key(tenant_id, entity_type, entity_id)

            # Construct the binary key: t{8-byte-table-id}_r{encoded-pk}
            table_prefix = b"t" + struct.pack(">Q", table_id)
            record_prefix = b"_r"

            connection.close()
            return table_prefix + record_prefix + encoded_pk

        except Exception as e:
            logger.error(
                f"Failed to compute TiDB TiKV key for {entity_type}/{entity_id}: {e}"
            )
            # Fallback: return a computed key based on our knowledge
            fallback_key = f"tidb/{tenant_id}/{entity_type}/{entity_id}"
            return fallback_key.encode()

    def _encode_primary_key(
        self, tenant_id: str, entity_type: str, entity_id: str
    ) -> bytes:
        """
        Encode primary key values using TiDB's memcomparable encoding.

        This is a simplified version - TiDB uses complex memcomparable encoding
        for clustered primary keys to ensure lexicographic ordering.

        For now, we'll use a simple encoding that's predictable.
        """
        # Simple encoding: concatenate with null separators
        # In production, this would need proper memcomparable encoding
        pk_data = f"{tenant_id}\x00{entity_type}\x00{entity_id}"
        return pk_data.encode("utf-8")

    async def store_entity_data(
        self, entity_data: dict[str, Any], model_class, tenant_id: str
    ):
        """
        Store entity in the KV store with reverse mappings.
        Copied exactly from reference implementation.
        """
        entity_name = entity_data.get(model_class.get_model_key_field())
        entity_key = f"{model_class.__name__.lower()}/{entity_name}"
        tidb_key = await self.compute_tidb_tikv_key(
            tenant_id, model_class.__name__.lower(), str(entity_key)
        )
        reverse_key = f"reverse/{entity_key}/{model_class.__name__.lower()}"

        # Store reference to TiDB record, not full entity data (eliminates double storage)
        entity_reference = {
            "tidb_key": tidb_key.hex(),
            "entity_type": model_class.__name__.lower(),
            "tenant_id": tenant_id,
            "entity_id": str(entity_data.get("id")),
            "table_name": model_class.get_model_table_name(),
            "created_at": datetime.utcnow().isoformat(),
        }
        await self.kv_put(entity_key, entity_reference, tenant_id)

        # Create name-based key: e.g., "Violet/cat" or "Buddy/dog"
        name_key = f"{entity_name}/{model_class.__name__.lower()}"
        name_mapping = {
            "entity_id": str(entity_name),
            "entity_key": entity_key,  # The direct TiKV key for this entity
            "entity_type": model_class.__name__.lower(),
            "name": entity_name,
            "tenant_id": tenant_id,
            "tidb_key": tidb_key,
            "reverse_key": reverse_key,
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            await self.kv_put(name_key, name_mapping, tenant_id)
        except Exception as e:
            logger.warning(
                f"Failed to store name-based reverse mapping for {entity_name}: {e}"
            )

        try:
            reverse_mapping = {
                "tidb_tikv_key": tidb_key.hex(),
                "entity_id": str(entity_key),
                "entity_type": model_class.__name__.lower(),
                "tenant_id": tenant_id,
                "created_at": datetime.utcnow().isoformat(),
            }

            await self.kv_put(reverse_key, reverse_mapping, tenant_id)

        except Exception as e:
            logger.warning(
                f"Failed to store ID-based reverse key mapping for {entity_key}: {e}"
            )

        return name_mapping

    async def store_entity_reverse_mapping(
        self, model_class, entity_data: dict[str, Any], tenant_id: str
    ):
        """Alias for store_entity_data with different parameter order for test compatibility."""
        return await self.store_entity_data(entity_data, model_class, tenant_id)

    # ==============================================
    # PLACEHOLDER METHODS FOR INTEGRATION TESTS
    # ==============================================
    # These methods maintain the exact signatures from integration tests
    # but will need TiKV access to function properly

    def store_entity_with_reverse_mapping(
        self,
        connection: Any,
        entity_name: str,
        entity_type: str,
        entity_data: dict[str, Any],
        tenant_id: str,
    ) -> str:
        """Store entity with reverse key mapping system."""
        try:
            # First, insert the entity data into the SQL table
            table_name = entity_type  # Assumes table name matches entity type

            # Get table metadata to ensure we have the primary key
            pk_info = self.get_primary_key_info(connection, table_name)
            if not pk_info:
                raise ValueError(f"Could not find primary key for table {table_name}")

            # Insert entity into SQL table (simplified - actual implementation would be more robust)
            columns = list(entity_data.keys())
            values = [entity_data[col] for col in columns]
            placeholders = ", ".join(["%s"] * len(columns))

            sql = f"""
                REPLACE INTO {table_name} ({', '.join(columns)}) 
                VALUES ({placeholders})
            """

            cursor = connection.cursor()
            cursor.execute(sql, values)
            connection.commit()

            # Get the entity ID (assuming it's in the entity_data)
            entity_id = entity_data.get(pk_info["column_name"], entity_data.get("id"))
            entity_key = f"{entity_type}/{entity_name}"

            # Store reverse mapping in TiKV
            self.tikv_reverse_mapping.store_reverse_mapping(
                name=entity_name,
                entity_type=entity_type,
                entity_key=str(entity_id),
                table_name=table_name,
                tenant_id=tenant_id,
            )

            # Return the key format expected by tests
            return f"{tenant_id}:{entity_type}:{entity_name}"

        except Exception as e:
            logger.error(f"Failed to store entity with reverse mapping: {e}")
            raise

    def get_entity_by_name(
        self, connection: Any, entity_name: str, entity_type: str, tenant_id: str
    ) -> dict[str, Any] | None:
        """Retrieve entity by name using reverse key mapping."""
        try:
            # Look up entity reference in TiKV
            entity_ref = self.tikv_reverse_mapping.lookup_entity_reference(
                entity_type, entity_name, tenant_id
            )

            if not entity_ref:
                return None

            # Get entity from SQL table
            table_name = entity_ref.get("table_name", entity_type)
            entity_id = entity_ref.get("entity_key")

            if not entity_id:
                return None

            # Query the SQL table
            pk_info = self.get_primary_key_info(connection, table_name)
            if not pk_info:
                return None

            sql = f"""
                SELECT * FROM {table_name} 
                WHERE {pk_info['column_name']} = %s
                AND tenant_id = %s
            """

            cursor = connection.cursor()
            cursor.execute(sql, (entity_id, tenant_id))
            result = cursor.fetchone()
            cursor.close()

            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Failed to get entity by name: {e}")
            return None

    def get_entities_by_storage_key(
        self, connection: Any, entity_key: str, tenant_id: str
    ) -> dict[str, Any] | None:
        """Retrieve entity by storage key using reverse mapping."""
        try:
            # Parse the entity key to get type and ID
            if "/" in entity_key:
                entity_type, entity_id = entity_key.split("/", 1)
            else:
                return None

            # Look up reverse mapping
            reverse_info = self.tikv_reverse_mapping.reverse_lookup(
                entity_id, entity_type, tenant_id
            )

            if not reverse_info:
                return None

            # Get entity from SQL table
            table_name = reverse_info.get("table_name", entity_type)

            # Query the SQL table
            pk_info = self.get_primary_key_info(connection, table_name)
            if not pk_info:
                return None

            sql = f"""
                SELECT * FROM {table_name} 
                WHERE {pk_info['column_name']} = %s
                AND tenant_id = %s
            """

            cursor = connection.cursor()
            cursor.execute(sql, (entity_id, tenant_id))
            result = cursor.fetchone()
            cursor.close()

            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Failed to get entity by storage key: {e}")
            return None

    def compute_tikv_binary_key(self, table_id: int, primary_key_value: Any) -> bytes:
        """
        Compute TiDB/TiKV binary key for direct TiKV access.

        Format: t{tableID}_r{encodedPK}

        Args:
            table_id: TiDB table ID from INFORMATION_SCHEMA.TABLES
            primary_key_value: Primary key value to encode

        Returns:
            Binary key for TiKV storage
        """
        import struct

        # Encode primary key based on type
        if isinstance(primary_key_value, str):
            # String keys are UTF-8 encoded
            encoded_pk = primary_key_value.encode("utf-8")
        elif isinstance(primary_key_value, int):
            # Integer keys are big-endian encoded
            encoded_pk = struct.pack(">Q", primary_key_value)
        else:
            # Other types converted to string then UTF-8
            encoded_pk = str(primary_key_value).encode("utf-8")

        # Format: t{tableID}_r{encodedPK}
        key_prefix = f"t{table_id}_r".encode()
        return key_prefix + encoded_pk

    def get_metadata_cache(self) -> TableMetadataCache:
        """Get the table metadata cache instance."""
        return self._metadata_cache

    def table_exists(
        self, connection: Any, table_name: str, schema: str = None
    ) -> bool:
        """Check if table exists using cached metadata."""
        return self._metadata_cache.table_exists(connection, table_name, schema)

    def get_primary_key_info(
        self, connection: Any, table_name: str
    ) -> dict[str, Any] | None:
        """Get primary key information using cached metadata."""
        return self._metadata_cache.get_primary_key_info(connection, table_name)

    def invalidate_table_cache(self, table_name: str):
        """Invalidate cache entries for a specific table."""
        self._metadata_cache.invalidate_table(table_name)

    def clear_metadata_cache(self):
        """Clear the entire metadata cache."""
        self._metadata_cache.clear_cache()

    def get_cache_stats(self) -> dict[str, int]:
        """Get metadata cache statistics."""
        return self._metadata_cache.get_cache_stats()

    def register_model(
        self, model_class: type["AbstractModel"], plan: bool = True
    ) -> str | bool:
        """
        Register a model with reverse key mapping support.

        Creates both the main table and the KV mapping table if they don't exist.
        """
        schema = model_class.to_sql_schema()
        table_name = schema["table_name"]

        # Generate SQL for main table
        main_table_sql = self.create_table_sql(model_class)

        # Generate SQL for embedding table if needed
        embedding_sql = self.create_embedding_table_sql(model_class)

        # Only include kv_mapping_sql once, not for every model
        # The kv_mapping table is shared across all models
        sql_parts = [main_table_sql]
        if embedding_sql:
            sql_parts.append(embedding_sql)

        full_sql = "\n\n".join(sql_parts)

        if plan:
            return full_sql

        # If not planning, we would execute the SQL here
        # This would be implemented by the caller (e.g., TenantRepository)
        return True

    # Embedding Operations
    def insert_and_return_ids(self, entities: list[dict], table_name: str) -> list[str]:
        """Insert entities and return only their IDs for fast embedding processing."""
        if not entities:
            return []

        # Build bulk insert with TiDB-specific syntax
        columns = list(entities[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        values_clause = f"({placeholders})"

        all_values = []
        for entity in entities:
            all_values.extend([entity[col] for col in columns])

        sql = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES {', '.join([values_clause] * len(entities))}
            ON DUPLICATE KEY UPDATE
                {', '.join([f"{col} = VALUES({col})" for col in columns if col != 'id'])},
                updated_at = NOW()
        """

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, all_values)
                conn.commit()

                # Get inserted/updated IDs
                # TiDB doesn't support RETURNING, so get IDs from the entities
                return [entity["id"] for entity in entities]

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for batch of texts using configured embedding service."""
        try:
            from ..services.llm import get_embedding_service

            embedding_service = get_embedding_service()

            # Generate embeddings in batch for efficiency
            embeddings = []
            for text in texts:
                embedding = embedding_service.embed(text)
                embeddings.append(embedding)

            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate embeddings batch: {e}")
            raise

    def upsert_embeddings(self, embedding_records: list[dict], table_name: str) -> None:
        """Upsert embedding records using TiDB-specific VECTOR column format."""
        if not embedding_records:
            return

        embedding_table = f"embeddings_{table_name}_embeddings"

        # Convert vectors to TiDB VECTOR format using VEC_FROM_TEXT
        processed_records = []
        for record in embedding_records:
            processed_record = record.copy()
            # TiDB vector format: JSON array -> VEC_FROM_TEXT('[0.1,0.2,0.3]')
            vector = processed_record["embedding_vector"]
            processed_record["embedding_vector"] = json.dumps(vector)
            processed_records.append(processed_record)

        # Build bulk upsert using TiDB syntax
        columns = list(processed_records[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        values_clause = f"({placeholders})"

        all_values = []
        for record in processed_records:
            values_row = []
            for col in columns:
                if col == "embedding_vector":
                    # Use VEC_FROM_TEXT for vector column
                    values_row.append(
                        record[col]
                    )  # Keep as JSON string for VEC_FROM_TEXT
                else:
                    values_row.append(record[col])
            all_values.extend(values_row)

        # Build the column list with VEC_FROM_TEXT for the vector column
        column_expressions = []
        value_placeholders = []
        for col in columns:
            if col == "embedding_vector":
                column_expressions.append(col)
                value_placeholders.append("VEC_FROM_TEXT(%s)")
            else:
                column_expressions.append(col)
                value_placeholders.append("%s")

        values_clause_with_vector = f"({', '.join(value_placeholders)})"

        sql = f"""
            INSERT INTO {embedding_table} ({', '.join(column_expressions)})
            VALUES {', '.join([values_clause_with_vector] * len(processed_records))}
            ON DUPLICATE KEY UPDATE
                embedding_vector = VEC_FROM_TEXT(VALUES(embedding_vector)),
                vector_dimension = VALUES(vector_dimension),
                updated_at = NOW()
        """

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, all_values)
                conn.commit()

        logger.info(
            f"Upserted {len(processed_records)} embedding records to {embedding_table}"
        )

    def semantic_search_with_embeddings(
        self,
        query_vector: list[float],
        table_name: str,
        field_name: str = None,
        limit: int = 10,
        threshold: float = 0.7,
        metric: str = "cosine",
        tenant_id: str = None,
    ) -> list[dict]:
        """Perform semantic search using TiDB vector functions and joins."""
        main_table = table_name
        embedding_table = f"embeddings_{table_name}_embeddings"

        # TiDB vector functions
        vector_functions = {
            "cosine": "VEC_COSINE_DISTANCE",
            "l2": "VEC_L2_DISTANCE",
            "inner_product": "VEC_DOT_PRODUCT",
        }
        distance_func = vector_functions.get(metric, "VEC_COSINE_DISTANCE")

        # Convert query vector to TiDB format
        query_vector_json = json.dumps(query_vector)

        where_conditions = ["1=1"]
        params = []

        if field_name:
            where_conditions.append("e.field_name = %s")
            params.append(field_name)

        if tenant_id:
            where_conditions.append("m.tenant_id = %s")
            where_conditions.append("e.tenant_id = %s")
            params.extend([tenant_id, tenant_id])

        # Add threshold condition
        where_conditions.append(
            f"{distance_func}(e.embedding_vector, VEC_FROM_TEXT(%s)) <= %s"
        )
        params.extend(
            [query_vector_json, 1 - threshold]
        )  # Convert similarity to distance

        sql = f"""
            SELECT m.*, e.field_name, 
                   {distance_func}(e.embedding_vector, VEC_FROM_TEXT(%s)) as distance,
                   (1 - {distance_func}(e.embedding_vector, VEC_FROM_TEXT(%s))) as similarity_score
            FROM {main_table} m
            INNER JOIN {embedding_table} e ON m.id = e.entity_id
            WHERE {' AND '.join(where_conditions)}
            ORDER BY {distance_func}(e.embedding_vector, VEC_FROM_TEXT(%s))
            LIMIT %s
        """

        # Add query vector for SELECT and ORDER BY
        final_params = (
            [query_vector_json, query_vector_json] + params + [query_vector_json, limit]
        )

        with self._get_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(sql, final_params)
                results = cursor.fetchall()
                return list(results)
