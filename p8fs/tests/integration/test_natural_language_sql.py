"""Integration tests for natural language to SQL generation using real LLMs."""

import asyncio
import json
import os
import pytest
from p8fs.models.p8 import Resources, Agent, User
from p8fs.services.llm.models import CallingContext
from p8fs_cluster.config.settings import config


@pytest.mark.integration
@pytest.mark.llm
@pytest.mark.asyncio
async def test_natural_language_to_sql_resources():
    """Test SQL generation for Resources model with various queries."""
    
    # Skip if no API key is configured
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("LLM API key not configured (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")
    
    context = CallingContext(
        tenant_id="test-tenant",
        model="gpt-4o-mini",  # Use mini model for faster tests
        user_id="test-user"
    )
    
    # Test Case 1: Simple content search
    print("\n=== Test 1: Content Search ===")
    query = "Find all resources that contain the word 'documentation' in their content"
    result = await Resources.natural_language_to_sql(
        query=query,
        context=context,
        dialect="postgresql",
        confidence_threshold=80
    )
    
    print(f"Query: {query}")
    print(f"Generated SQL: {result['query']}")
    print(f"Confidence: {result['confidence']}%")
    if 'brief_explanation' in result:
        print(f"Explanation: {result['brief_explanation']}")
    
    # Just verify we got a valid SQL query back
    assert result['query'] is not None
    assert len(result['query']) > 0
    assert result['confidence'] >= 0
    
    # Test Case 2: Date filtering with metadata
    print("\n=== Test 2: Date and Metadata Query ===")
    query = "Show me resources created in the last 7 days that have 'priority' set to 'high' in their metadata"
    result = await Resources.natural_language_to_sql(
        query=query,
        context=context,
        dialect="postgresql",
        confidence_threshold=75
    )
    
    print(f"Query: {query}")
    print(f"Generated SQL: {result['query']}")
    print(f"Confidence: {result['confidence']}%")
    if 'brief_explanation' in result:
        print(f"Explanation: {result['brief_explanation']}")
    
    # Test Case 3: Aggregation query
    print("\n=== Test 3: Aggregation Query ===")
    query = "Count the number of resources by category and show the top 5 categories"
    result = await Resources.natural_language_to_sql(
        query=query,
        context=context,
        dialect="postgresql",
        confidence_threshold=70
    )
    
    print(f"Query: {query}")
    print(f"Generated SQL: {result['query']}")
    print(f"Confidence: {result['confidence']}%")
    
    # Just verify we got a valid SQL query back
    assert result['query'] is not None
    assert len(result['query']) > 0
    
    # Test Case 4: Complex join-like query
    print("\n=== Test 4: Complex Query with Multiple Conditions ===")
    query = "Find resources with summaries that mention 'API' and were created by users whose IDs start with 'admin'"
    result = await Resources.natural_language_to_sql(
        query=query,
        context=context,
        dialect="postgresql",
        confidence_threshold=70
    )
    
    print(f"Query: {query}")
    print(f"Generated SQL: {result['query']}")
    print(f"Confidence: {result['confidence']}%")
    
    # Note: Tenant isolation is handled at the repository level, not in the generated SQL
    # The LLM doesn't need to know about tenant_id as it's automatically added by the framework
    
    # Just verify we got a valid SQL query back
    assert result['query'] is not None
    assert len(result['query']) > 0


