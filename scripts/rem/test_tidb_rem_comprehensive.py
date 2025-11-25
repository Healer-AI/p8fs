#!/usr/bin/env python3
"""
Comprehensive REM testing script for TiDB provider.

This script is designed to run inside the dreaming worker pod or API pod
to test REM functionality against TiDB provider with test-tenant.

Tests include:
- KV read/write operations
- Resource and moment creation
- Entity lookups (LOOKUP queries)
- Semantic search (SEARCH queries)
- Graph traversal (TRAVERSE queries)
- Dreaming runs (moments and affinity generation)
- Quality validation

Usage:
  # Run all tests
  python scripts/rem/test_tidb_rem_comprehensive.py

  # Run specific test category
  python scripts/rem/test_tidb_rem_comprehensive.py --category kv
  python scripts/rem/test_tidb_rem_comprehensive.py --category resources
  python scripts/rem/test_tidb_rem_comprehensive.py --category dreaming
  python scripts/rem/test_tidb_rem_comprehensive.py --category queries
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

import typer
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)
app = typer.Typer(help="Comprehensive REM testing for TiDB provider")

TEST_TENANT = "test-tenant"


class TestResults:
    """Track test results and statistics."""

    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.errors = []

    def record_pass(self, test_name: str):
        self.tests_run += 1
        self.tests_passed += 1
        logger.info(f"✓ PASS: {test_name}")

    def record_fail(self, test_name: str, error: str):
        self.tests_run += 1
        self.tests_failed += 1
        self.errors.append((test_name, error))
        logger.error(f"✗ FAIL: {test_name} - {error}")

    def print_summary(self):
        logger.info("\n" + "=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total tests: {self.tests_run}")
        logger.info(f"Passed: {self.tests_passed}")
        logger.info(f"Failed: {self.tests_failed}")

        if self.errors:
            logger.info("\nFailed tests:")
            for test_name, error in self.errors:
                logger.info(f"  - {test_name}: {error}")

        logger.info("=" * 80 + "\n")

        return self.tests_failed == 0


async def test_kv_operations(results: TestResults):
    """Test KV storage read/write operations."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING KV OPERATIONS")
    logger.info("=" * 80 + "\n")

    from p8fs.providers import get_provider

    provider = get_provider()
    provider.connect_sync()
    kv = provider.kv

    # Test 1: Write and read simple value
    test_key = f"{TEST_TENANT}/test/simple-key"
    test_value = {"data": "test-value", "timestamp": datetime.now(timezone.utc).isoformat()}

    try:
        await kv.put(test_key, test_value)
        retrieved = await kv.get(test_key)

        if retrieved and retrieved.get("data") == test_value["data"]:
            results.record_pass("KV: Write and read simple value")
        else:
            results.record_fail("KV: Write and read simple value", f"Retrieved {retrieved} != {test_value}")
    except Exception as e:
        results.record_fail("KV: Write and read simple value", str(e))

    # Test 2: Array-based entity mapping (REM entity lookup pattern)
    entity_key = f"{TEST_TENANT}/sarah-chen/resource"
    entity_value = {
        "entity_ids": [str(uuid4()), str(uuid4()), str(uuid4())],
        "table_name": "resources",
        "entity_type": "person"
    }

    try:
        await kv.put(entity_key, entity_value)
        retrieved = await kv.get(entity_key)

        if retrieved and len(retrieved.get("entity_ids", [])) == 3:
            results.record_pass("KV: Array-based entity mapping")
        else:
            results.record_fail("KV: Array-based entity mapping", f"Retrieved {retrieved}")
    except Exception as e:
        results.record_fail("KV: Array-based entity mapping", str(e))

    # Test 3: Scan by prefix
    try:
        scan_results = await kv.scan(f"{TEST_TENANT}/", limit=10)

        if scan_results and len(scan_results) > 0:
            results.record_pass(f"KV: Scan by prefix (found {len(scan_results)} keys)")
        else:
            results.record_fail("KV: Scan by prefix", "No results returned")
    except Exception as e:
        results.record_fail("KV: Scan by prefix", str(e))

    # Test 4: Delete operation
    try:
        await kv.delete(test_key)
        retrieved = await kv.get(test_key)

        if retrieved is None:
            results.record_pass("KV: Delete operation")
        else:
            results.record_fail("KV: Delete operation", f"Key still exists: {retrieved}")
    except Exception as e:
        results.record_fail("KV: Delete operation", str(e))


