"""
Integration tests for REM Query Provider with real embeddings.

Tests all query types with actual database and embedding service.
"""

import pytest
from uuid import uuid4
from p8fs.providers import get_provider
from p8fs.providers.rem_query import (
    REMQueryProvider,
    REMQueryPlan,
    QueryType,
    SQLParameters,
    LookupParameters,
    SearchParameters,
)
from p8fs_cluster.config.settings import config


@pytest.fixture
def rem_provider():
    """Create REM provider with PostgreSQL backend."""
    pg_provider = get_provider()
    return REMQueryProvider(pg_provider, tenant_id="tenant-test")


@pytest.fixture
def seed_data(rem_provider):
    """Seed test data with real embeddings."""
    provider = rem_provider.provider

    # Delete existing test data
    provider.execute("DELETE FROM public.resources WHERE tenant_id = 'tenant-test'")

    # Generate deterministic UUIDs for test data
    ml_uuid = str(uuid4())
    dl_uuid = str(uuid4())
    py_uuid = str(uuid4())

    # Insert test resources with valid UUIDs
    test_resources = [
        {
            "id": ml_uuid,
            "tenant_id": "tenant-test",
            "name": "Introduction to Machine Learning",
            "content": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed. It focuses on developing algorithms that can access data and use it to learn for themselves.",
            "category": "article"
        },
        {
            "id": dl_uuid,
            "tenant_id": "tenant-test",
            "name": "Deep Learning Fundamentals",
            "content": "Deep learning is a machine learning technique that teaches computers to do what comes naturally to humans: learn by example. It is a key technology behind driverless cars, voice control, and many other applications.",
            "category": "tutorial"
        },
        {
            "id": py_uuid,
            "tenant_id": "tenant-test",
            "name": "Python for Data Science",
            "content": "Python has become the de facto language for data science and machine learning. Libraries like NumPy, Pandas, and Scikit-learn make it easy to work with data and build models.",
            "category": "guide"
        },
    ]

    for resource in test_resources:
        provider.execute(
            """INSERT INTO public.resources (id, tenant_id, name, content, category)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                   name = EXCLUDED.name,
                   content = EXCLUDED.content,
                   category = EXCLUDED.category
            """,
            (resource["id"], resource["tenant_id"], resource["name"],
             resource["content"], resource["category"])
        )

    # Generate real embeddings for each resource
    print("\n🔄 Generating real embeddings...")
    for resource in test_resources:
        # Generate embedding using provider's real embedding service
        embeddings = provider.generate_embeddings_batch([resource["content"]])
        embedding = embeddings[0]

        # Store embedding
        provider.execute(
            """INSERT INTO embeddings.resources_embeddings
               (id, entity_id, field_name, embedding, embedding_provider, tenant_id)
               VALUES (%s, %s, %s, %s::vector, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                   embedding = EXCLUDED.embedding
            """,
            (
                f"emb-{resource['id']}",
                resource["id"],
                "content",
                f"[{','.join(map(str, embedding))}]",
                "openai-ada-002",
                "tenant-test"
            )
        )

    print("✅ Seed data created with real embeddings")

    yield test_resources

    # Cleanup
    provider.execute("DELETE FROM public.resources WHERE tenant_id = 'tenant-test'")


@pytest.mark.integration
def test_sql_query(rem_provider, seed_data):
    """Test SQL query with WHERE, ORDER BY, LIMIT."""
    plan = REMQueryPlan(
        query_type=QueryType.SQL,
        parameters=SQLParameters(
            table_name="resources",
            tenant_id="tenant-test",
            select_fields=["id", "name", "category"],
            where_clause="category = 'article'",
            order_by=["name"],
            limit=10
        )
    )

    results = rem_provider.execute(plan)

    assert len(results) == 1
    assert results[0]["id"] == seed_data[0]["id"]  # Use UUID from seed_data
    assert results[0]["name"] == "Introduction to Machine Learning"
    assert results[0]["category"] == "article"

    print(f"\n✅ SQL Query: Found {len(results)} results")


