"""Query command for executing queries with different search strategies."""

import json
import sys
from p8fs_cluster.logging import get_logger
from p8fs.providers import PostgreSQLProvider

logger = get_logger(__name__)


async def query_command(args):
    """Execute query using specified hint (semantic, sql, graph, hybrid)."""
    try:
        # Get the query from args or stdin
        if args.query:
            query = args.query
        else:
            prompt = "Enter SQL query (Ctrl+D when done):" if args.hint == "sql" else "Enter query (Ctrl+D when done):"
            print(prompt)
            query = sys.stdin.read().strip()

        if not query:
            print("No query provided", file=sys.stderr)
            return 1

        logger.info(f"Executing {args.hint} query: {query[:50]}...")

        # For SQL hint, use the existing provider logic
        if args.hint == "sql":
            # Get the appropriate provider
            provider_map = {
                "postgres": PostgreSQLProvider,
                "postgresql": PostgreSQLProvider,
            }

            # Lazy import other providers if needed
            if args.provider.lower() == "tidb":
                from p8fs.providers import TiDBProvider
                provider_map["tidb"] = TiDBProvider
            elif args.provider.lower() == "rocksdb":
                from p8fs.providers import RocksDBProvider
                provider_map["rocksdb"] = RocksDBProvider

            provider_class = provider_map.get(args.provider.lower())
            if not provider_class:
                print(f"Unknown provider: {args.provider}", file=sys.stderr)
                print(f"Available providers: {', '.join(provider_map.keys())}", file=sys.stderr)
                return 1

            provider = provider_class()

            # Execute SQL query directly
            results = provider.execute(query, params=None)
        else:
            # For other hints, use TenantRepository with the query method
            from p8fs.repository.TenantRepository import TenantRepository
            from p8fs.models.p8 import Resources, Agent, User, Session, Job, Files

            # Map table names to model classes
            model_map = {
                "resources": Resources,
                "agent": Agent,
                "user": User,
                "session": Session,
                "job": Job,
                "files": Files
            }

            # Get the appropriate model class
            model_class = model_map.get(args.table.lower(), Resources)

            # Use selected model for queries
            repo = TenantRepository(
                model_class=model_class,
                tenant_id=args.tenant_id,
                provider_name=args.provider
            )

            # Execute query using the repository's query method
            results = await repo.query(
                query_text=query,
                hint=args.hint,
                limit=args.limit,
                threshold=args.threshold
            )

        # Output results
        if args.format == "json":
            print(json.dumps(results, indent=2, default=str))
        elif args.format == "jsonl":
            for row in results:
                print(json.dumps(row, default=str))
        else:  # table format
            if results:
                # For semantic search results, handle score field specially
                if args.hint == "semantic" and isinstance(results[0], dict) and "score" in results[0]:
                    # Format with score
                    headers = list(results[0].keys())
                    print("\t".join(headers))
                    print("-" * (len("\t".join(headers)) + 10))

                    for row in results:
                        values = []
                        for h in headers:
                            if h == "score":
                                values.append(f"{row.get(h, 0):.4f}")
                            else:
                                values.append(str(row.get(h, "")))
                        print("\t".join(values))
                else:
                    # Standard formatting
                    headers = list(results[0].keys())
                    print("\t".join(headers))
                    print("-" * (len("\t".join(headers)) + 10))

                    # Print rows
                    for row in results:
                        values = [str(row.get(h, "")) for h in headers]
                        print("\t".join(values))
            else:
                print("No results")

        return 0

    except Exception as e:
        logger.error(f"Query command failed: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        return 1
