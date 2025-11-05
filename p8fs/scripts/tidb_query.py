#!/usr/bin/env python3
"""
TiDB Query Utility - Execute queries against the cluster TiDB database.

Usage:
    # Show databases
    uv run python scripts/tidb_query.py --show-databases

    # Show tables in a database
    uv run python scripts/tidb_query.py --database public --show-tables

    # Describe a table
    uv run python scripts/tidb_query.py --database public --describe errors

    # Execute custom query
    uv run python scripts/tidb_query.py --database public --query "SELECT COUNT(*) FROM errors"

    # Apply migration file
    uv run python scripts/tidb_query.py --database public --apply-migration /tmp/migration.sql

    # Generate and apply models migration
    uv run python scripts/tidb_query.py --generate-and-apply-models

Environment:
    P8FS_TIDB_HOST: TiDB host (default: fresh-cluster-tidb.tikv-cluster.svc.cluster.local)
    P8FS_TIDB_PORT: TiDB port (default: 4000)
    P8FS_TIDB_USER: TiDB user (default: root)
    P8FS_TIDB_PASSWORD: TiDB password (default: empty)
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

try:
    import pymysql
    from p8fs_cluster.logging import get_logger
except ImportError as e:
    print(f"Error: Missing dependencies. Run: uv pip install pymysql", file=sys.stderr)
    sys.exit(1)

logger = get_logger(__name__)


class TiDBClient:
    """Simple TiDB client for executing queries."""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        user: str = None,
        password: str = None,
        database: str = None
    ):
        self.host = host or os.getenv("P8FS_TIDB_HOST", "fresh-cluster-tidb.tikv-cluster.svc.cluster.local")
        self.port = port or int(os.getenv("P8FS_TIDB_PORT", "4000"))
        self.user = user or os.getenv("P8FS_TIDB_USER", "root")
        self.password = password or os.getenv("P8FS_TIDB_PASSWORD", "")
        self.database = database

        # For local port-forward testing
        if "localhost" in self.host or "127.0.0.1" in self.host:
            self.port = 4000

        self.connection = None

    def connect(self):
        """Establish connection to TiDB."""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            logger.info(f"Connected to TiDB at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to TiDB: {e}")
            return False

    def execute(self, query: str, params=None):
        """Execute a query and return results."""
        if not self.connection:
            if not self.connect():
                return None

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params or ())

                # For SELECT queries, fetch results
                if query.strip().upper().startswith("SELECT") or query.strip().upper().startswith("SHOW") or query.strip().upper().startswith("DESCRIBE"):
                    results = cursor.fetchall()
                    return results
                else:
                    # For INSERT/UPDATE/DELETE, commit
                    self.connection.commit()
                    return {"affected_rows": cursor.rowcount}

        except Exception as e:
            logger.error(f"Query failed: {e}")
            logger.debug(f"Query was: {query[:200]}")
            return None

    def execute_file(self, file_path: str):
        """Execute SQL from a file."""
        if not Path(file_path).exists():
            logger.error(f"File not found: {file_path}")
            return False

        # Connect without selecting a database for migrations
        # This allows CREATE DATABASE and USE statements to work properly
        if self.connection:
            self.connection.close()
        self.database = None  # Don't select a database yet
        if not self.connect():
            logger.error("Failed to establish connection")
            return False

        sql_content = Path(file_path).read_text()

        # Split by semicolon and execute each statement
        statements = [s.strip() for s in sql_content.split(";") if s.strip()]

        success_count = 0
        error_count = 0

        for stmt in statements:
            # Skip comments and empty lines
            if stmt.startswith("--") or not stmt:
                continue

            try:
                result = self.execute(stmt)
                if result is not None:
                    success_count += 1
                    logger.debug(f"Executed: {stmt[:50]}...")
                else:
                    error_count += 1

            except Exception as e:
                error_count += 1
                logger.error(f"Failed to execute statement: {e}")
                logger.debug(f"Statement: {stmt[:100]}")

        logger.info(f"Executed {success_count} statements successfully, {error_count} failed")
        return error_count == 0

    def show_databases(self):
        """Show all databases."""
        results = self.execute("SHOW DATABASES")
        if results:
            print("\n📚 Databases:")
            for row in results:
                print(f"   - {row['Database']}")
        return results

    def show_tables(self, database: str = None):
        """Show tables in a database."""
        db = database or self.database
        if not db:
            logger.error("No database specified")
            return None

        results = self.execute(f"SHOW TABLES FROM {db}")
        if results:
            print(f"\n📋 Tables in '{db}':")
            for row in results:
                # The key name varies, could be 'Tables_in_<db>' or just table name
                table_name = list(row.values())[0]
                print(f"   - {table_name}")
        return results

    def describe_table(self, table: str, database: str = None):
        """Describe a table schema."""
        db = database or self.database
        if not db:
            logger.error("No database specified")
            return None

        results = self.execute(f"DESCRIBE {db}.{table}")
        if results:
            print(f"\n🔍 Table '{db}.{table}' schema:")
            print(f"   {'Field':<20} {'Type':<20} {'Null':<5} {'Key':<5} {'Default':<10}")
            print("   " + "-" * 70)
            for row in results:
                print(f"   {row['Field']:<20} {row['Type']:<20} {row['Null']:<5} {row.get('Key', ''):<5} {str(row.get('Default', '')):<10}")
        return results

    def close(self):
        """Close the connection."""
        if self.connection:
            self.connection.close()
            logger.info("Connection closed")


def generate_models_migration():
    """Generate TiDB migration from Python models."""
    import subprocess

    logger.info("Generating TiDB migration from Python models...")

    # Generate migration using the p8fs.models.p8 module
    result = subprocess.run(
        ["uv", "run", "python", "-m", "p8fs.models.p8", "--provider", "tidb", "--plan"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    if result.returncode != 0:
        logger.error(f"Failed to generate migration: {result.stderr}")
        return None

    # Write to temp file
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False)
    temp_file.write(result.stdout)
    temp_file.close()

    logger.info(f"Generated migration to {temp_file.name}")
    return temp_file.name


def main():
    parser = argparse.ArgumentParser(description="TiDB Query Utility")
    parser.add_argument("--host", help="TiDB host")
    parser.add_argument("--port", type=int, help="TiDB port")
    parser.add_argument("--user", help="TiDB user")
    parser.add_argument("--password", help="TiDB password")
    parser.add_argument("--database", help="Database to use")

    # Operations
    parser.add_argument("--show-databases", action="store_true", help="Show all databases")
    parser.add_argument("--show-tables", action="store_true", help="Show tables in database")
    parser.add_argument("--describe", help="Describe table schema")
    parser.add_argument("--query", help="Execute custom query")
    parser.add_argument("--apply-migration", help="Apply SQL migration file")
    parser.add_argument("--generate-and-apply-models", action="store_true",
                       help="Generate and apply p8fs models migration")

    args = parser.parse_args()

    # Create client
    client = TiDBClient(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database
    )

    # Execute operations
    if args.show_databases:
        client.show_databases()

    elif args.show_tables:
        if not args.database:
            logger.error("--database required for --show-tables")
            sys.exit(1)
        client.show_tables(args.database)

    elif args.describe:
        if not args.database:
            logger.error("--database required for --describe")
            sys.exit(1)
        client.describe_table(args.describe, args.database)

    elif args.query:
        results = client.execute(args.query)
        if results:
            print("\n📊 Query results:")
            for row in results:
                print(f"   {row}")

    elif args.apply_migration:
        logger.info(f"Applying migration from {args.apply_migration}")
        success = client.execute_file(args.apply_migration)
        if success:
            print("✅ Migration applied successfully")
        else:
            print("❌ Migration failed")
            sys.exit(1)

    elif args.generate_and_apply_models:
        # Generate migration
        migration_file = generate_models_migration()
        if not migration_file:
            sys.exit(1)

        # Apply it
        logger.info(f"Applying generated migration to database '{args.database or 'public'}'...")

        # Create database if needed
        client.execute("CREATE DATABASE IF NOT EXISTS public")
        client.database = "public"

        success = client.execute_file(migration_file)

        # Clean up temp file
        Path(migration_file).unlink()

        if success:
            print("\n✅ Models migration applied successfully!")
            print("\nVerifying tables created:")
            client.show_tables("public")
        else:
            print("\n❌ Migration failed")
            sys.exit(1)
    else:
        parser.print_help()

    client.close()


if __name__ == "__main__":
    main()