async def test_resource_creation(results: TestResults):
    """Test creating resources with related entities."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING RESOURCE CREATION")
    logger.info("=" * 80 + "\n")

    from p8fs.models.p8 import Resources
    from p8fs.repository import TenantRepository

    repo = TenantRepository(Resources, tenant_id=TEST_TENANT)

    # Create test resources with entities (Sample 01 style)
    test_resources = [
        {
            "name": "Project Alpha Kickoff Meeting Notes",
            "content": "Sarah Chen and Mike Johnson discussed the TiDB migration project. Key goals: improve API performance by 50%, complete migration in 2 weeks.",
            "category": "meeting-notes",
            "related_entities": [
                {"entity_id": "sarah-chen", "entity_type": "person"},
                {"entity_id": "mike-johnson", "entity_type": "person"},
                {"entity_id": "project-alpha", "entity_type": "project"},
                {"entity_id": "tidb", "entity_type": "technology"},
                {"entity_id": "database-migration", "entity_type": "concept"},
            ],
            "resource_timestamp": datetime.now(timezone.utc) - timedelta(hours=2),
        },
        {
            "name": "TiDB Migration Technical Specification",
            "content": "Technical specification for migrating from PostgreSQL to TiDB. Sarah Chen authored this document covering schema changes, data migration strategy, and performance benchmarks.",
            "category": "technical-doc",
            "related_entities": [
                {"entity_id": "sarah-chen", "entity_type": "person"},
                {"entity_id": "tidb", "entity_type": "technology"},
                {"entity_id": "postgresql", "entity_type": "technology"},
                {"entity_id": "database-migration", "entity_type": "concept"},
            ],
            "resource_timestamp": datetime.now(timezone.utc) - timedelta(hours=4),
        },
        {
            "name": "Daily Standup Voice Memo",
            "content": "Sarah, Mike, and Emily discussed progress on the migration. Sarah reported API optimization is ahead of schedule. Mike mentioned Redis caching considerations.",
            "category": "meeting-notes",
            "related_entities": [
                {"entity_id": "sarah-chen", "entity_type": "person"},
                {"entity_id": "mike-johnson", "entity_type": "person"},
                {"entity_id": "emily-santos", "entity_type": "person"},
                {"entity_id": "api-performance", "entity_type": "concept"},
                {"entity_id": "redis", "entity_type": "technology"},
            ],
            "resource_timestamp": datetime.now(timezone.utc) - timedelta(hours=6),
        },
        {
            "name": "Code Review - Database Migration Module",
            "content": "Mike Johnson reviewed Sarah's database migration code. Approved with minor suggestions for error handling in the TiDB connection pool.",
            "category": "code-review",
            "related_entities": [
                {"entity_id": "sarah-chen", "entity_type": "person"},
                {"entity_id": "mike-johnson", "entity_type": "person"},
                {"entity_id": "tidb", "entity_type": "technology"},
                {"entity_id": "database-migration", "entity_type": "concept"},
            ],
            "resource_timestamp": datetime.now(timezone.utc) - timedelta(hours=8),
        },
    ]

    created_ids = []

    for resource_data in test_resources:
        try:
            resource = Resources(
                id=uuid4(),
                tenant_id=TEST_TENANT,
                **resource_data
            )

            success = await repo.put(resource)

            if success:
                created_ids.append(str(resource.id))
                results.record_pass(f"Resource creation: {resource_data['name']}")
            else:
                results.record_fail(f"Resource creation: {resource_data['name']}", "put() returned False")
        except Exception as e:
            results.record_fail(f"Resource creation: {resource_data['name']}", str(e))

    # Verify resources were created
    try:
        all_resources = await repo.select(filters={"tenant_id": TEST_TENANT}, limit=100)

        if len(all_resources) >= len(test_resources):
            results.record_pass(f"Resource verification: found {len(all_resources)} resources")
        else:
            results.record_fail("Resource verification", f"Expected {len(test_resources)}, found {len(all_resources)}")
    except Exception as e:
        results.record_fail("Resource verification", str(e))

    return created_ids


async def test_moment_creation(results: TestResults):
    """Test creating moments with temporal data."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING MOMENT CREATION")
    logger.info("=" * 80 + "\n")

    from p8fs.models.engram.models import Moment, Person
    from p8fs.repository import TenantRepository

    repo = TenantRepository(Moment, tenant_id=TEST_TENANT)

    # Create test moments
    test_moments = [
        {
            "name": "Kickoff Meeting",
            "content": "Project Alpha kickoff meeting with Sarah and Mike",
            "summary": "Discussed TiDB migration goals and timeline",
            "moment_type": "meeting",
            "present_persons": [
                Person(id="sarah-chen", name="Sarah Chen", role="Backend Lead").model_dump(),
                Person(id="mike-johnson", name="Mike Johnson", role="DevOps").model_dump(),
            ],
            "emotion_tags": ["excited", "focused"],
            "topic_tags": ["project-alpha", "tidb", "database-migration"],
            "resource_timestamp": datetime.now(timezone.utc) - timedelta(days=7),
            "resource_ends_timestamp": datetime.now(timezone.utc) - timedelta(days=7, hours=-2),
        },
        {
            "name": "Development Sprint",
            "content": "Sarah worked on database migration code",
            "summary": "Coding session for TiDB migration module",
            "moment_type": "coding",
            "present_persons": [
                Person(id="sarah-chen", name="Sarah Chen", role="Backend Lead").model_dump(),
            ],
            "emotion_tags": ["focused", "productive"],
            "topic_tags": ["tidb", "database-migration", "coding"],
            "resource_timestamp": datetime.now(timezone.utc) - timedelta(days=4),
            "resource_ends_timestamp": datetime.now(timezone.utc) - timedelta(days=4, hours=-4),
        },
    ]

    created_ids = []

    for moment_data in test_moments:
        try:
            moment = Moment(
                id=uuid4(),
                tenant_id=TEST_TENANT,
                **moment_data
            )

            success = await repo.put(moment)

            if success:
                created_ids.append(str(moment.id))
                results.record_pass(f"Moment creation: {moment_data['name']}")
            else:
                results.record_fail(f"Moment creation: {moment_data['name']}", "put() returned False")
        except Exception as e:
            results.record_fail(f"Moment creation: {moment_data['name']}", str(e))

    return created_ids


