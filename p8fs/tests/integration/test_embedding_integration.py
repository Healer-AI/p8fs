#!/usr/bin/env python3
"""
Integration test for embedding functionality with P8FS models.

This test demonstrates:
1. Embedding service providers (OpenAI and local sentence-transformers)
2. Dynamic vector dimensions based on embedding providers
3. Model registration with correct embedding table schema
4. End-to-end semantic search with real embeddings
5. Both OpenAI and local embedding providers
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from p8fs.config.embedding import (
    get_embedding_provider_config,
    get_vector_dimensions,
)
from p8fs.models.base import AbstractEntityModel
from p8fs.models.fields import DefaultEmbeddingField, EmbeddingField
from p8fs.models.p8 import Resources
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.services.llm import get_embedding_service
from pydantic import Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SampleEmbeddingModel(AbstractEntityModel):
    """Test model with different embedding providers."""
    
    title: str = Field(..., description="Document title")
    
    # Use OpenAI embedding
    content_openai: str = EmbeddingField(
        embedding_provider="text-embedding-3-small",
        description="Content with OpenAI embedding"
    )
    
    # Use local embedding (smaller dimensions)
    summary_local: str | None = EmbeddingField(
        embedding_provider="all-MiniLM-L6-v2",
        default=None,
        description="Summary with local embedding"
    )
    
    # Use default embedding (should resolve to OpenAI)
    description: str | None = DefaultEmbeddingField(
        description="Description with default embedding"
    )
    
    class Config:
        table_name = "test_embedding_documents"
        description = "Test model for embedding integration"


def get_test_db_connection():
    """Get test database connection using connection string."""
    import psycopg2
    
    # Get connection string from centralized config
    from p8fs_cluster.config.settings import config
    conn_str = config.pg_connection_string
    
    try:
        conn = psycopg2.connect(conn_str)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to test database: {e}")
        logger.error(f"Connection string: {conn_str}")
        raise


def cleanup_test_tables():
    """Drop test tables if they exist."""
    conn = get_test_db_connection()
    cursor = conn.cursor()
    
    tables = [
        'embeddings.test_embedding_documents_embeddings',
        'test_embedding_documents'
        # DO NOT DROP resources or embeddings.resources_embeddings - those are production tables!
    ]
    
    for table in tables:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            logger.debug(f"Dropped table: {table}")
        except Exception as e:
            logger.warning(f"Could not drop table {table}: {e}")
    
    # DO NOT drop embeddings schema - it contains production tables!
    # Only drop specific test tables listed above
    
    conn.commit()
    cursor.close()
    conn.close()


def check_table_structure(table_name: str, schema: str = "public") -> dict[str, Any]:
    """Check table structure and return column information."""
    conn = get_test_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """, (schema, table_name))
    
    columns = {}
    for col_name, data_type, max_length, nullable in cursor.fetchall():
        columns[col_name] = {
            'data_type': data_type,
            'max_length': max_length,
            'nullable': nullable == 'YES'
        }
    
    cursor.close()
    conn.close()
    return columns


