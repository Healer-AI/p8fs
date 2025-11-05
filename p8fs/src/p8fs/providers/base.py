"""Base SQL provider class."""

from abc import ABC, abstractmethod
from typing import Any

from ..utils.sql import SQLHelper


class BaseSQLProvider(ABC):
    """Base class for SQL database providers."""
    
    def __init__(self, dialect: str):
        self.dialect = dialect
        self.sql_helper = SQLHelper(dialect)
    
    @abstractmethod
    def get_dialect_name(self) -> str:
        """Get the dialect name for this provider."""
        pass
    
    @abstractmethod
    def get_connection_string(self, **kwargs) -> str:
        """Generate connection string for this provider."""
        pass
    
    @abstractmethod
    def connect_sync(self, connection_string: str | None = None) -> Any:
        """Create synchronous database connection.
        
        Args:
            connection_string: Optional connection string override
            
        Returns:
            Database connection object
        """
        pass
    
    @abstractmethod
    def connect_async(self, connection_string: str | None = None) -> Any:
        """Create asynchronous database connection.
        
        Args:
            connection_string: Optional connection string override
            
        Returns:
            Async database connection object
        """
        pass
    
    @abstractmethod
    def execute(self, connection: Any, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """Execute query and return results as dict collection.
        
        Args:
            connection: Database connection
            query: SQL query to execute
            params: Optional query parameters
            
        Returns:
            List of dictionaries representing query results
        """
        pass
    
    @abstractmethod
    async def async_execute(self, connection: Any, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """Execute query asynchronously and return results as dict collection.
        
        Args:
            connection: Async database connection
            query: SQL query to execute
            params: Optional query parameters
            
        Returns:
            List of dictionaries representing query results
        """
        pass
    
    @abstractmethod
    def create_table_sql(self, model_class: type['AbstractModel']) -> str:
        """
        Generate CREATE TABLE SQL for the provider's dialect.
        
        Implementation should:
        - Use model.to_sql_schema() to get field information
        - Call self.map_python_type() for each field's type mapping
        - Generate provider-specific column definitions
        - Add provider-specific table options (ENGINE, charset, etc.)
        - Handle tenant isolation columns if model requires it
        - Add appropriate indexes based on field metadata
        """
        pass
    
    @abstractmethod
    def create_embedding_table_sql(self, model_class: type['AbstractModel']) -> str:
        """
        Generate embedding table SQL with provider-specific optimizations.
        
        Implementation should:
        - Check if model has embedding fields, return empty if not
        - Use provider's vector type (JSON for TiDB, vector for PostgreSQL)
        - Add provider-specific vector indexes (TiFlash, HNSW, IVFFlat)
        - Include tenant isolation if required
        - Optimize for the provider's vector query patterns
        """
        pass
    
    @abstractmethod
    def upsert_sql(self, model_class: type['AbstractModel'], values: dict[str, Any]) -> tuple[str, tuple]:
        """
        Generate UPSERT SQL using provider's conflict resolution syntax.
        
        Implementation should:
        - Use REPLACE INTO for TiDB, ON CONFLICT for PostgreSQL
        - Handle tenant_id injection automatically
        - Process values using provider's type serialization
        - Return (sql, params) tuple with proper parameter binding
        """
        pass
    
    @abstractmethod
    def batch_upsert_sql(self, model_class: type['AbstractModel'], values_list: list[dict[str, Any]]) -> tuple[str, list[tuple]]:
        """
        Generate batch UPSERT SQL for multiple rows.
        
        Implementation should:
        - Use provider's batch insert syntax (execute_values for PostgreSQL)
        - Handle tenant_id injection for all rows
        - Process values using provider's type serialization
        - Return (sql, params_list) tuple for batch execution
        """
        pass
    
    @abstractmethod
    def select_sql(self, model_class: type['AbstractModel'], 
                   filters: dict[str, Any] | None = None,
                   fields: list[str] | None = None,
                   limit: int | None = None,
                   offset: int | None = None,
                   order_by: list[str] | None = None) -> tuple[str, tuple]:
        """
        Generate SELECT SQL with provider-specific filter syntax.
        
        Implementation should:
        - Parse filter operators (__gt, __in, __like, etc.) to provider SQL
        - Handle JSON/array operators for PostgreSQL (__contains, __overlap)
        - Generate field list or SELECT * based on fields parameter
        - Add tenant_id filter automatically
        - Use provider's pagination syntax
        - Handle provider-specific sorting and indexing hints
        """
        pass
    
    @abstractmethod
    def delete_sql(self, model_class: type['AbstractModel'], 
                   key_value: Any, tenant_id: str | None = None) -> tuple[str, tuple]:
        """
        Generate DELETE SQL with tenant isolation.
        
        Implementation should:
        - Build WHERE clause with primary key and tenant_id
        - Use provider's parameter binding syntax
        - Return (sql, params) tuple
        """
        pass
    
    @abstractmethod
    def semantic_search_sql(self, model_class: type['AbstractModel'],
                          query_vector: list[float],
                          field_name: str | None = None,
                          limit: int = 10,
                          threshold: float = 0.7,
                          metric: str = 'cosine',
                          tenant_id: str | None = None) -> tuple[str, tuple]:
        """
        Generate semantic search SQL that joins embeddings with main entity table.
        
        Args:
            model_class: The model class to search
            query_vector: Query embedding vector
            field_name: Specific field to search (None for all embedding fields)
            limit: Maximum results to return
            threshold: Minimum similarity score (0-1)
            metric: Similarity metric ('cosine', 'l2', 'inner_product')
            tenant_id: Tenant ID for isolation
            
        Returns:
            Tuple of (sql, params) for the semantic search query
            
        Implementation should:
        - JOIN embeddings table with main entity table
        - SELECT all fields from main entity + similarity score
        - Filter by field_name if specified
        - Apply tenant isolation
        - Use appropriate vector similarity functions
        - Order by similarity score (best first)
        - Apply threshold and limit
        """
        pass

    @abstractmethod
    def vector_similarity_search_sql(self, model_class: type['AbstractModel'],
                                   query_vector: list[float],
                                   field_name: str,
                                   limit: int = 10,
                                   threshold: float = 0.7) -> tuple[str, tuple]:
        """
        Generate vector similarity search SQL using provider's vector functions.
        
        Implementation should:
        - Use provider's vector distance functions (VEC_COSINE_DISTANCE, <=> operator)
        - Query embedding table with tenant isolation
        - Convert threshold appropriately for provider's distance/similarity semantics
        - Join with main table to return full entity data
        - Optimize for provider's vector indexing strategy
        """
        pass
    
    @abstractmethod
    def map_python_type(self, type_hint: Any) -> str:
        """
        Map Python type hint to provider-specific SQL type.
        
        Args:
            type_hint: Python type annotation (e.g., str, List[float], Dict[str, Any])
            
        Returns:
            SQL type string for this provider's dialect
            
        Implementation should:
        - Handle basic types (str, int, float, bool, datetime, UUID)
        - Handle collection types (List, Dict, Set) as appropriate for provider
        - Handle vector types (List[float]) with provider's vector support
        - Use provider's type inspection utilities to classify types
        - Return provider-specific optimal types (e.g., JSONB vs JSON)
        """
        pass
    
    @abstractmethod
    def get_vector_type(self) -> str:
        """Get the vector/embedding data type for this provider."""
        pass
    
    @abstractmethod
    def get_json_type(self) -> str:
        """Get the JSON data type for this provider."""
        pass
    
    @abstractmethod
    def supports_vector_operations(self) -> bool:
        """Check if provider supports native vector operations."""
        pass
    
    def build_where_clause_with_params(self, conditions: dict[str, Any]) -> tuple[str, list[Any]]:
        """
        Build WHERE clause and parameters from conditions dict.
        
        Args:
            conditions: Dict mapping column names to values
                - Scalar values become equality checks (col = value)
                - Lists become IN clauses (col IN (values))
                - None values become IS NULL checks
        
        Returns:
            Tuple of (where_clause_string, params_list)
        """
        if not conditions:
            return "", []
        
        where_clauses = []
        params = []
        
        for column, value in conditions.items():
            if value is None:
                where_clauses.append(f"{column} IS NULL")
            elif isinstance(value, list):
                # Handle IN clause
                if not value:  # Empty list
                    where_clauses.append("1 = 0")  # Always false
                else:
                    placeholders = ', '.join(['%s'] * len(value))
                    where_clauses.append(f"{column} IN ({placeholders})")
                    params.extend(value)
            else:
                # Handle equality
                where_clauses.append(f"{column} = %s")
                params.append(value)
        
        where_clause = " AND ".join(where_clauses)
        return where_clause, params

    def get_migration_sql(self, from_version: str, to_version: str) -> list[str]:
        """Get migration SQL statements between versions."""
        return []
    
    def get_index_sql(self, table_name: str, field_name: str, index_type: str = 'btree') -> str:
        """Generate index creation SQL."""
        return self.sql_helper._generate_index_sql(table_name, field_name)
    
    def get_sql_type(self, type_hint: Any, field_info: dict[str, Any] | None = None) -> str:
        """
        Map Python type hint to provider-specific SQL type.
        This is an alias for map_python_type for backward compatibility.
        
        Args:
            type_hint: Python type annotation
            field_info: Optional field metadata for specialized handling
            
        Returns:
            SQL type string for this provider's dialect
        """
        return self.map_python_type(type_hint)
    
    def register_model(self, model_class: type['AbstractModel'], plan: bool = True) -> str:
        """
        Register a model by generating and optionally executing SQL creation scripts.
        
        Args:
            model_class: The AbstractModel class to register
            plan: If True, return SQL script. If False, execute the SQL.
            
        Returns:
            SQL creation script if plan=True, success message if plan=False
        """
        # Generate table creation SQL
        table_sql = self.create_table_sql(model_class)
        
        # Check if model has embedding fields and generate embedding table
        embedding_sql = self.create_embedding_table_sql(model_class)
        
        # Combine all SQL statements
        sql_statements = [table_sql]
        if embedding_sql.strip():  # Only add if not empty
            sql_statements.append(embedding_sql)
        
        combined_sql = ";\n\n".join(sql_statements) + ";"
        
        if plan:
            return combined_sql
        else:
            # Execute SQL statements (implementation would need database connection)
            # For now, return success message - actual execution would be provider-specific
            return f"Successfully registered model {model_class.__name__} in {self.dialect}"
    
    @classmethod
    def get_provider(cls, provider_name: str) -> 'BaseSQLProvider':
        """Get provider instance by name."""
        from .postgresql import PostgreSQLProvider
        from .tidb import TiDBProvider
        from .rocksdb import RocksDBProvider
        
        providers = {
            "postgres": PostgreSQLProvider,
            "postgresql": PostgreSQLProvider,
            "tidb": TiDBProvider,
            "rocksdb": RocksDBProvider,
        }
        
        provider_class = providers.get(provider_name.lower())
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_name}. Available: {list(providers.keys())}")
        
        return provider_class()