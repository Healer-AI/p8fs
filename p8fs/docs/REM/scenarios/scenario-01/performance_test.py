#!/usr/bin/env python3
"""
Performance Test for Scenario 1 REM Queries

Tests query performance and validates functionality of the REM system
using the 15 engrams from Scenario 1 (Product Manager's Week).

Usage:
    # Process engrams and run all performance tests
    uv run python performance_test.py --process-engrams --run-tests

    # Just run performance tests (assumes engrams already processed)
    uv run python performance_test.py --run-tests

    # Just process engrams
    uv run python performance_test.py --process-engrams
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime

from p8fs.models.engram.processor import EngramProcessor
from p8fs.models.p8 import Resources
from p8fs.query.rem_parser import REMQueryParser
from p8fs.providers.rem_query import REMQueryProvider
from p8fs.providers.postgresql import PostgreSQLProvider
from p8fs.repository.TenantRepository import TenantRepository
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class PerformanceTestResults:
    """Track performance test results."""

    def __init__(self):
        self.tests: List[Dict[str, Any]] = []
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0

    def add_test(
        self,
        test_name: str,
        query: str,
        execution_time: float,
        result_count: int,
        expected_min: int = 0,
        passed: bool = True,
        error: str = None,
    ):
        """Add test result."""
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
        else:
            self.failed_tests += 1

        self.tests.append(
            {
                "test_name": test_name,
                "query": query,
                "execution_time_ms": round(execution_time * 1000, 2),
                "result_count": result_count,
                "expected_min": expected_min,
                "passed": passed,
                "error": error,
            }
        )

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 80)
        print("PERFORMANCE TEST SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {self.total_tests}")
        print(f"Passed: {self.passed_tests}")
        print(f"Failed: {self.failed_tests}")
        print(f"Success Rate: {(self.passed_tests/self.total_tests*100):.1f}%")
        print()

        # Performance statistics
        times = [t["execution_time_ms"] for t in self.tests if t["passed"]]
        if times:
            print("Performance Statistics (ms):")
            print(f"  Min: {min(times):.2f}")
            print(f"  Max: {max(times):.2f}")
            print(f"  Avg: {sum(times)/len(times):.2f}")
            print(f"  Median: {sorted(times)[len(times)//2]:.2f}")
        print()

        # Print detailed results
        print("Detailed Results:")
        print("-" * 80)
        for test in self.tests:
            status = "✓" if test["passed"] else "✗"
            print(f"{status} {test['test_name']}")
            print(f"  Query: {test['query']}")
            print(f"  Time: {test['execution_time_ms']}ms")
            print(f"  Results: {test['result_count']} (expected >= {test['expected_min']})")
            if test["error"]:
                print(f"  Error: {test['error']}")
            print()

    def save_json(self, output_path: Path):
        """Save results to JSON file."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": self.total_tests,
                "passed_tests": self.passed_tests,
                "failed_tests": self.failed_tests,
                "success_rate": round(self.passed_tests / self.total_tests * 100, 1),
            },
            "tests": self.tests,
        }

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        print(f"Results saved to: {output_path}")