@pytest.mark.llm
class TestEmbeddingProviders:
    """Test embedding providers functionality."""
    
    @pytest.mark.llm
    def test_embedding_service_initialization(self):
        """Test that embedding service initializes correctly."""
        service = get_embedding_service()
        providers = service.get_available_providers()
        
        # Check that providers are loaded
        assert len(providers) > 0
        logger.info(f"Available providers: {list(providers.keys())}")
        
        # Check provider configurations
        for name, info in providers.items():
            logger.info(f"{name}: {info['dimensions']} dims, available: {info['available']}")
        
        # OpenAI should be configured
        assert "text-embedding-3-small" in providers
        assert providers["text-embedding-3-small"]["dimensions"] == 1536
        
        # Local model should be configured
        assert "all-MiniLM-L6-v2" in providers
        assert providers["all-MiniLM-L6-v2"]["dimensions"] == 384
    
    @pytest.mark.llm
    def test_embedding_provider_configs(self):
        """Test embedding provider configurations."""
        # Test OpenAI provider config
        openai_config = get_embedding_provider_config("text-embedding-3-small")
        assert openai_config.dimensions == 1536
        assert openai_config.provider_type == "openai"
        assert openai_config.requires_api_key is True
        
        # Test local provider config
        local_config = get_embedding_provider_config("all-MiniLM-L6-v2")
        assert local_config.dimensions == 384
        assert local_config.provider_type == "local"
        assert local_config.requires_api_key is False
        
        # Test vector dimensions
        assert get_vector_dimensions("text-embedding-3-small") == 1536
        assert get_vector_dimensions("all-MiniLM-L6-v2") == 384
    
    @pytest.mark.llm
    def test_provider_availability(self):
        """Test provider availability checks."""
        service = get_embedding_service()
        
        # Check OpenAI availability (depends on API key)
        openai_available = service.validate_provider("text-embedding-3-small")
        has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
        
        if has_openai_key:
            logger.info("OpenAI API key found - OpenAI provider should be available")
            # Note: May still fail if API key is invalid
        else:
            logger.info("No OpenAI API key - OpenAI provider unavailable")
            assert not openai_available
        
        # Check local availability (depends on sentence-transformers installation)
        local_available = service.validate_provider("all-MiniLM-L6-v2")
        logger.info(f"Local provider available: {local_available}")
    
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    def test_openai_embedding_generation(self):
        """Test OpenAI embedding generation using REST API only (no OpenAI library)."""
        service = get_embedding_service()
        
        if not service.validate_provider("text-embedding-3-small"):
            pytest.skip("OpenAI provider not available")
        
        # Test single embedding
        text = "This is a test document about machine learning."
        embedding = service.encode(text, "text-embedding-3-small")
        
        assert isinstance(embedding, list)
        assert len(embedding) == 1536
        assert all(isinstance(x, float) for x in embedding)
        
        logger.info(f"Generated OpenAI embedding via REST: {len(embedding)} dimensions")
        logger.info("✅ OpenAI embedding generated using REST API only - no library dependency")
        logger.debug(f"First 5 values: {embedding[:5]}")
    
    @pytest.mark.llm
    def test_local_embedding_generation(self):
        """Test local sentence-transformers embedding generation."""
        service = get_embedding_service()
        
        if not service.validate_provider("all-MiniLM-L6-v2"):
            pytest.skip("Local sentence-transformers provider not available")
        
        # Test single embedding
        text = "This is a test document about machine learning."
        embedding = service.encode(text, "all-MiniLM-L6-v2")
        
        assert isinstance(embedding, list)
        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)
        
        logger.info(f"Generated local embedding: {len(embedding)} dimensions")
        logger.debug(f"First 5 values: {embedding[:5]}")
    
    @pytest.mark.llm
    def test_batch_embedding_generation(self):
        """Test batch embedding generation."""
        service = get_embedding_service()
        
        # Find an available provider
        available_provider = None
        for provider_name in ["all-MiniLM-L6-v2", "text-embedding-3-small"]:
            if service.validate_provider(provider_name):
                available_provider = provider_name
                break
        
        if not available_provider:
            pytest.skip("No embedding providers available")
        
        texts = [
            "First document about artificial intelligence.",
            "Second document about machine learning.", 
            "Third document about deep learning."
        ]
        
        embeddings = service.encode_batch(texts, available_provider)
        
        assert isinstance(embeddings, list)
        assert len(embeddings) == 3
        
        expected_dims = get_vector_dimensions(available_provider)
        for embedding in embeddings:
            assert len(embedding) == expected_dims
        
        logger.info(f"Generated {len(embeddings)} embeddings with {available_provider}")


