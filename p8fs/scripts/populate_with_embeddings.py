#!/usr/bin/env python3
"""
Populate test data for dreaming worker testing.

Creates resources, sessions, and moments with proper embeddings and graph_paths.
This is the recommended script for local testing of the dreaming worker.

Requirements:
    - PostgreSQL running: docker compose up postgres -d
    - OPENAI_API_KEY set: source ~/.bash_profile

Usage:
    source ~/.bash_profile
    uv run python scripts/populate_with_embeddings.py

Note:
    Sets P8FS_EMBEDDING_PROVIDER=text-embedding-3-small to use OpenAI embeddings
    (1536 dimensions) instead of FastEmbed (384 dimensions).
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

# IMPORTANT: Set embedding provider BEFORE any p8fs imports
# Import cluster config first and override the default
from p8fs_cluster.config import config
config.default_embedding_provider = "text-embedding-3-small"

from p8fs.models.p8 import Resources, Session
from p8fs.models.engram.models import Moment
from p8fs.repository import TenantRepository
from p8fs.providers import get_provider
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

TENANT_ID = "tenant-test"

async def populate_data():
    """Populate sessions, resources, and moments with embeddings."""

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set. Please run: source ~/.bash_profile")
        return

    logger.info(f"Using OpenAI embedding provider: {config.default_embedding_provider}")

    provider = get_provider()
    provider.connect_sync()

    # Clean up old data
    logger.info("Cleaning up old data...")
    provider.execute("DELETE FROM moments WHERE tenant_id = %s", (TENANT_ID,))
    provider.execute("DELETE FROM sessions WHERE tenant_id = %s", (TENANT_ID,))
    provider.execute("DELETE FROM resources WHERE tenant_id = %s", (TENANT_ID,))

    # Delete embeddings
    provider.execute("DELETE FROM embeddings.moments_embeddings WHERE tenant_id = %s", (TENANT_ID,))
    provider.execute("DELETE FROM embeddings.resources_embeddings WHERE tenant_id = %s", (TENANT_ID,))

    now = datetime.now()

    # Create repositories
    resource_repo = TenantRepository(Resources, TENANT_ID)
    moment_repo = TenantRepository(Moment, TENANT_ID)

    # Create resources with graph_paths
    logger.info("\nCreating resources...")
    resources = []

    resource1 = Resources(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="API Design Document",
        category="documentation",
        content="Complete API redesign for microservices architecture. Focus on scalability and performance. The new design includes authentication service, data service, and notification service.",
        graph_paths=[
            {"dst": "api-redesign", "rel": "mentions", "entity_type": "project"},
            {"dst": "alice-chen", "rel": "mentions", "entity_type": "person"}
        ]
    )
    await resource_repo.put(resource1)
    resources.append(resource1)
    logger.info(f"  ✓ Created: {resource1.name}")

    resource2 = Resources(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Database Migration Plan",
        category="documentation",
        content="Migration strategy from PostgreSQL to TiDB. Includes dual-write phase, validation, and rollback plan. Expected completion in Q2 2024.",
        graph_paths=[
            {"dst": "database-migration", "rel": "mentions", "entity_type": "project"},
            {"dst": "bob-martinez", "rel": "mentions", "entity_type": "person"}
        ]
    )
    await resource_repo.put(resource2)
    resources.append(resource2)
    logger.info(f"  ✓ Created: {resource2.name}")

    resource3 = Resources(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Morning Journal",
        category="diary",
        content="Woke up early and went for a run. Beautiful weather, clear skies. Felt energized and ready to tackle the day ahead.",
        graph_paths=[]
    )
    await resource_repo.put(resource3)
    resources.append(resource3)
    logger.info(f"  ✓ Created: {resource3.name}")

    # Create sessions
    logger.info("\nCreating sessions...")

    session1_id = str(uuid4())
    provider.execute(
        """
        INSERT INTO sessions
        (id, tenant_id, name, query, session_type, graph_paths, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
        """,
        (session1_id, TENANT_ID, "API Design Discussion",
         "How should we design the new microservices API?", "chat",
         f'[{{"dst": "{resources[0].id}", "rel": "discusses", "entity_type": "resource"}}]')
    )
    logger.info("  ✓ Created: API Design Discussion")

    session2_id = str(uuid4())
    provider.execute(
        """
        INSERT INTO sessions
        (id, tenant_id, name, query, session_type, graph_paths, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
        """,
        (session2_id, TENANT_ID, "Database Migration Planning",
         "What's the best strategy for migrating to TiDB?", "chat",
         f'[{{"dst": "{resources[1].id}", "rel": "discusses", "entity_type": "resource"}}]')
    )
    logger.info("  ✓ Created: Database Migration Planning")

    session3_id = str(uuid4())
    provider.execute(
        """
        INSERT INTO sessions
        (id, tenant_id, name, query, session_type, graph_paths, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
        """,
        (session3_id, TENANT_ID, "Morning Reflection",
         "What are my goals for today?", "chat",
         f'[{{"dst": "{resources[2].id}", "rel": "discusses", "entity_type": "resource"}}]')
    )
    logger.info("  ✓ Created: Morning Reflection")

    # Create moments with embeddings
    logger.info("\nCreating moments...")

    moment1 = Moment(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Team Standup Meeting",
        content="Discussed progress on API redesign and database migration. Team is excited about the new architecture. Alice presented the microservices design.",
        summary="Daily standup with engineering team",
        moment_type="meeting",
        topic_tags=["work", "standup", "api", "database"],
        emotion_tags=["excited", "collaborative", "focused"],
        resource_timestamp=now - timedelta(hours=2),
        resource_ends_timestamp=now - timedelta(hours=1, minutes=45),
        location="Office"
    )
    await moment_repo.put(moment1)
    logger.info(f"  ✓ Created: {moment1.name}")

    moment2 = Moment(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Coding Session - API Implementation",
        content="Deep work session implementing new API endpoints for authentication service. Made good progress on OAuth 2.0 integration and token management.",
        summary="Productive coding session on authentication",
        moment_type="work_session",
        topic_tags=["coding", "api", "authentication", "oauth"],
        emotion_tags=["focused", "productive", "satisfied"],
        resource_timestamp=now - timedelta(days=1, hours=3),
        resource_ends_timestamp=now - timedelta(days=1, hours=1),
        location="Home Office"
    )
    await moment_repo.put(moment2)
    logger.info(f"  ✓ Created: {moment2.name}")

    moment3 = Moment(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Morning Run",
        content="5km run in the park. Clear sky, beautiful weather. Felt energized and refreshed. Great way to start the day.",
        summary="Morning exercise",
        moment_type="exercise",
        topic_tags=["exercise", "running", "outdoors", "health"],
        emotion_tags=["energized", "happy", "peaceful"],
        resource_timestamp=now - timedelta(hours=12),
        resource_ends_timestamp=now - timedelta(hours=11, minutes=30),
        location="City Park"
    )
    await moment_repo.put(moment3)
    logger.info(f"  ✓ Created: {moment3.name}")

    moment4 = Moment(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Database Research",
        content="Studied TiDB documentation on vector search capabilities and VEC_COSINE_DISTANCE function. Learned about performance optimization for large vector datasets.",
        summary="Learning session on TiDB vector search",
        moment_type="learning",
        topic_tags=["learning", "database", "tidb", "vectors"],
        emotion_tags=["curious", "engaged", "focused"],
        resource_timestamp=now - timedelta(days=2, hours=5),
        resource_ends_timestamp=now - timedelta(days=2, hours=4),
        location="Home Office"
    )
    await moment_repo.put(moment4)
    logger.info(f"  ✓ Created: {moment4.name}")

    # Verify embeddings were created
    logger.info("\n" + "="*80)
    logger.info("VERIFICATION")
    logger.info("="*80)

    counts = provider.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM resources WHERE tenant_id = %s) as resources,
            (SELECT COUNT(*) FROM sessions WHERE tenant_id = %s) as sessions,
            (SELECT COUNT(*) FROM moments WHERE tenant_id = %s) as moments,
            (SELECT COUNT(*) FROM embeddings.resources_embeddings WHERE tenant_id = %s) as resource_embeddings,
            (SELECT COUNT(*) FROM embeddings.moments_embeddings WHERE tenant_id = %s) as moment_embeddings
        """,
        (TENANT_ID, TENANT_ID, TENANT_ID, TENANT_ID, TENANT_ID)
    )

    if counts:
        stats = counts[0]
        logger.info(f"✓ Created {stats['resources']} resources")
        logger.info(f"✓ Created {stats['sessions']} sessions")
        logger.info(f"✓ Created {stats['moments']} moments")
        logger.info(f"✓ Generated {stats['resource_embeddings']} resource embeddings")
        logger.info(f"✓ Generated {stats['moment_embeddings']} moment embeddings")

    logger.info("\n✓ Demo data with embeddings populated successfully!")


if __name__ == "__main__":
    asyncio.run(populate_data())
