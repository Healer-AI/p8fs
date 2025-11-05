#!/usr/bin/env python3
"""SeaweedFS Event Processing CLI.

Command-line interface for SeaweedFS event processing services including
gRPC subscriber, HTTP poller, and event capturer.
"""

import asyncio
import logging
import os

import typer
from rich.console import Console
from rich.logging import RichHandler

from .event_capturer import SeaweedFSEventCapturer
from .grpc_subscriber import SeaweedFSgRPCSubscriber
from .http_poller import SeaweedFSHTTPPoller

app = typer.Typer(
    name="seaweedfs-events",
    help="SeaweedFS Event Processing Services",
    rich_markup_mode="rich",
    add_completion=False,
)
console = Console()


def setup_logging(debug: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)]
    )


def get_config_with_k8s_detection():
    """Get configuration with Kubernetes auto-detection."""
    # Default values
    filer_host = "localhost"
    filer_grpc_port = 18888
    filer_http_port = 8888
    nats_url = "nats://localhost:4222"
    
    # Check if running in Kubernetes
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        console.print("[yellow]Detected Kubernetes environment[/yellow]")
        filer_host = "seaweedfs-filer.p8fs.svc.cluster.local"
        nats_url = "nats://nats.p8fs.svc.cluster.local:4222"
    
    # Override with environment variables if set
    filer_host = os.getenv("SEAWEEDFS_FILER_HOST", filer_host)
    filer_grpc_port = int(os.getenv("SEAWEEDFS_FILER_GRPC_PORT", str(filer_grpc_port)))
    filer_http_port = int(os.getenv("SEAWEEDFS_FILER_HTTP_PORT", str(filer_http_port)))
    nats_url = os.getenv("NATS_URL", nats_url)
    
    return {
        "filer_host": filer_host,
        "filer_grpc_port": filer_grpc_port,
        "filer_http_port": filer_http_port,
        "nats_url": nats_url,
    }


