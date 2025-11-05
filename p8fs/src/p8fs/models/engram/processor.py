"""Engram processor for handling Kubernetes-like documents."""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4, uuid5, NAMESPACE_DNS

import yaml
from p8fs_cluster.logging import get_logger

from p8fs.repository import TenantRepository
from p8fs.models.p8 import Resources

from .models import EngramDocument  
from p8fs.models.p8 import Engram, Moment

logger = get_logger(__name__)


class EngramProcessor:
    """Processes Engram documents with upserts, patches, and associations."""
    
    def __init__(self, repo: TenantRepository):
        self.repo = repo
    
    async def process(self, content: str, content_type: str, tenant_id: str, session_id: UUID | None = None) -> dict[str, Any]:
        """Process content as potential Engram document."""
        try:
            # Parse content
            if content_type == "application/x-yaml":
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)
            
            # Validate as Engram
            try:
                doc = EngramDocument.model_validate(data)
                logger.info(f"Parsed document kind: {doc.kind}, p8Kind: {doc.p8Kind}")
                if doc.is_engram():
                    logger.info("Document identified as engram, processing...")
                    return await self._process_engram(doc, tenant_id, session_id)
                else:
                    logger.info("Document is not an engram, storing as resource...")
            except Exception as e:
                logger.warning(f"Failed to parse as engram document: {e}")
                pass
            
            # Not an Engram, store as regular resource
            return await self._store_as_resource(data, tenant_id, session_id)
            
        except Exception as e:
            logger.error(f"Error processing content: {e}")
            raise
    
    async def _process_engram(self, doc: EngramDocument, tenant_id: str, session_id: UUID | None) -> dict[str, Any]:
        """Process validated Engram document."""
        # Store Engram if it has a summary
        engram_id = None
        if doc.metadata.summary:
            engram_id = await self._store_engram(doc, tenant_id, session_id)
        
        # Process operations
        results = {
            "engram_id": str(engram_id) if engram_id else None,
            "upserts": 0,
            "patches": 0,
            "associations": 0
        }
        
        # Process upserts
        if doc.spec.upserts:
            results["upserts"] = await self._process_upserts(
                doc.spec.upserts, 
                tenant_id, 
                session_id
            )
        
        # Process patches
        if doc.spec.patches:
            results["patches"] = await self._process_patches(
                doc.spec.patches, 
                tenant_id, 
                session_id
            )
        
        # Process associations (ensure nodes exist first)
        if doc.spec.associations:
            # Ensure graph nodes exist for entities before creating associations
            await self._ensure_graph_nodes(tenant_id)
            results["associations"] = await self._process_associations(
                doc.spec.associations, 
                tenant_id, 
                session_id
            )
        
        return results
    
    async def _store_engram(self, doc: EngramDocument, tenant_id: str, session_id: UUID | None) -> UUID:
        """Store Engram entity."""
        engram = Engram(
            id=uuid4(),
            tenant_id=tenant_id,
            name=doc.metadata.name,
            summary=doc.metadata.summary,
            content=json.dumps(doc.model_dump(), default=str),  # Convert dict to JSON string, handling datetime
            uri=doc.metadata.uri or "engram://processed", 
            processed_at=datetime.now(timezone.utc),
            operation_count={
                "upserts": len(doc.spec.upserts or []),
                "patches": len(doc.spec.patches or []),
                "associations": len(doc.spec.associations or [])
            }
        )
        
        # Use create_resource method which expects proper Engram data
        engram_dict = engram.model_dump()
        await self.repo.create_resource(engram_dict)
        
        return engram.id
    
    async def _process_upserts(self, upserts: list[dict[str, Any]], tenant_id: str, session_id: UUID | None) -> int:
        """Process upsert operations."""
        count = 0
        
        for entity in upserts:
            entity_type = entity.get("entityType", "resource")
            
            if entity_type == "moment" or entity_type == "models.Moment":
                # Create moment with full specification support
                # Generate UUID from string ID to ensure uniqueness
                entity_id = entity.get("id", str(uuid4()))
                if not entity_id.count('-') == 4:  # Not already a UUID
                    entity_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{entity_id}"))
                
                moment_data = {
                    "id": entity_id,
                    "tenant_id": entity.get("tenant_id") or tenant_id,
                    "name": entity.get("name", "Untitled Moment"),  # Default name required
                    "content": entity.get("content", ""),
                    "summary": entity.get("summary"),
                    "uri": entity.get("uri", "moment://processed"),  # URI is required
                    "metadata": entity.get("metadata", {})
                }
                
                # Handle timestamp fields (support multiple formats)
                if entity.get("resource_timestamp"):
                    moment_data["resource_timestamp"] = entity.get("resource_timestamp")
                    
                if entity.get("resource_ends_timestamp"):
                    moment_data["resource_ends_timestamp"] = entity.get("resource_ends_timestamp")
                
                # Additional moment-specific fields from specification
                if entity.get("present_persons"):
                    moment_data["present_persons"] = entity.get("present_persons")
                
                if entity.get("location"):
                    moment_data["location"] = entity.get("location")
                    
                if entity.get("background_sounds"):
                    moment_data["background_sounds"] = entity.get("background_sounds")
                    
                if entity.get("moment_type"):
                    moment_data["moment_type"] = entity.get("moment_type")
                    
                if entity.get("emotion_tags"):
                    moment_data["emotion_tags"] = entity.get("emotion_tags")
                    
                if entity.get("topic_tags"):
                    moment_data["topic_tags"] = entity.get("topic_tags")
                
                await self.repo.create_moment(moment_data)
            else:
                # Create resource
                await self.repo.create_resource({
                    "id": entity.get("id", str(uuid4())),
                    "tenant_id": tenant_id,
                    "session_id": str(session_id) if session_id else None,
                    "content": json.dumps(entity),
                    "content_type": "application/json",
                    "metadata": entity.get("metadata")
                })
            
            count += 1
        
        return count
    
    async def _process_patches(self, patches: list[dict[str, Any]], tenant_id: str, session_id: UUID | None) -> int:
        """Process patch operations to update existing entities."""
        count = 0
        
        for patch in patches:
            entity_id = patch.get("id") or patch.get("entityId")
            fields_to_update = patch.get("fields") or patch.get("updates", {})
            
            if not entity_id or not fields_to_update:
                logger.warning(f"Invalid patch operation: missing id or fields")
                continue
            
            try:
                # Try to find the entity as a resource first
                existing_resource = await self.repo.get_resource(entity_id)
                if existing_resource:
                    # Update the resource
                    updated_content = existing_resource.get("content", {})
                    if isinstance(updated_content, str):
                        try:
                            updated_content = json.loads(updated_content)
                        except json.JSONDecodeError:
                            updated_content = {"content": updated_content}
                    
                    # Merge fields
                    for key, value in fields_to_update.items():
                        if key == "metadata" and isinstance(value, dict):
                            # Merge metadata
                            if "metadata" not in updated_content:
                                updated_content["metadata"] = {}
                            updated_content["metadata"].update(value)
                        else:
                            updated_content[key] = value
                    
                    await self.repo.update_resource(entity_id, {
                        "content": json.dumps(updated_content,default=str),
                        "metadata": updated_content.get("metadata")
                    })
                    count += 1
                    continue
                
                # Try to find as a moment
                existing_moment = await self.repo.get_moment(entity_id)
                if existing_moment:
                    update_data = {}
                    for key, value in fields_to_update.items():
                        if key == "metadata" and isinstance(value, dict):
                            # Merge metadata
                            existing_metadata = existing_moment.get("metadata", {})
                            existing_metadata.update(value)
                            update_data["metadata"] = existing_metadata
                        else:
                            update_data[key] = value
                    
                    await self.repo.update_moment(entity_id, update_data)
                    count += 1
                    continue
                
                logger.warning(f"Entity {entity_id} not found for patch operation")
                
            except Exception as e:
                logger.error(f"Error processing patch for entity {entity_id}: {e}")
        
        return count
    
    async def _process_associations(self, associations: list[dict[str, Any]], tenant_id: str, session_id: UUID | None) -> int:
        """Process association operations to create entity relationships."""
        count = 0
        
        for assoc in associations:
            # Handle both dict and model objects
            if hasattr(assoc, 'model_dump'):
                assoc_data = assoc.model_dump()
            else:
                assoc_data = assoc
            
            # Extract association details - support both spec formats
            from_type = assoc_data.get("from_type") or assoc_data.get("fromType")
            from_id = assoc_data.get("from_id") or assoc_data.get("fromEntityId") 
            to_type = assoc_data.get("to_type") or assoc_data.get("toType")
            to_id = assoc_data.get("to_id") or assoc_data.get("toEntityId")
            relationship = assoc_data.get("relationship") or assoc_data.get("relationType")
            metadata = assoc_data.get("metadata", {})
            
            # Normalize entity types to graph node labels
            def normalize_entity_type(entity_type):
                if not entity_type:
                    return "resource"
                # Convert models.Moment -> moments, models.Engram -> engrams, etc.
                if entity_type.startswith("models."):
                    base_type = entity_type.replace("models.", "").lower()
                    # Convert singular to plural for table names
                    if base_type == "moment":
                        return "moments"
                    elif base_type == "engram":
                        return "engrams" 
                    elif base_type == "user":
                        return "users"
                    else:
                        return base_type + "s"  # Simple pluralization
                return entity_type.lower()
            
            from_type = normalize_entity_type(from_type)
            to_type = normalize_entity_type(to_type)
            
            if not all([from_id, to_id, relationship]):
                logger.warning(f"Invalid association: missing required fields")
                continue
            
            try:
                # Convert string IDs to UUIDs if needed
                if from_id and not from_id.count('-') == 4:
                    from_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{from_id}"))
                if to_id and not to_id.count('-') == 4:
                    to_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{to_id}"))
                
                # Create graph association
                association_id = str(uuid4())
                result = await self.repo.create_association({
                    "id": association_id,
                    "tenant_id": tenant_id,
                    "session_id": str(session_id) if session_id else None,
                    "from_entity_type": from_type or "resource",
                    "from_entity_id": from_id,
                    "to_entity_type": to_type or "resource", 
                    "to_entity_id": to_id,
                    "relationship_type": relationship,
                    "metadata": metadata
                })
                
                if result is not None:
                    count += 1
                
            except Exception as e:
                logger.error(f"Error creating association {from_id} -> {to_id}: {e}")
        
        return count
    
    async def _sync_table_to_graph(self, table_name: str):
        """Sync a specific table to graph database."""
        try:
            from p8fs.services import PostgresGraphProvider
            
            # Initialize graph provider
            graph = PostgresGraphProvider(self.repo.engram_repo.provider)
            
            # Sync the specific table
            result = graph.ensure_nodes([table_name])
            nodes_created = result.get(table_name, 0)
            
            if nodes_created > 0:
                logger.info(f"Synced {nodes_created} {table_name} nodes to graph")
            
        except Exception as e:
            logger.error(f"Failed to sync {table_name} to graph: {e}")
    
    async def _ensure_graph_nodes(self, tenant_id: str):
        """Final sync to ensure all entities have corresponding graph nodes."""
        try:
            # Final sync for any remaining entities
            await self._sync_table_to_graph('engrams')
            await self._sync_table_to_graph('moments')
            logger.info("Final graph nodes synchronization completed")
            
        except Exception as e:
            logger.error(f"Failed to ensure graph nodes: {e}")
    
    async def _store_as_resource(self, data: dict[str, Any], tenant_id: str, session_id: UUID | None) -> dict[str, Any]:
        """Store non-Engram content as regular resource."""
        resource_id = uuid4()
        
        await self.repo.create_resource({
            "id": str(resource_id),
            "tenant_id": tenant_id,
            "session_id": str(session_id) if session_id else None,
            "content": json.dumps(data),
            "content_type": "application/json"
        })
        
        return {"resource_id": str(resource_id)}