class Scenario1PerformanceTest:
    """Performance test suite for Scenario 1."""

    def __init__(self):
        self.engram_dir = Path(__file__).parent / "engrams"
        self.results = PerformanceTestResults()

        # Initialize database and repository
        # TenantRepository needs the MODEL CLASS (Resources), not the provider
        self.tenant_repo = TenantRepository(Resources, tenant_id="tenant-test")

        # Initialize engram processor
        self.processor = EngramProcessor(self.tenant_repo)

        # Initialize REM query components
        self.pg_provider = PostgreSQLProvider()
        self.rem_provider = REMQueryProvider(self.pg_provider, tenant_id="tenant-test")
        self.parser = REMQueryParser(tenant_id="tenant-test")

    async def process_engrams(self):
        """Process all engrams from the scenario."""
        import yaml

        print("\n" + "=" * 80)
        print("PROCESSING ENGRAMS")
        print("=" * 80)

        engram_files = sorted(self.engram_dir.glob("*.yaml"))
        print(f"Found {len(engram_files)} engram files\n")

        for engram_file in engram_files:
            print(f"Processing: {engram_file.name}")
            start = time.time()

            try:
                # Read and process the engram file
                with open(engram_file, "r") as f:
                    content = f.read()

                result = await self.processor.process(
                    content=content,
                    content_type="application/x-yaml",
                    tenant_id="tenant-test",
                )
                elapsed = time.time() - start
                print(f"  ✓ Completed in {elapsed:.2f}s")
                print(f"    Resource ID: {result.get('resource_id')}")
                print(f"    Moments created: {result.get('moments_created', 0)}")
            except Exception as e:
                print(f"  ✗ Failed: {e}")
                logger.error(f"Failed to process {engram_file.name}", exc_info=True)

        print(f"\nAll engrams processed")

    def run_query_test(
        self, test_name: str, query: str, expected_min: int = 0, validate_fn=None
    ) -> Tuple[bool, int, float]:
        """
        Run a single query test.

        Args:
            test_name: Name of the test
            query: REM query string
            expected_min: Minimum expected result count
            validate_fn: Optional function to validate results

        Returns:
            Tuple of (passed, result_count, execution_time)
        """
        try:
            # Parse query
            plan = self.parser.parse(query)

            # Execute and time query
            start = time.time()
            results = self.rem_provider.execute(plan)
            execution_time = time.time() - start

            # Get result count
            if isinstance(results, dict):
                # TRAVERSE queries return dict with 'nodes' key
                result_count = len(results.get("nodes", []))
            else:
                result_count = len(results)

            # Validate results
            passed = result_count >= expected_min

            if validate_fn:
                validation_passed = validate_fn(results)
                passed = passed and validation_passed

            self.results.add_test(
                test_name=test_name,
                query=query,
                execution_time=execution_time,
                result_count=result_count,
                expected_min=expected_min,
                passed=passed,
            )

            return passed, result_count, execution_time

        except Exception as e:
            logger.error(f"Query test failed: {test_name}", exc_info=True)
            self.results.add_test(
                test_name=test_name,
                query=query,
                execution_time=0,
                result_count=0,
                expected_min=expected_min,
                passed=False,
                error=str(e),
            )
            return False, 0, 0

    def run_day1_tests(self):
        """Test Day 1 (Monday) - Basic Entity Lookup."""
        print("\n" + "=" * 80)
        print("DAY 1 TESTS - Basic Entity Lookup")
        print("=" * 80 + "\n")

        # Test 1: Lookup by person name
        self.run_query_test(
            test_name="Day 1: Lookup Sarah Chen",
            query='LOOKUP "Sarah Chen"',
            expected_min=1,
        )

        # Test 2: Lookup meeting
        self.run_query_test(
            test_name="Day 1: Lookup Monday Morning Standup",
            query='LOOKUP "Monday Morning Team Standup"',
            expected_min=1,
        )

        # Test 3: Search for API issues
        self.run_query_test(
            test_name="Day 1: Search for API rate limiting",
            query='SEARCH "API rate limiting" IN resources',
            expected_min=1,
        )

        # Test 4: SQL query for meetings
        self.run_query_test(
            test_name="Day 1: SQL query for meetings",
            query="SELECT * FROM resources WHERE category='meeting' LIMIT 10",
            expected_min=2,  # At least Monday standup and design review
        )

    def run_day3_tests(self):
        """Test Day 3 (Wednesday) - Temporal Relationships."""
        print("\n" + "=" * 80)
        print("DAY 3 TESTS - Temporal Relationships")
        print("=" * 80 + "\n")

        # Test 1: Traverse from CEO sync
        self.run_query_test(
            test_name="Day 3: Traverse from CEO sync (depth 2)",
            query='TRAVERSE WITH LOOKUP "Wednesday Late Afternoon CEO Sync" DEPTH 2',
            expected_min=1,
        )

        # Test 2: Find all discussions about onboarding
        self.run_query_test(
            test_name="Day 3: Search for onboarding flow discussions",
            query='SEARCH "onboarding flow" IN resources',
            expected_min=3,
        )

        # Test 3: Lookup API Rate Limiting Issue
        self.run_query_test(
            test_name="Day 3: Lookup API Rate Limiting Issue",
            query='LOOKUP "API Rate Limiting Issue"',
            expected_min=0,  # This is a concept, might not be in KV yet
        )

        # Test 4: Timeline of events
        self.run_query_test(
            test_name="Day 3: Get events chronologically",
            query="SELECT * FROM resources WHERE category='meeting' ORDER BY resource_timestamp LIMIT 10",
            expected_min=5,
        )

    def run_day5_tests(self):
        """Test Day 5 (Friday) - Complex Causal Chains."""
        print("\n" + "=" * 80)
        print("DAY 5 TESTS - Complex Causal Chains")
        print("=" * 80 + "\n")

        # Test 1: Multi-hop traversal from onboarding flow
        self.run_query_test(
            test_name="Day 5: Traverse onboarding flow (depth 3)",
            query='TRAVERSE WITH LOOKUP "Onboarding Flow Redesign" DEPTH 3',
            expected_min=1,
        )

        # Test 2: Find all Jamie's interactions
        self.run_query_test(
            test_name="Day 5: Search for Jamie Lee interactions",
            query='SEARCH "Jamie Lee" IN moments',
            expected_min=5,
        )

        # Test 3: Traverse with edge type filtering
        self.run_query_test(
            test_name="Day 5: Traverse with implements edge type",
            query='TRAVERSE implements WITH LOOKUP "Kevin Park" DEPTH 2',
            expected_min=0,  # May not have results if KV not populated
        )

        # Test 4: Complex SQL query
        self.run_query_test(
            test_name="Day 5: Complex SQL - meetings with participants",
            query="SELECT * FROM moments WHERE emotion_tags @> '[\"confident\"]'::jsonb LIMIT 10",
            expected_min=2,
        )

    def run_day7_tests(self):
        """Test Day 7 (Sunday) - Complete Narrative Queries."""
        print("\n" + "=" * 80)
        print("DAY 7 TESTS - Complete Narrative Queries")
        print("=" * 80 + "\n")

        # Test 1: Traverse from Sunday reflection
        self.run_query_test(
            test_name="Day 7: Traverse from Sunday reflection (depth 3)",
            query='TRAVERSE WITH LOOKUP "Sunday Evening Weekly Reflection" DEPTH 3',
            expected_min=1,
        )

        # Test 2: Search for entire week summary
        self.run_query_test(
            test_name="Day 7: Search for weekly summary",
            query='SEARCH "entire week summary retrospective" IN resources',
            expected_min=1,
        )

        # Test 3: Find all reflections
        self.run_query_test(
            test_name="Day 7: Find all reflection moments",
            query="SELECT * FROM moments WHERE moment_type='reflection' LIMIT 20",
            expected_min=5,
        )

        # Test 4: Complex traversal with multiple depths
        self.run_query_test(
            test_name="Day 7: Deep traversal from Sarah Chen (depth 4)",
            query='TRAVERSE WITH LOOKUP "Sarah Chen" DEPTH 4',
            expected_min=1,
        )

        # Test 5: Semantic search for crisis management
        self.run_query_test(
            test_name="Day 7: Search for crisis and resolution",
            query='SEARCH "API blocker crisis resolution" IN resources',
            expected_min=2,
        )

    def run_performance_benchmarks(self):
        """Run performance-focused benchmarks."""
        print("\n" + "=" * 80)
        print("PERFORMANCE BENCHMARKS")
        print("=" * 80 + "\n")

        # Benchmark 1: LOOKUP performance
        queries = [
            'LOOKUP "Sarah Chen"',
            'LOOKUP "Mike Johnson"',
            'LOOKUP "Jamie Lee"',
            'LOOKUP "Alex Rodriguez"',
            'LOOKUP "Kevin Park"',
        ]

        for i, query in enumerate(queries, 1):
            self.run_query_test(
                test_name=f"Benchmark: LOOKUP person {i}",
                query=query,
                expected_min=0,  # May not all be in KV
            )

        # Benchmark 2: SEARCH performance
        search_queries = [
            'SEARCH "onboarding" IN resources',
            'SEARCH "API rate limiting" IN resources',
            'SEARCH "user research" IN resources',
            'SEARCH "deployment" IN resources',
        ]

        for i, query in enumerate(search_queries, 1):
            self.run_query_test(
                test_name=f"Benchmark: SEARCH query {i}",
                query=query,
                expected_min=1,
            )

        # Benchmark 3: TRAVERSE performance at different depths
        for depth in [1, 2, 3]:
            self.run_query_test(
                test_name=f"Benchmark: TRAVERSE depth {depth}",
                query=f'TRAVERSE WITH LOOKUP "Friday Morning Sprint Completion Standup" DEPTH {depth}',
                expected_min=1,
            )

    def run_all_tests(self):
        """Run all performance tests."""
        print("\n" + "=" * 80)
        print("SCENARIO 1 PERFORMANCE TEST SUITE")
        print("=" * 80)

        self.run_day1_tests()
        self.run_day3_tests()
        self.run_day5_tests()
        self.run_day7_tests()
        self.run_performance_benchmarks()

        # Print summary
        self.results.print_summary()

        # Save results
        output_file = Path(__file__).parent / "performance_results.json"
        self.results.save_json(output_file)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Scenario 1 Performance Tests")
    parser.add_argument(
        "--process-engrams", action="store_true", help="Process all engram files"
    )
    parser.add_argument(
        "--run-tests", action="store_true", help="Run performance tests"
    )
    args = parser.parse_args()

    if not args.process_engrams and not args.run_tests:
        parser.print_help()
        return

    test_suite = Scenario1PerformanceTest()

    if args.process_engrams:
        await test_suite.process_engrams()

    if args.run_tests:
        test_suite.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
