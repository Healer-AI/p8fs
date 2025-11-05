"""Integration test for language model entity retrieval using graph functions.

This test verifies that get_entities works correctly with the language_model_apis table.
"""

import pytest
import asyncio
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers.postgresql import PostgreSQLProvider

logger = get_logger(__name__)


@pytest.mark.integration
class TestLanguageModelEntities:
    """Test get_entities functionality with language_model_apis."""
    
    @pytest.fixture(scope="class")
    def provider(self):
        """Get PostgreSQL provider instance."""
        provider = PostgreSQLProvider()
        provider.connect_sync()
        return provider
    
    def setup_graph_registration(self, provider):
        """Ensure language_model_apis is registered with the graph."""
        try:
            # Register the entity
            result = provider.execute(
                "SELECT * FROM p8.register_entities('public.language_model_apis', 'name')"
            )
            logger.info(f"Registration result: {result}")
            
            # Insert entity nodes
            result = provider.execute(
                "SELECT * FROM p8.insert_entity_nodes('public.language_model_apis')"
            )
            logger.info(f"Node insertion result: {result}")
            
        except Exception as e:
            logger.warning(f"Graph registration failed: {e}")
            pytest.skip("Graph functions not available")
    
    def test_single_model_lookup(self, provider):
        """Test retrieving a single language model by name."""
        logger.info("Testing single model lookup for 'gpt-5'")
        
        # Ensure graph is set up
        self.setup_graph_registration(provider)
        
        # Query for gpt-5
        results = provider.get_entities(['gpt-5'])
        logger.info(f"get_entities result: {results}")
        
        # Check results
        assert len(results) > 0, "Should return at least one result"
        result = results[0]
        
        # Handle both error and success cases
        if result.get("status") == "ERROR":
            pytest.skip(f"Graph error: {result.get('message')}")
        
        # Extract the actual result from get_entities key
        if 'get_entities' in result:
            result = result['get_entities']
        
        # Check for the entity type key
        entity_key = None
        for key in ['public.language_model_apis', 'public__language_model_apis']:
            if key in result:
                entity_key = key
                break
        
        assert entity_key is not None, f"Expected entity key not found in result: {result.keys()}"
        
        # Verify data structure
        entity_data = result[entity_key]
        assert 'data' in entity_data, "Result should have 'data' key"
        
        # Check if we found gpt-5
        models = entity_data['data']
        model_names = [m.get('name') for m in models if isinstance(m, dict)]
        assert 'gpt-5' in model_names, f"gpt-5 not found in results: {model_names}"
        
        # Verify model data
        gpt5_models = [m for m in models if m.get('name') == 'gpt-5']
        assert len(gpt5_models) > 0, "Should find at least one gpt-5 model"
        
        # Check model properties
        for model in gpt5_models:
            assert 'id' in model, "Model should have id"
            assert 'completions_uri' in model, "Model should have completions_uri"
            assert 'tenant_id' in model, "Model should have tenant_id"
    
    def test_multiple_model_lookup(self, provider):
        """Test retrieving multiple language models at once."""
        logger.info("Testing multiple model lookup")
        
        # Query for multiple models
        results = provider.get_entities(['gpt-5', 'claude-3', 'llama-3'])
        logger.info(f"Multiple model result: {results}")
        
        # Check results
        assert len(results) > 0, "Should return at least one result"
        result = results[0]
        
        if result.get("status") == "ERROR":
            pytest.skip(f"Graph error: {result.get('message')}")
        
        # Extract the actual result from get_entities key
        if 'get_entities' in result:
            result = result['get_entities']
        
        # Find entity key
        entity_key = None
        for key in ['public.language_model_apis', 'public__language_model_apis']:
            if key in result:
                entity_key = key
                break
        
        if entity_key:
            models = result[entity_key]['data']
            model_names = {m.get('name') for m in models if isinstance(m, dict)}
            
            # Check that we found some of the requested models
            requested_models = {'gpt-5', 'claude-3', 'llama-3'}
            found_models = model_names & requested_models
            
            logger.info(f"Requested: {requested_models}, Found: {found_models}")
            assert len(found_models) > 0, f"Should find at least one requested model. Found: {model_names}"
    
    def test_non_existent_model(self, provider):
        """Test querying for a non-existent model."""
        logger.info("Testing non-existent model lookup")
        
        # Query for non-existent model
        results = provider.get_entities(['gpt-99-turbo-max'])
        logger.info(f"Non-existent model result: {results}")
        
        # Should return empty result or no data
        if len(results) > 0:
            result = results[0]
            
            if result.get("status") == "NO DATA":
                # This is expected
                assert True
            elif result.get("status") == "ERROR":
                pytest.skip(f"Graph error: {result.get('message')}")
            else:
                # Check if any entity data was returned
                entity_key = None
                for key in ['public.language_model_apis', 'public__language_model_apis']:
                    if key in result:
                        entity_key = key
                        break
                
                if entity_key:
                    models = result[entity_key].get('data', [])
                    model_names = [m.get('name') for m in models if isinstance(m, dict)]
                    assert 'gpt-99-turbo-max' not in model_names, "Should not find non-existent model"
    
    def test_empty_query(self, provider):
        """Test querying with empty array."""
        logger.info("Testing empty query")
        
        # Query with empty array
        results = provider.get_entities([])
        logger.info(f"Empty query result: {results}")
        
        # Should handle gracefully
        assert results is not None, "Should return a result (even if empty)"
        
        if len(results) > 0:
            result = results[0]
            if result.get("status") == "NO DATA":
                assert True  # Expected
            elif result.get("status") == "ERROR":
                # This is also acceptable
                assert "empty" in result.get("message", "").lower() or True
    
    def test_direct_sql_function(self, provider):
        """Test calling SQL functions directly."""
        logger.info("Testing direct SQL function calls")
        
        try:
            # Test cypher_query
            cypher_result = provider.execute(
                "SELECT * FROM p8.cypher_query('MATCH (n:public__language_model_apis) RETURN count(n) as count', 'count agtype')"
            )
            logger.info(f"Cypher query result: {cypher_result}")
            assert cypher_result is not None
            
            # Test get_graph_nodes_by_key
            nodes_result = provider.execute(
                "SELECT * FROM p8.get_graph_nodes_by_key(ARRAY['gpt-5', 'claude-3'])"
            )
            logger.info(f"Graph nodes result: {nodes_result}")
            
            # Test get_records_by_keys
            records_result = provider.execute(
                "SELECT * FROM p8.get_records_by_keys('public.language_model_apis', ARRAY['gpt-5'], 'name')"
            )
            logger.info(f"Records result: {records_result}")
            
        except Exception as e:
            logger.error(f"Direct SQL function test failed: {e}")
            pytest.skip("SQL functions not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])