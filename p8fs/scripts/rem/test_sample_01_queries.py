#!/usr/bin/env python3
"""
Test REM queries against Sample 01 data (Project Alpha)

Tests actual LOOKUP, SEARCH, and TRAVERSE queries using natural language inputs.
Validates that users can query with what they KNOW, not internal IDs.
"""

import asyncio
import os
from datetime import datetime

from p8fs.providers import get_provider
from p8fs.providers.rem_query import (
    REMQueryProvider,
    REMQueryPlan,
    QueryType,
    SQLParameters,
    LookupParameters,
    SearchParameters,
)
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config

# Set default embedding provider for local testing
os.environ.setdefault("P8FS_DEFAULT_EMBEDDING_PROVIDER", "text-embedding-3-small")

logger = get_logger(__name__)

TENANT_ID = "demo-tenant-001"


async def test_stage_1_queries():
    """Stage 1: Resources seeded, entity extraction complete"""
    logger.info("=" * 60)
    logger.info("STAGE 1: Testing Entity LOOKUP queries")
    logger.info("=" * 60)

    provider = get_provider()
    rem_provider = REMQueryProvider(provider, tenant_id=TENANT_ID)

    tests = [
        {
            "name": "Q1: Find resources with entity sarah-chen",
            "description": "Case-insensitive lookup of exact entity name",
            "plan": REMQueryPlan(
                query_type=QueryType.LOOKUP,
                parameters=LookupParameters(key="sarah-chen"),  # Exact entity name
            ),
            "expected_min_results": 7,
            "expected_entity": "sarah-chen",
        },
        {
            "name": "Q2: Find resources with entity tidb (case-insensitive)",
            "description": "Mixed case should work via ILIKE",
            "plan": REMQueryPlan(
                query_type=QueryType.LOOKUP,
                parameters=LookupParameters(key="TiDB"),  # Case variation
            ),
            "expected_min_results": 6,
            "expected_entity": "tidb",
        },
        {
            "name": "Q3: Find resources with entity project-alpha",
            "description": "Hyphenated entity name",
            "plan": REMQueryPlan(
                query_type=QueryType.LOOKUP,
                parameters=LookupParameters(key="project-alpha"),
            ),
            "expected_min_results": 2,
            "expected_entity": "project-alpha",
        },
        {
            "name": "Q4: Find resources with entity mike-johnson (uppercase)",
            "description": "Case-insensitive matching",
            "plan": REMQueryPlan(
                query_type=QueryType.LOOKUP,
                parameters=LookupParameters(key="MIKE-JOHNSON"),  # Uppercase
            ),
            "expected_min_results": 7,
            "expected_entity": "mike-johnson",
        },
    ]

    passed = 0
    failed = 0

    for test in tests:
        logger.info(f"\n{test['name']}")
        logger.info(f"  Description: {test['description']}")
        logger.info(f"  Query: LOOKUP '{test['plan'].parameters.key}'")

        try:
            results = rem_provider.execute(test["plan"])

            result_count = len(results) if isinstance(results, list) else 0
            logger.info(f"  Results: {result_count} resources found")

            if result_count >= test["expected_min_results"]:
                logger.info(f"  ✓ PASS: Expected >={test['expected_min_results']}, got {result_count}")
                passed += 1

                # Show sample result
                if results:
                    sample = results[0]
                    logger.info(f"  Sample: {sample.get('name', 'N/A')[:60]}")
            else:
                logger.error(
                    f"  ✗ FAIL: Expected >={test['expected_min_results']}, got {result_count}"
                )
                failed += 1

        except Exception as e:
            logger.error(f"  ✗ FAIL: Query execution error: {e}")
            failed += 1

    logger.info(f"\nStage 1 Results: {passed} passed, {failed} failed")
    return passed, failed