async def test_lookup_queries(results: TestResults):
    """Test entity LOOKUP queries using KV storage."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING LOOKUP QUERIES")
    logger.info("=" * 80 + "\n")

    from p8fs.providers import get_provider
    from p8fs.models.p8 import Resources
    from p8fs.repository import TenantRepository

    provider = get_provider()
    provider.connect_sync()
    kv = provider.kv

    repo = TenantRepository(Resources, tenant_id=TEST_TENANT)

    # Test 1: LOOKUP by entity name (case-insensitive)
    try:
        # Simulate LOOKUP "Sarah" query
        lookup_key = f"{TEST_TENANT}/sarah-chen/resource"
        kv_result = await kv.get(lookup_key)

        if kv_result and "entity_ids" in kv_result:
            entity_ids = kv_result["entity_ids"]

            # Fetch actual resources
            resources = await repo.select(
                filters={"tenant_id": TEST_TENANT},
                limit=100
            )

            if len(resources) > 0:
                results.record_pass(f"LOOKUP 'sarah-chen': found {len(resources)} resources")
            else:
                results.record_fail("LOOKUP 'sarah-chen'", "KV returned IDs but no resources found")
        else:
            results.record_fail("LOOKUP 'sarah-chen'", f"No KV entry found: {kv_result}")
    except Exception as e:
        results.record_fail("LOOKUP 'sarah-chen'", str(e))

    # Test 2: LOOKUP by project
    try:
        lookup_key = f"{TEST_TENANT}/project-alpha/resource"
        kv_result = await kv.get(lookup_key)

        if kv_result and "entity_ids" in kv_result:
            entity_ids = kv_result["entity_ids"]
            results.record_pass(f"LOOKUP 'project-alpha': found {len(entity_ids)} resource IDs")
        else:
            results.record_fail("LOOKUP 'project-alpha'", "No KV entry found")
    except Exception as e:
        results.record_fail("LOOKUP 'project-alpha'", str(e))

    # Test 3: LOOKUP by technology
    try:
        lookup_key = f"{TEST_TENANT}/tidb/resource"
        kv_result = await kv.get(lookup_key)

        if kv_result and "entity_ids" in kv_result:
            entity_ids = kv_result["entity_ids"]
            results.record_pass(f"LOOKUP 'tidb': found {len(entity_ids)} resource IDs")
        else:
            results.record_fail("LOOKUP 'tidb'", "No KV entry found")
    except Exception as e:
        results.record_fail("LOOKUP 'tidb'", str(e))


async def test_semantic_search(results: TestResults):
    """Test semantic SEARCH queries using embeddings."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING SEMANTIC SEARCH")
    logger.info("=" * 80 + "\n")

    from p8fs.models.p8 import Resources
    from p8fs.repository import TenantRepository

    repo = TenantRepository(Resources, tenant_id=TEST_TENANT)

    # Test 1: Search for database migration content
    try:
        query_text = "database migration from PostgreSQL to TiDB"
        results_list = await repo.semantic_search(
            query=query_text,
            field_name="content",
            limit=3
        )

        if results_list and len(results_list) > 0:
            results.record_pass(f"SEARCH 'database migration': found {len(results_list)} results")
        else:
            results.record_fail("SEARCH 'database migration'", "No results returned")
    except Exception as e:
        results.record_fail("SEARCH 'database migration'", str(e))

    # Test 2: Search for performance optimization
    try:
        query_text = "API performance optimization"
        results_list = await repo.semantic_search(
            query=query_text,
            field_name="content",
            limit=3
        )

        if results_list and len(results_list) > 0:
            results.record_pass(f"SEARCH 'performance optimization': found {len(results_list)} results")
        else:
            # This might fail if not enough content matches - that's ok
            logger.warning("SEARCH 'performance optimization' returned no results (may be expected)")
    except Exception as e:
        results.record_fail("SEARCH 'performance optimization'", str(e))


