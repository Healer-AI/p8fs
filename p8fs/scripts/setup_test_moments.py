#!/usr/bin/env python3
"""Setup test moment data with tags and dates for testing REM queries."""

import sys
import json
from datetime import datetime, timedelta
from uuid import uuid5, NAMESPACE_DNS
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


def make_moment_uuid(name: str) -> str:
    """Generate deterministic UUID from moment name."""
    return str(uuid5(NAMESPACE_DNS, f"moment:{name}"))


def setup_test_moments():
    """Insert test moments into PostgreSQL or TiDB."""
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

    # Create test moments with various tags and dates
    now = datetime.now()
    test_moments = [
        {
            "id": make_moment_uuid("work-meeting-1"),
            "tenant_id": "tenant-test",
            "name": "Team Standup Meeting",
            "content": "Discussed progress on the REM query system implementation. Everyone is excited about the new semantic search capabilities.",
            "category": "meeting",
            "resource_timestamp": now - timedelta(hours=2),
            "resource_ends_timestamp": now - timedelta(hours=1, minutes=45),
            "moment_type": "meeting",
            "topic_tags": ["work", "meeting", "rem-query", "standup"],
            "emotion_tags": ["excited", "collaborative", "focused"],
            "uri": "meeting://2025-11-06/standup",
        },
        {
            "id": make_moment_uuid("work-coding-1"),
            "tenant_id": "tenant-test",
            "name": "Coding Session - Database Integration",
            "content": "Implemented the TiDB connection pooling feature. Fixed several bugs related to transaction timeouts. Added comprehensive tests.",
            "category": "work",
            "resource_timestamp": now - timedelta(days=1, hours=3),
            "resource_ends_timestamp": now - timedelta(days=1, hours=1),
            "moment_type": "work_session",
            "topic_tags": ["work", "coding", "database", "tidb", "debugging"],
            "emotion_tags": ["focused", "productive", "satisfied"],
            "uri": "session://2025-11-05/coding",
        },
        {
            "id": make_moment_uuid("personal-exercise-1"),
            "tenant_id": "tenant-test",
            "name": "Morning Run",
            "content": "Went for a 5km run in the park. Beautiful weather, clear sky. Felt energized and ready for the day.",
            "category": "exercise",
            "resource_timestamp": now - timedelta(days=0, hours=12),
            "resource_ends_timestamp": now - timedelta(days=0, hours=11, minutes=30),
            "moment_type": "exercise",
            "topic_tags": ["personal", "exercise", "running", "outdoors"],
            "emotion_tags": ["energized", "happy", "peaceful"],
            "uri": "activity://2025-11-06/morning-run",
        },
        {
            "id": make_moment_uuid("learning-docs-1"),
            "tenant_id": "tenant-test",
            "name": "Reading TiDB Documentation",
            "content": "Studied TiDB vector search capabilities and VEC_COSINE_DISTANCE function. Learned about performance optimization for large vector datasets.",
            "category": "learning",
            "resource_timestamp": now - timedelta(days=2, hours=5),
            "resource_ends_timestamp": now - timedelta(days=2, hours=4),
            "moment_type": "learning",
            "topic_tags": ["learning", "database", "tidb", "vectors", "documentation"],
            "emotion_tags": ["curious", "focused", "engaged"],
            "uri": "study://2025-11-04/tidb-docs",
        },
        {
            "id": make_moment_uuid("planning-1"),
            "tenant_id": "tenant-test",
            "name": "Weekly Planning Session",
            "content": "Planned upcoming features for the REM query system. Prioritized type-agnostic LOOKUP and semantic SEARCH improvements.",
            "category": "planning",
            "resource_timestamp": now - timedelta(days=3, hours=10),
            "resource_ends_timestamp": now - timedelta(days=3, hours=9),
            "moment_type": "planning",
            "topic_tags": ["work", "planning", "rem-query", "prioritization"],
            "emotion_tags": ["thoughtful", "strategic", "organized"],
            "uri": "planning://2025-11-03/weekly",
        },
    ]

    print("Setting up test moments...")

    for moment in test_moments:
        try:
            # Check if exists
            check_sql = "SELECT id FROM public.moments WHERE id = %s AND tenant_id = %s"
            existing = provider.execute(check_sql, (moment["id"], moment["tenant_id"]))

            if existing:
                print(f"  ✓ {moment['id']} already exists")
                continue

            # Convert tags to JSON for JSONB columns
            topic_tags_json = json.dumps(moment["topic_tags"])
            emotion_tags_json = json.dumps(moment["emotion_tags"])

            # Insert with JSONB casting
            insert_sql = """
                INSERT INTO public.moments
                (id, tenant_id, name, content, category, resource_timestamp, resource_ends_timestamp,
                 moment_type, topic_tags, emotion_tags, uri, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, NOW())
            """
            provider.execute(
                insert_sql,
                (
                    moment["id"],
                    moment["tenant_id"],
                    moment["name"],
                    moment["content"],
                    moment["category"],
                    moment["resource_timestamp"],
                    moment["resource_ends_timestamp"],
                    moment["moment_type"],
                    topic_tags_json,
                    emotion_tags_json,
                    moment["uri"],
                ),
            )
            print(f"  ✓ Created {moment['id']}")

        except Exception as e:
            print(f"  ✗ Failed to create {moment['id']}: {e}")

    # Verify
    count_sql = "SELECT COUNT(*) as count FROM public.moments WHERE tenant_id = 'tenant-test'"
    result = provider.execute(count_sql)
    count = result[0]["count"] if result else 0

    print(f"\nTotal test moments: {count}")

    # Show some example queries
    print("\n" + "="*60)
    print("Example REM queries you can try:")
    print("="*60)
    print('\n1. Recent moments:')
    print('   SELECT * FROM moments ORDER BY resource_timestamp DESC LIMIT 3')
    print('\n2. Work-related moments:')
    print("   SELECT * FROM moments WHERE topic_tags @> ARRAY['work']")
    print('\n3. Moments from last 2 days:')
    print(f"   SELECT * FROM moments WHERE resource_timestamp > '{(now - timedelta(days=2)).isoformat()}'")
    print('\n4. Happy moments:')
    print("   SELECT * FROM moments WHERE emotion_tags @> ARRAY['happy']")
    print('\n5. Semantic search:')
    print('   SEARCH "database work" IN moments')

    return 0


if __name__ == "__main__":
    sys.exit(setup_test_moments())
