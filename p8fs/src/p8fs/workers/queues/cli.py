"""CLI tools for P8FS queue management."""

import asyncio
import json

import typer
from p8fs_cluster.config.settings import config
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from p8fs.services.nats import ConsumerManager, NATSClient, StreamManager

from .config import QueueSize
from .storage_worker import WorkerManager
from .tiered_router import TieredStorageRouter

app = typer.Typer(name="queues", help="P8FS queue management tools")
console = Console()

# Add SeaweedFS events as a subcommand
from .seaweedfs_events.cli import app as seaweedfs_app

app.add_typer(seaweedfs_app, name="seaweedfs-events", help="SeaweedFS event processing services")


@app.command()
def setup():
    """Set up all P8FS storage streams and consumers."""
    async def run():
        async with NATSClient() as client:
            stream_manager = StreamManager(client)
            consumer_manager = ConsumerManager(client)
            
            console.print("[yellow]Setting up P8FS storage streams...[/yellow]")
            await stream_manager.setup_storage_streams()
            
            console.print("[yellow]Setting up P8FS storage consumers...[/yellow]")
            await consumer_manager.setup_storage_consumers()
            
            console.print("[green]✓ Setup complete[/green]")
    
    asyncio.run(run())


@app.command()
def cleanup():
    """Clean up all P8FS storage streams and consumers."""
    confirm = typer.confirm("This will delete all streams and consumers. Continue?")
    if not confirm:
        return
        
    async def run():
        async with NATSClient() as client:
            stream_manager = StreamManager(client)
            consumer_manager = ConsumerManager(client)
            
            console.print("[yellow]Deleting P8FS storage consumers...[/yellow]")
            await consumer_manager.delete_storage_consumers()
            
            console.print("[yellow]Deleting P8FS storage streams...[/yellow]")
            await stream_manager.delete_storage_streams()
            
            console.print("[green]✓ Cleanup complete[/green]")
    
    asyncio.run(run())


@app.command()
def status():
    """Show status of all streams and consumers."""
    async def run():
        async with NATSClient() as client:
            stream_manager = StreamManager(client)
            consumer_manager = ConsumerManager(client)
            
            # Get stream status
            console.print("[bold]Streams:[/bold]")
            stream_status = await stream_manager.get_stream_status()
            
            stream_table = Table()
            stream_table.add_column("Stream")
            stream_table.add_column("Status")
            stream_table.add_column("Messages")
            stream_table.add_column("Consumers")
            stream_table.add_column("Size (bytes)")
            
            for name, info in stream_status.items():
                if info.get("status") == "active":
                    stream_table.add_row(
                        name,
                        "[green]Active[/green]",
                        str(info["messages"]),
                        str(info["consumers"]),
                        str(info["bytes"])
                    )
                else:
                    stream_table.add_row(
                        name,
                        "[red]Error[/red]",
                        "-", "-", "-"
                    )
            
            console.print(stream_table)
            
            # Get consumer status
            console.print("\n[bold]Consumers:[/bold]")
            consumer_status = await consumer_manager.get_consumer_status()
            
            consumer_table = Table()
            consumer_table.add_column("Consumer")
            consumer_table.add_column("Status")
            consumer_table.add_column("Stream")
            consumer_table.add_column("Delivered")
            consumer_table.add_column("Pending")
            
            for name, info in consumer_status.items():
                if info.get("status") == "active":
                    consumer_table.add_row(
                        name,
                        "[green]Active[/green]",
                        info["stream"],
                        str(info["delivered"]),
                        str(info["num_pending"])
                    )
                else:
                    consumer_table.add_row(
                        name,
                        "[red]Error[/red]",
                        "-", "-", "-"
                    )
            
            console.print(consumer_table)
    
    asyncio.run(run())


@app.command()
def router(action: str = typer.Argument(..., help="Action: start, status, validate")):
    """Manage the tiered storage router."""
    async def run():
        async with NATSClient() as client:
            router = TieredStorageRouter(client)
            await router.setup()
            
            if action == "start":
                console.print("[yellow]Starting tiered storage router...[/yellow]")
                try:
                    await router.start()
                except KeyboardInterrupt:
                    console.print("\n[yellow]Stopping router...[/yellow]")
                    await router.stop()
                    
            elif action == "status":
                status = await router.get_status()
                console.print(JSON(json.dumps(status, indent=2)))
                
            elif action == "validate":
                validation = await router.validate_setup()
                if validation["all_healthy"]:
                    console.print("[green]✓ All streams and consumers are healthy[/green]")
                else:
                    console.print("[red]✗ Some components are unhealthy[/red]")
                    console.print(JSON(json.dumps(validation, indent=2)))
            else:
                console.print(f"[red]Unknown action: {action}[/red]")
    
    asyncio.run(run())


@app.command()
def worker(
    action: str = typer.Argument(..., help="Action: start, status"),
    queue_size: str | None = typer.Option(None, help="Queue size: small, medium, large"),
    tenant_id: str = typer.Option(..., help="Tenant ID")
):
    """Manage storage workers."""
    async def run():
        async with NATSClient() as client:
            manager = WorkerManager(client, tenant_id)
            
            if action == "start":
                if queue_size:
                    try:
                        size = QueueSize(queue_size)
                        console.print(f"[yellow]Starting {size.value} worker for tenant {tenant_id}...[/yellow]")
                        await manager.start_worker(size)
                    except ValueError:
                        console.print(f"[red]Invalid queue size: {queue_size}[/red]")
                        return
                    except KeyboardInterrupt:
                        console.print(f"\n[yellow]Stopping {size.value} worker...[/yellow]")
                        await manager.stop_worker(size)
                else:
                    console.print(f"[yellow]Starting all workers for tenant {tenant_id}...[/yellow]")
                    try:
                        await manager.start_all_workers()
                    except KeyboardInterrupt:
                        console.print("\n[yellow]Stopping all workers...[/yellow]")
                        await manager.stop_all_workers()
                        
            elif action == "status":
                status = await manager.get_status()
                console.print(JSON(json.dumps(status, indent=2)))
            else:
                console.print(f"[red]Unknown action: {action}[/red]")
    
    asyncio.run(run())


@app.command()
def purge(stream_name: str):
    """Purge all messages from a stream."""
    confirm = typer.confirm(f"This will delete all messages from stream '{stream_name}'. Continue?")
    if not confirm:
        return
        
    async def run():
        async with NATSClient() as client:
            stream_manager = StreamManager(client)
            
            try:
                await stream_manager.purge_stream(stream_name)
                console.print(f"[green]✓ Purged stream '{stream_name}'[/green]")
            except ValueError as e:
                console.print(f"[red]Error: {e}[/red]")
            except Exception as e:
                console.print(f"[red]Failed to purge stream: {e}[/red]")
    
    asyncio.run(run())


@app.command()
def config_info():
    """Show current configuration."""
    console.print("[bold]P8FS Queue Configuration:[/bold]")
    
    config_table = Table()
    config_table.add_column("Setting")
    config_table.add_column("Value")
    
    config_table.add_row("NATS URL", config.nats_url)
    config_table.add_row("Small File Threshold", "100 MB")
    config_table.add_row("Large File Threshold", "1 GB")
    config_table.add_row("Router Timeout", "30 seconds")
    config_table.add_row("Worker Timeouts", "Small: 5m, Medium: 10m, Large: 30m")
    
    console.print(config_table)


if __name__ == "__main__":
    app()