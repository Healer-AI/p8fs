"""PostgreSQL SQL provider implementation with automatic connection management.

This provider supports PostgreSQL 14+ with pgvector extension for embeddings and 
Apache AGE for graph operations. All operations automatically handle connections.

Quick Start Examples:
    >>> from p8fs.providers import get_provider
    >>> provider = get_provider()  # Gets PostgreSQL provider from config
    >>> 
    >>> # KV Storage (temporary data with TTL)
    >>> import asyncio
    >>> 
    >>> async def kv_example():
    ...     kv = provider.kv
    ...     
    ...     # Store session data with 1 hour TTL
    ...     await kv.put("session:user123", {
    ...         "user_id": "user123",
    ...         "ip": "192.168.1.1",
    ...         "last_active": "2024-01-01T12:00:00Z"
    ...     }, ttl_seconds=3600)
    ...     
    ...     # Get value
    ...     session = await kv.get("session:user123")
    ...     print(session["ip"])  # "192.168.1.1"
    ...     
    ...     # Scan by prefix
    ...     all_sessions = await kv.scan("session:", limit=100)
    >>> 
    >>> # SQL Operations (no connection management needed!)
    >>> 
    >>> # Get all language models
    >>> models = provider.execute("SELECT * FROM language_model_apis ORDER BY name")
    >>> for model in models:
    ...     print(f"{model['name']}: {model['base_uri']}")
    >>> 
    >>> # Query with parameters
    >>> openai_models = provider.execute(
    ...     "SELECT name, completions_uri FROM language_model_apis WHERE base_uri LIKE %s",
    ...     ("%openai.com%",)
    ... )
    >>> 
    >>> # Use select_where for convenient filtering
    >>> recent_models = provider.select_where(
    ...     "language_model_apis",
    ...     where={
    ...         "created_at__gte": "2024-01-01",
    ...         "name__like": "gpt%"
    ...     },
    ...     fields=["name", "completions_uri", "created_at"],
    ...     order_by=["-created_at"],  # Newest first
    ...     limit=10
    ... )
    >>> 
    >>> # Insert with RETURNING
    >>> new_model = provider.execute(
    ...     '''INSERT INTO language_model_apis 
    ...        (name, base_uri, scheme, completions_uri, tenant_id) 
    ...        VALUES (%s, %s, %s, %s, %s) 
    ...        RETURNING *''',
    ...     ("my-llm", "https://api.mycompany.com", "https", "/v1/completions", "default")
    ... )
    >>> print(f"Created model with ID: {new_model[0]['id']}")
    >>> 
    >>> # Update
    >>> result = provider.execute(
    ...     "UPDATE language_model_apis SET token = %s WHERE name = %s",
    ...     ("new-secret-key", "my-llm")
    ... )
    >>> print(f"Updated {result[0]['affected_rows']} rows")

Reference implementation based on proven patterns from:
- External PostgreSQL service implementations
- SQL model helper utilities

Original KV Storage Usage Examples:
    from p8fs.providers.postgresql import PostgreSQLProvider
    
    provider = PostgreSQLProvider()
    kv = provider.kv
    
    # Device authorization flow
    await kv.put("device-auth:abc123", {
        "device_code": "abc123",
        "user_code": "A1B2-C3D4", 
        "status": "pending",
        "client_id": "desktop_app"
    }, ttl_seconds=600)
    
    # Retrieve and approve
    auth_data = await kv.get("device-auth:abc123")
    auth_data["status"] = "approved"
    auth_data["access_token"] = "jwt_token_here"
    await kv.put("device-auth:abc123", auth_data, ttl_seconds=300)
    
    # Scan for pending requests
    pending = await kv.scan("device-auth:", limit=10)
    user_codes = await kv.scan("user-code:", limit=10)
    
    # Find by field value
    request = await kv.find_by_field("user_code", "A1B2-C3D4", "device-auth:")

The KV provider uses PostgreSQL AGE graph functions (p8.put_kv, p8.get_kv, p8.scan_kv)
for graph-based temporary storage with TTL support.
"""

from typing import Any

import psycopg2
import psycopg2.extras
from p8fs_cluster.config import config
from p8fs_cluster.logging import get_logger
from tenacity import retry, stop_after_attempt, wait_fixed

from .base import BaseSQLProvider
from .kv import BaseKVProvider, PostgreSQLKVProvider

logger = get_logger(__name__)


