#!/usr/bin/env python3
"""Setup test data for REM query testing."""

import sys
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


def setup_test_data():
    """Insert test data into PostgreSQL or TiDB."""
    # Get provider based on config
    if config.storage_provider == "tidb":
        from p8fs.providers import TiDBProvider
        provider = TiDBProvider()
        print(f"Using TiDB provider ({config.tidb_host}:{config.tidb_port})")
    else:
        from p8fs.providers import PostgreSQLProvider
        provider = PostgreSQLProvider()
        print(f"Using PostgreSQL provider ({config.pg_host}:{config.pg_port})")

    conn = provider.connect_sync()

    # Create resources if they don't exist
    test_resources = [
        {
            "id": "test-resource-1",
            "tenant_id": "tenant-test",
            "category": "diary",
            "name": "Morning Journal",
            "content": "Today I woke up early and went for a run. The weather was beautiful.",
        },
        {
            "id": "test-resource-2",
            "tenant_id": "tenant-test",
            "category": "diary",
            "name": "Evening Reflection",
            "content": "Spent the afternoon working on the project. Made good progress on the database queries.",
        },
        {
            "id": "test-resource-3",
            "tenant_id": "tenant-test",
            "category": "note",
            "name": "Meeting Notes",
            "content": "Discussed the new features with the team. Everyone is excited about the REM query system.",
        },
    ]

    print("Setting up test data in PostgreSQL...")

    for resource in test_resources:
        try:
            # Check if exists
            check_sql = "SELECT id FROM public.resources WHERE id = %s AND tenant_id = %s"
            existing = provider.execute(check_sql, (resource["id"], resource["tenant_id"]))

            if existing:
                print(f"  ✓ {resource['id']} already exists")
                continue

            # Insert
            insert_sql = """
                INSERT INTO public.resources (id, tenant_id, category, name, content, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """
            provider.execute(
                insert_sql,
                (
                    resource["id"],
                    resource["tenant_id"],
                    resource["category"],
                    resource["name"],
                    resource["content"],
                ),
            )
            print(f"  ✓ Created {resource['id']}")

        except Exception as e:
            print(f"  ✗ Failed to create {resource['id']}: {e}")

    # Generate embeddings for SEARCH testing
    print("\nGenerating embeddings for semantic search...")

    try:
        # Get all test resources that need embeddings
        sql = "SELECT id, content FROM public.resources WHERE tenant_id = 'tenant-test'"
        resources = provider.execute(sql)

        for resource in resources:
            # Check if embedding already exists
            check_sql = """
                SELECT COUNT(*) as count FROM embeddings.resources_embeddings
                WHERE entity_id = %s AND tenant_id = %s AND field_name = 'content'
            """
            existing = provider.execute(check_sql, (resource["id"], "tenant-test"))

            if existing and existing[0]["count"] > 0:
                print(f"  ✓ {resource['id']} already has embeddings")
                continue

            # Generate embedding using provider's embedding service
            try:
                embeddings = provider.generate_embeddings_batch([resource["content"]])
                embedding_vector = embeddings[0]

                # Insert embedding
                insert_sql = """
                    INSERT INTO embeddings.resources_embeddings
                    (entity_id, tenant_id, field_name, embedding, embedding_provider, vector_dimension, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """
                provider.execute(
                    insert_sql,
                    (
                        resource["id"],
                        "tenant-test",
                        "content",
                        embedding_vector,
                        config.embedding_provider,
                        len(embedding_vector),
                    ),
                )
                print(f"  ✓ Generated embedding for {resource['id']}")

            except Exception as e:
                print(f"  ✗ Failed to generate embedding for {resource['id']}: {e}")

    except Exception as e:
        print(f"Warning: Could not generate embeddings: {e}")
        print("SEARCH queries will not work without embeddings")

    # Verify
    count_sql = "SELECT COUNT(*) as count FROM public.resources WHERE tenant_id = 'tenant-test'"
    result = provider.execute(count_sql)
    count = result[0]["count"] if result else 0

    embedding_sql = "SELECT COUNT(*) as count FROM embeddings.resources_embeddings WHERE tenant_id = 'tenant-test'"
    embedding_result = provider.execute(embedding_sql)
    embedding_count = embedding_result[0]["count"] if embedding_result else 0

    print(f"\nTotal test resources: {count}")
    print(f"Total embeddings: {embedding_count}")
    return 0


if __name__ == "__main__":
    sys.exit(setup_test_data())
