"""
P8FS Core CLI interface for agent and query commands.
"""

import argparse
import asyncio
import sys

from p8fs_cluster.logging import setup_logging
from p8fs_cluster.config.settings import config

# Import command handlers from modular structure
from p8fs.cli_commands import (
    agent_command,
    query_command,
    process_command,
    scheduler_command,
    sql_gen_command,
    router_command,
    dreaming_command,
    files_command,
    test_worker_command,
    eval_command,
    storage_worker_command,
    ingest_images_command,
    retry_command,
)


def main():
    """Main CLI entry point."""
    # Setup logging
    setup_logging()

    parser = argparse.ArgumentParser(
        description="P8FS Core CLI - Agent, Query, Process, Router, Scheduler, and SQL Generation commands",
        prog="p8fs"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Agent command
    agent_parser = subparsers.add_parser(
        "agent",
        help="Run an agent query using MemoryProxy"
    )
    agent_parser.add_argument(
        "--agent",
        default=config.default_tenant_id,
        help=f"Agent name/tenant ID (default: {config.default_tenant_id})"
    )
    agent_parser.add_argument(
        "--model",
        default="gpt-4",
        help="Model to use (default: gpt-4)"
    )
    agent_parser.add_argument(
        "question",
        nargs="?",
        help="Question to ask (if not provided, reads from stdin)"
    )

    # Query command
    query_parser = subparsers.add_parser(
        "query",
        help="Execute query with different search strategies (semantic, sql, graph, hybrid)"
    )
    query_parser.add_argument(
        "--hint",
        default="semantic",
        choices=["semantic", "sql", "graph", "hybrid"],
        help="Query strategy hint (default: semantic)"
    )
    query_parser.add_argument(
        "--provider",
        default="postgresql",
        choices=["postgres", "postgresql", "tidb", "rocksdb"],
        help="Database provider (default: postgresql)"
    )
    query_parser.add_argument(
        "--table",
        default="resources",
        choices=["resources", "agent", "user", "session", "job", "files"],
        help="Table/model to query (default: resources)"
    )
    query_parser.add_argument(
        "--format",
        default="table",
        choices=["table", "json", "jsonl"],
        help="Output format (default: table)"
    )
    query_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results (default: 10)"
    )
    query_parser.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        help="Minimum similarity score for semantic search (default: 0.7)"
    )
    query_parser.add_argument(
        "--tenant-id",
        default=config.default_tenant_id,
        help=f"Tenant ID for queries (default: {config.default_tenant_id})"
    )
    query_parser.add_argument(
        "query",
        nargs="?",
        help="Query text (natural language for semantic, SQL for sql hint)"
    )

    # Process command
    process_parser = subparsers.add_parser(
        "process",
        help="Process files or folders (default: only new/modified files)"
    )
    process_parser.add_argument(
        "path",
        help="Path to the file or folder to process"
    )
    process_parser.add_argument(
        "--output-format",
        default="summary",
        choices=["summary", "json"],
        help="Output format (default: summary)"
    )
    process_parser.add_argument(
        "--generate-embeddings",
        action="store_true",
        default=True,
        help="Generate embeddings (default: True)"
    )
    process_parser.add_argument(
        "--no-generate-embeddings",
        action="store_false",
        dest="generate_embeddings",
        help="Skip embedding generation"
    )
    process_parser.add_argument(
        "--extended",
        action="store_true",
        default=False,
        help="Use extended processing (default: False)"
    )
    process_parser.add_argument(
        "--save-to-storage",
        action="store_true",
        default=True,
        help="Save chunks to storage (default: True)"
    )
    process_parser.add_argument(
        "--no-save-to-storage",
        action="store_false",
        dest="save_to_storage",
        help="Skip saving to storage"
    )
    process_parser.add_argument(
        "--tenant-id",
        default=config.default_tenant_id,
        help=f"Tenant ID for storage (default: {config.default_tenant_id})"
    )
    process_parser.add_argument(
        "-o", "--output",
        help="Output chunks to file as simple text with CHUNK N markers"
    )
    process_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print chunks to stdout with CHUNK N markers"
    )
    process_parser.add_argument(
        "--force",
        action="store_true",
        help="Force reprocessing of all files (default: only process new/modified files)"
    )
    process_parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of files to process (useful for testing)"
    )

    # Scheduler command
    scheduler_parser = subparsers.add_parser(
        "scheduler",
        help="Run the task scheduler for automated job execution"
    )
    scheduler_parser.add_argument(
        "--tenant-id",
        default=config.default_tenant_id,
        help=f"Tenant ID for scheduled tasks (default: {config.default_tenant_id})"
    )
    scheduler_parser.add_argument(
        "--list-tasks",
        action="store_true",
        help="List discovered tasks and exit"
    )

    # Router command
    router_parser = subparsers.add_parser(
        "router",
        help="Run the tiered storage router (creates NATS consumers and routes messages by size)"
    )
    router_parser.add_argument(
        "--worker-id",
        help="Unique worker ID for the router (default: auto-generated)"
    )

    # SQL Generation command
    sql_gen_parser = subparsers.add_parser(
        "sql-gen",
        help="Generate SQL from natural language queries",
        epilog="""
Examples:
  # Generate SQL for finding resources
  p8fs sql-gen --model resources "Find all resources with 'API' in their content"

  # Generate MySQL query for agents
  p8fs sql-gen --model agent --dialect mysql "Show agents in research category"

  # Generate SQL with low confidence threshold
  p8fs sql-gen --model user --confidence-threshold 60 "Find active admin users"

  # Output as JSON
  p8fs sql-gen --model resources --format json "Count resources by category"
"""
    )
    sql_gen_parser.add_argument(
        "--model",
        required=True,
        choices=["resources", "agent", "user", "session", "job"],
        help="Model to generate SQL for"
    )
    sql_gen_parser.add_argument(
        "--dialect",
        default="postgresql",
        choices=["postgresql", "mysql", "sqlite"],
        help="Target SQL dialect (default: postgresql)"
    )
    sql_gen_parser.add_argument(
        "--llm-model",
        default="gpt-4o",
        help="Language model to use for generation (default: gpt-4o)"
    )
    sql_gen_parser.add_argument(
        "--confidence-threshold",
        type=int,
        default=80,
        help="Confidence threshold for explanations (0-100, default: 80)"
    )
    sql_gen_parser.add_argument(
        "--format",
        default="pretty",
        choices=["pretty", "json"],
        help="Output format (default: pretty)"
    )
    sql_gen_parser.add_argument(
        "--show-examples",
        action="store_true",
        help="Show example usage for generated SQL"
    )
    sql_gen_parser.add_argument(
        "--tenant-id",
        default=config.default_tenant_id,
        help=f"Tenant ID for context (default: {config.default_tenant_id})"
    )
    sql_gen_parser.add_argument(
        "query",
        nargs="?",
        help="Natural language query (if not provided, reads from stdin)"
    )

    # Dreaming command
    dreaming_parser = subparsers.add_parser(
        "dreaming",
        help="Run dreaming worker to analyze user content insights",
        epilog="""
Examples:
  # Process specific tenant in direct mode (default)
  p8fs dreaming --tenant-id tenant-test

  # Process all active tenants from last 24 hours
  p8fs dreaming

  # Use batch mode for async processing
  p8fs dreaming --mode batch --tenant-id tenant-test

  # Check batch job completions
  p8fs dreaming --mode completion

  # Process tenants from last 48 hours
  p8fs dreaming --lookback-hours 48
"""
    )
    dreaming_parser.add_argument(
        "--mode",
        default="direct",
        choices=["direct", "batch", "completion"],
        help="Processing mode: direct (sync), batch (async), completion (check pending)"
    )
    dreaming_parser.add_argument(
        "--tenant-id",
        help="Specific tenant ID to process (if not provided, processes all active tenants)"
    )
    dreaming_parser.add_argument(
        "--lookback-hours",
        type=int,
        default=24,
        help="Look back this many hours for tenant activity (default: 24)"
    )
    dreaming_parser.add_argument(
        "--model",
        default="gpt-4-turbo-preview",
        help="LLM model to use (default: gpt-4-turbo-preview)"
    )
    dreaming_parser.add_argument(
        "--task",
        default="dreams",
        choices=["dreams", "moments"],
        help="Task type: dreams (extract goals/fears/dreams) or moments (classify temporal activities)"
    )
    dreaming_parser.add_argument(
        "--recipient-email",
        help="Email address to send moment digest (defaults to tenant email from database)"
    )
    dreaming_parser.add_argument(
        "--polling",
        action="store_true",
        default=False,
        help="Enable polling mode (continuously check for work). Default: False for local testing"
    )
    dreaming_parser.add_argument(
        "--poll-interval",
        type=int,
        default=300,
        help="Polling interval in seconds (default: 300)"
    )

    # Files command
    files_parser = subparsers.add_parser(
        "files",
        help="File storage operations (upload, download, list, delete, info)",
        epilog="""
Examples:
  # Upload a file
  p8fs files upload document.pdf

  # Upload with custom remote path
  p8fs files upload local.txt reports/report.txt

  # List files
  p8fs files list

  # List files recursively
  p8fs files list --recursive

  # Download a file
  p8fs files download uploads/2025/10/11/document.pdf

  # Get file info
  p8fs files info uploads/2025/10/11/document.pdf

  # Delete a file
  p8fs files delete uploads/2025/10/11/document.pdf --force
"""
    )
    files_parser.add_argument(
        "files_action",
        choices=["upload", "download", "list", "delete", "info"],
        help="Action to perform"
    )
    files_parser.add_argument(
        "local_path",
        nargs="?",
        help="Local file path (for upload/download)"
    )
    files_parser.add_argument(
        "remote_path",
        nargs="?",
        help="Remote file path (for upload/download/delete/info)"
    )
    files_parser.add_argument(
        "--tenant-id",
        default=config.default_tenant_id,
        help=f"Tenant ID (default: {config.default_tenant_id})"
    )
    files_parser.add_argument(
        "--content-type",
        help="Content type for upload (auto-detected if not specified)"
    )
    files_parser.add_argument(
        "--path",
        help="Directory path for list (default: /)"
    )
    files_parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="List files recursively"
    )
    files_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum files to list (default: 100)"
    )
    files_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Skip confirmation for delete"
    )

    # Test Worker command
    test_worker_parser = subparsers.add_parser(
        "test-worker",
        help="Publish test storage event to NATS for local worker testing",
        epilog="""
Examples:
  # Test with a PDF document
  p8fs test-worker tests/sample_data/content/sample.pdf

  # Test with specific tenant
  p8fs test-worker document.pdf --tenant-id my-tenant

  # Test with large file (routes to large worker tier)
  p8fs test-worker large-video.mp4
"""
    )
    test_worker_parser.add_argument(
        "file",
        help="Path to file to simulate upload for"
    )
    test_worker_parser.add_argument(
        "--tenant-id",
        default=config.default_tenant_id,
        help=f"Tenant ID for event (default: {config.default_tenant_id})"
    )

    # Storage Worker command
    storage_worker_parser = subparsers.add_parser(
        "storage-worker",
        help="Run storage worker to process files from NATS queue",
        epilog="""
Examples:
  # Run worker with self-test (uploads file, publishes event, processes it)
  kubectl port-forward -n p8fs svc/seaweedfs-s3 8333:8333 &
  kubectl port-forward -n p8fs svc/nats 4222:4222 &
  p8fs storage-worker --tier small --send-sample p8fs/tests/sample_data/content/Sample.pdf

  # Run worker normally (processes from queue)
  p8fs storage-worker --tier small

  # Different tiers
  p8fs storage-worker --tier medium
  p8fs storage-worker --tier large
"""
    )
    storage_worker_parser.add_argument(
        "--tier",
        required=True,
        choices=["small", "medium", "large"],
        help="Worker tier (determines memory and file size handling)"
    )
    storage_worker_parser.add_argument(
        "--tenant-id",
        default=config.default_tenant_id,
        help=f"Tenant ID for worker (default: {config.default_tenant_id})"
    )
    storage_worker_parser.add_argument(
        "--send-sample",
        metavar="FILE",
        help="Self-test mode: upload file to SeaweedFS, publish event, and process it"
    )

    # Eval command
    eval_parser = subparsers.add_parser(
        "eval",
        help="Run evaluation agent with structured output",
        epilog="""
Examples:
  # Analyze diary with DreamModel, output YAML
  p8fs eval --agent-model DreamModel \\
            --file tests/sample_data/content/diary_sample.md \\
            --model claude-sonnet-4-5 \\
            --output analysis.yaml

  # Use custom model with JSON output
  p8fs eval --agent-model p8.Agent \\
            --file notes.txt \\
            --schema-format json \\
            --format json \\
            --output analysis.json

  # Print to stdout
  p8fs eval --agent-model DreamModel --file diary.md
"""
    )
    eval_parser.add_argument(
        "--agent-model",
        required=True,
        help="Agent model to use (e.g., DreamModel, p8.Agent, models.agentlets.dreaming.DreamModel)"
    )
    eval_parser.add_argument(
        "--file",
        required=True,
        help="File to analyze"
    )
    eval_parser.add_argument(
        "--model",
        default="claude-sonnet-4-5",
        help="LLM model to use (default: claude-sonnet-4-5)"
    )
    eval_parser.add_argument(
        "--schema-format",
        default="yaml",
        choices=["yaml", "json", "markdown"],
        help="Schema format in prompt (default: yaml)"
    )
    eval_parser.add_argument(
        "--format",
        default="yaml",
        choices=["yaml", "json", "raw"],
        help="Output format (default: yaml)"
    )
    eval_parser.add_argument(
        "--output",
        "-o",
        help="Output file path (if not specified, prints to stdout)"
    )
    eval_parser.add_argument(
        "--tenant-id",
        default=config.default_tenant_id,
        help=f"Tenant ID for context (default: {config.default_tenant_id})"
    )

    # Ingest Images command
    ingest_images_parser = subparsers.add_parser(
        "ingest-images",
        help="Ingest sample images from Unsplash with CLIP embeddings",
        epilog="""
Examples:
  # Ingest 100 sample images (default)
  p8fs ingest-images

  # Ingest 50 images for specific tenant
  p8fs ingest-images --tenant-id tenant-test --count 50

  # Use Unsplash API key for higher quality results
  p8fs ingest-images --count 100 --unsplash-key YOUR_API_KEY
"""
    )
    ingest_images_parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of images to fetch (default: 100)"
    )
    ingest_images_parser.add_argument(
        "--tenant-id",
        default=config.default_tenant_id,
        help=f"Tenant ID to store images for (default: {config.default_tenant_id})"
    )
    ingest_images_parser.add_argument(
        "--unsplash-key",
        help="Unsplash API access key (optional, uses demo mode if not provided)"
    )

    # Retry command
    retry_parser = subparsers.add_parser(
        "retry",
        help="Retry processing for file already in SeaweedFS",
        epilog="""
Examples:
  # Retry with full S3 path
  p8fs retry --uri /buckets/tenant-test/uploads/Sample.pdf --tenant-id tenant-test

  # Retry with partial path (auto-constructs full path)
  p8fs retry --uri Sample.pdf --tenant-id tenant-test

  # Retry with size specification (if file check unavailable)
  p8fs retry --uri large_video.mp4 --size 500000000 --tenant-id tenant-test

  # Check if file exists before retrying (requires admin credentials)
  p8fs retry --uri Sample.pdf --check-exists --tenant-id tenant-test

Prerequisites:
  # Port-forward NATS for CLI usage
  kubectl port-forward -n p8fs svc/nats 4222:4222

Architecture:
  Manual Event → NATS → Router → Size Queue → Worker → Database

Note: File must already be uploaded to SeaweedFS. Use 'p8fs files upload' first.
"""
    )
    retry_parser.add_argument(
        "--uri",
        required=True,
        help="S3 URI (full: /buckets/tenant/path or partial: filename)"
    )
    retry_parser.add_argument(
        "--tenant-id",
        default=config.default_tenant_id,
        help=f"Tenant ID (default: {config.default_tenant_id})"
    )
    retry_parser.add_argument(
        "--size",
        type=int,
        help="File size in bytes (optional, will attempt to detect if not provided)"
    )
    retry_parser.add_argument(
        "--check-exists",
        action="store_true",
        help="Check if file exists in SeaweedFS before retrying (requires admin credentials)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Execute the appropriate command
    if args.command == "agent":
        return asyncio.run(agent_command(args))
    elif args.command == "query":
        return asyncio.run(query_command(args))
    elif args.command == "process":
        return asyncio.run(process_command(args))
    elif args.command == "router":
        return asyncio.run(router_command(args))
    elif args.command == "scheduler":
        return asyncio.run(scheduler_command(args))
    elif args.command == "sql-gen":
        return asyncio.run(sql_gen_command(args))
    elif args.command == "dreaming":
        return asyncio.run(dreaming_command(args))
    elif args.command == "test-worker":
        return asyncio.run(test_worker_command(args))
    elif args.command == "storage-worker":
        return asyncio.run(storage_worker_command(args))
    elif args.command == "eval":
        return asyncio.run(eval_command(args))
    elif args.command == "files":
        return asyncio.run(files_command(args))
    elif args.command == "ingest-images":
        return ingest_images_command(args)
    elif args.command == "retry":
        return asyncio.run(retry_command(args))
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
