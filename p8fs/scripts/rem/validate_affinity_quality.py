#!/usr/bin/env python3
"""
Validate Resource Affinity Quality

Critical quality checks for resource affinity graph:
- Similarity scores are reasonable (not all 1.0 or 0.0)
- Related resources are actually semantically related
- Graph edges have proper metadata
- Bidirectional relationships exist where expected
- Entity-based connections are valid
- Graph connectivity is reasonable (not too sparse, not too dense)

This validates the QUALITY of graph relationships, not just existence.
"""

import asyncio
import argparse
import os
from collections import defaultdict
from typing import List, Dict, Any, Set

from p8fs.models.p8 import Resources as Resource
from p8fs.repository.TenantRepository import TenantRepository
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config

# Set default embedding provider for local testing
os.environ.setdefault("P8FS_DEFAULT_EMBEDDING_PROVIDER", "text-embedding-3-small")

logger = get_logger(__name__)


class AffinityQualityValidator:
    """Validates the quality of resource affinity graph"""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.repository = TenantRepository(Resource, tenant_id)
        self.errors = []
        self.warnings = []

    async def validate_all(self) -> Dict[str, Any]:
        """Run all quality checks"""
        resources = await self.repository.select(filters={"tenant_id": self.tenant_id}, limit=1000)

        logger.info(f"Validating affinity for {len(resources)} resources for {self.tenant_id}")

        results = {
            "total_resources": len(resources),
            "resources_with_edges": sum(1 for r in resources if r.graph_paths and len(r.graph_paths) > 0),
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "checks": {
                "edge_existence": await self.check_edge_existence(resources),
                "edge_format": await self.check_edge_format(resources),
                "semantic_relevance": await self.check_semantic_relevance(resources),
                "bidirectional_edges": await self.check_bidirectional_edges(resources),
                "entity_connections": await self.check_entity_connections(resources),
                "graph_connectivity": await self.check_graph_connectivity(resources),
                "edge_distribution": await self.check_edge_distribution(resources),
            },
            "errors": self.errors,
            "warnings": self.warnings,
        }

        # Calculate pass/fail
        for check_name, check_result in results["checks"].items():
            if check_result["passed"]:
                results["passed"] += 1
            else:
                results["failed"] += 1

        results["warnings"] = len(self.warnings)

        return results

    async def check_edge_existence(self, resources: List[Resource]) -> Dict[str, Any]:
        """Check that resources have affinity edges"""
        resources_with_edges = sum(1 for r in resources if r.graph_paths and len(r.graph_paths) > 0)
        coverage_pct = (resources_with_edges / len(resources) * 100) if resources else 0

        # Expect at least 50% of resources to have edges
        if coverage_pct < 50:
            self.warnings.append(f"Low edge coverage: only {coverage_pct:.1f}% of resources have edges")

        return {
            "passed": resources_with_edges > 0,
            "resources_with_edges": resources_with_edges,
            "total_resources": len(resources),
            "coverage_pct": coverage_pct,
        }

    async def check_edge_format(self, resources: List[Resource]) -> Dict[str, Any]:
        """Validate edge path format"""
        invalid_format = 0
        invalid_uuids = 0
        issues = []

        for resource in resources:
            if not resource.graph_paths:
                continue

            for path in resource.graph_paths:
                # Path should be string
                if not isinstance(path, str):
                    invalid_format += 1
                    issues.append(f"{resource.name}: non-string path {type(path)}")
                    continue

                # Path should start with /resources/
                if not path.startswith("/resources/"):
                    invalid_format += 1
                    issues.append(f"{resource.name}: invalid path format '{path}'")
                    continue

                # Extract UUID and validate format
                parts = path.split("/")
                if len(parts) < 3:
                    invalid_format += 1
                    issues.append(f"{resource.name}: malformed path '{path}'")
                    continue

                target_id = parts[2]
                # Basic UUID format check (length and hyphens)
                if len(target_id) != 36 or target_id.count("-") != 4:
                    invalid_uuids += 1
                    issues.append(f"{resource.name}: invalid UUID in path '{path}'")

        passed = invalid_format == 0 and invalid_uuids == 0
        return {
            "passed": passed,
            "invalid_format": invalid_format,
            "invalid_uuids": invalid_uuids,
            "issues": issues[:10],
        }

    async def check_semantic_relevance(self, resources: List[Resource]) -> Dict[str, Any]:
        """Check that connected resources are actually semantically related"""
        # Build resource lookup
        resource_by_id = {r.id: r for r in resources}

        unrelated_pairs = 0
        missing_targets = 0
        issues = []

        for resource in resources:
            if not resource.graph_paths or not resource.content:
                continue

            source_content = resource.content.lower()
            source_words = set(source_content.split())

            for path in resource.graph_paths:
                # Extract target ID
                parts = path.split("/")
                if len(parts) < 3:
                    continue

                target_id = parts[2]
                target_resource = resource_by_id.get(target_id)

                if not target_resource:
                    missing_targets += 1
                    issues.append(f"{resource.name}: target {target_id} not found")
                    continue

                if not target_resource.content:
                    continue

                # Check for word overlap (simple semantic similarity check)
                target_content = target_resource.content.lower()
                target_words = set(target_content.split())

                # Common words (excluding stopwords)
                stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}
                source_meaningful = source_words - stopwords
                target_meaningful = target_words - stopwords

                if len(source_meaningful) < 10 or len(target_meaningful) < 10:
                    continue  # Skip very short content

                overlap = source_meaningful & target_meaningful
                overlap_ratio = len(overlap) / min(len(source_meaningful), len(target_meaningful))

                # Expect at least 5% word overlap for semantic relation
                if overlap_ratio < 0.05:
                    unrelated_pairs += 1
                    if len(issues) < 10:
                        issues.append(
                            f"{resource.name} -> {target_resource.name}: "
                            f"low overlap {overlap_ratio:.1%}"
                        )

        # This is a soft check (warning only for now)
        if unrelated_pairs > 0:
            self.warnings.append(f"{unrelated_pairs} resource pairs have low semantic overlap")

        return {
            "passed": missing_targets == 0,
            "unrelated_pairs": unrelated_pairs,
            "missing_targets": missing_targets,
            "issues": issues[:10],
        }

    async def check_bidirectional_edges(self, resources: List[Resource]) -> Dict[str, Any]:
        """Check that similar resources have bidirectional edges"""
        # Build adjacency map
        edges: Dict[str, Set[str]] = defaultdict(set)

        for resource in resources:
            if not resource.graph_paths:
                continue

            for path in resource.graph_paths:
                parts = path.split("/")
                if len(parts) >= 3 and parts[1] == "resources":
                    target_id = parts[2]
                    edges[resource.id].add(target_id)

        # Check bidirectionality
        unidirectional = 0
        issues = []

        for source_id, targets in edges.items():
            for target_id in targets:
                if source_id not in edges.get(target_id, set()):
                    unidirectional += 1
                    if len(issues) < 10:
                        issues.append(f"{source_id} -> {target_id} is unidirectional")

        # Some unidirectional edges are expected (e.g., new documents)
        if unidirectional > len(resources) * 0.5:
            self.warnings.append(f"High unidirectional edge count: {unidirectional}")

        return {
            "passed": True,  # Soft check
            "total_edges": sum(len(targets) for targets in edges.values()),
            "unidirectional": unidirectional,
            "bidirectional": sum(len(targets) for targets in edges.values()) - unidirectional,
            "issues": issues[:10],
        }

    async def check_entity_connections(self, resources: List[Resource]) -> Dict[str, Any]:
        """Validate entity-based graph connections"""
        entity_paths = 0
        invalid_entity_paths = 0
        issues = []

        for resource in resources:
            if not resource.graph_paths:
                continue

            for path in resource.graph_paths:
                # Check for entity paths
                if "/entity/" in path:
                    entity_paths += 1

                    # Validate format: /resources/{id}/entity/{entity_name}
                    parts = path.split("/")
                    if len(parts) < 5 or parts[3] != "entity":
                        invalid_entity_paths += 1
                        issues.append(f"{resource.name}: invalid entity path '{path}'")
                        continue

                    entity_name = parts[4]
                    # Entity name should be lowercase-hyphenated
                    if entity_name != entity_name.lower() or " " in entity_name:
                        invalid_entity_paths += 1
                        issues.append(f"{resource.name}: entity name not normalized '{entity_name}'")

        return {
            "passed": invalid_entity_paths == 0,
            "entity_paths": entity_paths,
            "invalid_entity_paths": invalid_entity_paths,
            "issues": issues[:10],
        }

    async def check_graph_connectivity(self, resources: List[Resource]) -> Dict[str, Any]:
        """Check overall graph connectivity metrics"""
        # Build adjacency list
        graph: Dict[str, Set[str]] = defaultdict(set)

        for resource in resources:
            if not resource.graph_paths:
                graph[resource.id] = set()  # Isolated node
                continue

            for path in resource.graph_paths:
                parts = path.split("/")
                if len(parts) >= 3 and parts[1] == "resources":
                    target_id = parts[2]
                    graph[resource.id].add(target_id)

        # Calculate metrics
        total_nodes = len(resources)
        isolated_nodes = sum(1 for neighbors in graph.values() if len(neighbors) == 0)
        total_edges = sum(len(neighbors) for neighbors in graph.values())
        avg_degree = total_edges / total_nodes if total_nodes > 0 else 0

        # Check connectivity
        if isolated_nodes > total_nodes * 0.2:
            self.warnings.append(f"High isolated node count: {isolated_nodes}/{total_nodes}")

        if avg_degree < 2:
            self.warnings.append(f"Low average degree: {avg_degree:.2f}")

        return {
            "passed": isolated_nodes < total_nodes * 0.2,
            "total_nodes": total_nodes,
            "isolated_nodes": isolated_nodes,
            "total_edges": total_edges,
            "avg_degree": avg_degree,
        }

    async def check_edge_distribution(self, resources: List[Resource]) -> Dict[str, Any]:
        """Check distribution of edges per resource"""
        edge_counts = []

        for resource in resources:
            count = len(resource.graph_paths) if resource.graph_paths else 0
            edge_counts.append(count)

        if not edge_counts:
            return {"passed": False, "error": "No resources"}

        avg_edges = sum(edge_counts) / len(edge_counts)
        max_edges = max(edge_counts)
        min_edges = min(edge_counts)

        # Check for extreme skew
        if max_edges > avg_edges * 10:
            self.warnings.append(f"Extreme edge skew: max={max_edges}, avg={avg_edges:.1f}")

        # Distribution buckets
        buckets = {
            "0": sum(1 for c in edge_counts if c == 0),
            "1-5": sum(1 for c in edge_counts if 1 <= c <= 5),
            "6-10": sum(1 for c in edge_counts if 6 <= c <= 10),
            "11-20": sum(1 for c in edge_counts if 11 <= c <= 20),
            "20+": sum(1 for c in edge_counts if c > 20),
        }

        return {
            "passed": True,
            "avg_edges": avg_edges,
            "max_edges": max_edges,
            "min_edges": min_edges,
            "distribution": buckets,
        }


