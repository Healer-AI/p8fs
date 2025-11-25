#!/usr/bin/env python3
"""
Simple demonstration of moment generation and querying.

Shows:
1. Creating resources with embeddings
2. Creating sessions with graph paths
3. Creating moments with time classification, emotion tags, and entity references
4. Querying moments to verify structure
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers import get_provider
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models.p8 import Resources, Session, Moment

logger = get_logger(__name__)
TENANT_ID = "tenant-demo-moments"


async def create_sample_data():
    """Create sample resources, sessions, and moments."""
    logger.info("=" * 80)
    logger.info("CREATING SAMPLE DATA")
    logger.info("=" * 80)

    provider = get_provider()
    provider.connect_sync()

    # Clean up
    logger.info("\nCleaning up old data...")
    provider.execute("DELETE FROM moments WHERE tenant_id = %s", (TENANT_ID,))
    provider.execute("DELETE FROM sessions WHERE tenant_id = %s", (TENANT_ID,))
    provider.execute("DELETE FROM resources WHERE tenant_id = %s", (TENANT_ID,))

    base_time = datetime.now(timezone.utc) - timedelta(hours=2)

    # Create resources
    logger.info("\n1. Creating Resources with Embeddings...")
    resource_repo = TenantRepository(Resources, tenant_id=TENANT_ID)

    resource1 = Resources(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Team Standup - OAuth Implementation",
        content="Good morning team! Sarah finished OAuth 2.1 PKCE flow. Mike deployed to staging. John reviewed the PR. Great progress on authentication!",
        category="meeting",
        resource_type="transcript",
        resource_timestamp=base_time,
        metadata={"participants": ["sarah", "mike", "john"]},
    )
    await resource_repo.put(resource1)
    logger.info(f"  ✓ Created: {resource1.name}")

    resource2 = Resources(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="One-on-One with Sarah",
        content="Career discussion with Sarah about tech lead role for microservices architecture. She's excited but nervous. Discussed growth opportunities.",
        category="conversation",
        resource_type="transcript",
        resource_timestamp=base_time + timedelta(hours=1),
        metadata={"participants": ["sarah", "john"]},
    )
    await resource_repo.put(resource2)
    logger.info(f"  ✓ Created: {resource2.name}")

    # Create sessions with graph paths
    logger.info("\n2. Creating Sessions with Graph Paths...")
    session_repo = TenantRepository(Session, tenant_id=TENANT_ID)

    session1 = Session(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Morning Standup Session",
        query="What did the team discuss in standup?",
        agent="chat",
        session_type="chat",
        metadata={"resource_id": resource1.id},
        graph_paths=[
            f"/resources/{resource1.id}/person/sarah",
            f"/resources/{resource1.id}/person/mike",
            f"/resources/{resource1.id}/topic/oauth-implementation",
            f"/resources/{resource1.id}/topic/authentication",
        ],
    )
    await session_repo.put(session1)
    logger.info(f"  ✓ Created: {session1.name}")
    logger.info(f"    Graph Paths: {len(session1.graph_paths)} paths")

    session2 = Session(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Career Development Discussion",
        query="Career growth conversation with Sarah",
        agent="chat",
        session_type="chat",
        metadata={"resource_id": resource2.id},
        graph_paths=[
            f"/resources/{resource2.id}/person/sarah",
            f"/resources/{resource2.id}/topic/tech-lead",
            f"/resources/{resource2.id}/topic/career-growth",
            f"/resources/{resource2.id}/emotion/excited",
            f"/resources/{resource2.id}/emotion/nervous",
        ],
    )
    await session_repo.put(session2)
    logger.info(f"  ✓ Created: {session2.name}")
    logger.info(f"    Graph Paths: {len(session2.graph_paths)} paths")

    # Create moments with rich metadata
    logger.info("\n3. Creating Moments with Time Classification, Emotions, Entity Paths...")
    moment_repo = TenantRepository(Moment, tenant_id=TENANT_ID)

    moment1 = Moment(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Morning Team Standup",
        content="Daily standup meeting discussing OAuth implementation progress, staging deployment, and PR reviews.",
        summary="Team aligned on authentication work",
        category="meeting",
        uri=f"moment://{uuid4()}",
        resource_type="moment",
        resource_timestamp=base_time,
        resource_ends_timestamp=base_time + timedelta(minutes=15),

        # Time classification
        moment_type="meeting",

        # Emotion tags
        emotion_tags=["focused", "collaborative", "positive"],

        # Topic tags
        topic_tags=["oauth-2.1", "authentication", "pkce-flow", "staging-deployment"],

        # Present persons
        present_persons={
            "sarah": {
                "user_id": "user-sarah",
                "fingerprint_id": "fp-sarah-123",
                "user_label": "Sarah (Senior Engineer)",
            },
            "mike": {
                "user_id": "user-mike",
                "fingerprint_id": "fp-mike-456",
                "user_label": "Mike (DevOps)",
            },
            "john": {
                "user_id": "user-john",
                "fingerprint_id": "fp-john-789",
                "user_label": "John (Engineering Lead)",
            },
        },

        # Graph paths to related entities
        graph_paths=[
            "/entity/person/sarah",
            "/entity/person/mike",
            "/entity/person/john",
            "/entity/topic/oauth-implementation",
            "/entity/project/authentication-service",
        ],

        metadata={
            "duration_minutes": 15,
            "meeting_type": "standup",
            "key_decisions": ["OAuth PR approved", "Staging deployment successful"],
        },
    )
    await moment_repo.put(moment1)
    logger.info(f"  ✓ Created: {moment1.name}")
    logger.info(f"    Type: {moment1.moment_type}")
    logger.info(f"    Emotions: {moment1.emotion_tags}")
    logger.info(f"    Duration: {moment1.duration_seconds() / 60:.1f} minutes")
    logger.info(f"    Present: {len(moment1.present_persons)} people")
    logger.info(f"    Graph Paths: {len(moment1.graph_paths)} paths")

    moment2 = Moment(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Sarah's Career Discussion",
        content="One-on-one conversation with Sarah about stepping into a tech lead role for the microservices architecture project. Discussed her readiness and growth opportunities.",
        summary="Career development conversation about tech leadership",
        category="conversation",
        uri=f"moment://{uuid4()}",
        resource_type="moment",
        resource_timestamp=base_time + timedelta(hours=1),
        resource_ends_timestamp=base_time + timedelta(hours=1, minutes=20),

        # Time classification
        moment_type="conversation",

        # Emotion tags
        emotion_tags=["optimistic", "nervous", "excited", "thoughtful"],

        # Topic tags
        topic_tags=["career-growth", "tech-lead", "microservices", "leadership", "mentorship"],

        # Present persons
        present_persons={
            "sarah": {
                "user_id": "user-sarah",
                "fingerprint_id": "fp-sarah-123",
                "user_label": "Sarah (Senior Engineer)",
            },
            "john": {
                "user_id": "user-john",
                "fingerprint_id": "fp-john-789",
                "user_label": "John (Engineering Lead)",
            },
        },

        # Graph paths to related entities
        graph_paths=[
            "/entity/person/sarah",
            "/entity/person/john",
            "/entity/topic/career-development",
            "/entity/topic/tech-lead-role",
            "/entity/project/microservices-migration",
            "/entity/emotion/nervous",
            "/entity/emotion/excited",
        ],

        metadata={
            "duration_minutes": 20,
            "conversation_type": "one-on-one",
            "outcomes": ["Sarah interested in tech lead role", "Follow-up meeting next week"],
        },
    )
    await moment_repo.put(moment2)
    logger.info(f"  ✓ Created: {moment2.name}")
    logger.info(f"    Type: {moment2.moment_type}")
    logger.info(f"    Emotions: {moment2.emotion_tags}")
    logger.info(f"    Duration: {moment2.duration_seconds() / 60:.1f} minutes")
    logger.info(f"    Present: {len(moment2.present_persons)} people")
    logger.info(f"    Graph Paths: {len(moment2.graph_paths)} paths")

    moment3 = Moment(
        id=str(uuid4()),
        tenant_id=TENANT_ID,
        name="Q4 Planning Session",
        content="Strategic planning meeting for Q4 microservices migration. Discussed timeline, resource allocation, and technical approach. Team committed to authentication service as first target.",
        summary="Q4 roadmap and microservices migration planning",
        category="meeting",
        uri=f"moment://{uuid4()}",
        resource_type="moment",
        resource_timestamp=base_time + timedelta(hours=3),
        resource_ends_timestamp=base_time + timedelta(hours=3, minutes=45),

        # Time classification
        moment_type="planning",

        # Emotion tags
        emotion_tags=["focused", "strategic", "collaborative", "determined"],

        # Topic tags
        topic_tags=["q4-planning", "microservices-migration", "architecture", "resource-allocation", "timeline"],

        # Present persons
        present_persons={
            "sarah": {"user_id": "user-sarah", "user_label": "Sarah (Senior Engineer)"},
            "mike": {"user_id": "user-mike", "user_label": "Mike (DevOps)"},
            "john": {"user_id": "user-john", "user_label": "John (Engineering Lead)"},
            "lisa": {"user_id": "user-lisa", "user_label": "Lisa (Product Manager)"},
        },

        # Graph paths to related entities
        graph_paths=[
            "/entity/person/sarah",
            "/entity/person/mike",
            "/entity/person/lisa",
            "/entity/topic/q4-roadmap",
            "/entity/project/microservices-migration",
            "/entity/project/authentication-service",
        ],

        metadata={
            "duration_minutes": 45,
            "meeting_type": "planning",
            "action_items": [
                "Mike: Infrastructure proposal by Friday",
                "Sarah: Auth service architecture doc",
                "John: Resource allocation plan",
            ],
        },
    )
    await moment_repo.put(moment3)
    logger.info(f"  ✓ Created: {moment3.name}")
    logger.info(f"    Type: {moment3.moment_type}")
    logger.info(f"    Emotions: {moment3.emotion_tags}")
    logger.info(f"    Duration: {moment3.duration_seconds() / 60:.1f} minutes")
    logger.info(f"    Present: {len(moment3.present_persons)} people")
    logger.info(f"    Graph Paths: {len(moment3.graph_paths)} paths")

    return provider


async def query_moments(provider):
    """Query and display saved moments."""
    logger.info("\n" + "=" * 80)
    logger.info("QUERYING SAVED MOMENTS")
    logger.info("=" * 80)

    # Query all moments
    moments = provider.execute(
        """
        SELECT
            id, name, moment_type, emotion_tags, topic_tags,
            resource_timestamp, resource_ends_timestamp,
            present_persons, graph_paths, location, content, summary
        FROM moments
        WHERE tenant_id = %s
        ORDER BY resource_timestamp
        """,
        (TENANT_ID,),
    )

    logger.info(f"\nFound {len(moments)} moments:\n")

    for i, moment in enumerate(moments, 1):
        logger.info(f"\n{i}. {moment['name']}")
        logger.info(f"   {'─' * 70}")
        logger.info(f"   Type: {moment['moment_type']}")
        logger.info(f"   Time: {moment['resource_timestamp']}")

        if moment['resource_ends_timestamp']:
            duration = (moment['resource_ends_timestamp'] - moment['resource_timestamp']).total_seconds() / 60
            logger.info(f"   Duration: {duration:.1f} minutes")

        logger.info(f"   Emotions: {', '.join(moment['emotion_tags'])}")
        logger.info(f"   Topics: {', '.join(moment['topic_tags'][:5])}...")

        if moment['present_persons']:
            persons = [p.get('user_label', p.get('user_id', '')) for p in moment['present_persons'].values()]
            logger.info(f"   Present: {', '.join(persons)}")

        if moment['graph_paths']:
            logger.info(f"   Graph Paths ({len(moment['graph_paths'])}):")
            for path in moment['graph_paths'][:3]:
                logger.info(f"     - {path}")
            if len(moment['graph_paths']) > 3:
                logger.info(f"     ... and {len(moment['graph_paths']) - 3} more")

        logger.info(f"   Summary: {moment['summary']}")

    # Statistics
    logger.info("\n" + "=" * 80)
    logger.info("STATISTICS")
    logger.info("=" * 80)

    # Moments by type
    type_stats = provider.execute(
        """
        SELECT moment_type, COUNT(*) as count
        FROM moments
        WHERE tenant_id = %s
        GROUP BY moment_type
        ORDER BY count DESC
        """,
        (TENANT_ID,),
    )

    logger.info("\nMoments by Type:")
    for stat in type_stats:
        logger.info(f"  {stat['moment_type']}: {stat['count']}")

    # Most common emotions
    emotion_stats = provider.execute(
        """
        SELECT emotion, COUNT(*) as count
        FROM moments, unnest(emotion_tags) as emotion
        WHERE tenant_id = %s
        GROUP BY emotion
        ORDER BY count DESC
        LIMIT 10
        """,
        (TENANT_ID,),
    )

    logger.info("\nMost Common Emotions:")
    for stat in emotion_stats:
        logger.info(f"  {stat['emotion']}: {stat['count']}")

    # Sessions with graph paths
    logger.info("\n" + "=" * 80)
    logger.info("SESSIONS WITH GRAPH PATHS")
    logger.info("=" * 80)

    sessions = provider.execute(
        """
        SELECT name, graph_paths
        FROM sessions
        WHERE tenant_id = %s AND graph_paths IS NOT NULL
        ORDER BY created_at
        """,
        (TENANT_ID,),
    )

    for session in sessions:
        logger.info(f"\n{session['name']}:")
        for path in session['graph_paths']:
            logger.info(f"  → {path}")


async def main():
    """Run demonstration."""
    logger.info("\n" + "=" * 80)
    logger.info("MOMENTS DEMONSTRATION")
    logger.info("=" * 80)

    provider = await create_sample_data()
    await query_moments(provider)

    logger.info("\n" + "=" * 80)
    logger.info("DEMONSTRATION COMPLETE")
    logger.info("=" * 80)
    logger.info("\n✓ Created resources with embeddings")
    logger.info("✓ Created sessions with graph paths")
    logger.info("✓ Created moments with:")
    logger.info("  - Time classification (moment_type)")
    logger.info("  - Emotion tags")
    logger.info("  - Topic tags")
    logger.info("  - Present persons")
    logger.info("  - Graph paths to related entities")
    logger.info("\n")


if __name__ == "__main__":
    asyncio.run(main())
