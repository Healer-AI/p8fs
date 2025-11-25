"""SQL generation command for natural language to SQL conversion."""

import json
import sys
from p8fs_cluster.logging import get_logger
from p8fs.services.llm import CallingContext

logger = get_logger(__name__)


async def sql_gen_command(args):
    """Generate SQL from natural language queries using model schemas."""
    try:
        # Import the model dynamically
        if args.model == "resources":
            from p8fs.models.p8 import Resources as ModelClass
        elif args.model == "agent":
            from p8fs.models.p8 import Agent as ModelClass
        elif args.model == "user":
            from p8fs.models.p8 import User as ModelClass
        elif args.model == "session":
            from p8fs.models.p8 import Session as ModelClass
        elif args.model == "job":
            from p8fs.models.p8 import Job as ModelClass
        else:
            print(f"❌ Unknown model: {args.model}", file=sys.stderr)
            print("Available models: resources, agent, user, session, job")
            return 1

        # Get the query from stdin or args
        if args.query:
            query = args.query
        else:
            print("Enter your natural language query (Ctrl+D when done):")
            query = sys.stdin.read().strip()

        if not query:
            print("No query provided", file=sys.stderr)
            return 1

        # Create calling context
        context = CallingContext(
            tenant_id=args.tenant_id,
            model=args.llm_model,
            user_id="cli-user"
        )

        # Generate SQL
        logger.info(f"Generating SQL for model {args.model} with query: {query[:50]}...")

        result = await ModelClass.natural_language_to_sql(
            query=query,
            context=context,
            dialect=args.dialect,
            confidence_threshold=args.confidence_threshold
        )

        # Display results based on format
        if args.format == "json":
            print(json.dumps(result, indent=2))
        else:
            # Pretty print
            print(f"\n{'='*80}")
            print(f"Model: {ModelClass.__name__}")
            print(f"Query: {query}")
            print(f"Dialect: {args.dialect.upper()}")
            print(f"{'='*80}\n")

            print(f"Generated SQL:")
            print(f"{result['query']}\n")

            print(f"Confidence: {result['confidence']}%")

            if 'brief_explanation' in result:
                print(f"\nExplanation: {result['brief_explanation']}")

            # Show example usage if requested
            if args.show_examples and result['confidence'] >= args.confidence_threshold:
                print(f"\n{'─'*80}")
                print("Example usage:")
                print(f"```sql")
                print(f"-- Connect to your {args.dialect} database")
                print(f"-- Ensure tenant_id is set appropriately")
                print(f"{result['query']}")
                print(f"```")

        return 0

    except Exception as e:
        logger.error(f"SQL generation failed: {e}", exc_info=True)
        print(f"❌ SQL generation error: {e}", file=sys.stderr)
        return 1
