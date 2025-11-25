"""REM query command for executing REM query strings."""

import json
import sys
from typing import List, Dict, Any
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config

logger = get_logger(__name__)


def format_results(results: List[Dict[str, Any]], format_type: str = "table") -> str:
    """Format query results for output."""
    if not results:
        return "No results found"

    if format_type == "json":
        return json.dumps(results, indent=2, default=str)
    elif format_type == "jsonl":
        return "\n".join(json.dumps(r, default=str) for r in results)
    else:  # table format
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(show_header=True, header_style="bold magenta")

        # Add columns from first result
        if results:
            for key in results[0].keys():
                table.add_column(key, overflow="fold")

            # Add rows
            for result in results:
                table.add_row(*[str(v) if v is not None else "" for v in result.values()])

        # Capture table as string
        from io import StringIO
        string_io = StringIO()
        temp_console = Console(file=string_io, force_terminal=True, width=120)
        temp_console.print(table)
        return string_io.getvalue()


async def rem_command(args):
    """Execute REM query from query string."""
    try:
        # Get query string from args or stdin
        if args.query:
            query_string = args.query
        else:
            print("Enter REM query (Ctrl+D when done):")
            query_string = sys.stdin.read().strip()

        if not query_string:
            print("Error: No query provided", file=sys.stderr)
            return 1

        logger.info(f"Executing REM query: {query_string[:100]}...")

        # Get provider
        provider_map = {
            "postgres": "PostgreSQLProvider",
            "postgresql": "PostgreSQLProvider",
            "tidb": "TiDBProvider",
        }

        provider_name = args.provider.lower()
        provider_class_name = provider_map.get(provider_name)

        if not provider_class_name:
            print(f"Unknown provider: {args.provider}", file=sys.stderr)
            print(f"Available providers: {', '.join(provider_map.keys())}", file=sys.stderr)
            return 1

        # Import appropriate provider and REM query provider
        if provider_name in ["postgres", "postgresql"]:
            from p8fs.providers import PostgreSQLProvider
            from p8fs.providers.rem_query import REMQueryProvider
            from p8fs.query.rem_parser import REMQueryParser

            pg_provider = PostgreSQLProvider()
            connection = pg_provider.connect_sync()
            rem_provider = REMQueryProvider(pg_provider, tenant_id=args.tenant_id)

        elif provider_name == "tidb":
            from p8fs.providers import TiDBProvider
            from p8fs.providers.rem_query_tidb import TiDBREMQueryProvider
            from p8fs.query.rem_parser import REMQueryParser

            tidb_provider = TiDBProvider()
            connection = tidb_provider.connect_sync()
            rem_provider = TiDBREMQueryProvider(tidb_provider, tenant_id=args.tenant_id)

        # Parse query string into query plan
        parser = REMQueryParser(default_table=args.table, tenant_id=args.tenant_id)
        query_plan = parser.parse(query_string)

        logger.debug(f"Parsed query plan: type={query_plan.query_type}")

        # Execute query plan
        results = rem_provider.execute(query_plan)

        # Format and output results
        output = format_results(results, args.format)
        print(output)

        # Print summary
        print(f"\n{len(results)} result(s) found", file=sys.stderr)

        return 0

    except Exception as e:
        logger.exception("REM query failed")
        print(f"Error: {e}", file=sys.stderr)
        return 1