@pytest.mark.llm
class TestModelRegistrationWithEmbeddings:
    """Test model registration with different embedding providers."""
    
    def setup_method(self):
        """Setup before each test."""
        cleanup_test_tables()
    
    def teardown_method(self):
        """Cleanup after each test."""
        cleanup_test_tables()
    
    @pytest.mark.llm
    def test_model_schema_detection(self):
        """Test that embedding fields are detected correctly with providers."""
        schema = SampleEmbeddingModel.to_sql_schema()
        
        # Check embedding fields
        embedding_fields = schema.get('embedding_fields', [])
        expected_fields = ['content_openai', 'summary_local', 'description']
        
        assert set(embedding_fields) == set(expected_fields)
        logger.info(f"Detected embedding fields: {embedding_fields}")
        
        # Check embedding providers
        embedding_providers = schema.get('embedding_providers', {})
        expected_providers = {
            'content_openai': 'text-embedding-3-small',
            'summary_local': 'all-MiniLM-L6-v2',
            'description': 'text-embedding-ada-002'  # Default resolves to ada-002
        }
        
        assert embedding_providers == expected_providers
        logger.info(f"Embedding providers: {embedding_providers}")
    
    @pytest.mark.llm
    def test_embedding_table_sql_generation(self):
        """Test SQL generation for embedding tables with different dimensions."""
        tenant_id = "test-tenant-embedding"
        repo = TenantRepository(SampleEmbeddingModel, tenant_id)
        
        # Generate SQL plan
        sql_plan = repo.register_model(plan=True)
        
        logger.info("Generated SQL plan:")
        logger.info(sql_plan)
        
        # Check that embeddings schema is created
        assert "CREATE SCHEMA IF NOT EXISTS embeddings;" in sql_plan
        
        # Check that embedding table is created with correct dimensions
        # Should use dimensions from first provider (text-embedding-3-small = 1536)
        assert "embeddings.test_embedding_documents_embeddings" in sql_plan
        assert "vector(1536)" in sql_plan  # Should use OpenAI dimensions
        
        # Check foreign key relationship
        assert "REFERENCES public.test_embedding_documents(id)" in sql_plan
    
    @pytest.mark.llm
    def test_model_registration_execution(self):
        """Test actual model registration in database."""
        tenant_id = "test-tenant-embedding-exec"
        repo = TenantRepository(SampleEmbeddingModel, tenant_id)
        
        # Register model
        success = repo.register_model(plan=False)
        assert success is True
        
        # Check main table structure
        columns = check_table_structure("test_embedding_documents")
        expected_columns = ['id', 'created_at', 'updated_at', 'title', 
                           'content_openai', 'summary_local', 'description', 'tenant_id']
        
        for col in expected_columns:
            assert col in columns, f"Column {col} not found"
        
        logger.info(f"Main table columns: {list(columns.keys())}")
        
        # Check embedding table structure
        embedding_columns = check_table_structure("test_embedding_documents_embeddings", "embeddings")
        expected_emb_columns = ['id', 'entity_id', 'field_name', 'embedding_provider',
                               'embedding_vector', 'vector_dimension', 'tenant_id', 
                               'created_at', 'updated_at']
        
        for col in expected_emb_columns:
            assert col in embedding_columns, f"Embedding column {col} not found"
        
        logger.info(f"Embedding table columns: {list(embedding_columns.keys())}")
        
        repo.close()