async def test_graph_traversal(results: TestResults):
    """Test graph TRAVERSE queries using graph_paths."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING GRAPH TRAVERSAL")
    logger.info("=" * 80 + "\n")

    from p8fs.models.p8 import Resources
    from p8fs.repository import TenantRepository

    repo = TenantRepository(Resources, tenant_id=TEST_TENANT)

    # Test 1: Find resources with graph_paths populated
    try:
        # After affinity runs, resources should have graph_paths
        resources_with_edges = await repo.select(
            filters={"tenant_id": TEST_TENANT},
            limit=100
        )

        edges_found = sum(1 for r in resources_with_edges if r.graph_paths and len(r.graph_paths) > 0)

        if edges_found > 0:
            results.record_pass(f"Graph edges: {edges_found} resources have graph_paths")
        else:
            logger.warning("No graph_paths found (run affinity dreaming first)")
    except Exception as e:
        results.record_fail("Graph edges check", str(e))

    # Test 2: Inspect InlineEdge structure
    try:
        resources = await repo.select(
            filters={"tenant_id": TEST_TENANT},
            limit=100
        )

        for resource in resources:
            if resource.graph_paths and len(resource.graph_paths) > 0:
                edge = resource.graph_paths[0]

                # Validate InlineEdge structure
                has_dst = "dst" in edge
                has_rel_type = "rel_type" in edge
                has_weight = "weight" in edge

                if has_dst and has_rel_type and has_weight:
                    results.record_pass(f"InlineEdge structure valid for {resource.name}")
                    break
                else:
                    results.record_fail(f"InlineEdge structure for {resource.name}",
                                      f"Missing fields: dst={has_dst}, rel_type={has_rel_type}, weight={has_weight}")
                    break
    except Exception as e:
        results.record_fail("InlineEdge validation", str(e))


async def test_dreaming_moments(results: TestResults):
    """Test dreaming worker moment generation."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING DREAMING - MOMENTS GENERATION")
    logger.info("=" * 80 + "\n")

    from p8fs.workers.dreaming import DreamingWorker

    worker = DreamingWorker()

    try:
        # Process moments for test tenant
        logger.info(f"Running moment generation for {TEST_TENANT}...")
        job = await worker.process_moments(
            tenant_id=TEST_TENANT,
            model=config.default_model
        )

        if job.status == "completed" and job.result:
            moment_count = job.result.get("total_moments", 0)
            results.record_pass(f"Dreaming moments: generated {moment_count} moments")
        else:
            results.record_fail("Dreaming moments", f"Status: {job.status}, Result: {job.result}")
    except Exception as e:
        results.record_fail("Dreaming moments", str(e))