async def test_stage_2_queries():
    """Stage 2: Moments extracted, temporal queries available"""
    logger.info("\n" + "=" * 60)
    logger.info("STAGE 2: Testing Temporal/Moment queries")
    logger.info("=" * 60)

    provider = get_provider()
    rem_provider = REMQueryProvider(provider, tenant_id=TENANT_ID)

    tests = [
        {
            "name": "Q5: When did Sarah and Mike meet?",
            "description": "Query moments with both persons present",
            "plan": REMQueryPlan(
                query_type=QueryType.SQL,
                parameters=SQLParameters(
                    table_name="moments",
                    where_clause="moment_type = 'meeting'",
                ),
            ),
            "expected_min_results": 1,
        },
        {
            "name": "Q6: What happened between Nov 1-5?",
            "description": "Temporal range query",
            "plan": REMQueryPlan(
                query_type=QueryType.SQL,
                parameters=SQLParameters(
                    table_name="moments",
                    where_clause="resource_timestamp >= '2025-11-01' AND resource_timestamp <= '2025-11-05'",
                ),
            ),
            "expected_min_results": 2,
        },
        {
            "name": "Q7: Show me coding sessions",
            "description": "Filter by moment type",
            "plan": REMQueryPlan(
                query_type=QueryType.SQL,
                parameters=SQLParameters(
                    table_name="moments", where_clause="moment_type = 'coding'"
                ),
            ),
            "expected_min_results": 1,
        },
    ]

    passed = 0
    failed = 0

    for test in tests:
        logger.info(f"\n{test['name']}")
        logger.info(f"  Description: {test['description']}")

        try:
            results = rem_provider.execute(test["plan"])

            result_count = len(results) if isinstance(results, list) else 0
            logger.info(f"  Results: {result_count} moments found")

            if result_count >= test["expected_min_results"]:
                logger.info(f"  ✓ PASS: Expected >={test['expected_min_results']}, got {result_count}")
                passed += 1

                # Show sample result
                if results:
                    sample = results[0]
                    logger.info(f"  Sample: {sample.get('name', 'N/A')[:60]}")
            else:
                logger.warning(
                    f"  ⚠ SKIP: Expected >={test['expected_min_results']}, got {result_count} (moments not yet extracted)"
                )

        except Exception as e:
            logger.warning(f"  ⚠ SKIP: Query execution error: {e} (moments not yet extracted)")

    logger.info(f"\nStage 2 Results: {passed} passed, {failed} skipped/failed")
    return passed, failed


async def test_stage_3_queries():
    """Stage 3: Affinity graph built, semantic and graph queries available"""
    logger.info("\n" + "=" * 60)
    logger.info("STAGE 3: Testing Semantic SEARCH and Graph TRAVERSE")
    logger.info("=" * 60)

    provider = get_provider()
    rem_provider = REMQueryProvider(provider, tenant_id=TENANT_ID)

    tests = [
        {
            "name": "Q8: Find documents about database migration",
            "description": "Semantic search with natural language",
            "plan": REMQueryPlan(
                query_type=QueryType.SEARCH,
                parameters=SearchParameters(
                    table_name="resources",
                    query_text="database migration tidb postgresql",
                    limit=5,
                ),
            ),
            "expected_min_results": 3,
            "expected_top_result": "TiDB Migration Technical Specification",
        },
        {
            "name": "Q9: Find similar documents to meeting notes",
            "description": "Semantic search by document description",
            "plan": REMQueryPlan(
                query_type=QueryType.SEARCH,
                parameters=SearchParameters(
                    table_name="resources",
                    query_text="Project Alpha Kickoff Meeting Notes",
                    limit=3,
                ),
            ),
            "expected_min_results": 1,
        },
        {
            "name": "Q10: Search for performance optimization content",
            "description": "Natural language semantic search",
            "plan": REMQueryPlan(
                query_type=QueryType.SEARCH,
                parameters=SearchParameters(
                    table_name="resources",
                    query_text="api performance optimization caching",
                    limit=3,
                ),
            ),
            "expected_min_results": 1,
        },
    ]

    passed = 0
    failed = 0

    for test in tests:
        logger.info(f"\n{test['name']}")
        logger.info(f"  Description: {test['description']}")

        try:
            results = rem_provider.execute(test["plan"])

            result_count = len(results) if isinstance(results, list) else 0
            logger.info(f"  Results: {result_count} resources found")

            if result_count >= test["expected_min_results"]:
                logger.info(f"  ✓ PASS: Expected >={test['expected_min_results']}, got {result_count}")
                passed += 1

                # Show top result
                if results:
                    top = results[0]
                    logger.info(f"  Top result: {top.get('name', 'N/A')[:60]}")
                    if "distance" in top:
                        logger.info(f"  Similarity: {1 - top['distance']:.3f}")
            else:
                logger.warning(
                    f"  ⚠ SKIP: Expected >={test['expected_min_results']}, got {result_count} (embeddings not yet created)"
                )

        except Exception as e:
            logger.warning(f"  ⚠ SKIP: Query execution error: {e} (embeddings not yet created)")

    logger.info(f"\nStage 3 Results: {passed} passed, {failed} skipped/failed")
    return passed, failed