class PostgreSQLProvider(BaseSQLProvider):
    """PostgreSQL-specific SQL provider with pgvector support."""

    def __init__(self):
        super().__init__(dialect="postgresql")
        self._connection = None
        self._connection_string = None
        self._kv = None

    def get_dialect_name(self) -> str:
        """Get the dialect name for this provider."""
        return "postgresql"

    def get_connection_string(
        self,
        host: str = "localhost",
        port: int = 5438,
        user: str = "postgres",
        password: str = "postgres",
        # database: str = "p8fs",
        database: str = "app",
        **kwargs,
    ) -> str:
        """Generate PostgreSQL connection string."""
        auth = f"{user}:{password}@" if password else f"{user}@"
        return f"postgresql://{auth}{host}:{port}/{database}"

    def get_vector_type(self) -> str:
        """PostgreSQL uses pgvector extension."""
        return "vector"

    def get_json_type(self) -> str:
        """PostgreSQL JSONB type for better performance."""
        return "JSONB"

    @property
    def kv(self) -> BaseKVProvider:
        """Get KV storage provider for temporary data like device authorization."""
        if not self._kv:
            self._kv = PostgreSQLKVProvider(self)
        return self._kv

    def supports_vector_operations(self) -> bool:
        """PostgreSQL supports vector operations via pgvector."""
        return True

    def _reopen_connection(self) -> Any:
        """Reopen PostgreSQL connection with retry logic.

        Based on percolate PostgresService._reopen_connection pattern.
        """
        if self._connection:
            try:
                self._connection.close()
            except Exception as e:
                # Log close errors but continue cleanup
                logger.debug(f"Error closing PostgreSQL connection: {e}")
            self._connection = None

        @retry(wait=wait_fixed(1), stop=stop_after_attempt(4), reraise=True)
        def open_connection_with_retry(conn_string):
            logger.trace(
                f"Opening PostgreSQL connection: {conn_string.split('@')[1] if '@' in conn_string else conn_string}"
            )
            return psycopg2.connect(conn_string, connect_timeout=5) 

        self._connection = open_connection_with_retry(self._connection_string)
        self._connection.autocommit = False

        # Test connection
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        logger.trace("PostgreSQL connection reopened successfully")
        return self._connection

    def apply_user_context(self, connection: Any, user_id: str, tenant_id: str):
        """Apply user context for row-level security.

        Based on percolate PostgresService pattern.
        """
        try:
            with connection.cursor() as cursor:
                # Call the p8.set_user_context function if it exists
                cursor.execute(
                    "SELECT p8.set_user_context(%s::uuid, %s::uuid)",
                    (user_id, tenant_id),
                )
                result = cursor.fetchone()
                logger.debug(
                    f"Applied user context: user={user_id}, tenant={tenant_id}, result={result}"
                )
        except psycopg2.Error as e:
            # Function might not exist in test environments
            logger.warning(
                f"Could not apply user context (function may not exist): {e}"
            )

    def connect_sync(self, connection_string: str | None = None) -> Any:
        """Create synchronous PostgreSQL connection using psycopg2.

        Based on percolate PostgresService connection patterns.
        """
        self._connection_string = connection_string or config.pg_connection_string

        # Check if we have a valid connection
        if self._connection:
            try:
                # Test if connection is still valid
                self._connection.poll()
                if self._connection.closed == 0:
                    return self._connection
            except Exception:
                logger.debug("Existing connection is invalid, reopening...")

        # Reopen connection
        return self._reopen_connection()

    def connect_async(self, connection_string: str | None = None) -> Any:
        """Create asynchronous PostgreSQL connection.

        For now, returns sync connection. Can be upgraded to asyncpg later.
        """
        logger.trace(
            "Async connection requested, returning sync connection (asyncpg not implemented yet)"
        )
        return self.connect_sync(connection_string)

    def execute(
        self, query: str, params: tuple | None = None, connection: Any | None = None
    ) -> list[dict[str, Any]]:
        print("-----------------------------------------------------------")
        """Execute query and return results as dict collection.

        Automatically handles connection if not provided.

        Args:
            query: SQL query to execute
            params: Optional query parameters
            connection: Optional connection to use. If None, creates and manages one automatically.

        Returns:
            List of dictionaries with query results

        Examples:
            >>> provider = PostgreSQLProvider()
            >>>
            >>> # Simple select
            >>> models = provider.execute("SELECT * FROM language_model_apis WHERE name = %s", ("gpt-4",))
            >>>
            >>> # Insert with returning
            >>> result = provider.execute(
            ...     "INSERT INTO sessions (id, summary) VALUES (%s, %s) RETURNING *",
            ...     ("sess-123", "Test session")
            ... )
            >>>
            >>> # Update
            >>> provider.execute(
            ...     "UPDATE language_model_apis SET token = %s WHERE name = %s",
            ...     ("new-token", "gpt-4")
            ... )
        """

        # Auto-manage connection if not provided
        auto_managed = connection is None
        if auto_managed:
            connection = self.connect_sync()

        cursor = None
        try:
            cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            logger.debug(f"Executing query: {query[:100]}...")
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Handle different query types
            if query.strip().upper().startswith(("SELECT", "WITH")):
                # Fetch results for SELECT queries
                results = cursor.fetchall()
                # Convert RealDictRow to regular dict
                return [dict(row) for row in results]
            else:
                # For INSERT/UPDATE/DELETE, commit and return affected rows info
                connection.commit()
                return [{"affected_rows": cursor.rowcount}]

        except psycopg2.Error as e:
            logger.error(f"Query execution failed: {e}")
            if connection:
                connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
            # Only close connection if we created it
            if auto_managed and connection and not connection.closed:
                connection.close()

    async def async_execute(
        self, connection: Any, query: str, params: tuple | None = None
    ) -> list[dict[str, Any]]:
        """Execute query asynchronously.

        Automatically handles connection if not provided.

        For now, calls sync version. Can be upgraded to asyncpg later.
        """
        return self.execute(query, params, connection)

    def create_table_sql(self, model_class: type["AbstractModel"]) -> str:
        """Generate PostgreSQL-optimized CREATE TABLE SQL."""
        schema = model_class.to_sql_schema()
        table_name = schema["table_name"]

        # Generate column definitions
        columns = []
        for field_name, field_info in schema["fields"].items():
            # Get the Python type annotation
            python_type = field_info.get("type")

            # Map the Python type to SQL type
            if python_type:
                column_type = self.map_python_type(python_type)
            elif "sql_type" in field_info:
                column_type = field_info["sql_type"]
            else:
                column_type = "TEXT"  # Default fallback

            # Double-check: Override if we detect it's a JSON type
            if field_info.get("is_json", False):
                column_type = "JSONB"

            constraints = []

            if field_info.get("is_primary_key"):
                constraints.append("PRIMARY KEY")
            if field_info.get("nullable", True) is False:
                constraints.append("NOT NULL")
            if field_info.get("unique", False):
                constraints.append("UNIQUE")
            
            # Add DEFAULT for timestamp fields
            default_clause = ""
            if field_name in ["created_at", "updated_at"] and column_type == "TIMESTAMPTZ":
                default_clause = " DEFAULT NOW()"

            constraint_str = " " + " ".join(constraints) if constraints else ""
            columns.append(f"    {field_name} {column_type}{default_clause}{constraint_str}")

        # Add system fields if not already defined in the model
        # NOTE: These are system fields managed by the repository layer
        existing_fields = set(schema["fields"].keys())

        # Add tenant_id if tenant isolation is required
        if schema.get("tenant_isolated", False):
            if "tenant_id" not in existing_fields:
                columns.append("    tenant_id TEXT NOT NULL")

        # Add system timestamps - databases should manage these with triggers
        if "created_at" not in existing_fields:
            columns.append("    created_at TIMESTAMPTZ DEFAULT NOW()")
        if "updated_at" not in existing_fields:
            columns.append("    updated_at TIMESTAMPTZ DEFAULT NOW()")

        # CRITICAL: Always specify schema explicitly to avoid AGE extension conflicts
        # The AGE extension sets search_path with ag_catalog first, which causes
        # CREATE TABLE without schema to create in ag_catalog instead of public
        # This ensures all application tables are created in the correct schema
        qualified_table_name = (
            table_name if "." in table_name else f"public.{table_name}"
        )

        columns_sql = ",\n".join(columns)
        sql = f"""CREATE TABLE IF NOT EXISTS {qualified_table_name} (
{columns_sql}
);"""

        # Add GIN indexes for JSON fields
        additional_indexes = []
        for field_name, field_info in schema["fields"].items():
            if field_info.get("is_json", False):
                additional_indexes.append(
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{field_name}_gin ON {table_name} USING GIN ({field_name});"
                )

        if additional_indexes:
            sql += "\n\n" + "\n".join(additional_indexes)

        # Add composite unique constraint for business key + tenant_id if needed
        business_key = None
        for field_name, field_info in schema["fields"].items():
            if field_info.get("is_key", False):
                business_key = field_name
                break
        
        if business_key and schema.get("tenant_isolated", False):
            # Add composite unique constraint for multi-tenant uniqueness
            constraint_name = f"{table_name}_{business_key}_tenant_id_key"
            sql += f"\n\n-- Ensure business key is unique per tenant\nALTER TABLE {qualified_table_name} DROP CONSTRAINT IF EXISTS {constraint_name};\nALTER TABLE {qualified_table_name} ADD CONSTRAINT {constraint_name} UNIQUE ({business_key}, tenant_id);"

        # Add call to register_entities function for all tables (except kv_storage)
        # Skip KV storage and other system tables
        if table_name != "kv_storage":
            # Get the key field from the schema - no hardcoded defaults
            key_field = schema["key_field"]

            # Add register_entities call with p8graph
            sql += f"\n\n-- Register entity for graph integration\nSELECT * FROM p8.register_entities('{table_name}', '{key_field}', false, 'p8graph');"

        # Add triggers for automatic timestamp management
        # The update_updated_at_column() function is defined in 00_install.sql
        trigger_sql = f"""
-- Create trigger for automatic updated_at timestamp
DROP TRIGGER IF EXISTS update_{table_name}_updated_at ON {qualified_table_name};
CREATE TRIGGER update_{table_name}_updated_at 
    BEFORE UPDATE ON {qualified_table_name}
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();"""
        
        sql += "\n" + trigger_sql

        return sql

    def create_embedding_table_sql(self, model_class: type["AbstractModel"]) -> str:
        """Generate PostgreSQL embedding table with vector indexes."""
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
        
        # Always use 'id' as the primary key for foreign key references
        primary_key_field = 'id'
        
        # Get the actual SQL type of the id field
        primary_key_info = schema["fields"]['id']
        primary_key_sql_type = self.map_python_type(primary_key_info["type"])

        # Determine vector dimensions based on embedding providers
        vector_dims = self._get_vector_dimensions_for_model(schema)

        # NOTE: System fields (created_at, updated_at) are always added to embedding tables
        # These should be managed by database triggers for automatic timestamping
        sql = f"""-- Create embeddings schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS embeddings;

CREATE TABLE IF NOT EXISTS {embedding_table_name} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id {primary_key_sql_type} NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(255) NOT NULL,
    embedding_vector vector({vector_dims}),
    vector_dimension INTEGER DEFAULT {vector_dims},
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (entity_id) REFERENCES public.{main_table_name}({primary_key_field}) ON DELETE CASCADE
);"""

        # Add tenant isolation if required
        if schema.get("tenant_isolated", False):
            sql = sql.replace(
                f"embedding_vector vector({vector_dims}),",
                f"embedding_vector vector({vector_dims}),\n    tenant_id TEXT NOT NULL,",
            )
            # Add unique constraint for tenant-isolated embeddings
            sql = sql.replace(
                "ON DELETE CASCADE\n);",
                "ON DELETE CASCADE,\n    UNIQUE(entity_id, field_name, tenant_id)\n);",
            )
        else:
            # Add unique constraint for non-tenant embeddings
            sql = sql.replace(
                "ON DELETE CASCADE\n);",
                "ON DELETE CASCADE,\n    UNIQUE(entity_id, field_name)\n);",
            )

        # Add vector-specific indexes
        index_prefix = f"{main_table_name}_embeddings"
        vector_indexes = [
            f"CREATE INDEX IF NOT EXISTS idx_{index_prefix}_vector_cosine ON {embedding_table_name} USING ivfflat (embedding_vector vector_cosine_ops);",
            f"CREATE INDEX IF NOT EXISTS idx_{index_prefix}_vector_l2 ON {embedding_table_name} USING ivfflat (embedding_vector vector_l2_ops);",
            f"CREATE INDEX IF NOT EXISTS idx_{index_prefix}_vector_ip ON {embedding_table_name} USING ivfflat (embedding_vector vector_ip_ops);",
            f"CREATE INDEX IF NOT EXISTS idx_{index_prefix}_entity_field ON {embedding_table_name} (entity_id, field_name);",
            f"CREATE INDEX IF NOT EXISTS idx_{index_prefix}_provider ON {embedding_table_name} (embedding_provider);",
            f"CREATE INDEX IF NOT EXISTS idx_{index_prefix}_field_provider ON {embedding_table_name} (field_name, embedding_provider);",
        ]

        return sql + "\n\n" + "\n".join(vector_indexes)

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

    def get_vector_operator(self, metric: str = "cosine") -> str:
        """Get PostgreSQL vector distance operator."""
        operators = {"cosine": "<=>", "l2": "<->", "inner_product": "<#>"}
        return operators.get(metric, "<=>")

    def get_vector_distance_function(self, metric: str = "cosine") -> str:
        """Get PostgreSQL vector distance operator (same as get_vector_operator for PostgreSQL)."""
        return self.get_vector_operator(metric)

    def vector_similarity_search_sql(
        self,
        model_class: type["AbstractModel"],
        query_vector: list[float],
        field_name: str,
        limit: int = 10,
        threshold: float = 0.7,
        metric: str = "cosine",
    ) -> tuple[str, tuple]:
        """Generate PostgreSQL-optimized vector similarity search."""
        schema = model_class.to_sql_schema()
        embedding_table_name = f"embeddings.{schema['table_name']}_embeddings"
        operator = self.get_vector_operator(metric)

        vector_str = f"[{','.join(map(str, query_vector))}]"

        if metric == "cosine":
            # For cosine, convert distance to similarity
            sql = f"""
                SELECT entity_id, field_name, embedding_vector,
                       1 - (embedding_vector {operator} %s::vector) as similarity
                FROM {embedding_table_name}
                WHERE field_name = %s
                AND 1 - (embedding_vector {operator} %s::vector) > %s
                ORDER BY embedding_vector {operator} %s::vector
                LIMIT %s
            """
            params = (vector_str, field_name, vector_str, threshold, vector_str, limit)
        else:
            # For L2 and inner product, use distance directly
            distance_threshold = 1.0 - threshold  # Convert similarity to distance
            sql = f"""
                SELECT entity_id, field_name, embedding_vector,
                       embedding_vector {operator} %s::vector as distance
                FROM {embedding_table_name}
                WHERE field_name = %s
                AND embedding_vector {operator} %s::vector < %s
                ORDER BY embedding_vector {operator} %s::vector
                LIMIT %s
            """
            params = (
                vector_str,
                field_name,
                vector_str,
                distance_threshold,
                vector_str,
                limit,
            )

        return sql.strip(), params

    def upsert_sql(
        self, model_class: type["AbstractModel"], values: dict[str, Any]
    ) -> tuple[str, tuple]:
        """Generate PostgreSQL UPSERT SQL using ON CONFLICT syntax.

        Based on percolate SqlModelHelper.upsert_query() pattern with psycopg2.extras.execute_values
        for batch processing and proper SQL parameter binding.
        """

        schema = model_class.to_sql_schema()
        table_name = schema["table_name"]
        primary_key = "id"  # Always use id as the primary key for ON CONFLICT

        # Serialize values for database compatibility (based on SqlModelHelper.serialize_for_db)
        serialized_values = self.serialize_for_db(values)

        # Get field names and build SQL
        columns = list(serialized_values.keys())
        non_id_fields = [f for f in columns if f != primary_key]

        # Use %s placeholders for psycopg2 parameter binding
        insert_columns = ", ".join(columns)
        insert_placeholders = ", ".join(["%s"] * len(columns))

        # Build UPDATE SET clause for non-primary key fields
        update_assignments = [f"{col} = EXCLUDED.{col}" for col in non_id_fields]

        # Only add updated_at if it's not already in the model fields
        if "updated_at" not in serialized_values:
            update_assignments.append("updated_at = NOW()")

        sql = f"""
            INSERT INTO {table_name} ({insert_columns})
            VALUES ({insert_placeholders})
            ON CONFLICT ({primary_key})
            DO UPDATE SET {', '.join(update_assignments)}
        """

        # Return SQL and values as tuple (psycopg2 format)
        params = tuple(serialized_values.values())
        return sql.strip(), params

    def serialize_for_db(self, data: dict[str, Any]) -> dict[str, Any]:
        """Serialize model data for database storage.

        Based on SqlModelHelper.serialize_for_db() with proper type adaptation
        for PostgreSQL/psycopg2 compatibility.
        """
        import json
        import uuid
        import datetime

        def adapt_value(value):
            """Adapt Python values for PostgreSQL storage."""
            if value is None:
                return None

            # UUID objects - convert to string
            if isinstance(value, uuid.UUID):
                return str(value)

            # Enum values - get the actual value
            if (
                hasattr(value, "value")
                and hasattr(value, "__class__")
                and hasattr(value.__class__, "__bases__")
            ):
                if any("Enum" in str(base) for base in value.__class__.__bases__):
                    return value.value

            # String escaping for SQL safety (psycopg2 handles this automatically)
            if isinstance(value, str):
                return value

            # Collections - convert to JSON string for JSONB storage
            if isinstance(value, (dict, list)):
                def json_serializer(obj):
                    """Custom JSON serializer for nested objects."""
                    # Handle enums
                    if hasattr(obj, 'value') and hasattr(obj.__class__, '__bases__'):
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

            # Handle datetime objects - psycopg2 handles these automatically
            if isinstance(value, (datetime.datetime, datetime.date)):
                return value

            # Boolean values - psycopg2 handles these
            if isinstance(value, bool):
                return value

            return value

        # Apply adaptation to all values
        return {k: adapt_value(v) for k, v in data.items()}

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
        """Generate PostgreSQL semantic search SQL with JOIN to main entity table."""
        schema = model_class.to_sql_schema()
        main_table = f"public.{schema['table_name']}"
        embedding_table = f"embeddings.{schema['table_name']}_embeddings"
        primary_key = schema["key_field"]
        operator = self.get_vector_operator(metric)

        vector_str = f"[{','.join(map(str, query_vector))}]"

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

        if metric == "cosine":
            # For cosine, convert distance to similarity (1 - distance)
            similarity_expr = f"1 - (e.embedding_vector {operator} %s::vector)"
            threshold_condition = f"{similarity_expr} > %s"
            order_clause = f"e.embedding_vector {operator} %s::vector ASC"  # Lower distance = better

            sql = f"""
                SELECT m.*, 
                       {similarity_expr} as similarity_score,
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
            params.append(vector_str)  # For similarity calculation
            if field_name:
                params.append(field_name)
            else:
                embedding_fields = schema.get("embedding_fields", [])
                params.extend(embedding_fields)
            if tenant_id and schema.get("tenant_isolated", True):
                params.extend([tenant_id, tenant_id])
            params.extend([vector_str, threshold, vector_str, limit])

        else:
            # For L2 and inner product, use distance directly
            distance_expr = f"e.embedding_vector {operator} %s::vector"
            distance_threshold = 1.0 - threshold  # Convert similarity to distance
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
            params.append(vector_str)  # For distance calculation
            if field_name:
                params.append(field_name)
            else:
                embedding_fields = schema.get("embedding_fields", [])
                params.extend(embedding_fields)
            if tenant_id and schema.get("tenant_isolated", True):
                params.extend([tenant_id, tenant_id])
            params.extend([vector_str, distance_threshold, vector_str, limit])

        return sql.strip(), tuple(params)

    def get_full_text_search_sql(
        self,
        model_class: type["AbstractModel"],
        query: str,
        fields: list[str],
        limit: int = 10,
    ) -> tuple[str, tuple]:
        """Generate PostgreSQL full-text search SQL."""
        schema = model_class.to_sql_schema()
        table_name = schema["table_name"]

        # Create tsvector from specified fields
        coalesce_fields = [f"COALESCE({field}, '')" for field in fields]
        tsvector_fields = " || ' ' || ".join(coalesce_fields)

        sql = f"""
            SELECT *, ts_rank(to_tsvector('english', {tsvector_fields}), plainto_tsquery('english', %s)) as rank
            FROM {table_name}
            WHERE to_tsvector('english', {tsvector_fields}) @@ plainto_tsquery('english', %s)
            ORDER BY rank DESC
            LIMIT %s
        """

        params = (query, query, limit)
        return sql, params

    def create_full_text_index_sql(self, table_name: str, fields: list[str]) -> str:
        """Create PostgreSQL full-text search index."""
        coalesce_fields = [f"COALESCE({field}, '')" for field in fields]
        fields_expr = " || ' ' || ".join(coalesce_fields)
        tsvector_expr = f"to_tsvector('english', {fields_expr})"
        return f"CREATE INDEX idx_{table_name}_fts ON {table_name} USING GIN ({tsvector_expr});"

    def get_vacuum_sql(self, table_name: str, full: bool = False) -> str:
        """Generate VACUUM SQL for maintenance."""
        if full:
            return f"VACUUM FULL ANALYZE {table_name};"
        return f"VACUUM ANALYZE {table_name};"

    def get_migration_sql(self, from_version: str, to_version: str) -> list[str]:
        """Get PostgreSQL-specific migration SQL."""
        migrations = []

        # Example migration patterns
        if from_version == "1.0.0" and to_version == "1.1.0":
            migrations.extend(
                [
                    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS version VARCHAR(50) DEFAULT '1.1.0'",
                    "UPDATE documents SET version = '1.1.0' WHERE version IS NULL",
                ]
            )

        return migrations

    def get_partition_sql(
        self, table_name: str, partition_key: str, partition_type: str = "RANGE"
    ) -> str:
        """Generate table partitioning SQL."""
        return f"""
            ALTER TABLE {table_name} 
            PARTITION BY {partition_type} ({partition_key});
        """

    def map_python_type(self, type_hint: Any) -> str:
        """
        Map Python type to PostgreSQL type.

        NOTE: For Union types like UUID | str, the first type takes precedence in database schema.
        UUID types are preferred over str for database storage if PostgreSQL supports it.
        When serializing for upserts, UUID values are converted to str for JSON compatibility.
        """
        import typing
        import types
        from datetime import datetime
        from uuid import UUID

        # Special handling for dict types from typing module
        # Check if it's dict or typing.Dict first
        if hasattr(type_hint, "__origin__"):
            origin = type_hint.__origin__
            # Handle typing.Dict, typing.List, etc.
            if origin is dict or (
                hasattr(typing, "Dict") and origin is getattr(typing, "Dict")
            ):
                return "JSONB"
            elif origin is list or (
                hasattr(typing, "List") and origin is getattr(typing, "List")
            ):
                # Check if it's a vector (list of floats)
                args = getattr(type_hint, "__args__", ())
                if args and args[0] == float:
                    return "vector(1536)"
                return "JSONB"

        # Handle Union types (Optional and other unions)
        # Support both typing.Union and types.UnionType (Python 3.10+ syntax)
        is_union = (
            hasattr(type_hint, "__origin__") and type_hint.__origin__ is typing.Union
        ) or (hasattr(types, "UnionType") and isinstance(type_hint, types.UnionType))

        if is_union:
            # Get the non-None type from Union, prioritizing database-native types
            args = [arg for arg in type_hint.__args__ if arg is not type(None)]
            if args:
                # Check if any of the args is dict type
                for arg in args:
                    if arg == dict or (
                        hasattr(arg, "__origin__") and arg.__origin__ is dict
                    ):
                        return "JSONB"
                    elif arg == list or (
                        hasattr(arg, "__origin__") and arg.__origin__ is list
                    ):
                        # Check if it's a vector type (List[float])
                        if (
                            hasattr(arg, "__args__")
                            and arg.__args__
                            and arg.__args__[0] == float
                        ):
                            return "vector(1536)"
                        return "JSONB"

                # Prioritize UUID over str if both are present (database schema preference)
                if UUID in args:
                    type_hint = UUID
                else:
                    type_hint = args[0]  # First type takes precedence

        # Basic type mappings
        if type_hint == str:
            return "TEXT"
        elif type_hint == int:
            return "BIGINT"
        elif type_hint == float:
            return "DOUBLE PRECISION"
        elif type_hint == bool:
            return "BOOLEAN"
        elif type_hint == datetime:
            return "TIMESTAMPTZ"
        elif type_hint == UUID:
            return "UUID"
        elif type_hint == dict or type_hint == list:
            return "JSONB"

        # Collection types with type arguments
        if hasattr(type_hint, "__origin__"):
            origin = type_hint.__origin__
            if origin is list or origin is list:
                args = getattr(type_hint, "__args__", ())
                if args and args[0] == float:
                    # For vector fields, use dynamic dimensions (will be 1536 by default)
                    return "vector(1536)"  # This gets updated in create_embedding_table_sql
                return "JSONB"
            elif origin is dict or origin is dict or origin is set or origin is set:
                return "JSONB"

        # Default to TEXT for unknown types
        return "TEXT"

    def batch_upsert_sql(
        self, model_class: type["AbstractModel"], values_list: list[dict[str, Any]]
    ) -> tuple[str, list[tuple]]:
        """Generate PostgreSQL batch UPSERT using execute_values.

        Creates SQL template suitable for psycopg2.extras.execute_values
        with ON CONFLICT DO UPDATE for upsert behavior.

        Args:
            model_class: Model class to generate SQL for
            values_list: List of dictionaries with field values

        Returns:
            Tuple[str, List[tuple]]: SQL template and parameters list

        Raises:
            ValueError: If values_list is empty
        """
        if not values_list:
            raise ValueError("Empty values list for batch upsert")

        schema = model_class.to_sql_schema()
        table_name = schema["table_name"]
        primary_key = "id"  # Always use id as the primary key for ON CONFLICT

        # Use first row to determine columns
        first_row = values_list[0]
        columns = list(first_row.keys())
        non_id_fields = [f for f in columns if f != primary_key]

        # Build the SQL template for execute_values
        insert_columns = ", ".join(columns)
        value_template = "(" + ", ".join(["%s"] * len(columns)) + ")"

        # Build UPDATE SET clause
        update_assignments = [f"{col} = EXCLUDED.{col}" for col in non_id_fields]

        # Only add updated_at if it's not already in the model fields
        if "updated_at" not in columns:
            update_assignments.append("updated_at = NOW()")

        sql = f"""
            INSERT INTO {table_name} ({insert_columns})
            VALUES %s
            ON CONFLICT ({primary_key})
            DO UPDATE SET {', '.join(update_assignments)}
        """

        # Serialize all rows
        params_list = []
        for row in values_list:
            serialized = self.serialize_for_db(row)
            params_list.append(tuple(serialized[col] for col in columns))

        return sql.strip(), params_list

    async def async_execute_batch(
        self,
        query: str,
        params_list: list[tuple],
        connection: Any,
        page_size: int = 1000,
    ) -> int:
        """Async execute batch operation using psycopg2.extras.execute_values."""
        try:
            import psycopg2.extras

            cursor = connection.cursor()

            # Use execute_values for efficient batch insert
            psycopg2.extras.execute_values(
                cursor, query, params_list, template=None, page_size=page_size
            )

            affected_rows = cursor.rowcount or len(params_list)
            cursor.close()

            return affected_rows

        except Exception as e:
            logger.error(f"Failed to async execute batch: {e}")
            raise

    def execute_batch(
        self,
        connection: Any,
        query: str,
        params_list: list[tuple],
        page_size: int = 1000,
    ) -> dict[str, Any]:
        """Execute batch operation using psycopg2.extras.execute_values.

        Based on percolate batch processing patterns for efficient bulk operations.
        """
        cursor = None
        try:
            cursor = connection.cursor()

            logger.debug(f"Executing batch operation with {len(params_list)} rows")

            # Check if this is an embedding table insert that needs a custom template
            if "embeddings" in query and "embedding_vector" in query:
                # For embedding tables, we need a custom template to handle NOW() functions
                template = "(%s, %s, %s, %s, %s::vector, %s, %s, NOW(), NOW())"
                psycopg2.extras.execute_values(
                    cursor,
                    query,
                    params_list,
                    template=template,
                    page_size=page_size,
                )
            else:
                # Use execute_values for efficient batch processing with default template
                psycopg2.extras.execute_values(
                    cursor,
                    query,
                    params_list,
                    template=None,  # Use default template from VALUES clause
                    page_size=page_size,
                )

            affected_rows = cursor.rowcount
            connection.commit()

            logger.info(f"Batch operation completed: {affected_rows} rows affected")
            return {"affected_rows": affected_rows, "batch_size": len(params_list)}

        except psycopg2.Error as e:
            logger.error(f"Batch execution failed: {e}")
            if connection:
                connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()

    def select_where(
        self,
        table_name: str,
        where: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        order_by: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Convenience method for SELECT queries with automatic connection handling.

        Args:
            table_name: Name of the table to query
            where: Dict of field filters. Supports operators via __ syntax:
                   - field__gt: greater than
                   - field__gte: greater than or equal
                   - field__lt: less than
                   - field__lte: less than or equal
                   - field__like: SQL LIKE pattern matching
                   - field__in: IN clause with list of values
            fields: List of fields to select (default: all fields)
            order_by: List of fields to order by. Prefix with - for DESC
            limit: Maximum number of rows to return
            offset: Number of rows to skip

        Returns:
            List of dictionaries with query results

        Examples:
            >>> # Get recent language models
            >>> models = provider.select_where(
            ...     "language_model_apis",
            ...     where={"created_at__gte": "2024-01-01"},
            ...     fields=["name", "base_uri"],
            ...     order_by=["-created_at"],
            ...     limit=10
            ... )
            >>>
            >>> # Find models by name pattern
            >>> gpt_models = provider.select_where(
            ...     "language_model_apis",
            ...     where={"name__like": "gpt%"},
            ...     order_by=["name"]
            ... )
        """
        # Build SELECT clause
        select_fields = ", ".join(fields) if fields else "*"
        sql = f"SELECT {select_fields} FROM {table_name}"
        params = []

        # Build WHERE clause
        if where:
            where_conditions = []
            for filter_key, filter_value in where.items():
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
                    elif operator == "like":
                        where_conditions.append(f"{field} LIKE %s")
                        params.append(filter_value)
                    elif operator == "in":
                        placeholders = ", ".join(["%s"] * len(filter_value))
                        where_conditions.append(f"{field} IN ({placeholders})")
                        params.extend(filter_value)
                else:
                    where_conditions.append(f"{filter_key} = %s")
                    params.append(filter_value)

            if where_conditions:
                sql += " WHERE " + " AND ".join(where_conditions)

        # Add ORDER BY
        if order_by:
            order_clauses = []
            for order_field in order_by:
                # Check if order_field already contains ASC/DESC
                upper_field = order_field.upper()
                if " ASC" in upper_field or " DESC" in upper_field:
                    # Already has direction, use as-is
                    order_clauses.append(order_field)
                elif order_field.startswith("-"):
                    # Django-style: -field means DESC
                    order_clauses.append(f"{order_field[1:]} DESC")
                else:
                    # Default to ASC
                    order_clauses.append(f"{order_field} ASC")
            sql += " ORDER BY " + ", ".join(order_clauses)

        # Add LIMIT and OFFSET
        if limit:
            sql += f" LIMIT {limit}"
        if offset:
            sql += f" OFFSET {offset}"

        # Execute with automatic connection handling
        return self.execute(sql, tuple(params) if params else None)

    def select_sql(
        self,
        model_class: type["AbstractModel"],
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: list[str] | None = None,
    ) -> tuple[str, tuple]:
        """Generate PostgreSQL SELECT with advanced filtering."""
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
                    elif operator == "ilike":
                        where_conditions.append(f"{field} ILIKE %s")
                        params.append(filter_value)
                    elif operator == "contains":
                        where_conditions.append(f"{field} @> %s::jsonb")
                        params.append(filter_value)
                    elif operator == "overlap":
                        where_conditions.append(f"{field} && %s::jsonb")
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
                # Check if order_field already contains ASC/DESC
                upper_field = order_field.upper()
                if " ASC" in upper_field or " DESC" in upper_field:
                    # Already has direction, use as-is
                    order_clauses.append(order_field)
                elif order_field.startswith("-"):
                    # Django-style: -field means DESC
                    order_clauses.append(f"{order_field[1:]} DESC")
                else:
                    # Default to ASC
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
        """Generate PostgreSQL DELETE with tenant isolation."""
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

    # Embedding Operations
    def insert_and_return_ids(self, entities: list[dict], table_name: str) -> list[str]:
        """Insert entities and return only their IDs for fast embedding processing."""
        if not entities:
            return []

        # Build bulk insert with RETURNING id
        columns = list(entities[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        values_clause = f"({placeholders})"

        all_values = []
        for entity in entities:
            all_values.extend([entity[col] for col in columns])

        sql = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES {', '.join([values_clause] * len(entities))}
            ON CONFLICT (id) DO UPDATE SET
                {', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col != 'id'])},
                updated_at = NOW()
            RETURNING id
        """

        conn = self.connect_sync()
        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute(sql, all_values)
            result = cursor.fetchall()
            conn.commit()
            return [row[0] for row in result]
        except psycopg2.Error as e:
            logger.error(f"Failed to insert and return IDs: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
            if conn and not conn.closed:
                conn.close()

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for batch of texts using configured embedding service."""
        try:
            from ..services.llm import get_embedding_service

            embedding_service = get_embedding_service()

            # Generate embeddings in batch for efficiency
            # Use encode_batch for better performance
            embeddings = embedding_service.encode_batch(texts)
            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate embeddings batch: {e}")
            raise

    def upsert_embeddings(self, embedding_records: list[dict], table_name: str) -> None:
        """Upsert embedding records using PostgreSQL-specific vector format."""
        if not embedding_records:
            return

        embedding_table = f"embeddings.{table_name}_embeddings"

        # Convert vectors to PostgreSQL vector format
        processed_records = []
        for record in embedding_records:
            processed_record = record.copy()
            # PostgreSQL pgvector format: '[0.1,0.2,0.3]'
            vector = processed_record["embedding_vector"]
            processed_record["embedding_vector"] = f"[{','.join(map(str, vector))}]"
            processed_records.append(processed_record)

        # Build bulk upsert
        columns = list(processed_records[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        values_clause = f"({placeholders})"

        all_values = []
        for record in processed_records:
            all_values.extend([record[col] for col in columns])

        sql = f"""
            INSERT INTO {embedding_table} ({', '.join(columns)})
            VALUES {', '.join([values_clause] * len(processed_records))}
            ON CONFLICT (entity_id, field_name, embedding_provider) 
            DO UPDATE SET
                embedding_vector = EXCLUDED.embedding_vector::vector,
                vector_dimension = EXCLUDED.vector_dimension,
                updated_at = NOW()
        """

        conn = self.connect_sync()
        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute(sql, all_values)
            conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Failed to upsert embeddings: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
            if conn and not conn.closed:
                conn.close()

        logger.info(
            f"Upserted {len(processed_records)} embedding records to {embedding_table}"
        )

    def get_entities(
        self, keys: list[str], userid: str | None = None
    ) -> list[dict[str, Any]]:
        """Get entities by keys using p8.get_entities function.

        This uses the AGE graph database function to lookup entities.

        Args:
            keys: List of entity keys to fetch
            userid: Optional user ID for access control

        Returns:
            List of entity dictionaries grouped by entity type
        """
        if not keys:
            return [{"status": "NO DATA", "message": "No keys provided"}]

        cursor = None
        try:
            conn = self.connect_sync()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Call p8.get_entities function
            cursor.execute("SELECT * FROM p8.get_entities(%s)", (keys,))
            result = cursor.fetchone()

            if not result:
                return [
                    {
                        "status": "NO DATA",
                        "message": f"No data found for keys: {keys}. Please try another method or approach.",
                    }
                ]

            # The function returns a JSONB object, extract and return it
            return [dict(result)]

        except psycopg2.Error as e:
            logger.error(f"Error calling get_entities: {e}")
            return [{"status": "ERROR", "message": f"Database error: {str(e)}"}]
        finally:
            if cursor:
                cursor.close()

    def add_node(
        self,
        node_key: str,
        node_label: str,
        properties: dict[str, Any] | None = None,
        userid: str | None = None,
    ) -> dict[str, Any]:
        """Add a node directly to the p8 graph.

        This is for special nodes outside the indexed entity system.

        Args:
            node_key: Unique key for the node
            node_label: Node type/label (e.g. 'DeviceAuth', 'Configuration')
            properties: Additional node properties as JSON
            userid: Optional user ID for access control

        Returns:
            Node data as dict or error dict
        """
        cursor = None
        try:
            conn = self.connect_sync()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Call p8.add_node function
            import json

            cursor.execute(
                "SELECT p8.add_node(%s, %s, %s::jsonb, %s)",
                (node_key, node_label, json.dumps(properties or {}), userid),
            )
            result = cursor.fetchone()

            if result and "add_node" in result:
                return result["add_node"]
            return {"status": "ERROR", "message": "Failed to add node"}

        except psycopg2.Error as e:
            logger.error(f"Error adding node: {e}")
            return {"status": "ERROR", "message": f"Database error: {str(e)}"}
        finally:
            if cursor:
                cursor.close()

    def get_nodes_by_key(
        self, keys: list[str], userid: str | None = None
    ) -> list[dict[str, Any]]:
        """Get graph nodes by their keys.

        Direct node retrieval without going through the entity system.

        Args:
            keys: List of node keys to fetch
            userid: Optional user ID for access control

        Returns:
            List of node data dictionaries
        """
        if not keys:
            return []

        cursor = None
        try:
            conn = self.connect_sync()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Call p8.get_graph_nodes_by_key function
            cursor.execute(
                "SELECT * FROM p8.get_graph_nodes_by_key(%s, %s)", (keys, userid)
            )
            results = cursor.fetchall()

            return [dict(row) for row in results]

        except psycopg2.Error as e:
            logger.error(f"Error getting nodes by key: {e}")
            return []
        finally:
            if cursor:
                cursor.close()

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
        """Perform semantic search joining embeddings with main entity table."""
        main_table = table_name
        embedding_table = f"embeddings.{table_name}_embeddings"

        # Use the correct vector operator for the metric
        operator = self.get_vector_operator(metric)

        # Convert query vector to PostgreSQL format
        query_vector_str = f"[{','.join(map(str, query_vector))}]"

        where_conditions = ["1=1"]
        params = []

        if field_name:
            where_conditions.append("e.field_name = %s")
            params.append(field_name)

        if tenant_id:
            where_conditions.append("m.tenant_id = %s")
            where_conditions.append("e.tenant_id = %s")
            params.extend([tenant_id, tenant_id])

        # Don't filter by threshold - just use limit and sort by best match first

        sql = f"""
            SELECT m.*, e.field_name, 
                   (e.embedding_vector {operator} %s::vector) as distance,
                   (1 - (e.embedding_vector {operator} %s::vector)) as score
            FROM {main_table} m
            INNER JOIN {embedding_table} e ON m.id = e.entity_id
            WHERE {' AND '.join(where_conditions)}
            ORDER BY e.embedding_vector {operator} %s::vector
            LIMIT %s
        """

        # Add query vector for SELECT, score calculation, ORDER BY, and limit
        final_params = (
            [query_vector_str, query_vector_str] + params + [query_vector_str, limit]
        )

        conn = self.connect_sync()
        cursor = None
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(sql, final_params)
            results = cursor.fetchall()
            return [dict(row) for row in results]
        except psycopg2.Error as e:
            logger.error(f"Semantic search failed: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if conn and not conn.closed:
                conn.close()