@app.command("grpc")
def start_grpc_subscriber(
    filer_host: str | None = typer.Option(None, "--filer-host", help="SeaweedFS filer hostname"),
    filer_port: int | None = typer.Option(None, "--filer-port", help="SeaweedFS filer gRPC port"),
    path_prefix: str = typer.Option("/buckets/", "--path-prefix", help="Path prefix to monitor"),
    client_name: str | None = typer.Option(None, "--client-name", help="Unique client identifier"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
):
    """Start gRPC metadata subscriber for real-time events."""
    setup_logging(debug)
    
    # Get configuration with auto-detection
    config_values = get_config_with_k8s_detection()
    
    # Override with command line arguments if provided
    if filer_host:
        config_values["filer_host"] = filer_host
    if filer_port:
        config_values["filer_grpc_port"] = filer_port
        
    console.print("[green]Starting gRPC subscriber[/green]")
    console.print(f"Filer: [cyan]{config_values['filer_host']}:{config_values['filer_grpc_port']}[/cyan]")
    console.print(f"Path prefix: [cyan]{path_prefix}[/cyan]")
    
    async def run_grpc_service():
        subscriber = SeaweedFSgRPCSubscriber(
            filer_host=config_values["filer_host"],
            filer_grpc_port=config_values["filer_grpc_port"],
            path_prefix=path_prefix,
            client_name=client_name,
        )
        
        try:
            await subscriber.setup()
            await subscriber.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down gRPC subscriber...[/yellow]")
        except Exception as e:
            console.print(f"[red]gRPC subscriber failed: {e}[/red]")
            raise
        finally:
            await subscriber.stop()
    
    asyncio.run(run_grpc_service())


@app.command("http")
def start_http_poller(
    filer_host: str | None = typer.Option(None, "--filer-host", help="SeaweedFS filer hostname"),
    filer_port: int | None = typer.Option(None, "--filer-port", help="SeaweedFS filer HTTP port"),
    path_prefix: str = typer.Option("/buckets/", "--path-prefix", help="Path prefix to monitor"),
    poll_interval: float = typer.Option(5.0, "--poll-interval", help="Polling interval in seconds"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
):
    """Start HTTP poller for file change detection (fallback method)."""
    setup_logging(debug)
    
    # Get configuration with auto-detection
    config_values = get_config_with_k8s_detection()
    
    # Override with command line arguments if provided
    if filer_host:
        config_values["filer_host"] = filer_host
    if filer_port:
        config_values["filer_http_port"] = filer_port
        
    console.print("[green]Starting HTTP poller[/green]")
    console.print(f"Filer: [cyan]{config_values['filer_host']}:{config_values['filer_http_port']}[/cyan]")
    console.print(f"Path prefix: [cyan]{path_prefix}[/cyan]")
    console.print(f"Poll interval: [cyan]{poll_interval}s[/cyan]")
    
    async def run_http_service():
        poller = SeaweedFSHTTPPoller(
            filer_host=config_values["filer_host"],
            filer_http_port=config_values["filer_http_port"],
            path_prefix=path_prefix,
            poll_interval=poll_interval,
        )
        
        try:
            await poller.setup()
            await poller.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down HTTP poller...[/yellow]")
        except Exception as e:
            console.print(f"[red]HTTP poller failed: {e}[/red]")
            raise
        finally:
            await poller.stop()
    
    asyncio.run(run_http_service())


@app.command("capture")
def start_event_capturer(
    filer_host: str | None = typer.Option(None, "--filer-host", help="SeaweedFS filer hostname"),
    filer_port: int | None = typer.Option(None, "--filer-port", help="SeaweedFS filer gRPC port"),
    path_prefix: str = typer.Option("/buckets/", "--path-prefix", help="Path prefix to monitor"),
    output_dir: str = typer.Option("./seaweedfs_events", "--output-dir", help="Directory to save captured events"),
    client_name: str | None = typer.Option(None, "--client-name", help="Unique client identifier"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
):
    """Capture raw SeaweedFS events to disk for debugging."""
    setup_logging(debug)
    
    # Get configuration with auto-detection
    config_values = get_config_with_k8s_detection()
    
    # Override with command line arguments if provided
    if filer_host:
        config_values["filer_host"] = filer_host
    if filer_port:
        config_values["filer_grpc_port"] = filer_port
        
    console.print("[green]Starting event capturer[/green]")
    console.print(f"Filer: [cyan]{config_values['filer_host']}:{config_values['filer_grpc_port']}[/cyan]")
    console.print(f"Path prefix: [cyan]{path_prefix}[/cyan]")
    console.print(f"Output directory: [cyan]{output_dir}[/cyan]")
    
    async def run_capturer_service():
        capturer = SeaweedFSEventCapturer(
            filer_host=config_values["filer_host"],
            filer_grpc_port=config_values["filer_grpc_port"],
            path_prefix=path_prefix,
            output_dir=output_dir,
            client_name=client_name,
        )
        
        try:
            await capturer.setup()
            await capturer.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down event capturer...[/yellow]")
        except Exception as e:
            console.print(f"[red]Event capturer failed: {e}[/red]")
            raise
        finally:
            await capturer.stop()
    
    asyncio.run(run_capturer_service())


@app.command("config")
def show_config():
    """Show current configuration values."""
    config_values = get_config_with_k8s_detection()
    
    console.print("[bold]SeaweedFS Event Processing Configuration:[/bold]")
    console.print(f"Filer Host: [cyan]{config_values['filer_host']}[/cyan]")
    console.print(f"Filer gRPC Port: [cyan]{config_values['filer_grpc_port']}[/cyan]")
    console.print(f"Filer HTTP Port: [cyan]{config_values['filer_http_port']}[/cyan]")
    console.print(f"NATS URL: [cyan]{config_values['nats_url']}[/cyan]")
    
    console.print("\n[bold]Environment Variables:[/bold]")
    env_vars = [
        "SEAWEEDFS_FILER_HOST",
        "SEAWEEDFS_FILER_GRPC_PORT", 
        "SEAWEEDFS_FILER_HTTP_PORT",
        "NATS_URL",
        "WATCH_PATH_PREFIX",
        "KUBERNETES_SERVICE_HOST",
    ]
    
    for var in env_vars:
        value = os.getenv(var, "[dim]not set[/dim]")
        console.print(f"{var}: {value}")


if __name__ == "__main__":
    app()