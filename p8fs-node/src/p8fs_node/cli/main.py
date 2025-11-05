"""CLI commands for p8fs-node content processing."""

import asyncio
import json
from pathlib import Path

import typer

from p8fs_cluster.config.settings import config
from p8fs_node import auto_register, get_content_provider
from p8fs_node.services.embeddings import get_embedding_service
from p8fs_node.workers.storage import StorageWorker
from p8fs_node.models.content import ContentProcessingResult

app = typer.Typer(help="P8FS Node - Content processing and storage")


@app.command()
def process(
    file_path: str = typer.Argument(..., help="Path to the file to process"),
    output_format: str = typer.Option("summary", help="Output format (summary, json)"),
    generate_embeddings: bool = typer.Option(True, help="Generate embeddings"),
    extended: bool = typer.Option(False, help="Use extended processing"),
    save_to_storage: bool = typer.Option(True, help="Save chunks to storage"),
    tenant_id: str = typer.Option(config.default_tenant_id, help=f"Tenant ID for storage (default: {config.default_tenant_id})"),
) -> None:
    """Process a file and optionally save to storage."""
    
    async def _process():
        # Resolve file path
        path = Path(file_path)
        if not path.exists():
            # Try relative to current directory
            path = Path.cwd() / file_path
            if not path.exists():
                typer.echo(f"❌ File not found: {file_path}")
                raise typer.Exit(1)
        
        # Register all content providers
        auto_register()
        
        # Get the appropriate provider for this file
        provider = get_content_provider(str(path))
        if not provider:
            typer.echo(f"❌ No provider found for file: {path}")
            raise typer.Exit(1)
            
        typer.echo(f"Processing {path} with {type(provider).__name__}...")
        
        try:
            # Process content using correct provider interface
            chunks = await provider.to_markdown_chunks(str(path), extended=extended)
            metadata = await provider.to_metadata(str(path))
            
            typer.echo("✅ Processed successfully:")
            typer.echo(f"   - {len(chunks)} chunks created")
            typer.echo(f"   - Title: {metadata.title}")
            typer.echo(f"   - Content type: {metadata.content_type}")
            
            # Generate embeddings if requested
            embeddings = None
            if generate_embeddings:
                try:
                    embedding_service = get_embedding_service()
                    texts = [chunk.content for chunk in chunks]
                    embeddings = await embedding_service.embed_batch(texts)
                    typer.echo(f"   - Generated {len(embeddings)} embeddings")
                except Exception as e:
                    typer.echo(f"⚠️  Warning: Failed to generate embeddings: {e}")
            
            # Create processing result
            result = ContentProcessingResult(
                success=True,
                content_type=metadata.content_type,
                chunks=chunks,
                metadata=metadata,
                processing_time=0.1
            )
            
            if save_to_storage:
                # Initialize storage worker and save chunks
                storage_worker = StorageWorker(tenant_id=tenant_id)
                storage_result = await storage_worker.save_chunks_to_storage(result, str(path))
                
                file_id = storage_result.get("file_id")
                resource_ids = storage_result.get("resource_ids", [])
                
                if file_id:
                    typer.echo(f"✅ Registered file: {file_id}")
                    typer.echo(f"✅ Saved {len(resource_ids)} chunks to storage")
                    if resource_ids:
                        typer.echo(f"   Resource IDs: {resource_ids[:3]}{'...' if len(resource_ids) > 3 else ''}")
                else:
                    typer.echo(f"❌ Failed to register file, but saved {len(resource_ids)} chunks")
            
            # Output the result
            if output_format == "json":
                output = {
                    "metadata": metadata.model_dump() if hasattr(metadata, 'model_dump') else metadata.__dict__,
                    "chunks": [chunk.model_dump() if hasattr(chunk, 'model_dump') else chunk.__dict__ for chunk in chunks],
                    "embeddings": embeddings
                }
                typer.echo(json.dumps(output, indent=2, default=str))
            
        except Exception as e:
            typer.echo(f"❌ Error processing file: {e}")
            import traceback
            typer.echo(traceback.format_exc())
            raise typer.Exit(1)
    
    # Run the async function
    asyncio.run(_process())


@app.command()
def list_providers() -> None:
    """List all available content providers."""
    auto_register()
    
    from p8fs_node.providers.registry import (
        list_content_providers,
        list_supported_content_types,
    )
    
    providers = list_content_providers()
    supported_types = list_supported_content_types()
    
    typer.echo("📋 Available Content Providers:")
    for provider_name in providers:
        typer.echo(f"  - {provider_name}")
    
    typer.echo("\n📂 Supported Content Types:")
    for content_type in supported_types:
        typer.echo(f"  - {content_type}")


@app.command()
def test_file(
    file_path: str = typer.Argument(..., help="Path to test file detection")
) -> None:
    """Test which provider would handle a specific file."""
    auto_register()
    
    provider = get_content_provider(file_path)
    if provider:
        typer.echo(f"📄 File: {file_path}")
        typer.echo(f"🔧 Provider: {type(provider).__name__}")
        typer.echo(f"📋 Supported types: {provider.supported_types}")
    else:
        typer.echo(f"❌ No provider found for: {file_path}")


def main():
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()