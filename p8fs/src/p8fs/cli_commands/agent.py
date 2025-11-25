"""Agent command for running agent queries using MemoryProxy."""

import sys
from p8fs_cluster.logging import get_logger
from p8fs.services.llm import CallingContext, MemoryProxy

logger = get_logger(__name__)


async def agent_command(args):
    """Execute agent command using MemoryProxy in streaming mode."""
    try:
        # Initialize MemoryProxy
        proxy = MemoryProxy()

        # Create calling context
        context = CallingContext(
            model=args.model,
            temperature=0.7,
            tenant_id=args.agent,
            stream=True  # Enable streaming
        )

        # Get the question from stdin or args
        if args.question:
            question = args.question
        else:
            print("Enter your question (Ctrl+D when done):")
            question = sys.stdin.read().strip()

        if not question:
            print("No question provided", file=sys.stderr)
            return 1

        logger.info(f"Agent: {args.agent}, Model: {args.model}, Question: {question[:50]}...")

        # Stream the response
        print(f"\n[{args.agent}] Thinking...\n", file=sys.stderr)

        async for chunk in proxy.stream(question, context):
            if isinstance(chunk, dict) and "choices" in chunk and chunk["choices"]:
                choice = chunk["choices"][0]
                if "delta" in choice:
                    delta = choice["delta"]
                    if "content" in delta:
                        print(delta["content"], end="", flush=True)
            elif isinstance(chunk, str):
                # Handle plain string responses
                print(chunk, end="", flush=True)

        print()  # Final newline
        return 0

    except Exception as e:
        logger.error(f"Agent command failed: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        return 1
