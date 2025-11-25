#!/usr/bin/env python3
"""
Test REM query functionality

Runs predefined test questions against seeded data to validate REM system.

Usage:
    python scripts/rem/test_rem_queries.py --tenant dev-tenant-001
    python scripts/rem/test_rem_queries.py --tenant dev-tenant-001 --category temporal
    python scripts/rem/test_rem_queries.py --all-tenants
"""

import asyncio
import argparse
import os
from datetime import datetime
from typing import Optional

from p8fs.providers import get_provider
from p8fs.providers.rem_query import REMQueryProvider, REMQueryPlan, QueryType, SQLParameters, LookupParameters, SearchParameters
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config

# Set default embedding provider for local testing
os.environ.setdefault("P8FS_DEFAULT_EMBEDDING_PROVIDER", "text-embedding-3-small")

logger = get_logger(__name__)


# Test questions organized by category
TEST_QUESTIONS = {
    "temporal": [
        {
            "question": "What moments did I have recently?",
            "plan": REMQueryPlan(
                query_type=QueryType.SQL,
                parameters=SQLParameters(
                    table_name="moments",
                    order_by=["resource_timestamp DESC"],
                    limit=5,
                ),
            ),
            "expected_fields": ["name", "moment_type", "resource_timestamp"],
        },
        {
            "question": "What meetings happened in the last week?",
            "plan": REMQueryPlan(
                query_type=QueryType.SQL,
                parameters=SQLParameters(
                    table_name="moments",
                    where_clause="moment_type = 'meeting' AND resource_timestamp > NOW() - INTERVAL '7 days'",
                    order_by=["resource_timestamp DESC"],
                ),
            ),
            "expected_fields": ["name", "present_persons", "summary"],
        },
    ],
    "people": [
        {
            "question": "Who is Alice Chen?",
            "plan": REMQueryPlan(
                query_type=QueryType.LOOKUP,
                parameters=LookupParameters(key="alice-chen"),
            ),
            "expected_fields": ["entity_id", "entity_type"],
        },
        {
            "question": "What moments include Bob Martinez?",
            "plan": REMQueryPlan(
                query_type=QueryType.SQL,
                parameters=SQLParameters(
                    table_name="moments",
                    where_clause="present_persons::text LIKE '%Bob Martinez%'",
                ),
            ),
            "expected_fields": ["name", "present_persons"],
        },
    ],
    "content": [
        {
            "question": "What documents did I upload?",
            "plan": REMQueryPlan(
                query_type=QueryType.SQL,
                parameters=SQLParameters(
                    table_name="resources",
                    order_by=["created_at DESC"],
                    limit=10,
                ),
            ),
            "expected_fields": ["name", "category"],
        },
    ],
    "semantic": [
        {
            "question": "Find resources about database migration",
            "plan": REMQueryPlan(
                query_type=QueryType.SEARCH,
                parameters=SearchParameters(
                    table_name="resources",
                    query_text="database migration",
                    embedding_field="content",
                    limit=5,
                ),
            ),
            "expected_fields": ["name", "content", "distance"],
            "min_results": 1,
        },
        {
            "question": "Search moments about planning",
            "plan": REMQueryPlan(
                query_type=QueryType.SEARCH,
                parameters=SearchParameters(
                    table_name="moments",
                    query_text="planning and strategy",
                    embedding_field="content",
                    limit=5,
                ),
            ),
            "expected_fields": ["name", "summary"],
        },
    ],
    "entities": [
        {
            "question": "What is the API Redesign project?",
            "plan": REMQueryPlan(
                query_type=QueryType.LOOKUP,
                parameters=LookupParameters(key="api-redesign"),
            ),
            "expected_fields": ["entity_id"],
        },
        {
            "question": "Find resources mentioning auth-system",
            "plan": REMQueryPlan(
                query_type=QueryType.SQL,
                parameters=SQLParameters(
                    table_name="resources",
                    where_clause="related_entities::text LIKE '%auth-system%'",
                ),
            ),
            "expected_fields": ["name", "related_entities"],
        },
    ],
}


