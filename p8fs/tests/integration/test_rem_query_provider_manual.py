"""
Integration tests for REM Query Provider with real embeddings.
Manual execution version (no pytest fixtures).
"""

import sys
sys.path.insert(0, "/Users/sirsh/code/p8fs-modules/p8fs/src")

from p8fs.providers import get_provider
from p8fs.providers.rem_query import (
    REMQueryProvider,
    REMQueryPlan,
    QueryType,
    SQLParameters,
    LookupParameters,
    SearchParameters,
)


def setup_test_data(provider):
    """Create test tables and seed data with real embeddings."""
    print("\n📦 Setting up test data...")

    # Create test resources table
    provider.execute("""
        CREATE TABLE IF NOT EXISTS public.resources (
            id VARCHAR(255) PRIMARY KEY,
            tenant_id VARCHAR(255) NOT NULL,
            name VARCHAR(500),
            content TEXT,
            category VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Create embeddings schema and table
    provider.execute("CREATE SCHEMA IF NOT EXISTS embeddings")

    provider.execute("""
        CREATE TABLE IF NOT EXISTS embeddings.resources_embeddings (
            id VARCHAR(255) PRIMARY KEY,
            entity_id VARCHAR(255) NOT NULL,
            field_name VARCHAR(100) NOT NULL,
            embedding vector(1536),
            embedding_provider VARCHAR(100),
            tenant_id VARCHAR(255),
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (entity_id) REFERENCES public.resources(id) ON DELETE CASCADE
        )
    """)

    # Delete existing test data
    provider.execute("DELETE FROM public.resources WHERE tenant_id = 'tenant-test'")

    # Insert test resources
    test_resources = [
        {
            "id": "res-ml-1",
            "tenant_id": "tenant-test",
            "name": "Introduction to Machine Learning",
            "content": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed. It focuses on developing algorithms that can access data and use it to learn for themselves.",
            "category": "article"
        },
        {
            "id": "res-dl-1",
            "tenant_id": "tenant-test",
            "name": "Deep Learning Fundamentals",
            "content": "Deep learning is a machine learning technique that teaches computers to do what comes naturally to humans: learn by example. It is a key technology behind driverless cars, voice control, and many other applications.",
            "category": "tutorial"
        },
        {
            "id": "res-py-1",
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
    print("🔄 Generating real embeddings (this may take a few seconds)...")
    for i, resource in enumerate(test_resources, 1):
        print(f"  {i}/3: {resource['name'][:50]}...")

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

    print("✅ Seed data created with real embeddings\n")
    return test_resources


def test_sql_query(rem_provider):
    """Test SQL query with WHERE, ORDER BY, LIMIT."""
    print("="*80)
    print("TEST 1: SQL Query")
    print("="*80)

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

    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    assert results[0]["id"] == "res-ml-1"
    assert results[0]["category"] == "article"

    print(f"✅ Found {len(results)} article(s):")
    for result in results:
        print(f"  • {result['name']} ({result['category']})")
    print()


def test_lookup_query(rem_provider):
    """Test key-based lookup."""
    print("="*80)
    print("TEST 2: LOOKUP Query")
    print("="*80)

    plan = REMQueryPlan(
        query_type=QueryType.LOOKUP,
        parameters=LookupParameters(
            table_name="resources",
            tenant_id="tenant-test",
            key="res-dl-1",
            fields=["id", "name", "content"]
        )
    )

    results = rem_provider.execute(plan)

    assert len(results) == 1
    assert results[0]["id"] == "res-dl-1"
    assert "deep learning" in results[0]["content"].lower()

    print(f"✅ Found resource:")
    print(f"  • ID: {results[0]['id']}")
    print(f"  • Name: {results[0]['name']}")
    print(f"  • Content: {results[0]['content'][:80]}...")
    print()


def test_search_query(rem_provider):
    """Test semantic search with real embeddings."""
    print("="*80)
    print("TEST 3: SEARCH Query (Real Embeddings)")
    print("="*80)

    plan = REMQueryPlan(
        query_type=QueryType.SEARCH,
        parameters=SearchParameters(
            table_name="resources",
            tenant_id="tenant-test",
            query_text="artificial intelligence and neural networks",
            embedding_field="content",
            limit=3,
            threshold=0.5,
            metric="cosine"
        )
    )

    print("🔍 Searching for: 'artificial intelligence and neural networks'")
    print("   (This will generate a real embedding via API...)\n")

    results = rem_provider.execute(plan)

    assert len(results) > 0, "Should find semantically similar results"

    print(f"✅ Found {len(results)} semantically similar results:")
    for i, result in enumerate(results, 1):
        distance = result.get("distance", 0.0)
        similarity = 1.0 - distance
        print(f"  {i}. {result['name']}")
        print(f"     Similarity: {similarity:.2%} (distance: {distance:.4f})")

    # Verify ML/DL content ranks high
    top_result_names = [r["name"] for r in results[:2]]
    assert any("Machine Learning" in name or "Deep Learning" in name
               for name in top_result_names), \
        "Top results should include ML/DL content"
    print()


def test_search_different_query(rem_provider):
    """Test semantic search with different query."""
    print("="*80)
    print("TEST 4: SEARCH Query (Different Topic)")
    print("="*80)

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

    print("🔍 Searching for: 'programming languages for data analysis'\n")

    results = rem_provider.execute(plan)

    assert len(results) > 0

    print(f"✅ Found {len(results)} results:")
    for i, result in enumerate(results, 1):
        distance = result.get("distance", 0.0)
        similarity = 1.0 - distance
        print(f"  {i}. {result['name']}")
        print(f"     Similarity: {similarity:.2%}")

    # Python should rank high for programming query
    top_result_names = [r["name"] for r in results[:2]]
    assert any("Python" in name for name in top_result_names), \
        "Python content should rank high"
    print()


def test_sql_complex(rem_provider):
    """Test SQL with complex WHERE clause."""
    print("="*80)
    print("TEST 5: SQL Complex Query")
    print("="*80)

    plan = REMQueryPlan(
        query_type=QueryType.SQL,
        parameters=SQLParameters(
            table_name="resources",
            tenant_id="tenant-test",
            select_fields=["id", "name", "category"],
            where_clause="category IN ('article', 'tutorial')",
            order_by=["category", "name"],
        )
    )

    results = rem_provider.execute(plan)

    assert len(results) == 2

    print(f"✅ Found {len(results)} results:")
    for result in results:
        print(f"  • {result['name']} ({result['category']})")
    print()


def run_all_tests():
    """Run all integration tests."""
    print("\n" + "="*80)
    print("🧪 REM Query Provider - Integration Tests (Real Embeddings)")
    print("="*80)

    # Create providers
    pg_provider = get_provider()
    rem_provider = REMQueryProvider(pg_provider, tenant_id="tenant-test")

    # Setup test data
    setup_test_data(pg_provider)

    try:
        # Run tests
        test_sql_query(rem_provider)
        test_lookup_query(rem_provider)
        test_search_query(rem_provider)
        test_search_different_query(rem_provider)
        test_sql_complex(rem_provider)

        print("="*80)
        print("🎉 All tests passed!")
        print("="*80)
        print()

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        print("🧹 Cleaning up test data...")
        pg_provider.execute("DELETE FROM public.resources WHERE tenant_id = 'tenant-test'")
        print("✅ Cleanup complete\n")


if __name__ == "__main__":
    run_all_tests()