async def test_dreaming_affinity(results: TestResults):
    """Test dreaming worker affinity generation."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING DREAMING - AFFINITY GENERATION")
    logger.info("=" * 80 + "\n")

    from p8fs.workers.dreaming import DreamingWorker

    worker = DreamingWorker()

    try:
        # Process affinity for test tenant
        logger.info(f"Running affinity generation for {TEST_TENANT}...")
        stats = await worker.process_resource_affinity(
            tenant_id=TEST_TENANT,
            use_llm=False  # Use basic mode for faster testing
        )

        if stats.get("total_edges_added", 0) > 0:
            results.record_pass(
                f"Dreaming affinity: {stats['total_updated']} resources updated, "
                f"{stats['total_edges_added']} edges added"
            )
        else:
            logger.warning(f"Affinity stats: {stats}")
            results.record_fail("Dreaming affinity", "No edges added")
    except Exception as e:
        results.record_fail("Dreaming affinity", str(e))


async def validate_data_quality(results: TestResults):
    """Validate overall data quality metrics."""
    logger.info("\n" + "=" * 80)
    logger.info("VALIDATING DATA QUALITY")
    logger.info("=" * 80 + "\n")

    from p8fs.models.p8 import Resources
    from p8fs.models.engram.models import Moment
    from p8fs.repository import TenantRepository

    resource_repo = TenantRepository(Resources, tenant_id=TEST_TENANT)
    moment_repo = TenantRepository(Moment, tenant_id=TEST_TENANT)

    # Check resource count
    try:
        resources = await resource_repo.select(filters={"tenant_id": TEST_TENANT}, limit=1000)
        resource_count = len(resources)

        if resource_count > 0:
            results.record_pass(f"Data quality: {resource_count} resources in database")
        else:
            results.record_fail("Data quality: resources", "No resources found")
    except Exception as e:
        results.record_fail("Data quality: resources", str(e))

    # Check moment count
    try:
        moments = await moment_repo.select(filters={"tenant_id": TEST_TENANT}, limit=1000)
        moment_count = len(moments)

        if moment_count > 0:
            results.record_pass(f"Data quality: {moment_count} moments in database")
        else:
            logger.warning("No moments found (run dreaming first)")
    except Exception as e:
        results.record_fail("Data quality: moments", str(e))

    # Check entity coverage
    try:
        resources = await resource_repo.select(filters={"tenant_id": TEST_TENANT}, limit=1000)
        resources_with_entities = sum(1 for r in resources if r.related_entities and len(r.related_entities) > 0)

        coverage = (resources_with_entities / len(resources) * 100) if resources else 0

        if coverage > 50:
            results.record_pass(f"Entity coverage: {coverage:.1f}% of resources have entities")
        else:
            results.record_fail("Entity coverage", f"Only {coverage:.1f}% coverage")
    except Exception as e:
        results.record_fail("Entity coverage", str(e))


@app.command()
def run(
    category: str = typer.Option(None, help="Test category: kv, resources, moments, queries, dreaming, all"),
):
    """Run comprehensive REM tests for TiDB provider."""

    async def run_tests():
        results = TestResults()

        logger.info("\n" + "=" * 80)
        logger.info("P8FS REM COMPREHENSIVE TEST SUITE")
        logger.info(f"Tenant: {TEST_TENANT}")
        logger.info(f"Provider: {config.storage_provider}")
        logger.info(f"Environment: {config.environment}")
        logger.info("=" * 80)

        # Run test categories
        if not category or category == "all" or category == "kv":
            await test_kv_operations(results)

        if not category or category == "all" or category == "resources":
            await test_resource_creation(results)

        if not category or category == "all" or category == "moments":
            await test_moment_creation(results)

        if not category or category == "all" or category == "queries":
            await test_lookup_queries(results)
            await test_semantic_search(results)
            await test_graph_traversal(results)

        if not category or category == "all" or category == "dreaming":
            await test_dreaming_moments(results)
            await test_dreaming_affinity(results)

        if not category or category == "all":
            await validate_data_quality(results)

        # Print summary
        success = results.print_summary()

        return 0 if success else 1

    exit_code = asyncio.run(run_tests())
    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