# CLI interface for testing
if __name__ == "__main__":
    import asyncio
    import sys
    from pathlib import Path
    
    import typer
    from p8fs_cluster.config.settings import config
    from p8fs.repository.TenantRepository import TenantRepository
    from p8fs.providers import get_provider
    from p8fs.models.p8 import Engram, Moment
    
    app = typer.Typer(help="Engram processor CLI")
    
    @app.command()
    def process_file(
        file_path: str = typer.Argument(help="Path to JSON/YAML engram file"),
        tenant_id: str = typer.Option("test-tenant", help="Tenant ID"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output")
    ):
        """Process an engram file and store in database."""
        async def run():
            try:
                # Create a multi-model repository wrapper  
                class MultiModelRepo:
                    def __init__(self, tenant_id):
                        self.tenant_id = tenant_id
                        # Initialize repositories for different models (let them create their own providers)
                        self.engram_repo = TenantRepository(Engram, tenant_id)
                        self.moment_repo = TenantRepository(Moment, tenant_id)
                    
                    # Delegate methods to appropriate repositories
                    async def create_resource(self, data):
                        # Create engram entity for resources
                        engram = Engram(**data)
                        return await self.engram_repo.upsert(engram)
                    
                    async def create_moment(self, data):
                        moment = Moment(**data)
                        return await self.moment_repo.upsert(moment)
                    
                    async def create_association(self, data):
                        # Create graph edge using PostgresGraphProvider
                        try:
                            from p8fs.services import PostgresGraphProvider, GraphAssociation
                            
                            # Initialize graph provider
                            graph = PostgresGraphProvider(self.engram_repo.provider)
                            
                            # Create association model
                            association = GraphAssociation(
                                from_entity_id=data.get("from_entity_id"),
                                to_entity_id=data.get("to_entity_id"),
                                relationship_type=data.get("relationship_type"),
                                from_entity_type=data.get("from_entity_type"),
                                to_entity_type=data.get("to_entity_type"),
                                metadata=data.get("metadata"),
                                tenant_id=data.get("tenant_id")
                            )
                            
                            # Create the association
                            result = graph.create_association(association)
                            return result
                                
                        except Exception as e:
                            logger.error(f"Database error creating graph association: {e}", exc_info=True)
                            logger.debug(f"Association data: {data}")
                            # Don't return None for database errors - let them propagate
                            raise RuntimeError(f"Database error creating graph association: {e}") from e
                    
                    async def get_resource(self, entity_id):
                        try:
                            return await self.engram_repo.get_by_id(entity_id)
                        except Exception as e:
                            logger.error(f"Database error getting resource {entity_id}: {e}", exc_info=True)
                            # Don't return None for database errors - let them propagate
                            raise RuntimeError(f"Database error retrieving resource: {e}") from e
                    
                    async def get_moment(self, entity_id):
                        try:
                            return await self.moment_repo.get_by_id(entity_id)
                        except Exception as e:
                            logger.warning(f"Failed to get moment {entity_id}: {e}")
                            return None
                    
                    async def update_resource(self, entity_id, data):
                        return await self.engram_repo.update_by_id(entity_id, data)
                    
                    async def update_moment(self, entity_id, data):
                        return await self.moment_repo.update_by_id(entity_id, data)
                
                repo = MultiModelRepo(tenant_id)
                
                # Initialize processor
                processor = EngramProcessor(repo)
                
                # Read file
                path = Path(file_path)
                if not path.exists():
                    typer.echo(f"File not found: {file_path}", err=True)
                    raise typer.Exit(1)
                
                content = path.read_text()
                content_type = "application/x-yaml" if path.suffix.lower() in ['.yaml', '.yml'] else "application/json"
                
                typer.echo(f"Processing {content_type} file: {file_path}")
                typer.echo(f"Tenant ID: {tenant_id}")
                
                if verbose:
                    typer.echo("File content:")
                    typer.echo(content)
                    typer.echo("-" * 50)
                
                # Process file
                result = await processor.process(content, content_type, tenant_id)
                
                # Display results
                typer.echo("✅ Processing completed successfully!")
                typer.echo(f"Results: {result}")
                
                if result.get("engram_id"):
                    typer.echo(f"📄 Engram stored with ID: {result['engram_id']}")
                
                if result.get("upserts", 0) > 0:
                    typer.echo(f"➕ Created {result['upserts']} entities")
                
                if result.get("patches", 0) > 0:
                    typer.echo(f"🔄 Applied {result['patches']} patches")
                
                if result.get("associations", 0) > 0:
                    typer.echo(f"🔗 Created {result['associations']} associations")
                
                if result.get("resource_id"):
                    typer.echo(f"📦 Generic resource stored with ID: {result['resource_id']}")
                
            except Exception as e:
                typer.echo(f"❌ Error: {e}", err=True)
                if verbose:
                    import traceback
                    traceback.print_exc()
                raise typer.Exit(1)
        
        asyncio.run(run())
    
    app()