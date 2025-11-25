#!/usr/bin/env python3
"""
Comprehensive demo of moment generation workflow.

This script demonstrates:
1. Creating rich sample resources with embeddings
2. Creating sessions
3. Generating moments from resources using DreamModel/MomentBuilder
4. Saving moments to database
5. Querying moments to verify time classification, emotion tags, and entity relationships
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers import get_provider
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models.p8 import Resources, Session, Moment
from p8fs.services.llm import MemoryProxy
from p8fs.models.agentlets.moments import MomentBuilder

logger = get_logger(__name__)
TENANT_ID = "tenant-demo-moments"


async def create_sample_resources(repo: TenantRepository) -> list[Resources]:
    """Create rich sample resources with varied content."""
    logger.info("Creating sample resources...")

    base_time = datetime.now(timezone.utc) - timedelta(hours=2)

    resources = [
        Resources(
            id=str(uuid4()),
            tenant_id=TENANT_ID,
            name="Team Standup - OAuth Implementation",
            content="""
            Good morning team! Let's do our standup.

            Sarah: Yesterday I finished the OAuth 2.1 PKCE flow implementation. Today I'm working on token refresh logic and rate limiting. No blockers.

            Mike: I deployed the authentication service to staging. Had some issues with the database connection pool but got it sorted. Today I'm setting up monitoring and alerts. Need to sync with Sarah about the token expiry configuration.

            John: I reviewed Sarah's PR on the OAuth implementation - looks solid. Today I'm planning Q4 roadmap with product team. We need to discuss capacity for the microservices migration project.

            Great work everyone! We're making good progress on authentication. Let's regroup tomorrow.
            """,
            category="meeting",
            resource_type="transcript",
            resource_timestamp=base_time,
            metadata={"participants": ["sarah", "mike", "john"], "duration_minutes": 15},
        ),
        Resources(
            id=str(uuid4()),
            tenant_id=TENANT_ID,
            name="One-on-One with Sarah - Career Discussion",
            content="""
            John: Hey Sarah, thanks for making time. I wanted to check in on how you're feeling about your role and growth here.

            Sarah: Thanks for asking! I'm really happy with the technical work. The OAuth project has been challenging in a good way. I feel like I'm learning a lot.

            John: That's great to hear. You've been doing excellent work. Have you thought about what you want to focus on next?

            Sarah: Actually yes. I'm really interested in distributed systems and would love to get more involved in the microservices architecture planning. Maybe take on a tech lead role for one of the services?

            John: That's perfect timing. We're planning the Q4 migration and I think you'd be a great fit for leading the authentication service team. Let's talk more about that next week.

            Sarah: That would be amazing! I'm excited about it.

            John: Awesome. Also, don't forget to take some time off soon - you've been working hard.

            Sarah: Thanks, I will. Probably take a few days next month.
            """,
            category="conversation",
            resource_type="transcript",
            resource_timestamp=base_time + timedelta(hours=1),
            metadata={"participants": ["sarah", "john"], "duration_minutes": 20, "type": "one-on-one"},
        ),
        Resources(
            id=str(uuid4()),
            tenant_id=TENANT_ID,
            name="Personal Note - Weekend Plans",
            content="""
            Feeling pretty good after the 1:1 with John. The tech lead opportunity is exciting but also a bit nerve-wracking. Need to think about whether I'm ready for that level of responsibility.

            Weekend plans:
            - Finish reading "Designing Data-Intensive Applications"
            - Go hiking with Alex on Saturday
            - Meal prep for the week
            - Maybe start that side project I've been thinking about

            Feeling: Optimistic but slightly anxious about the new role. Need to trust myself more.
            """,
            category="journal",
            resource_type="text",
            resource_timestamp=base_time + timedelta(hours=2),
            metadata={"type": "personal"},
        ),
        Resources(
            id=str(uuid4()),
            tenant_id=TENANT_ID,
            name="Q4 Planning Meeting - Microservices Migration",
            content="""
            Attendees: John (Engineering Lead), Sarah (Senior Engineer), Mike (DevOps), Lisa (Product Manager)

            Lisa: Okay team, let's talk Q4 priorities. The big initiative is the microservices migration. We need to break down the monolith and improve our deployment velocity.

            John: Agreed. I'm thinking we start with authentication as it's the most isolated domain. Sarah has deep context there and could lead the effort.

            Sarah: I'd be excited to take that on. We'd need to consider the OAuth work I just finished and how it fits into a standalone service.

            Mike: From DevOps perspective, we'll need to set up new CI/CD pipelines, service mesh configuration, and monitoring for each service. That's going to be significant infrastructure work.

            John: Right. Mike, can you scope out the infrastructure requirements? We need to understand the lift before committing.

            Mike: I'll have a proposal by end of week.

            Lisa: What about timeline? Can we get auth service separated by end of Q4?

            John: If we dedicate Sarah full-time and give Mike 50% capacity for infrastructure, I think Q4 is realistic but tight. We'd need to push some other work.

            Lisa: Let's do it. This is the highest priority. I'll work with the other teams on dependencies.

            Action items:
            - Mike: Infrastructure proposal by Friday
            - Sarah: Architecture design doc for auth service by next week
            - John: Resource allocation plan
            - Lisa: Stakeholder communication plan
            """,
            category="meeting",
            resource_type="transcript",
            resource_timestamp=base_time + timedelta(hours=3),
            metadata={"participants": ["john", "sarah", "mike", "lisa"], "duration_minutes": 45, "type": "planning"},
        ),
    ]

    # Save resources
    for resource in resources:
        await repo.put(resource)
        logger.info(f"  Created: {resource.name}")

    logger.info(f"✓ Created {len(resources)} resources")
    return resources


async def generate_embeddings(repo: TenantRepository, resources: list[Resources]):
    """Generate embeddings for resources."""
    logger.info("\nGenerating embeddings...")

    provider = repo.provider
    for resource in resources:
        try:
            # Generate embedding for content
            embeddings = provider.generate_embeddings_batch([resource.content])
            embedding = embeddings[0]

            # Save embedding
            provider.execute(
                """
                INSERT INTO embeddings.resources_embeddings
                (id, entity_id, field_name, embedding_vector, embedding_provider, vector_dimension, tenant_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_id, field_name) DO UPDATE
                SET embedding_vector = EXCLUDED.embedding_vector
                """,
                (
                    str(uuid4()),
                    resource.id,
                    "content",
                    embedding,
                    "openai",
                    len(embedding),
                    TENANT_ID,
                ),
            )
            logger.info(f"  Generated embedding for: {resource.name}")
        except Exception as e:
            logger.error(f"  Failed to generate embedding for {resource.name}: {e}")

    logger.info("✓ Embeddings generated")


async def create_sample_sessions(repo: TenantRepository, resources: list[Resources]) -> list[Session]:
    """Create sessions linked to resources."""
    logger.info("\nCreating sessions...")

    sessions = [
        Session(
            id=str(uuid4()),
            tenant_id=TENANT_ID,
            name="Morning Standup Session",
            query="What did the team discuss in standup?",
            agent="chat",
            session_type="chat",
            metadata={"resource_id": resources[0].id},
            graph_paths=[f"/resources/{resources[0].id}/team/sarah", f"/resources/{resources[0].id}/team/mike"],
        ),
        Session(
            id=str(uuid4()),
            tenant_id=TENANT_ID,
            name="Career Development Discussion",
            query="Career growth conversation with Sarah",
            agent="chat",
            session_type="chat",
            metadata={"resource_id": resources[1].id, "type": "one-on-one"},
            graph_paths=[f"/resources/{resources[1].id}/person/sarah", f"/resources/{resources[1].id}/topic/tech-lead"],
        ),
    ]

    for session in sessions:
        await TenantRepository(Session, tenant_id=TENANT_ID).put(session)
        logger.info(f"  Created session: {session.name}")

    logger.info(f"✓ Created {len(sessions)} sessions")
    return sessions


async def generate_moments(resources: list[Resources]) -> list[Moment]:
    """Generate moments from resources using MomentBuilder."""
    logger.info("\nGenerating moments from resources...")

    memory_proxy = MemoryProxy()

    all_moments = []

    for resource in resources:
        logger.info(f"\n  Analyzing: {resource.name}")

        # Build prompt for MomentBuilder
        prompt = f"""Analyze this temporal data and extract distinct moments.

