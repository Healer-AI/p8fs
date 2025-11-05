#!/usr/bin/env python3
"""
Apply migrations to cluster TiDB.

Prerequisites:
1. Stop local TiDB docker container: docker compose stop tidb
2. Set up port-forward: kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000

Usage:
    python scripts/apply_migrations_to_cluster.py <migration_file>
    python scripts/apply_migrations_to_cluster.py extensions/migrations/tidb/20251018_153000_add_model_pipeline_run_at.sql

This script connects to the cluster TiDB via localhost:4000 (requires active port-forward)
and applies the specified migration file.
"""

import pymysql
import sys
import os
from pathlib import Path


def run_migration(migration_file: str):
    """Connect to cluster TiDB and run the migration."""

    # Check if migration file exists
    if not os.path.exists(migration_file):
        print(f"❌ Migration file not found: {migration_file}")
        return 1

    print(f"=== Applying Migration to Cluster TiDB ===")
    print(f"Migration file: {migration_file}\n")

    try:
        # Connect to TiDB
        print("Connecting to cluster TiDB (localhost:4000 via port-forward)...")
        connection = pymysql.connect(
            host='127.0.0.1',
            port=4000,
            user='root',
            database='public',  # Use 'public' schema for TiDB cluster
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        print("✅ Connected successfully!\n")

        with connection.cursor() as cursor:
            # Check TiDB version
            cursor.execute("SELECT VERSION();")
            version = cursor.fetchone()
            print(f"TiDB Version: {version['VERSION()']}\n")

            # Read migration file
            print(f"Reading migration file...")
            with open(migration_file, 'r') as f:
                migration_sql = f.read()

            # Remove comment lines
            lines = [line for line in migration_sql.split('\n') if not line.strip().startswith('--')]
            cleaned_sql = '\n'.join(lines)

            # Split by semicolons and execute each statement
            statements = [s.strip() for s in cleaned_sql.split(';') if s.strip()]

            print(f"Found {len(statements)} SQL statement(s) to execute\n")

            for i, statement in enumerate(statements, 1):
                # Skip comments
                if statement.startswith('--'):
                    continue

                print(f"Executing statement {i}/{len(statements)}...")
                print(f"  {statement[:100]}{'...' if len(statement) > 100 else ''}")

                try:
                    cursor.execute(statement)
                    print(f"  ✅ Success\n")
                except pymysql.Error as e:
                    # Check if it's a "duplicate column" or "duplicate key" error
                    if 'Duplicate column name' in str(e) or 'Duplicate key name' in str(e):
                        print(f"  ⚠️  Already exists (skipping): {e}\n")
                    else:
                        print(f"  ❌ Error: {e}\n")
                        raise

        connection.commit()
        print("✅ Migration committed successfully\n")

        # Show files table structure
        print("Current files table structure:")
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = 'public'
                  AND TABLE_NAME = 'files'
                ORDER BY ORDINAL_POSITION;
            """)
            columns = cursor.fetchall()

            for col in columns:
                nullable = "NULL" if col['IS_NULLABLE'] == 'YES' else "NOT NULL"
                print(f"  {col['COLUMN_NAME']:<30} {col['DATA_TYPE']:<20} {nullable}")

        connection.close()

        print("\n=== Migration Complete ===")
        print("✅ Migration applied successfully to cluster TiDB")

        return 0

    except pymysql.Error as e:
        print(f"\n❌ Database error: {e}")
        print("\nTroubleshooting:")
        print("1. Ensure local TiDB is stopped: docker compose stop tidb")
        print("2. Ensure port-forward is active: kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/apply_migrations_to_cluster.py <migration_file>")
        print("\nExample:")
        print("  python scripts/apply_migrations_to_cluster.py extensions/migrations/tidb/20251018_153000_add_model_pipeline_run_at.sql")
        print("\nPrerequisites:")
        print("  1. Stop local TiDB: docker compose stop tidb")
        print("  2. Port-forward:   kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000")
        sys.exit(1)

    migration_file = sys.argv[1]
    sys.exit(run_migration(migration_file))
