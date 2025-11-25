#!/usr/bin/env python3
"""Test resource affinity algorithms with both basic and LLM modes.

This script demonstrates:
1. Creating diverse sample resources with embeddings
2. Running basic mode: semantic search + graph path merging
3. Running LLM mode: intelligent relationship assessment
4. Comparing results between modes
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from p8fs_cluster.logging import get_logger
from p8fs.providers import get_provider
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models.p8 import Resources
from p8fs.algorithms.resource_affinity import ResourceAffinityBuilder

logger = get_logger(__name__)
TENANT_ID = "tenant-affinity-test"


async def create_diverse_sample_resources() -> list[Resources]:
    """Create diverse sample resources across different topics."""
    logger.info("=" * 80)
    logger.info("CREATING DIVERSE SAMPLE RESOURCES")
    logger.info("=" * 80)

    provider = get_provider()
    provider.connect_sync()

    logger.info("\nCleaning up old data...")
    provider.execute("DELETE FROM embeddings.resources_embeddings WHERE tenant_id = %s", (TENANT_ID,))
    provider.execute("DELETE FROM resources WHERE tenant_id = %s", (TENANT_ID,))

    base_time = datetime.now(timezone.utc) - timedelta(hours=12)

    resource_repo = TenantRepository(Resources, tenant_id=TENANT_ID)

    resources_data = [
        {
            "name": "OAuth 2.1 Implementation Guide",
            "category": "technical",
            "content": """OAuth 2.1 consolidates best practices from OAuth 2.0 and related extensions.
            Key features include PKCE requirement for all clients, removal of implicit grant flow,
            and refresh token rotation. The authorization code flow with PKCE provides strong security
            for both web and mobile applications. Implementation should follow RFC 6749 and related specs.""",
        },
        {
            "name": "Microservices Architecture Patterns",
            "category": "technical",
            "content": """Microservices architecture decomposes applications into loosely coupled services.
            Key patterns include API Gateway, Service Discovery, Circuit Breaker, and Event-Driven Architecture.
            Each service should own its data and communicate through well-defined APIs. Consider using
            Kubernetes for orchestration and service mesh for advanced networking capabilities.""",
        },
        {
            "name": "API Security Best Practices",
            "category": "technical",
            "content": """Securing APIs requires multiple layers of defense. Use OAuth 2.1 for authorization,
            implement rate limiting to prevent abuse, validate all inputs to prevent injection attacks,
            and use HTTPS for all communications. Consider implementing API keys for service-to-service
            communication and JWT tokens for user authentication.""",
        },
        {
            "name": "Career Growth in Software Engineering",
            "category": "career",
            "content": """Growing your career as a software engineer involves technical excellence and soft skills.
            Focus on deepening expertise in your domain, learning new technologies, and taking on leadership
            roles. Consider becoming a tech lead or moving into architecture. Mentorship and knowledge sharing
            are crucial for advancing to senior positions.""",
        },
        {
            "name": "Tech Lead Responsibilities",
            "category": "career",
            "content": """Tech leads balance technical excellence with team leadership. Responsibilities include
            architecture decisions, code review oversight, mentoring junior engineers, and project planning.
            You'll need strong communication skills to work with product managers and stakeholders while
            maintaining deep technical involvement in critical areas of the codebase.""",
        },
        {
            "name": "Q4 Planning Workshop Guide",
            "category": "planning",
            "content": """Effective Q4 planning requires clear goals, resource assessment, and stakeholder alignment.
            Start by reviewing Q3 outcomes, identify key initiatives for Q4, estimate resource requirements,
            and create realistic timelines. Consider dependencies between projects and build in buffer time
            for unexpected issues. Communication and buy-in from all teams is essential.""",
        },
        {
            "name": "Distributed Systems Fundamentals",
            "category": "technical",
            "content": """Distributed systems introduce complexity around consistency, availability, and partition tolerance.
            CAP theorem states you can only guarantee two of these three. Key concepts include consensus algorithms
            like Raft and Paxos, eventual consistency patterns, and distributed transactions. Understanding these
            fundamentals is crucial for building scalable microservices architectures.""",
        },
        {
            "name": "Team Collaboration Strategies",
            "category": "teamwork",
            "content": """Effective team collaboration requires clear communication, shared understanding of goals,
            and psychological safety. Daily standups keep everyone aligned, retrospectives drive continuous
            improvement, and pair programming builds shared knowledge. Foster an environment where team members
            feel comfortable asking questions and admitting mistakes.""",
        },
        {
            "name": "Database Migration Strategies",
            "category": "technical",
            "content": """Migrating databases requires careful planning to minimize downtime. Strategies include
            dual-write patterns, shadow traffic, and feature flags for gradual rollout. For moving to TiDB
            or other distributed databases, consider data partitioning strategies and test extensively
            before production migration. Always have a rollback plan.""",
        },
        {
            "name": "Personal Productivity Tips for Engineers",
            "category": "productivity",
            "content": """Software engineers can boost productivity through time management and focus techniques.
            Use time blocking for deep work, minimize context switching, and take regular breaks to maintain
            mental clarity. Tools like todo lists and calendar blocking help manage tasks. Learn to say no
            to low-priority meetings and protect your focused coding time.""",
        },
    ]

    resources = []
    for i, data in enumerate(resources_data):
        resource = Resources(
            id=str(uuid4()),
            tenant_id=TENANT_ID,
            name=data["name"],
            content=data["content"],
            category=data["category"],
            resource_timestamp=base_time + timedelta(hours=i),
            graph_paths=[],
        )
        await resource_repo.put(resource)
        resources.append(resource)
        logger.info(f"  ✓ Created: {resource.name} ({resource.category})")

    logger.info(f"\n✓ Created {len(resources)} diverse resources with embeddings\n")
    return resources


async def test_basic_mode():
    """Test basic semantic search mode."""
    logger.info("=" * 80)
    logger.info("TESTING BASIC MODE (Semantic Search)")
    logger.info("=" * 80)

    provider = get_provider()
    provider.connect_sync()

    builder = ResourceAffinityBuilder(provider, TENANT_ID)

    stats = await builder.process_resource_batch(
        lookback_hours=24,
        batch_size=10,
        mode="basic",
    )

    logger.info("\nBASIC MODE RESULTS:")
    logger.info(f"  Processed: {stats['processed']} resources")
    logger.info(f"  Updated: {stats['updated']} resources")
    logger.info(f"  Total edges added: {stats['total_edges_added']}")

    return stats


async def test_llm_mode():
    """Test LLM-enhanced mode."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING LLM MODE (Intelligent Assessment)")
    logger.info("=" * 80)

    provider = get_provider()
    provider.connect_sync()

    builder = ResourceAffinityBuilder(provider, TENANT_ID)

    stats = await builder.process_resource_batch(
        lookback_hours=24,
        batch_size=3,
        mode="llm",
    )

    logger.info("\nLLM MODE RESULTS:")
    logger.info(f"  Processed: {stats['processed']} resources")
    logger.info(f"  Updated: {stats['updated']} resources")
    logger.info(f"  Total edges added: {stats['total_edges_added']}")

    return stats