@pytest.mark.integration
def test_lookup_query(rem_provider, seed_data):
    """Test key-based lookup."""
    dl_id = seed_data[1]["id"]  # Deep Learning resource
    plan = REMQueryPlan(
        query_type=QueryType.LOOKUP,
        parameters=LookupParameters(
            table_name="resources",
            tenant_id="tenant-test",
            key=dl_id,
            fields=["id", "name", "content"]
        )
    )

    results = rem_provider.execute(plan)

    assert len(results) == 1
    assert results[0]["id"] == dl_id
    assert results[0]["name"] == "Deep Learning Fundamentals"
    assert "deep learning" in results[0]["content"].lower()

    print(f"\n✅ LOOKUP Query: Found resource {results[0]['name']}")


@pytest.mark.integration
def test_lookup_multiple_keys(rem_provider, seed_data):
    """Test key-based lookup with multiple keys."""
    ml_id = seed_data[0]["id"]  # Machine Learning resource
    dl_id = seed_data[1]["id"]  # Deep Learning resource

    plan = REMQueryPlan(
        query_type=QueryType.LOOKUP,
        parameters=LookupParameters(
            table_name="resources",
            tenant_id="tenant-test",
            key=[ml_id, dl_id],  # Multiple keys as list
            fields=["id", "name", "content"]
        )
    )

    results = rem_provider.execute(plan)

    assert len(results) == 2, "Should return results for both keys"

    result_ids = {r["id"] for r in results}
    assert ml_id in result_ids, "Should find Machine Learning resource"
    assert dl_id in result_ids, "Should find Deep Learning resource"

    result_names = {r["name"] for r in results}
    assert "Introduction to Machine Learning" in result_names
    assert "Deep Learning Fundamentals" in result_names

    print(f"\n✅ LOOKUP Multiple Keys: Found {len(results)} resources")
    for result in results:
        print(f"  • {result['name']}")


@pytest.mark.integration
def test_search_query_with_real_embeddings(rem_provider, seed_data):
    """Test semantic search with real embeddings."""
    plan = REMQueryPlan(
        query_type=QueryType.SEARCH,
        parameters=SearchParameters(
            table_name="resources",
            tenant_id="tenant-test",
            query_text="artificial intelligence and neural networks",
            embedding_field="content",
            limit=3,
            threshold=0.6,  # Real embeddings have higher similarity
            metric="cosine"
        )
    )

    print("\n🔍 Executing semantic search with real embeddings...")
    results = rem_provider.execute(plan)

    assert len(results) > 0, "Should find semantically similar results"

    # Results should be ordered by similarity
    print(f"\n✅ SEARCH Query: Found {len(results)} results")
    for i, result in enumerate(results, 1):
        distance = result.get("distance", 0.0)
        similarity = 1.0 - distance
        print(f"  {i}. {result['name']}")
        print(f"     Similarity: {similarity:.2%}")

    # Verify results are relevant (ML/DL content should rank high)
    top_result_names = [r["name"] for r in results[:2]]
    assert any("Machine Learning" in name or "Deep Learning" in name
               for name in top_result_names), \
        "Top results should include ML/DL content for AI query"


@pytest.mark.integration
def test_search_different_query(rem_provider, seed_data):
    """Test semantic search with different query text."""
    plan = REMQueryPlan(
        query_type=QueryType.SEARCH,
        parameters=SearchParameters(
            table_name="resources",
            tenant_id="tenant-test",
            query_text="programming languages for data analysis",
            embedding_field="content",
            limit=3,
            threshold=0.5,
            metric="cosine"
        )
    )

    print("\n🔍 Executing semantic search for programming query...")
    results = rem_provider.execute(plan)

    assert len(results) > 0, "Should find results for programming query"

    print(f"\n✅ SEARCH Query: Found {len(results)} results")
    for i, result in enumerate(results, 1):
        distance = result.get("distance", 0.0)
        similarity = 1.0 - distance
        print(f"  {i}. {result['name']}")
        print(f"     Similarity: {similarity:.2%}")

    # Python guide should rank highly for programming query
    top_result_names = [r["name"] for r in results[:2]]
    assert any("Python" in name for name in top_result_names), \
        "Python content should rank high for programming query"