@pytest.mark.integration
@pytest.mark.llm
@pytest.mark.asyncio
async def test_natural_language_sql_dialects():
    """Test SQL generation across different dialects."""
    
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("LLM API key not configured (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")
    
    context = CallingContext(
        tenant_id="test-tenant",
        model="gpt-4o-mini",  # Use mini model for faster tests
        user_id="test-user"
    )
    
    query = "Get the 10 most recent resources with their metadata where the category is 'documentation'"
    
    # Test PostgreSQL
    print("\n=== PostgreSQL Dialect ===")
    pg_result = await Resources.natural_language_to_sql(
        query=query,
        context=context,
        dialect="postgresql",
        confidence_threshold=80
    )
    
    print(f"Query: {query}")
    print(f"PostgreSQL SQL: {pg_result['query']}")
    print(f"Confidence: {pg_result['confidence']}%")
    
    # Just verify we got a valid SQL query back
    assert pg_result['query'] is not None
    assert len(pg_result['query']) > 0
    
    # Test MySQL
    print("\n=== MySQL Dialect ===")
    mysql_result = await Resources.natural_language_to_sql(
        query=query,
        context=context,
        dialect="mysql",
        confidence_threshold=80
    )
    
    print(f"MySQL SQL: {mysql_result['query']}")
    print(f"Confidence: {mysql_result['confidence']}%")
    
    # Just verify we got a valid SQL query back
    assert mysql_result['query'] is not None
    assert len(mysql_result['query']) > 0
    
    # Test SQLite
    print("\n=== SQLite Dialect ===")
    sqlite_result = await Resources.natural_language_to_sql(
        query=query,
        context=context,
        dialect="sqlite",
        confidence_threshold=80
    )
    
    print(f"SQLite SQL: {sqlite_result['query']}")
    print(f"Confidence: {sqlite_result['confidence']}%")
    
    # Just verify all dialects produced valid queries
    for result in [pg_result, mysql_result, sqlite_result]:
        assert result['query'] is not None
        assert len(result['query']) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_natural_language_sql_different_models():
    """Test SQL generation with different models (Agent and User)."""
    
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("LLM API key not configured (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")
    
    context = CallingContext(
        tenant_id="test-tenant",
        model="gpt-4o-mini",  # Use mini model for faster tests
        user_id="test-user"
    )
    
    # Test with Agent model
    print("\n=== Agent Model Test ===")
    agent_query = "Find all agents in the 'research' category that have 'analysis' in their description"
    agent_result = await Agent.natural_language_to_sql(
        query=agent_query,
        context=context,
        dialect="postgresql",
        confidence_threshold=75
    )
    
    print(f"Query: {agent_query}")
    print(f"Generated SQL: {agent_result['query']}")
    print(f"Confidence: {agent_result['confidence']}%")
    
    # Just verify we got a valid SQL query back
    assert agent_result['query'] is not None
    assert len(agent_result['query']) > 0
    
    # Test with User model
    print("\n=== User Model Test ===")
    user_query = "Show me users who have logged in within the last 30 days and have 'admin' role"
    user_result = await User.natural_language_to_sql(
        query=user_query,
        context=context,
        dialect="postgresql",
        confidence_threshold=75
    )
    
    print(f"Query: {user_query}")
    print(f"Generated SQL: {user_result['query']}")
    print(f"Confidence: {user_result['confidence']}%")
    
    # Just verify we got a valid SQL query back
    assert user_result['query'] is not None
    assert len(user_result['query']) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_natural_language_sql_edge_cases():
    """Test edge cases and error handling."""
    
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("LLM API key not configured (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")
    
    context = CallingContext(
        tenant_id="test-tenant",
        model="gpt-4o-mini",  # Use mini model for faster tests
        user_id="test-user"
    )
    
    # Test ambiguous query
    print("\n=== Ambiguous Query Test ===")
    ambiguous_query = "Show me the stuff from last week"
    result = await Resources.natural_language_to_sql(
        query=ambiguous_query,
        context=context,
        dialect="postgresql",
        confidence_threshold=90  # High threshold to force explanation
    )
    
    print(f"Query: {ambiguous_query}")
    print(f"Generated SQL: {result['query']}")
    print(f"Confidence: {result['confidence']}%")
    print(f"Explanation: {result.get('brief_explanation', 'No explanation')}")
    
    # Just verify we got a result
    assert result['query'] is not None
    assert result['confidence'] >= 0
    
    # Test with invalid/nonsensical query
    print("\n=== Nonsensical Query Test ===")
    nonsense_query = "Purple monkey dishwasher from the resources"
    result = await Resources.natural_language_to_sql(
        query=nonsense_query,
        context=context,
        dialect="postgresql",
        confidence_threshold=50
    )
    
    print(f"Query: {nonsense_query}")
    print(f"Generated SQL: {result['query']}")
    print(f"Confidence: {result['confidence']}%")
    
    # Just verify we got a result
    assert result['query'] is not None
    assert result['confidence'] >= 0


if __name__ == "__main__":
    # Run a single test for quick verification
    asyncio.run(test_natural_language_to_sql_resources())