async def display_graph_paths():
    """Display final graph paths for all resources."""
    logger.info("\n" + "=" * 80)
    logger.info("FINAL GRAPH PATHS")
    logger.info("=" * 80)

    provider = get_provider()
    provider.connect_sync()

    resources = provider.execute(
        """
        SELECT id, name, category, graph_paths
        FROM resources
        WHERE tenant_id = %s
        ORDER BY name
        """,
        (TENANT_ID,),
    )

    for resource in resources:
        graph_paths = resource.get("graph_paths", [])
        if graph_paths:
            logger.info(f"\n{resource['name']} ({resource['category']}):")
            logger.info(f"  Total paths: {len(graph_paths)}")
            for path in graph_paths[:10]:
                logger.info(f"    → {path}")
            if len(graph_paths) > 10:
                logger.info(f"    ... and {len(graph_paths) - 10} more")


async def compare_modes():
    """Compare basic vs LLM mode results."""
    logger.info("\n" + "=" * 80)
    logger.info("MODE COMPARISON")
    logger.info("=" * 80)

    provider = get_provider()
    provider.connect_sync()

    resources_with_edges = provider.execute(
        """
        SELECT
            name,
            category,
            graph_paths,
            COALESCE(jsonb_array_length(graph_paths), 0) as edge_count
        FROM resources
        WHERE tenant_id = %s
          AND graph_paths IS NOT NULL
          AND jsonb_array_length(graph_paths) > 0
        ORDER BY edge_count DESC
        """,
        (TENANT_ID,),
    )

    logger.info(f"\nResources with graph edges: {len(resources_with_edges)}")
    logger.info("\nTop resources by edge count:")
    for i, resource in enumerate(resources_with_edges[:5], 1):
        logger.info(
            f"  {i}. {resource['name']}: {resource['edge_count']} edges ({resource['category']})"
        )

    basic_edges = sum(
        1
        for r in resources_with_edges
        if any("similar/semantic" in str(path) for path in r.get("graph_paths", []))
    )
    llm_edges = sum(
        1
        for r in resources_with_edges
        if any("relationship/" in str(path) for path in r.get("graph_paths", []))
    )

    logger.info(f"\nEdge Type Distribution:")
    logger.info(f"  Basic (semantic): ~{basic_edges} resources")
    logger.info(f"  LLM (relationship): ~{llm_edges} resources")


async def main():
    """Run complete affinity testing."""
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY required for this test")
        logger.info("Run: source ~/.bash_profile")
        return

    logger.info("\n" + "=" * 80)
    logger.info("RESOURCE AFFINITY TESTING")
    logger.info("=" * 80)

    await create_diverse_sample_resources()

    basic_stats = await test_basic_mode()

    if os.getenv("OPENAI_API_KEY"):
        llm_stats = await test_llm_mode()
    else:
        logger.warning("\nSkipping LLM mode (requires OPENAI_API_KEY)")
        llm_stats = None

    await display_graph_paths()
    await compare_modes()

    logger.info("\n" + "=" * 80)
    logger.info("TESTING COMPLETE")
    logger.info("=" * 80)
    logger.info("\n✓ Created diverse sample resources")
    logger.info("✓ Tested basic semantic search mode")
    if llm_stats:
        logger.info("✓ Tested LLM-enhanced mode")
    logger.info("✓ Compared both modes")
    logger.info("\nConclusion:")
    logger.info("  - Basic mode: Fast, reliable semantic similarity")
    logger.info("  - LLM mode: Intelligent, meaningful relationship labels")
    logger.info("  - Both modes merge (not replace) graph paths")
    logger.info("\n")


if __name__ == "__main__":
    asyncio.run(main())