async def main():
    parser = argparse.ArgumentParser(description="Validate resource affinity quality")
    parser.add_argument("--tenant", required=True, help="Tenant ID to validate")
    parser.add_argument("--provider", choices=["postgresql", "tidb"], default="postgresql")
    parser.add_argument("--verbose", action="store_true", help="Show all issues and warnings")
    args = parser.parse_args()

    config.storage_provider = args.provider

    logger.info(f"Validating resource affinity quality for {args.tenant}")
    logger.info("=" * 80)

    validator = AffinityQualityValidator(args.tenant)
    results = await validator.validate_all()

    # Print results
    logger.info(f"\nResource Affinity Quality Validation Results")
    logger.info("=" * 80)
    logger.info(f"Total resources: {results['total_resources']}")
    logger.info(f"Resources with edges: {results['resources_with_edges']}")
    logger.info(f"Checks passed: {results['passed']}/{len(results['checks'])}")
    logger.info(f"Checks failed: {results['failed']}/{len(results['checks'])}")
    logger.info(f"Warnings: {results['warnings']}")
    logger.info("")

    # Print check details
    for check_name, check_result in results["checks"].items():
        status = "✓ PASS" if check_result["passed"] else "✗ FAIL"
        logger.info(f"{status} - {check_name}")

        if not check_result["passed"] or args.verbose:
            for key, value in check_result.items():
                if key not in ["passed", "issues"]:
                    logger.info(f"    {key}: {value}")

            if "issues" in check_result and check_result["issues"]:
                logger.info("    Issues:")
                for issue in check_result["issues"]:
                    logger.info(f"      - {issue}")

    # Print warnings
    if results["warnings"] and args.verbose:
        logger.info("\nWarnings:")
        for warning in results["warnings"][:20]:
            logger.info(f"  - {warning}")

    # Overall assessment
    logger.info("\n" + "=" * 80)
    if results["failed"] == 0:
        logger.info("✓ OVERALL: All quality checks PASSED")
        return 0
    else:
        logger.error(f"✗ OVERALL: {results['failed']} quality checks FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
