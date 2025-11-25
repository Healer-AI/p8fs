#!/usr/bin/env python3
"""
Test script for 10 natural language REM queries.
Tests the /api/v1/rem/query endpoint with ask_ai=true using real Cerebras Qwen model.
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any

import httpx

from p8fs_auth.services.jwt_key_manager import JWTKeyManager

API_BASE_URL = "http://localhost:8000"

# Test queries from REMQueryService docstring
TEST_QUERIES = [
    {
        "name": "1. SEARCH - Semantic query",
        "query": "find documentation about databases",
        "table": "resources",
    },
    {
        "name": "2. SEARCH - Content discovery",
        "query": "show me diary entries",
        "table": "resources",
    },
    {
        "name": "3. SELECT - Recent files",
        "query": "get files from the last 3 days",
        "table": "resources",
    },
    {
        "name": "4. SELECT - Filter by category",
        "query": "list all documentation files",
        "table": "resources",
    },
    {
        "name": "5. SELECT - Sorted by update time",
        "query": "show files sorted by last update",
        "table": "resources",
    },
    {
        "name": "6. SELECT - With graph edges",
        "query": "get all resources with their relationships",
        "table": "resources",
    },
    {
        "name": "7. SELECT - Tag-based query",
        "query": "find files tagged with database",
        "table": "resources",
    },
    {
        "name": "8. SELECT - Temporal + category",
        "query": "recent documentation from this week",
        "table": "resources",
    },
    {
        "name": "9. LOOKUP - Direct key access",
        "query": "get resource abc-123",
        "table": "resources",
    },
    {
        "name": "10. TRAVERSE - Graph relationships",
        "query": "find all resources connected to project X",
        "table": "resources",
    },
]


async def get_test_token() -> str:
    """Generate a test JWT token for tenant-test."""
    jwt_manager = JWTKeyManager()
    access_token = await jwt_manager.create_access_token(
        user_id="test-user-123",
        client_id="test_client",
        scope=["read", "write"],
        additional_claims={
            "email": "test@example.com",
            "tenant": "tenant-test",
            "tenant_id": "tenant-test"
        }
    )
    return access_token


async def test_query(
    client: httpx.AsyncClient, token: str, query_data: Dict[str, str]
) -> Dict[str, Any]:
    """Test a single natural language query."""
    print(f"\n{'='*80}")
    print(f"Testing: {query_data['name']}")
    print(f"Natural Language: {query_data['query']}")

    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "query": query_data["query"],
        "ask_ai": True,
        "table": query_data["table"],
        "model": "openai:gpt-4o-mini",  # Fast and reliable query planning
    }

    try:
        response = await client.post(
            f"{API_BASE_URL}/api/v1/rem/query", headers=headers, json=payload, timeout=30.0
        )
        response.raise_for_status()
        result = response.json()

        print(f"Generated REM: {result.get('query', 'N/A')}")
        print(f"Success: {result.get('success', False)}")
        print(f"Result Count: {result.get('count', 0)}")

        if result.get("error"):
            print(f"Error: {result['error']}")

        return {
            "name": query_data["name"],
            "natural_query": query_data["query"],
            "generated_rem": result.get("query", ""),
            "success": result.get("success", False),
            "count": result.get("count", 0),
            "error": result.get("error"),
        }

    except Exception as e:
        print(f"Request failed: {e}")
        return {
            "name": query_data["name"],
            "natural_query": query_data["query"],
            "generated_rem": "",
            "success": False,
            "count": 0,
            "error": str(e),
        }


async def run_all_tests():
    """Run all 10 test queries."""
    print("=== REM Query Natural Language Test Suite ===")
    print(f"Testing {len(TEST_QUERIES)} queries with Cerebras Qwen 2.5 72B\n")

    # Generate test token
    token = await get_test_token()
    print(f"Generated test token for tenant-test")

    results = []
    async with httpx.AsyncClient() as client:
        for query_data in TEST_QUERIES:
            result = await test_query(client, token, query_data)
            results.append(result)
            await asyncio.sleep(0.5)  # Reduced rate limiting

    # Print summary
    print(f"\n{'='*80}")
    print("=== TEST SUMMARY ===")
    print(f"{'='*80}\n")

    successful = sum(1 for r in results if r["success"])
    print(f"Successful: {successful}/{len(results)}")
    print("")

    for i, result in enumerate(results, 1):
        status = "✅" if result["success"] else "❌"
        print(f"{i}. {status} {result['name']}")
        print(f"   Natural: {result['natural_query']}")
        print(f"   Generated: {result['generated_rem']}")
        if result.get("error"):
            print(f"   Error: {result['error']}")
        print("")

    # Save results to file
    output_file = "/tmp/rem_query_test_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to: {output_file}")

    return results


if __name__ == "__main__":
    asyncio.run(run_all_tests())