Resource: {resource.name}
Type: {resource.category}
Timestamp: {resource.resource_timestamp}
Content:
{resource.content}

Extract all distinct moments from this data. For each moment:
- Classify the moment type (conversation, meeting, reflection, planning, etc.)
- Identify emotion tags from language patterns
- Extract topic tags
- Identify who was present
- Set appropriate temporal boundaries
- Write clear summaries
"""

        try:
            # Call LLM to generate moments
            result = await memory_proxy.query(
                model=MomentBuilder,
                request={"content": resource.content},
                prompt=prompt,
                system_prompt=MomentBuilder.__doc__,
            )

            logger.info(f"  Extracted {result.total_moments} moments")

            # Convert moment dicts to Moment model instances
            for moment_data in result.moments:
                moment = Moment(
                    id=str(uuid4()),
                    tenant_id=TENANT_ID,
                    name=moment_data.get("name", f"Moment from {resource.name}"),
                    content=moment_data.get("content", ""),
                    summary=moment_data.get("summary"),
                    category=moment_data.get("category", resource.category),
                    uri=moment_data.get("uri", f"moment://{uuid4()}"),
                    resource_type="moment",
                    resource_timestamp=moment_data.get("resource_timestamp", resource.resource_timestamp),
                    resource_ends_timestamp=moment_data.get("resource_ends_timestamp"),
                    moment_type=moment_data.get("moment_type"),
                    emotion_tags=moment_data.get("emotion_tags", []),
                    topic_tags=moment_data.get("topic_tags", []),
                    present_persons=moment_data.get("present_persons"),
                    location=moment_data.get("location"),
                    background_sounds=moment_data.get("background_sounds"),
                    metadata=moment_data.get("metadata", {}),
                )
                all_moments.append(moment)

                logger.info(f"    - {moment.name}")
                logger.info(f"      Type: {moment.moment_type}")
                logger.info(f"      Emotions: {moment.emotion_tags}")
                logger.info(f"      Topics: {moment.topic_tags}")

        except Exception as e:
            logger.error(f"  Failed to generate moments: {e}")
            logger.exception(e)

    logger.info(f"\n✓ Generated {len(all_moments)} total moments")
    return all_moments


async def save_moments(repo: TenantRepository, moments: list[Moment]):
    """Save moments to database."""
    logger.info("\nSaving moments to database...")

    for moment in moments:
        await repo.put(moment)
        logger.info(f"  Saved: {moment.name}")

    logger.info(f"✓ Saved {len(moments)} moments")


async def query_and_display_moments(provider):
    """Query moments and display their properties."""
    logger.info("\n" + "=" * 80)
    logger.info("QUERYING SAVED MOMENTS")
    logger.info("=" * 80)

    # Query all moments
    moments = provider.execute(
        """
        SELECT
            id, name, moment_type, emotion_tags, topic_tags,
            resource_timestamp, resource_ends_timestamp,
            present_persons, location, content, summary
        FROM moments
        WHERE tenant_id = %s
        ORDER BY resource_timestamp
        """,
        (TENANT_ID,),
    )

    logger.info(f"\nFound {len(moments)} moments:\n")

    for i, moment in enumerate(moments, 1):
        logger.info(f"{i}. {moment['name']}")
        logger.info(f"   Type: {moment['moment_type']}")
        logger.info(f"   Time: {moment['resource_timestamp']}")

        if moment['resource_ends_timestamp']:
            duration = (moment['resource_ends_timestamp'] - moment['resource_timestamp']).total_seconds() / 60
            logger.info(f"   Duration: {duration:.1f} minutes")

        logger.info(f"   Emotions: {moment['emotion_tags']}")
        logger.info(f"   Topics: {moment['topic_tags']}")

        if moment['present_persons']:
            persons = list(moment['present_persons'].keys())
            logger.info(f"   Present: {persons}")

        if moment['location']:
            logger.info(f"   Location: {moment['location']}")

        logger.info(f"   Summary: {moment['summary']}")
        logger.info("")

    # Query moments with sessions (graph paths)
    logger.info("\n" + "=" * 80)
    logger.info("MOMENTS WITH SESSION GRAPH PATHS")
    logger.info("=" * 80)

    sessions_with_paths = provider.execute(
        """
        SELECT
            s.name as session_name,
            s.graph_paths,
            s.metadata,
            m.name as moment_name,
            m.moment_type
        FROM sessions s
        LEFT JOIN moments m ON m.id = s.moment_id
        WHERE s.tenant_id = %s AND s.graph_paths IS NOT NULL
        """,
        (TENANT_ID,),
    )

    for session in sessions_with_paths:
        logger.info(f"\nSession: {session['session_name']}")
        if session['moment_name']:
            logger.info(f"  Linked Moment: {session['moment_name']} ({session['moment_type']})")
        logger.info(f"  Graph Paths:")
        for path in session['graph_paths']:
            logger.info(f"    - {path}")

    # Statistics
    logger.info("\n" + "=" * 80)
    logger.info("MOMENT STATISTICS")
    logger.info("=" * 80)

    stats = provider.execute(
        """
        SELECT
            moment_type,
            COUNT(*) as count,
            ARRAY_AGG(DISTINCT emotion) as all_emotions
        FROM moments m,
             LATERAL unnest(m.emotion_tags) AS emotion
        WHERE m.tenant_id = %s
        GROUP BY moment_type
        ORDER BY count DESC
        """,
        (TENANT_ID,),
    )

    logger.info("\nMoments by Type:")
    for stat in stats:
        logger.info(f"  {stat['moment_type']}: {stat['count']} moments")
        logger.info(f"    Emotions: {stat['all_emotions']}")


async def main():
    """Run complete demo."""
    import os

    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY required for this demo")
        logger.info("Run: source ~/.bash_profile")
        return

    logger.info("=" * 80)
    logger.info("MOMENTS GENERATION DEMO")
    logger.info("=" * 80)

    # Get provider and create repositories
    provider = get_provider()
    provider.connect_sync()

    resource_repo = TenantRepository(Resources, tenant_id=TENANT_ID)

    # Clean up old data
    logger.info("\nCleaning up old data...")
    provider.execute("DELETE FROM moments WHERE tenant_id = %s", (TENANT_ID,))
    provider.execute("DELETE FROM sessions WHERE tenant_id = %s", (TENANT_ID,))
    provider.execute("DELETE FROM resources WHERE tenant_id = %s", (TENANT_ID,))
    provider.execute("DELETE FROM embeddings.resources_embeddings WHERE tenant_id = %s", (TENANT_ID,))

    # Create sample data (embeddings generated automatically via repo.put)
    resources = await create_sample_resources(resource_repo)
    sessions = await create_sample_sessions(resource_repo, resources)

    # Generate and save moments
    moments = await generate_moments(resources)
    moment_repo = TenantRepository(Moment, tenant_id=TENANT_ID)
    await save_moments(moment_repo, moments)

    # Query and display results
    await query_and_display_moments(provider)

    logger.info("\n" + "=" * 80)
    logger.info("DEMO COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