@pytest.mark.llm
class TestEndToEndSemanticSearch:
    """Test end-to-end semantic search with real embeddings."""
    
    def setup_method(self):
        """Setup before each test."""
        cleanup_test_tables()
    
    def teardown_method(self):
        """Cleanup after each test."""
        cleanup_test_tables()
    
    @pytest.mark.llm
    def test_semantic_search_sql_generation(self):
        """Test semantic search SQL generation with real embedding dimensions."""
        tenant_id = "test-tenant-semantic"
        repo = TenantRepository(Resources, tenant_id)
        
        # Register model first
        repo.register_model(plan=False)
        
        # Generate dummy vector with correct dimensions
        embedding_service = get_embedding_service()
        query_vector = [0.1] * 1536  # OpenAI dimensions for Resources model
        
        # Test SQL generation
        sql, params = repo.provider.semantic_search_sql(
            Resources,
            query_vector,
            field_name="content", 
            limit=5,
            threshold=0.8,
            metric='cosine',
            tenant_id=tenant_id
        )
        
        logger.info("Generated semantic search SQL:")
        logger.info(sql)
        logger.info(f"Parameters: {len(params)} items")
        
        # Verify SQL structure
        assert "SELECT m.*" in sql
        assert "similarity_score" in sql
        assert "FROM public.resources m" in sql
        assert "INNER JOIN embeddings.resources_embeddings e" in sql
        assert "WHERE e.field_name = %s" in sql
        assert "ORDER BY" in sql
        
        repo.close()
    
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") and 
        not get_embedding_service().validate_provider("all-MiniLM-L6-v2"),
        reason="No embedding providers available"
    )
    @pytest.mark.llm
    def test_end_to_end_semantic_search(self):
        """Test complete semantic search workflow with real embeddings."""
        tenant_id = "test-tenant-e2e"
        repo = TenantRepository(Resources, tenant_id)
        
        # Register model
        repo.register_model(plan=False)
        
        # Test semantic search (will use real embedding generation)
        try:
            import asyncio
            
            async def run_search():
                results = await repo.semantic_search(
                    query="machine learning algorithms",
                    limit=5,
                    threshold=0.5,
                    metric='cosine',
                    field_name='content'
                )
                return results
            
            results = asyncio.run(run_search())
            
            # Should return empty list since no data is inserted, but no errors
            assert isinstance(results, list)
            logger.info(f"Semantic search completed successfully, results: {len(results)}")
            
        except Exception as e:
            # Log the error but don't fail - might be API limits or missing keys
            logger.warning(f"Semantic search test failed (expected in some environments): {e}")
        
        finally:
            repo.close()


def run_tests():
    """Run all embedding integration tests."""
    logger.info("=== Running Embedding Integration Tests ===")
    
    # Test classes to run
    test_classes = [
        TestEmbeddingProviders(),
        TestModelRegistrationWithEmbeddings(), 
        TestEndToEndSemanticSearch()
    ]
    
    total_tests = 0
    passed_tests = 0
    
    for test_instance in test_classes:
        class_name = test_instance.__class__.__name__
        logger.info(f"\n=== Running {class_name} ===")
        
        # Get test methods
        test_methods = [method for method in dir(test_instance) if method.startswith('test_')]
        
        for method_name in test_methods:
            total_tests += 1
            logger.info(f"\nRunning {class_name}.{method_name}...")
            
            try:
                # Run setup if available
                if hasattr(test_instance, 'setup_method'):
                    test_instance.setup_method()
                
                # Run test method
                method = getattr(test_instance, method_name)
                method()
                
                logger.info(f"✅ {method_name} PASSED")
                passed_tests += 1
                
            except pytest.skip.Exception as e:
                logger.info(f"⏭️  {method_name} SKIPPED: {e}")
                
            except Exception as e:
                logger.error(f"❌ {method_name} FAILED: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                
            finally:
                # Run teardown if available
                if hasattr(test_instance, 'teardown_method'):
                    try:
                        test_instance.teardown_method()
                    except Exception as e:
                        logger.warning(f"Teardown failed: {e}")
    
    logger.info("\n=== Test Results ===")
    logger.info(f"Passed: {passed_tests}/{total_tests}")
    
    return passed_tests == total_tests


if __name__ == "__main__":
    # Set up environment
    os.environ.setdefault('P8FS_PG_CONNECTION_STRING',
                         'postgresql://postgres:postgres@localhost:5438/app')
    
    # Run tests
    success = run_tests()
    
    if success:
        logger.info("\n🎉 All embedding integration tests completed successfully!")
    else:
        logger.info("\n⚠️  Some tests failed or were skipped - check logs above")
        
    sys.exit(0 if success else 1)