async def run_query_test(
    rem_provider: REMQueryProvider,
    test: dict,
    tenant_id: str,
) -> dict:
    """Run a single query test and validate results"""
    question = test["question"]
    plan = test["plan"]
    expected_fields = test.get("expected_fields", [])
    min_results = test.get("min_results", 0)

    logger.info(f"Testing: {question}")
    logger.info(f"  Query type: {plan.query_type.value}")

    start_time = datetime.utcnow()

    try:
        results = await rem_provider.execute(plan)
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000

        result_count = len(results) if isinstance(results, list) else 1

        # Validate results
        validation = {
            "question": question,
            "query_type": plan.query_type.value,
            "success": True,
            "duration_ms": duration,
            "result_count": result_count,
            "errors": [],
        }

        # Check minimum results
        if result_count < min_results:
            validation["success"] = False
            validation["errors"].append(f"Expected at least {min_results} results, got {result_count}")

        # Check expected fields
        if results and expected_fields:
            first_result = results[0] if isinstance(results, list) else results
            missing_fields = [f for f in expected_fields if f not in first_result]
            if missing_fields:
                validation["success"] = False
                validation["errors"].append(f"Missing expected fields: {missing_fields}")

        # Log results
        if validation["success"]:
            logger.info(f"  ✓ PASS - {result_count} results in {duration:.0f}ms")
        else:
            logger.error(f"  ✗ FAIL - {validation['errors']}")

        return validation

    except Exception as e:
        logger.error(f"  ✗ ERROR - {e}")
        return {
            "question": question,
            "query_type": plan.query_type.value,
            "success": False,
            "duration_ms": 0,
            "result_count": 0,
            "errors": [str(e)],
        }


async def run_category_tests(
    tenant_id: str,
    category: Optional[str] = None,
):
    """Run tests for specified category or all categories"""
    provider = get_provider()
    rem = REMQueryProvider(provider, tenant_id)

    categories = [category] if category else TEST_QUESTIONS.keys()

    all_results = []

    for cat in categories:
        tests = TEST_QUESTIONS.get(cat, [])
        logger.info(f"\n{'='*60}")
        logger.info(f"Category: {cat.upper()}")
        logger.info(f"{'='*60}")

        for test in tests:
            result = await run_query_test(rem, test, tenant_id)
            all_results.append(result)

    return all_results


def print_summary(results: list[dict]):
    """Print test summary"""
    total = len(results)
    passed = sum(1 for r in results if r["success"])
    failed = total - passed

    logger.info(f"\n{'='*60}")
    logger.info(f"TEST SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Total tests: {total}")
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Success rate: {(passed/total*100):.1f}%")

    # Performance stats
    durations = [r["duration_ms"] for r in results if r["success"]]
    if durations:
        logger.info(f"\nPerformance:")
        logger.info(f"  Avg: {sum(durations)/len(durations):.0f}ms")
        logger.info(f"  Min: {min(durations):.0f}ms")
        logger.info(f"  Max: {max(durations):.0f}ms")

    # Failed tests
    if failed > 0:
        logger.info(f"\nFailed tests:")
        for r in results:
            if not r["success"]:
                logger.info(f"  - {r['question']}")
                for error in r["errors"]:
                    logger.info(f"    {error}")


async def main():
    parser = argparse.ArgumentParser(description="Test REM queries")
    parser.add_argument(
        "--tenant",
        help="Tenant ID to test (required unless --all-tenants)",
    )
    parser.add_argument(
        "--all-tenants",
        action="store_true",
        help="Test all known tenants",
    )
    parser.add_argument(
        "--category",
        choices=list(TEST_QUESTIONS.keys()),
        help="Test category to run",
    )
    parser.add_argument(
        "--provider",
        choices=["postgresql", "tidb"],
        default="postgresql",
        help="Database provider",
    )
    args = parser.parse_args()

    if not args.tenant and not args.all_tenants:
        parser.error("Either --tenant or --all-tenants is required")

    # Override config
    config.storage_provider = args.provider

    tenants = []
    if args.all_tenants:
        tenants = ["dev-tenant-001", "pm-tenant-002", "research-tenant-003"]
    else:
        tenants = [args.tenant]

    logger.info(f"Testing REM queries")
    logger.info(f"  Provider: {args.provider}")
    logger.info(f"  Tenants: {tenants}")
    logger.info(f"  Category: {args.category or 'all'}")

    all_results = []

    for tenant in tenants:
        logger.info(f"\n{'#'*60}")
        logger.info(f"Testing tenant: {tenant}")
        logger.info(f"{'#'*60}")

        results = await run_category_tests(tenant, args.category)
        all_results.extend(results)

    print_summary(all_results)


if __name__ == "__main__":
    asyncio.run(main())