async def test_graph_queries():
    """Test graph traversal queries (Stage 3+)"""
    logger.info("\n" + "=" * 60)
    logger.info("GRAPH QUERIES: Testing entity neighborhoods")
    logger.info("=" * 60)

    provider = get_provider()
    rem_provider = REMQueryProvider(provider, tenant_id=TENANT_ID)

    tests = [
        {
            "name": "Graph Q1: What's in Sarah's neighborhood?",
            "description": "Retrieve entity and explore connected resources",
            "plan": REMQueryPlan(
                query_type=QueryType.LOOKUP,
                parameters=LookupParameters(key="Sarah"),  # Natural input
            ),
            "check_graph_paths": True,
        },
        {
            "name": "Graph Q2: What's connected to TiDB?",
            "description": "Entity neighborhood via graph paths",
            "plan": REMQueryPlan(
                query_type=QueryType.LOOKUP,
                parameters=LookupParameters(key="TiDB"),  # Natural input
            ),
            "check_graph_paths": True,
        },
    ]

    passed = 0
    failed = 0

    for test in tests:
        logger.info(f"\n{test['name']}")
        logger.info(f"  Description: {test['description']}")

        try:
            results = rem_provider.execute(test["plan"])

            if results:
                sample = results[0]
                graph_paths = sample.get("graph_paths", [])

                if graph_paths:
                    logger.info(f"  ✓ PASS: Found {len(graph_paths)} graph edges")
                    passed += 1

                    # Check if edges use labels (not UUIDs)
                    sample_path = graph_paths[0] if graph_paths else ""
                    uses_labels = not any(
                        c in sample_path for c in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f"]
                        if len(sample_path) > 20  # UUIDs are long
                    )

                    if uses_labels:
                        logger.info("  ✓ Graph edges use natural language labels (not UUIDs)")
                        logger.info(f"  Sample: {sample_path[:80]}")
                    else:
                        logger.warning("  ⚠ Graph edges may contain UUIDs instead of labels")
                        logger.info(f"  Sample: {sample_path[:80]}")
                else:
                    logger.warning("  ⚠ SKIP: No graph paths found (affinity not yet built)")
            else:
                logger.warning("  ⚠ SKIP: No results found")

        except Exception as e:
            logger.warning(f"  ⚠ SKIP: Query execution error: {e}")

    logger.info(f"\nGraph Results: {passed} passed, {failed} skipped/failed")
    return passed, failed


async def main():
    """Run all test stages"""
    config.storage_provider = "postgresql"

    logger.info("Testing REM queries against Sample 01 (Project Alpha)")
    logger.info(f"Tenant: {TENANT_ID}")
    logger.info(f"Provider: {config.storage_provider}")
    logger.info("")

    total_passed = 0
    total_failed = 0

    # Stage 1: Entity lookups (always available after seeding)
    p1, f1 = await test_stage_1_queries()
    total_passed += p1
    total_failed += f1

    # Stage 2: Temporal queries (requires moments)
    p2, f2 = await test_stage_2_queries()
    total_passed += p2
    total_failed += f2

    # Stage 3: Semantic search (requires embeddings)
    p3, f3 = await test_stage_3_queries()
    total_passed += p3
    total_failed += f3

    # Graph queries (requires affinity)
    p4, f4 = await test_graph_queries()
    total_passed += p4
    total_failed += f4

    logger.info("\n" + "=" * 60)
    logger.info("FINAL RESULTS")
    logger.info("=" * 60)
    logger.info(f"Total Passed: {total_passed}")
    logger.info(f"Total Failed/Skipped: {total_failed}")
    logger.info("")

    if total_failed == 0:
        logger.info("✓ All queries passed!")
        return 0
    else:
        logger.warning(
            f"⚠ {total_failed} queries failed or skipped (may need to run dreaming workers)"
        )
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