@pytest.mark.integration
def test_sql_with_multiple_filters(rem_provider, seed_data):
    """Test SQL with complex WHERE clause."""
    plan = REMQueryPlan(
        query_type=QueryType.SQL,
        parameters=SQLParameters(
            table_name="resources",
            tenant_id="tenant-test",
            select_fields=["id", "name", "category"],
            where_clause="category IN ('article', 'tutorial')",
            order_by=["category", "name"],
            limit=10
        )
    )

    results = rem_provider.execute(plan)

    assert len(results) == 2, "Should find 2 resources (article + tutorial)"

    # Verify ordering: article comes before tutorial alphabetically
    assert results[0]["category"] == "article"
    assert results[1]["category"] == "tutorial"

    print(f"\n✅ SQL Complex Query: Found {len(results)} results")
    for result in results:
        print(f"  • {result['name']} ({result['category']})")


@pytest.mark.integration
def test_lookup_nonexistent_key(rem_provider, seed_data):
    """Test lookup with nonexistent key."""
    plan = REMQueryPlan(
        query_type=QueryType.LOOKUP,
        parameters=LookupParameters(
            table_name="resources",
            tenant_id="tenant-test",
            key="nonexistent-id",
            fields=["id", "name"]
        )
    )

    results = rem_provider.execute(plan)

    assert len(results) == 0, "Should return empty list for nonexistent key"

    print("\n✅ LOOKUP Nonexistent: Correctly returned empty results")


@pytest.mark.integration
def test_search_with_low_threshold(rem_provider, seed_data):
    """Test semantic search with different threshold."""
    plan = REMQueryPlan(
        query_type=QueryType.SEARCH,
        parameters=SearchParameters(
            table_name="resources",
            tenant_id="tenant-test",
            query_text="machine learning algorithms",
            embedding_field="content",
            limit=10,
            threshold=0.3,  # Lower threshold to get more results
            metric="cosine"
        )
    )

    results = rem_provider.execute(plan)

    # With lower threshold, should get all 3 resources
    assert len(results) >= 2, "Lower threshold should return more results"

    print(f"\n✅ SEARCH Low Threshold: Found {len(results)} results")
    for result in results:
        distance = result.get("distance", 0.0)
        print(f"  • {result['name']} (distance: {distance:.4f})")


if __name__ == "__main__":
    # Run tests manually
    import sys
    sys.path.insert(0, "/Users/sirsh/code/p8fs-modules/p8fs/src")

    from p8fs.providers import get_provider
    from p8fs.providers.rem_query import REMQueryProvider

    print("="*80)
    print("REM Query Provider - Integration Tests")
    print("="*80)

    # Create provider
    pg_provider = get_provider()
    rem_provider = REMQueryProvider(pg_provider, tenant_id="tenant-test")

    # Seed data
    print("\n📦 Seeding test data...")
    class FakeSeedData:
        pass
    seed_fixture = FakeSeedData()

    # Run seed_data fixture manually
    import pytest
    seed_gen = seed_data(rem_provider)
    test_resources = next(seed_gen)

    try:
        # Run tests
        print("\n" + "="*80)
        print("Running Tests")
        print("="*80)

        test_sql_query(rem_provider, test_resources)
        test_lookup_query(rem_provider, test_resources)
        test_search_query_with_real_embeddings(rem_provider, test_resources)
        test_search_different_query(rem_provider, test_resources)
        test_sql_with_multiple_filters(rem_provider, test_resources)
        test_lookup_nonexistent_key(rem_provider, test_resources)
        test_search_with_low_threshold(rem_provider, test_resources)

        print("\n" + "="*80)
        print("🎉 All tests passed!")
        print("="*80)

    finally:
        # Cleanup
        try:
            next(seed_gen)
        except StopIteration:
            pass
