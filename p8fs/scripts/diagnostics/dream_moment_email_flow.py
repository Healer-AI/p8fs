#!/usr/bin/env python3
"""
End-to-end diagnostic for dream analysis and moment email flow.

Follows the complete production pipeline:
1. Generate chat sessions (using agent/MemoryProxy)
2. Process files to create resources (using StorageWorker)
3. Run first-order dreaming: resources → moments (using MomentBuilder)
4. Send moment emails
5. Run second-order dreaming: moments → insights (WIP)

Usage:
    # Local PostgreSQL
    P8FS_STORAGE_PROVIDER=postgresql uv run python scripts/diagnostics/dream_moment_email_flow.py

    # Production TiDB
    P8FS_STORAGE_PROVIDER=tidb uv run python scripts/diagnostics/dream_moment_email_flow.py

    # Send actual email
    uv run python scripts/diagnostics/dream_moment_email_flow.py --send-email

    # Skip data generation
    uv run python scripts/diagnostics/dream_moment_email_flow.py --skip-data
"""

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)
console = Console()
app = typer.Typer(help="End-to-end dream and moment email flow diagnostic")


async def generate_chat_sessions(tenant_id: str, count: int = 3):
    """Generate chat sessions using agent/MemoryProxy."""
    console.print(f"\n[cyan]Step 1: Generate {count} Chat Sessions[/cyan]")

    from p8fs.services.llm import MemoryProxy, CallingContext

    questions = [
        "I want to learn more about distributed systems and improve my technical skills this quarter.",
        "Had a great team meeting today. We discussed the new features and everyone is aligned.",
        "Thinking about work-life balance. I need to set better boundaries and take more breaks.",
    ]

    proxy = MemoryProxy()
    created = 0

    for question in questions[:count]:
        try:
            context = CallingContext(
                model="gpt-4o-mini",
                tenant_id=tenant_id,
                temperature=0.7,
                max_tokens=200
            )

            # Run agent query (creates session)
            console.print(f"  [yellow]→[/yellow] Creating session: {question[:50]}...")
            response_chunks = []
            async for chunk in proxy.stream(question, context):
                if isinstance(chunk, str):
                    response_chunks.append(chunk)

            console.print(f"  [green]✓[/green] Session created")
            created += 1

        except Exception as e:
            console.print(f"  [red]✗[/red] Failed: {e}")

    console.print(f"\n  [green]Created {created}/{count} sessions[/green]")
    return created


async def process_sample_files(tenant_id: str):
    """Process sample files to create resources."""
    console.print("\n[cyan]Step 2: Process Sample Files[/cyan]")

    from p8fs.workers.storage import StorageWorker

    # Use the sample markdown file
    sample_file = Path("tests/sample_data/content/diary_sample.md")

    if not sample_file.exists():
        console.print(f"  [yellow]⚠[/yellow] Sample file not found: {sample_file}")
        return 0

    worker = StorageWorker(tenant_id=tenant_id)

    try:
        console.print(f"  [yellow]→[/yellow] Processing {sample_file.name}...")
        await worker.process_file(str(sample_file), tenant_id)
        console.print(f"  [green]✓[/green] Processed {sample_file.name}")
        return 1

    except Exception as e:
        console.print(f"  [red]✗[/red] Failed: {e}")
        return 0


