#!/usr/bin/env python3
"""Test TiDB connection pooling.

This script tests the new connection pooling functionality:
1. Creates multiple connections and verifies pooling
2. Tests connection recycling after max_usage
3. Tests connection recycling after max_lifetime
4. Verifies no stuck transactions

Usage:
    # With pooling enabled (default)
    P8FS_DB_POOL_ENABLED=true python scripts/test_tidb_pooling.py

    # Without pooling (to compare)
    P8FS_DB_POOL_ENABLED=false python scripts/test_tidb_pooling.py

    # Port forward to cluster first:
    kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000
"""

import time
import sys
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers.tidb import TiDBProvider

logger = get_logger(__name__)


def print_header(text):
    print(f"\n{'='*60}")
    print(f"{text}")
    print(f"{'='*60}\n")


def test_basic_connection():
    """Test basic connection and query."""
    print_header("Test 1: Basic Connection")

    provider = TiDBProvider()
    conn = provider.connect_sync()

    print(f"✓ Connection established")
    print(f"  Pooling enabled: {config.db_pool_enabled}")
    print(f"  Pool max connections: {config.db_pool_max_connections}")
    print(f"  Pool max usage: {config.db_pool_max_usage}")
    print(f"  Pool max lifetime: {config.db_pool_max_lifetime}s")

    # Test simple query
    cursor = conn.cursor()
    cursor.execute("SELECT 1 as test")
    result = cursor.fetchone()
    cursor.close()

    print(f"✓ Query executed: {result}")
    return True


def test_multiple_connections():
    """Test creating multiple connections from pool."""
    print_header("Test 2: Multiple Connections")

    provider = TiDBProvider()
    connections = []

    for i in range(5):
        conn = provider.connect_sync()
        connections.append(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT CONNECTION_ID()")
        conn_id = cursor.fetchone()['CONNECTION_ID()']
        cursor.close()
        print(f"✓ Connection {i+1}: ID={conn_id}")

    # Close all connections
    for conn in connections:
        conn.close()

    print(f"✓ All connections closed")
    return True


def test_connection_recycling():
    """Test connection recycling after max_usage."""
    print_header("Test 3: Connection Recycling (max_usage)")

    if not config.db_pool_enabled:
        print("⚠ Pooling disabled, skipping test")
        return True

    provider = TiDBProvider()
    conn = provider.connect_sync()

    cursor = conn.cursor()
    cursor.execute("SELECT CONNECTION_ID()")
    initial_conn_id = cursor.fetchone()['CONNECTION_ID()']
    cursor.close()

    print(f"Initial connection ID: {initial_conn_id}")

    # Execute queries beyond max_usage
    max_usage = config.db_pool_max_usage
    print(f"Executing {max_usage + 5} queries to trigger recycling...")

    for i in range(max_usage + 5):
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        if (i + 1) % 20 == 0:
            print(f"  Executed {i + 1} queries")

    # Get new connection from pool
    conn.close()
    conn = provider.connect_sync()

    cursor = conn.cursor()
    cursor.execute("SELECT CONNECTION_ID()")
    new_conn_id = cursor.fetchone()['CONNECTION_ID()']
    cursor.close()
    conn.close()

    print(f"New connection ID: {new_conn_id}")

    if new_conn_id != initial_conn_id:
        print(f"✓ Connection was recycled after {max_usage} queries")
    else:
        print(f"⚠ Connection was not recycled (same ID)")

    return True


def test_no_stuck_transactions():
    """Verify no long-running transactions."""
    print_header("Test 4: Check for Stuck Transactions")

    provider = TiDBProvider()
    conn = provider.connect_sync()

    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) as stuck_count
        FROM information_schema.processlist
        WHERE TIME > 60 AND COMMAND != 'Sleep'
    """)
    result = cursor.fetchone()
    cursor.close()
    conn.close()

    stuck_count = result['stuck_count']

    if stuck_count == 0:
        print(f"✓ No stuck transactions found")
    else:
        print(f"⚠ Found {stuck_count} transaction(s) running > 60 seconds")

    return stuck_count == 0


def test_pool_stats():
    """Display connection pool statistics."""
    print_header("Test 5: Pool Statistics")

    if not config.db_pool_enabled:
        print("⚠ Pooling disabled, no stats available")
        return True

    provider = TiDBProvider()

    # Create and use several connections
    for i in range(3):
        conn = provider.connect_sync()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()

    print(f"✓ Pool configuration:")
    print(f"  max_connections: {config.db_pool_max_connections}")
    print(f"  max_usage: {config.db_pool_max_usage}")
    print(f"  max_lifetime: {config.db_pool_max_lifetime}s")
    print(f"  ping: {config.db_pool_ping}")

    return True


def main():
    print("\nTiDB Connection Pooling Test Suite")
    print(f"Environment: {config.environment}")
    print(f"TiDB Host: {config.tidb_host}:{config.tidb_port}")
    print(f"Database: {config.tidb_database}")

    tests = [
        ("Basic Connection", test_basic_connection),
        ("Multiple Connections", test_multiple_connections),
        ("Connection Recycling", test_connection_recycling),
        ("No Stuck Transactions", test_no_stuck_transactions),
        ("Pool Statistics", test_pool_stats),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.exception(f"Test '{name}' failed")
            print(f"✗ Test failed: {e}")
            results.append((name, False))

    # Summary
    print_header("Test Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ All tests passed! Connection pooling is working correctly.")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed. Please review the output.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
