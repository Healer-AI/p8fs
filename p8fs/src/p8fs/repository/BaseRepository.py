"""Base repository implementation with common CRUD operations."""

import asyncio
from abc import ABC
from typing import Any, TypeVar

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from p8fs.models import AbstractModel
from p8fs.providers import BaseSQLProvider, get_provider

T = TypeVar("T", bound=AbstractModel)

logger = get_logger(__name__)


class BaseRepository(ABC):
    """
    Base repository providing common CRUD operations without tenant scoping.

    This class contains the shared database operations that both TenantRepository
    and SystemRepository need. Subclasses can add tenant scoping or other constraints
    by overriding the filter methods.
    """

    def __init__(self, model_class: type[T], tenant_id: str | None = None, provider_name: str | None = None, **kwargs):
        """
        Initialize base repository.

        Args:
            model_class: The AbstractModel class this repository manages
            tenant_id: Optional tenant ID for scoping (ignored in base repository)
            provider_name: Optional database provider override
            **kwargs: Additional keyword arguments (ignored for compatibility)
        """
        self.model_class = model_class
        self.provider_name = provider_name or config.storage_provider
        self.provider = self._create_provider()
        self.connection = None
        self.tenant_id = tenant_id

    def _create_provider(self) -> BaseSQLProvider:
        """Create the appropriate SQL provider based on configuration."""
        return get_provider()

    def _get_connection_string(self) -> str:
        """Get database connection string from centralized config."""
        if self.provider_name.lower() in ["postgres", "postgresql"]:
            return config.pg_connection_string
        elif self.provider_name.lower() == "tidb":
            return config.tidb_connection_string
        elif self.provider_name.lower() == "rocksdb":
            return f"tikv://{config.rocksdb_host}:{config.rocksdb_port}"
        else:
            raise ValueError(
                f"No connection string configured for provider: {self.provider_name}"
            )

    async def _get_connection(self):
        """Get or create async database connection."""
        if self.connection:
            return self.connection

        self.connection = self.provider.connect_async(self._get_connection_string())
        return self.connection

    def get_connection_sync(self):
        """Get synchronous database connection."""
        if self.connection:
            return self.connection

        self.connection = self.provider.connect_sync(self._get_connection_string())
        return self.connection

    def _build_filters(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Build filters for queries. Override in subclasses to add tenant scoping.

        Args:
            filters: Optional filter conditions

        Returns:
            Complete filter dict with any additional constraints
        """
        return filters or {}

    def _prepare_entity_data(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        """
        Prepare entity data for storage. Override in subclasses to add tenant_id.

        Args:
            entity_data: Raw entity data

        Returns:
            Entity data with any required additional fields
        """
        return entity_data.copy()

    async def get(self, key: str) -> T | None:
        """
        Retrieve a single entity by its key.
        
        This is equivalent to select_where with the key field filter,
        but more convenient for primary key lookups.
        """
        try:
            # Use model's get_model_key_field() method to get the correct key field
            key_field = self.model_class.get_model_key_field()
            
            
            # Use select method with key field filter
            results = await self.select(filters={key_field: key}, limit=1)
            
            if not results:
                return None
                
            return results[0]

        except Exception as e:
            logger.error(
                f"Failed to get {self.model_class.__name__} with key {key}: {e}"
            )
            raise

    async def select(
        self,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: list[str] | None = None,
    ) -> list[T | dict[str, Any]]:
        """
        Select multiple entities with comprehensive filtering.
        """
        try:
            # Build final filters with any repository-specific constraints
            final_filters = self._build_filters(filters)

            # Use provider's select_sql method
            sql, params = self.provider.select_sql(
                self.model_class,
                filters=final_filters,
                fields=fields,
                limit=limit,
                offset=offset,
                order_by=order_by,
            )

            conn = await self._get_connection()
            results = await self.provider.async_execute(conn, sql, params)

            if not results:
                return []

            # Return based on field selection
            if fields:
                return results
            else:
                return [self.model_class(**row) for row in results]

        except Exception as e:
            logger.error(f"Failed to select {self.model_class.__name__}: {e}")
            raise

    async def find_by_type(
        self,
        entity_type: str,
        limit: int = 100,
        offset: int = 0,
        order_by: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find entities by type name.

        This is particularly useful for finding Sessions, Users, or other entity types
        when you don't have the model class directly.

        Args:
            entity_type: The type name (e.g., 'Session', 'User', 'Agent')
            limit: Maximum number of results
            offset: Number of results to skip
            order_by: Fields to order by

        Returns:
            List of entity dictionaries
        """
        try:
            # For the current model class, check if it matches the type
            if self.model_class.__name__ == entity_type:
                # Use the regular select method
                results = await self.select(
                    filters=None,
                    fields=None,
                    limit=limit,
                    offset=offset,
                    order_by=order_by,
                )
                # Convert models to dicts
                return [
                    (
                        entity.model_dump()
                        if hasattr(entity, "model_dump")
                        else dict(entity)
                    )
                    for entity in results
                ]
            else:
                # For cross-type queries, we need to query the table directly
                # This would require knowing the table name for the entity type
                logger.warning(
                    f"Cross-type query for {entity_type} not implemented yet"
                )
                return []

        except Exception as e:
            logger.error(f"Failed to find_by_type {entity_type}: {e}")
            raise

    async def select_where_async(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        fields: list[str] | None = None,
        **conditions,
    ) -> list[T | dict[str, Any]]:
        """
        Select entities using WHERE conditions as kwargs.
        """
        try:
            # Convert kwargs to filters dict and apply repository constraints
            filters = self._build_filters(conditions if conditions else None)

            # Use provider's select_sql method
            sql, params = self.provider.select_sql(
                self.model_class,
                filters=filters,
                fields=fields,
                limit=limit,
                offset=offset,
                order_by=[order_by] if order_by else None,
            )

            conn = await self._get_connection()
            results = await self.provider.async_execute(conn, sql, params)

            if fields:
                return results
            else:
                return [self.model_class(**row) for row in results]

        except Exception as e:
            logger.error(f"Failed to select_where {self.model_class.__name__}: {e}")
            raise

    def upsert_sync(
        self, 
        entities: T | list[T] | dict[str, Any] | list[dict[str, Any]],
        create_embeddings: bool = True
    ) -> dict[str, Any]:
        """
        Synchronously upsert one or more entities.
        
        Args:
            entities: Entity or list of entities to upsert
            create_embeddings: Whether to generate embeddings for entities with embedding fields (default: True)
            
        Returns:
            Dictionary with success status and affected rows
        """
        try:
            # Normalize input to list
            if not isinstance(entities, list):
                entities_list = [entities]
            else:
                entities_list = entities

            # Convert all entities to dicts and apply repository-specific preparation
            data_list = []
            for entity in entities_list:
                if isinstance(entity, dict):
                    entity_data = entity.copy()
                elif hasattr(entity, "model_dump"):
                    entity_data = entity.model_dump()
                else:
                    entity_data = dict(entity)

                # Apply repository-specific data preparation (e.g., tenant_id injection)
                prepared_data = self._prepare_entity_data(entity_data)
                data_list.append(prepared_data)

            conn = self.get_connection_sync()

            if len(data_list) == 1:
                # Single entity
                sql, params = self.provider.upsert_sql(self.model_class, data_list[0])
                results = self.provider.execute(sql, params, conn)
                affected_rows = results[0].get("affected_rows", 1)
            else:
                # Multiple entities
                sql, params_list = self.provider.batch_upsert_sql(
                    self.model_class, data_list
                )

                if hasattr(self.provider, "execute_batch"):
                    result = self.provider.execute_batch(conn, sql, params_list)
                    affected_rows = result.get("affected_rows", len(data_list))
                else:
                    # Fallback to individual executions
                    affected_rows = 0
                    for params in params_list:
                        results = self.provider.execute(sql, params, conn)
                        affected_rows += results[0].get("affected_rows", 1)

            logger.info(
                f"Successfully upserted {affected_rows} {self.model_class.__name__} entities"
            )

            # Generate embeddings for entities with embedding fields
            if create_embeddings:
                try:
                    if conn:
                        conn.commit()

                    self._generate_embeddings_for_entities(data_list)
                except Exception as e:
                    logger.warning(
                        f"Embedding generation failed (entities still saved): {e}"
                    )

            return {
                "success": True,
                "affected_rows": affected_rows,
                "entity_count": len(data_list),
            }

        except Exception as e:
            logger.error(f"Failed to upsert {self.model_class.__name__}: {e}")
            if conn:
                conn.rollback()
            raise

    async def upsert(
        self,
        entities: T | list[T] | dict[str, Any] | list[dict[str, Any]],
        create_embeddings: bool = True
    ) -> dict[str, Any]:
        """
        Async upsert one or more entities with dual indexing.

        CONTRACTUAL OBLIGATION: Upsert performs dual indexing automatically:
        1. SQL persistence (INSERT/UPDATE in database table)
        2. Embedding index generation (vector search capability)
        3. Entity key index population (enables LOOKUP queries)

        Provider-specific implementations:
        - PostgreSQL: Stores entities in tables + creates AGE graph nodes for LOOKUP
        - TiDB: Stores entities in tables + creates TiKV reverse key lookups

        The caller should NEVER need to separately populate KV or manage indexing.
        This abstraction ensures consistent behavior across all storage providers.

        Args:
            entities: Entity or list of entities to upsert
            create_embeddings: Whether to generate embeddings for entities with embedding fields (default: True)

        Returns:
            Dictionary with success status and affected rows
        """
        try:
            # Normalize input to list
            if not isinstance(entities, list):
                entities_list = [entities]
            else:
                entities_list = entities

            # Convert all entities to dicts and apply repository-specific preparation
            data_list = []
            for entity in entities_list:
                if isinstance(entity, dict):
                    entity_data = entity.copy()
                elif hasattr(entity, "model_dump"):
                    entity_data = entity.model_dump()
                else:
                    entity_data = dict(entity)

                # Apply repository-specific data preparation (e.g., tenant_id injection)
                prepared_data = self._prepare_entity_data(entity_data)
                data_list.append(prepared_data)

            conn = await self._get_connection()

            if len(data_list) == 1:
                # Single entity
                logger.debug(f"Upserting {self.model_class.__name__} with fields: {list(data_list[0].keys())}")
                sql, params = self.provider.upsert_sql(self.model_class, data_list[0])
                results = await self.provider.async_execute(conn, sql, params)
                affected_rows = 1  # Assume success for async
            else:
                # Multiple entities - batch upsert
                sql, params_list = self.provider.batch_upsert_sql(
                    self.model_class, data_list
                )

                # Execute batch - use provider's async batch method if available
                if hasattr(self.provider, 'async_execute_batch'):
                    affected_rows = await self.provider.async_execute_batch(sql, params_list, conn)
                else:
                    # Fallback to individual execution for providers that don't support batch async
                    affected_rows = 0
                    for params in params_list:
                        await self.provider.async_execute(conn, sql, params)
                        affected_rows += 1

            logger.debug(
                f"Successfully async upserted {affected_rows} {self.model_class.__name__} entities"
            )

            # Generate embeddings for entities with embedding fields
            if create_embeddings:
                try:
                    # Use sync embedding generation for now (can be made async in future)
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._generate_embeddings_for_entities, data_list
                    )
                except Exception as e:
                    logger.warning(
                        f"Embedding generation failed (entities still saved): {e}"
                    )

            # Populate entity key index for LOOKUP queries (dual indexing)
            # This must happen after SQL upsert to ensure entity exists
            for entity_data in data_list:
                try:
                    await self._populate_entity_key_index(entity_data)
                except Exception as e:
                    # Log warning but don't fail upsert - KV population is best-effort
                    logger.warning(
                        f"Entity key index population failed for {entity_data.get('name', entity_data.get('id'))}: {e}"
                    )

            return {
                "success": True,
                "affected_rows": affected_rows,
                "entity_count": len(data_list),
            }

        except Exception as e:
            import traceback
            logger.error(f"Failed to async upsert {self.model_class.__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def _populate_entity_key_index(self, entity_data: dict[str, Any]) -> None:
        """
        Populate entity key index for LOOKUP queries.

        Provider-specific implementations:
        - PostgreSQL: Creates AGE graph nodes + reverse key lookups
        - TiDB: Stores reverse key mappings in TiKV
        - RocksDB: Stores reverse key mappings in RocksDB

        Creates KV entries:
        - {tenant_id}/{entity_name}/{table_name} → {entity_ids: [UUID...], table_name, entity_type}
        - {tenant_id}/{related_entity}/{table_name} → {entity_ids: [UUID...]} for graph edges

        This enables LOOKUP queries to find entities by human-friendly labels
        without knowing which table they're in.
        """
        try:
            entity_id = entity_data.get("id")
            table_name = self.model_class.get_model_table_name()

            if not entity_id:
                logger.debug(f"Entity missing ID, skipping key index: {entity_data.get('name', 'unknown')}")
                return

            # Get tenant_id for key namespacing
            tenant_id = entity_data.get("tenant_id") or self.tenant_id or "system"
            kv = self.provider.kv

            async def add_entity_mapping(key: str, entity_type: str = "entity"):
                """Add entity_id to the list of entities for this key."""
                existing = await kv.get(key)

                if existing:
                    # Append to existing list
                    if isinstance(existing, dict) and "entity_ids" in existing:
                        entity_ids = existing["entity_ids"]
                        if entity_id not in entity_ids:
                            entity_ids.append(entity_id)
                    else:
                        # Old format (single entity_id), migrate to list
                        old_id = existing.get("entity_id") if isinstance(existing, dict) else existing
                        entity_ids = [old_id, entity_id] if old_id and old_id != entity_id else [entity_id]
                else:
                    entity_ids = [entity_id]

                kv_value = {
                    "entity_ids": entity_ids,
                    "table_name": table_name,
                    "entity_type": entity_type
                }

                await kv.put(key, kv_value)

            # 1. Index by name (if present)
            entity_name = entity_data.get("name")
            if entity_name:
                await add_entity_mapping(
                    f"{tenant_id}/{entity_name}/{table_name}",
                    entity_type=table_name
                )
                logger.debug(f"Indexed entity name: {entity_name} → {entity_id}")

            # 2. Index graph_paths destinations (if present)
            graph_paths = entity_data.get("graph_paths", [])
            if graph_paths:
                for edge in graph_paths:
                    if isinstance(edge, dict):
                        related_name = edge.get("dst")
                        properties = edge.get("properties", {})
                        related_type = properties.get("dst_entity_type", "entity")
                    else:
                        # Fallback for legacy string format
                        related_name = str(edge)
                        related_type = "entity"

                    if not related_name:
                        continue

                    # Store mapping from related entity name back to this resource
                    await add_entity_mapping(
                        f"{tenant_id}/{related_name}/resource",
                        entity_type=related_type
                    )

                    logger.debug(f"Indexed graph edge: {related_name} → {entity_id}")

        except Exception as e:
            # Log warning but don't fail - KV population is best-effort
            logger.warning(f"Failed to populate entity key index: {e}")

    def create_with_embeddings(
        self, entities: T | list[T] | dict[str, Any] | list[dict[str, Any]]
    ) -> list[str]:
        """
        Clean implementation: Insert entities and generate embeddings using model class methods.

        This method follows the new architecture:
        1. Insert entities, get back just IDs (fast)
        2. Get embedding column values from model (model knows its schema)
        3. Generate embeddings for those values (ordered list)
        4. Build embedding records using model class method (testable)
        5. Upsert embeddings using provider helper

        Returns:
            List of entity IDs that were created/updated
        """
        # Normalize input to list
        if not isinstance(entities, list):
            entities_list = [entities]
        else:
            entities_list = entities

        # Convert all entities to dicts and apply repository-specific preparation
        data_list = []
        for entity in entities_list:
            if isinstance(entity, dict):
                entity_data = entity.copy()
            elif hasattr(entity, "model_dump"):
                entity_data = entity.model_dump()
            else:
                entity_data = dict(entity)

            # Apply repository-specific data preparation (e.g., tenant_id injection)
            prepared_data = self._prepare_entity_data(entity_data)
            data_list.append(prepared_data)

        if not data_list:
            return []

        try:
            # 1. Insert entities, get back just IDs (fast)
            schema = self.model_class.to_sql_schema()
            table_name = schema["table_name"]
            entity_ids = self.provider.insert_and_return_ids(data_list, table_name)

            # 2. Check if model has embedding columns, if not skip embedding generation
            if not hasattr(self.model_class, "get_embedding_column_values"):
                logger.debug(
                    f"Model {self.model_class.__name__} has no embedding columns, skipping embedding generation"
                )
                return entity_ids

            # 3. Get embedding column values from model (model knows its schema)
            embedding_values, column_metadata = (
                self.model_class.get_embedding_column_values(data_list)
            )

            if not embedding_values:
                logger.debug(
                    f"No embedding values found for {self.model_class.__name__} entities"
                )
                return entity_ids

            # 4. Generate embeddings for those values (ordered list)
            embedding_vectors = self.provider.generate_embeddings_batch(
                embedding_values
            )

            # 5. Build embedding records using model class method (testable)
            # Get tenant_id from prepared data (works for both tenant and non-tenant repos)
            tenant_id = data_list[0].get(
                "tenant_id", "00000000-0000-0000-0000-000000000000"
            )
            embedding_records = self.model_class.build_embedding_records(
                entity_ids=entity_ids,
                column_metadata=column_metadata,
                embedding_vectors=embedding_vectors,
                tenant_id=tenant_id,
            )

            # 6. Upsert embeddings using provider helper
            self.provider.upsert_embeddings(embedding_records, table_name)

            logger.info(
                f"Successfully created {len(entity_ids)} {self.model_class.__name__} entities with embeddings"
            )
            return entity_ids

        except Exception as e:
            logger.error(
                f"Failed to create {self.model_class.__name__} entities with embeddings: {e}"
            )
            raise
            
    def get_entities(
        self, keys: list[str]) -> list[dict[str, Any]]:
        """Get entities by keys using p8.get_entities function.

        This uses the AGE graph database function to lookup entities.

        Args:
            keys: List of entity keys to fetch
        Returns:
            List of entity dictionaries grouped by entity type
            
        """
        results = self.provider.get_entities(
                keys,
                # tenant_id=tenant_id
            )

        return results
            
    def semantic_search(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        metric: str = "cosine",
        field_name: str = None,
    ) -> list[dict[str, Any]]:
        """
        Clean semantic search implementation using provider-level operations.

        Args:
            query: Text query to find similar entities
            limit: Maximum results to return
            threshold: Minimum similarity score (0-1)
            metric: Similarity metric ('cosine', 'l2', 'inner_product')
            field_name: Specific field to search (searches all embedding fields if None)

        Returns:
            List of dicts with complete entity data and similarity scores
        """
        try:
            # 1. Generate embedding for query text using provider
            query_embedding = self.provider.generate_embeddings_batch([query])[0]

            # 2. Use provider's semantic search with embeddings
            schema = self.model_class.to_sql_schema()
            table_name = schema["table_name"]

            # Get tenant_id for filtering (subclasses can override _get_tenant_id_for_search)
            tenant_id = self._get_tenant_id_for_search()

            results = self.provider.semantic_search_with_embeddings(
                query_vector=query_embedding,
                table_name=table_name,
                field_name=field_name,
                limit=limit,
                threshold=threshold,
                metric=metric,
                tenant_id=tenant_id,
            )

            logger.info(
                f"Semantic search found {len(results)} results for query: {query[:50]}..."
            )
            return results

        except Exception as e:
            logger.error(f"Semantic search failed for {self.model_class.__name__}: {e}")
            raise

    def _get_tenant_id_for_search(self) -> str | None:
        """
        Get tenant ID for search filtering. Override in subclasses for tenant scoping.
        Base implementation returns None (no tenant filtering).
        """
        return None

    async def delete(self, key: str) -> bool:
        """
        Delete a single entity by its key.
        
        Args:
            key: The primary key value of the entity to delete
            
        Returns:
            True if entity was deleted, False if not found
        """
        try:
            # Get the key field name from model
            key_field = self.model_class.get_model_key_field()
            
            # Build filters with repository constraints
            filters = self._build_filters({key_field: key})
            
            # Generate DELETE SQL
            schema = self.model_class.to_sql_schema()
            table_name = schema["table_name"]
            
            # Build WHERE clause
            where_parts = []
            params = []
            for field, value in filters.items():
                where_parts.append(f"{field} = %s")
                params.append(value)
            
            where_clause = " AND ".join(where_parts)
            sql = f"DELETE FROM {table_name} WHERE {where_clause}"
            
            # Execute deletion
            conn = await self._get_connection()
            result = await self.provider.async_execute(conn, sql, params)
            
            # Check if rows were affected (provider-specific)
            affected = getattr(result, 'rowcount', 1) if result else 0
            
            logger.debug(f"Deleted {affected} {self.model_class.__name__} entities with key {key}")
            return affected > 0
            
        except Exception as e:
            logger.error(f"Failed to delete {self.model_class.__name__} with key {key}: {e}")
            raise

    async def query(
        self,
        query_text: str,
        hint: str = "hybrid",
        limit: int = 10,
        threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """
        Abstract query method that can use different search strategies based on hint.
        
        Args:
            query_text: Natural language query or SQL query
            hint: Query strategy - "semantic", "sql", "graph", or "hybrid"
            limit: Maximum results to return
            threshold: Minimum similarity score for semantic search
            
        Returns:
            List of matching entities with relevance scores
        """
        if hint == "semantic":
            # Use semantic search for natural language queries
            return self.semantic_search(
                query=query_text,
                limit=limit,
                threshold=threshold
            )
        elif hint == "sql":
            # Execute as raw SQL (synchronous)
            return self.execute(query_text)
        elif hint == "graph":
            # Placeholder for graph-based search
            raise NotImplementedError("Graph search not yet implemented")
        elif hint == "hybrid":
            # Placeholder for hybrid search combining multiple strategies
            raise NotImplementedError("Hybrid search not yet implemented")
        else:
            raise ValueError(f"Unsupported query hint: {hint}")

    async def execute(
        self, statement: str, params: tuple | None = None
    ) -> list[dict[str, Any]]:
        """
        Execute raw SQL. Subclasses can add automatic filter injection.
        """
        try:
            conn = await self._get_connection()
            results = await self.provider.async_execute(conn, statement, params)
            return results

        except Exception as e:
            logger.error(f"Failed to execute SQL: {e}")
            raise

    def register_model(self, model_class: type[T], plan: bool = True) -> str | bool:
        """Register a model in the database (create tables)."""
        sql_script = self.provider.register_model(model_class, plan=True)

        if plan:
            return sql_script
        else:
            # Execute the SQL script
            conn = None
            cursor = None
            try:
                conn = self.get_connection_sync()
                cursor = conn.cursor()

                statements = [
                    stmt.strip() for stmt in sql_script.split(";") if stmt.strip()
                ]

                for statement in statements:
                    if statement:
                        logger.debug(f"Executing: {statement[:100]}...")
                        cursor.execute(statement)

                conn.commit()
                logger.info(f"Successfully registered model {model_class.__name__}")
                return True

            except Exception as e:
                logger.error(f"Failed to register model {model_class.__name__}: {e}")
                if conn:
                    conn.rollback()
                raise
            finally:
                if cursor:
                    cursor.close()

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def _generate_embeddings_for_entities(
        self, entities: list[dict[str, Any]], sync: bool = False
    ) -> None:
        """Generate and store embeddings using batch operations and standard upsert logic."""
        schema = self.model_class.to_sql_schema()
        embedding_fields = schema.get("embedding_fields", [])

        if not embedding_fields:
            return

        try:
            from ..config.embedding import (
                get_default_embedding_provider,
                get_vector_dimensions,
            )
            from ..services.llm import get_embedding_service

            embedding_service = get_embedding_service()
            embedding_providers = schema.get("embedding_providers", {})

            # Step 1: Collect all text to embed, grouped by provider
            texts_by_provider = {}
            embedding_metadata = []

            for entity_data in entities:
                # Try to get entity ID from the model's key field
                key_field = self.model_class.get_model_key_field()
                entity_id = entity_data.get("id") or entity_data.get(key_field)
                if not entity_id:
                    logger.warning(
                        "Skipping embedding generation for entity without ID"
                    )
                    continue

                for field_name in embedding_fields:
                    field_value = entity_data.get(field_name)
                    if not field_value or not isinstance(field_value, str):
                        continue

                    provider_name = embedding_providers.get(field_name, "default")
                    if provider_name == "default":
                        provider_name = get_default_embedding_provider()

                    if provider_name not in texts_by_provider:
                        texts_by_provider[provider_name] = []

                    texts_by_provider[provider_name].append(field_value)
                    embedding_metadata.append(
                        {
                            "entity_id": entity_id,
                            "field_name": field_name,
                            "provider_name": provider_name,
                            "text_index": len(texts_by_provider[provider_name]) - 1,
                            "tenant_id": self._get_tenant_id_for_embedding(entity_data),
                        }
                    )

            if not embedding_metadata:
                return

            # Step 2: Generate embeddings in batch per provider
            embeddings_by_provider = {}
            for provider_name, texts in texts_by_provider.items():
                embeddings_by_provider[provider_name] = embedding_service.encode_batch(
                    texts, provider_name
                )

            # Step 3: Create embedding records for batch upsert
            table_name = schema.get("table_name", self.model_class.__name__.lower())
            embedding_records = []

            for meta in embedding_metadata:
                embedding_vector = embeddings_by_provider[meta["provider_name"]][
                    meta["text_index"]
                ]
                vector_dimension = get_vector_dimensions(meta["provider_name"])

                # Generate deterministic ID for embedding
                from p8fs.utils import make_uuid
                embedding_id = make_uuid(
                    f"{meta['entity_id']}-{meta['field_name']}-{meta['tenant_id']}"
                )
                
                embedding_record = {
                    "id": embedding_id,
                    "entity_id": meta["entity_id"],
                    "field_name": meta["field_name"],
                    "embedding_provider": meta["provider_name"],
                    "embedding_vector": embedding_vector,
                    "vector_dimension": vector_dimension,
                    "tenant_id": meta["tenant_id"],
                }
                embedding_records.append(embedding_record)

            # Step 4: Use standard upsert logic with embedding model
            if embedding_records:
                # Create a temporary repository for embedding table operations

                # Use provider's batch upsert directly
                embedding_table = f"embeddings.{table_name}_embeddings"
                conn = self.get_connection_sync()

                # Use provider's batch upsert SQL generation
                if len(embedding_records) == 1:
                    sql, params = self._build_embedding_upsert_sql(
                        embedding_table, embedding_records[0]
                    )
                    results = self.provider.execute(sql, params, conn)
                else:
                    sql, params_list = self._build_batch_embedding_upsert_sql(
                        embedding_table, embedding_records
                    )
                    if hasattr(self.provider, "execute_batch"):
                        self.provider.execute_batch(conn, sql, params_list)
                    else:
                        for params in params_list:
                            self.provider.execute(sql, params, conn)

                conn.commit()
                logger.info(
                    f"Generated and stored {len(embedding_records)} embeddings in batch"
                )

        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            if sync:
                raise

    def _get_tenant_id_for_embedding(self, entity_data: dict[str, Any]) -> str | None:
        """Extract tenant_id for embedding storage. Override in subclasses."""
        return entity_data.get("tenant_id")

    def _build_embedding_upsert_sql(
        self, table_name: str, embedding_data: dict[str, Any]
    ) -> tuple[str, tuple]:
        """Build upsert SQL for a single embedding record."""
        import json

        if self.provider_name.lower() == "tidb":
            # TiDB uses REPLACE INTO and VEC_FROM_TEXT()
            vector_json = json.dumps(embedding_data["embedding_vector"])
            sql = f"""
            REPLACE INTO {table_name}
            (id, entity_id, field_name, embedding_provider, embedding_vector, vector_dimension, tenant_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, VEC_FROM_TEXT(%s), %s, %s, NOW(), NOW())
            """
            # Convert UUIDs to strings for database compatibility
            from uuid import UUID
            record_id = str(embedding_data["id"]) if isinstance(embedding_data["id"], UUID) else embedding_data["id"]
            entity_id = str(embedding_data["entity_id"]) if isinstance(embedding_data["entity_id"], UUID) else embedding_data["entity_id"]

            params = (
                record_id,
                entity_id,
                embedding_data["field_name"],
                embedding_data["embedding_provider"],
                vector_json,
                embedding_data["vector_dimension"],
                embedding_data["tenant_id"],
            )
        else:
            # PostgreSQL uses ON CONFLICT
            sql = f"""
            INSERT INTO {table_name}
            (id, entity_id, field_name, embedding_provider, embedding_vector, vector_dimension, tenant_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (entity_id, field_name, tenant_id)
            DO UPDATE SET
                embedding_provider = EXCLUDED.embedding_provider,
                embedding_vector = EXCLUDED.embedding_vector,
                vector_dimension = EXCLUDED.vector_dimension,
                updated_at = NOW()
            """
            # Convert UUIDs to strings for database compatibility
            from uuid import UUID
            record_id = str(embedding_data["id"]) if isinstance(embedding_data["id"], UUID) else embedding_data["id"]
            entity_id = str(embedding_data["entity_id"]) if isinstance(embedding_data["entity_id"], UUID) else embedding_data["entity_id"]

            params = (
                record_id,
                entity_id,
                embedding_data["field_name"],
                embedding_data["embedding_provider"],
                embedding_data["embedding_vector"],
                embedding_data["vector_dimension"],
                embedding_data["tenant_id"],
            )

        return sql, params

    def _build_batch_embedding_upsert_sql(
        self, table_name: str, embedding_records: list[dict[str, Any]]
    ) -> tuple[str, list[tuple]]:
        """Build batch upsert SQL for multiple embedding records."""
        import json

        if self.provider_name.lower() == "tidb":
            sql = f"""
            REPLACE INTO {table_name}
            (id, entity_id, field_name, embedding_provider, embedding_vector, vector_dimension, tenant_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, VEC_FROM_TEXT(%s), %s, %s, NOW(), NOW())
            """
            params_list = []
            for record in embedding_records:
                # Convert UUIDs to strings for database compatibility
                from uuid import UUID
                record_id = str(record["id"]) if isinstance(record["id"], UUID) else record["id"]
                entity_id = str(record["entity_id"]) if isinstance(record["entity_id"], UUID) else record["entity_id"]

                vector_json = json.dumps(record["embedding_vector"])
                params_list.append(
                    (
                        record_id,
                        entity_id,
                        record["field_name"],
                        record["embedding_provider"],
                        vector_json,
                        record["vector_dimension"],
                        record["tenant_id"],
                    )
                )
        else:
            # For PostgreSQL with execute_values, we need a different SQL format
            # execute_values expects a single %s placeholder where it will insert the formatted VALUES
            sql = f"""
            INSERT INTO {table_name} 
            (id, entity_id, field_name, embedding_provider, embedding_vector, vector_dimension, tenant_id, created_at, updated_at)
            VALUES %s
            ON CONFLICT (entity_id, field_name, tenant_id) 
            DO UPDATE SET 
                embedding_provider = EXCLUDED.embedding_provider,
                embedding_vector = EXCLUDED.embedding_vector,
                vector_dimension = EXCLUDED.vector_dimension,
                updated_at = NOW()
            """
            params_list = []
            for record in embedding_records:
                # For PostgreSQL pgvector, convert the vector to the proper format
                if isinstance(record["embedding_vector"], list):
                    vector_str = f"[{','.join(map(str, record['embedding_vector']))}]"
                else:
                    vector_str = record["embedding_vector"]

                # Convert UUIDs to strings for psycopg2 compatibility
                from uuid import UUID
                record_id = str(record["id"]) if isinstance(record["id"], UUID) else record["id"]
                entity_id = str(record["entity_id"]) if isinstance(record["entity_id"], UUID) else record["entity_id"]

                params_list.append(
                    (
                        record_id,
                        entity_id,
                        record["field_name"],
                        record["embedding_provider"],
                        vector_str,
                        record["vector_dimension"],
                        record["tenant_id"]
                        # created_at and updated_at will be handled by NOW() in the template
                    )
                )

        return sql, params_list

    # ==================== Convenience Methods ====================
    # These delegate to the provider for easier access

    def execute(self, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """
        Execute SQL query and return results.

        Args:
            query: SQL query to execute
            params: Optional query parameters

        Returns:
            List of result dictionaries

        Example:
            sessions = repo.execute(
                "SELECT * FROM sessions WHERE created_at > %s ORDER BY created_at DESC",
                (datetime.now() - timedelta(days=7),)
            )
        """
        return self.provider.execute(query, params)

    async def execute_async(
        self, query: str, params: tuple | None = None
    ) -> list[dict[str, Any]]:
        """
        Execute SQL query asynchronously.

        Args:
            query: SQL query to execute
            params: Optional query parameters

        Returns:
            List of result dictionaries
        """
        return await self.provider.execute_async(query, params)

    def select_where(
        self,
        table: str | None = None,
        where: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        order_by: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Select records with filtering.

        Args:
            table: Table name (defaults to model's table)
            where: Filter conditions
            fields: Fields to select
            order_by: Sort fields (prefix with '-' for DESC)
            limit: Maximum records
            offset: Skip records

        Returns:
            List of result dictionaries

        Example:
            recent_sessions = repo.select_where(
                where={"session_type": "chat"},
                order_by=["-created_at"],
                limit=10
            )
        """
        # Use model's table if not specified
        if table is None:
            table = self.model_class.Config.table_name

        # Apply any filter transformations (e.g., tenant scoping)
        final_where = self._build_filters(where)

        return self.provider.select_where(
            table,
            where=final_where,
            fields=fields,
            order_by=order_by,
            limit=limit,
            offset=offset,
        )

    @property
    def kv(self):
        """
        Access KV storage through the provider.

        Returns:
            KV storage interface

        Example:
            # Store temporary data
            await repo.kv.put("session:123", {"status": "active"}, ttl_seconds=3600)

            # Retrieve data
            data = await repo.kv.get("session:123")
        """
        return self.provider.kv