async def run_first_order_dreaming(tenant_id: str, send_email: bool = False):
    """Run first-order dreaming: resources → moments."""
    console.print("\n[cyan]Step 3: First-Order Dreaming (Resources → Moments)[/cyan]")

    from p8fs.workers.dreaming import DreamingWorker

    worker = DreamingWorker()

    # Get recipient email for this tenant
    recipient_email = await worker._get_tenant_email(tenant_id) if send_email else None

    try:
        console.print("  [yellow]→[/yellow] Collecting recent data...")

        # Collect data (last 24 hours only to keep it manageable)
        data = await worker.collect_user_data(tenant_id, time_window_hours=24)

        console.print(f"  [dim]Found {len(data.sessions)} sessions, {len(data.resources)} resources[/dim]")

        console.print("  [yellow]→[/yellow] Processing moments from resources...")

        # Run moment extraction
        job = await worker.process_moments(
            tenant_id=tenant_id,
            model="gpt-4.1-mini",  # Fast and efficient
            recipient_email=recipient_email
        )

        if job.status == "completed":
            total_moments = job.result.get("total_moments", 0)

            if total_moments == 0:
                # Debug: check what was actually returned
                console.print(f"  [yellow]⚠[/yellow] No moments created")
                console.print(f"  [dim]Job result: {job.result}[/dim]")
            else:
                console.print(f"  [green]✓[/green] Created {total_moments} moments")

            if recipient_email and total_moments > 0:
                console.print(f"  [green]✓[/green] Email sent to {recipient_email}")

            return job

        else:
            error = job.result.get("error", "Unknown error")
            console.print(f"  [red]✗[/red] Failed: {error}")
            return None

    except Exception as e:
        console.print(f"  [red]✗[/red] Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


async def preview_moment_email(tenant_id: str):
    """Generate and save moment email preview."""
    console.print("\n[cyan]Step 4: Moment Email Preview[/cyan]")

    from p8fs.workers.dreaming_repository import DreamingRepository
    from p8fs.models.engram.models import Moment
    from p8fs.services.email import MomentEmailBuilder

    repo = DreamingRepository()

    # Get recent moments
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    moments_data = await repo.get_recent_moments(tenant_id, since, limit=10)

    if not moments_data:
        console.print("  [yellow]⚠[/yellow] No moments found")
        return False

    console.print(f"  [green]✓[/green] Found {len(moments_data)} recent moments")

    # Build email preview
    moments = [Moment(**m) for m in moments_data]
    builder = MomentEmailBuilder()
    html = builder.build_moment_email_html(moments[0], "Your Recent Moments")

    # Save preview
    preview_file = f"/tmp/moment_email_preview_{tenant_id}.html"
    with open(preview_file, 'w') as f:
        f.write(html)

    console.print(f"  [green]✓[/green] Preview saved: {preview_file}")
    return True


async def run_second_order_dreaming(tenant_id: str):
    """Run second-order dreaming: moments → insights (WIP)."""
    console.print("\n[cyan]Step 5: Second-Order Dreaming (Moments → Insights) [WIP][/cyan]")

    console.print("  [dim]Second-order processing: analyze patterns across moments[/dim]")
    console.print("  [dim]Extract themes, trends, and deeper insights[/dim]")
    console.print("  [dim]Generate meta-analysis and recommendations[/dim]")
    console.print("  [yellow]⚠[/yellow] Implementation in progress")

    # Placeholder for future implementation
    # This would:
    # 1. Collect moments from a time period
    # 2. Use LLM to analyze patterns and themes
    # 3. Generate insights about behavior, habits, goals
    # 4. Create summary reports or recommendations

    return None


async def show_final_stats(tenant_id: str, initial_counts: tuple, skip_data: bool):
    """Show final statistics and changes."""
    console.print("\n" + "="*70)

    from p8fs.workers.dreaming_repository import DreamingRepository

    repo = DreamingRepository()

    # Get final counts
    sessions = await repo.get_sessions(tenant_id, limit=1000)
    resources = await repo.get_resources(tenant_id, limit=1000)
    since = datetime.now(timezone.utc) - timedelta(days=1)
    moments = await repo.get_recent_moments(tenant_id, since, limit=100)

    # Calculate changes
    init_sessions, init_resources, init_moments = initial_counts
    new_sessions = len(sessions) - init_sessions
    new_resources = len(resources) - init_resources
    new_moments = len(moments) - init_moments

    # Display results
    table = Table(title="Diagnostic Results", box=box.ROUNDED)
    table.add_column("Type", style="cyan")
    table.add_column("Initial", justify="right")
    table.add_column("Final", justify="right")
    table.add_column("Created", style="green", justify="right")

    table.add_row("Sessions", str(init_sessions), str(len(sessions)), f"+{new_sessions}" if new_sessions > 0 else "0")
    table.add_row("Resources", str(init_resources), str(len(resources)), f"+{new_resources}" if new_resources > 0 else "0")
    table.add_row("Moments (24h)", str(init_moments), str(len(moments)), f"+{new_moments}" if new_moments > 0 else "0")

    console.print(table)

    # Check if we created the expected data
    success = True
    if not skip_data:
        if new_sessions == 0:
            console.print("[yellow]⚠[/yellow] No sessions were created")
            success = False
        if new_resources == 0:
            console.print("[yellow]⚠[/yellow] No resources were created")
            success = False
        if new_moments == 0:
            console.print("[yellow]⚠[/yellow] No moments were created from resources")
            success = False

    return success


@app.command()
def main(
    tenant_id: str = typer.Option("tenant-test", help="Tenant ID to test"),
    send_email: bool = typer.Option(False, help="Actually send email"),
    skip_data: bool = typer.Option(False, help="Skip generating new data"),
):
    """
    Run end-to-end diagnostic for complete dream and moment flow.
    """

    console.print(Panel.fit(
        "[bold cyan]Dream & Moment Email Flow Diagnostic[/bold cyan]\n\n"
        f"Provider: [yellow]{config.storage_provider}[/yellow]\n"
        f"Tenant: [yellow]{tenant_id}[/yellow]\n"
        f"Send Email: [yellow]{send_email}[/yellow]\n"
        f"Skip Data Generation: [yellow]{skip_data}[/yellow]",
        border_style="cyan"
    ))

    async def run():
        from p8fs.workers.dreaming_repository import DreamingRepository

        repo = DreamingRepository()

        # Get initial counts
        sessions = await repo.get_sessions(tenant_id, limit=1000)
        resources = await repo.get_resources(tenant_id, limit=1000)
        since = datetime.now(timezone.utc) - timedelta(days=1)
        moments = await repo.get_recent_moments(tenant_id, since, limit=100)

        initial_counts = (len(sessions), len(resources), len(moments))

        console.print(f"\n[bold]Initial State:[/bold] {len(sessions)} sessions, {len(resources)} resources, {len(moments)} moments")

        if not skip_data:
            # Step 1: Generate chat sessions
            await generate_chat_sessions(tenant_id, count=3)

            # Step 2: Process sample files
            await process_sample_files(tenant_id)
        else:
            console.print("\n[yellow]Skipping data generation[/yellow]")

        # Step 3: First-order dreaming (resources → moments)
        job = await run_first_order_dreaming(tenant_id, send_email=send_email)

        # Step 4: Preview moment email
        await preview_moment_email(tenant_id)

        # Step 5: Second-order dreaming (moments → insights)
        await run_second_order_dreaming(tenant_id)

        # Final stats
        success = await show_final_stats(tenant_id, initial_counts, skip_data)

        if success or skip_data:
            console.print("\n[green]✓ Diagnostic completed successfully![/green]")
        else:
            console.print("\n[yellow]⚠ Diagnostic completed with warnings[/yellow]")

    asyncio.run(run())


if __name__ == "__main__":
    app()
