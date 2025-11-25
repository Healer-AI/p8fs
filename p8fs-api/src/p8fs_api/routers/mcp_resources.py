"""MCP Resources for P8FS - Paginated table access and entity discovery.

Resources provide structured, paginated access to P8FS tables and entities.
Unlike tools which execute queries, resources expose data for browsing and discovery.
"""

from typing import Any
from urllib.parse import parse_qs, urlparse

import boto3
from fastmcp import FastMCP
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


def parse_resource_uri(uri: str) -> tuple[str, dict[str, Any]]:
    """Parse resource URI and extract query parameters.

    Args:
        uri: Resource URI (e.g., "p8fs://files?page=1&limit=20")

    Returns:
        Tuple of (base_uri, params_dict)

    Example:
        >>> parse_resource_uri("p8fs://files?page=2&limit=50")
        ("p8fs://files", {"page": 2, "limit": 50})
    """
    parsed = urlparse(uri)
    base_uri = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    # Parse query parameters
    params = {}
    if parsed.query:
        query_params = parse_qs(parsed.query)
        # Convert single-item lists to values
        for key, value in query_params.items():
            if key in ['page', 'limit', 'offset']:
                try:
                    params[key] = int(value[0]) if value else 1
                except (ValueError, TypeError):
                    # Default to 1 if invalid value
                    params[key] = 1
            else:
                params[key] = value[0] if len(value) == 1 else value

    # Set defaults
    params.setdefault('page', 1)
    params.setdefault('limit', 20)

    return base_uri, params


async def load_resource(uri: str, tenant_id: str) -> dict[str, Any]:
    """Load MCP resource by URI with tenant isolation.

    Supports:
    - p8fs://files?page=1&limit=20 - Files table
    - p8fs://resources?page=1&limit=20 - Resources table
    - p8fs://moments?page=1&limit=20 - Moments table
    - p8fs://entities/resources?page=1&limit=50 - Entity keys from resources
    - p8fs://entities/moments?page=1&limit=50 - Entity keys from moments
    - s3-upload://{tenant_id}/{filename} - Presigned S3 upload URL

    Args:
        uri: Resource URI
        tenant_id: Tenant ID for isolation

    Returns:
        Resource data dictionary
    """
    base_uri, params = parse_resource_uri(uri)
    page = params.get('page', 1)
    limit = min(params.get('limit', 20), 100)  # Cap at 100
    offset = (page - 1) * limit

    # === FILES RESOURCE ===
    if base_uri == "p8fs://files":
        from p8fs.models.p8 import Files
        from p8fs.repository.TenantRepository import TenantRepository

        repo = TenantRepository(
            model_class=Files,
            tenant_id=tenant_id,
            provider_name=config.storage_provider
        )

        # Get files ordered by created_at descending
        results = await repo.select(
            filters={},
            limit=limit,
            offset=offset,
            order_by=['-created_at']  # Minus sign for descending
        )

        # Format results
        files = []
        for result in results:
            file_dict = result if isinstance(result, dict) else (
                result.model_dump() if hasattr(result, 'model_dump') else result.__dict__
            )
            files.append({
                "id": str(file_dict.get("id", "")),
                "uri": file_dict.get("uri", ""),
                "name": file_dict.get("name", ""),
                "mime_type": file_dict.get("mime_type", ""),
                "size": file_dict.get("size", 0),
                "created_at": str(file_dict.get("created_at", "")),
                "metadata": file_dict.get("metadata", {})
            })

        return {
            "table": "files",
            "page": page,
            "limit": limit,
            "offset": offset,
            "count": len(files),
            "files": files,
            "info": "Files uploaded to P8FS, ordered by creation date"
        }

    # === RESOURCES RESOURCE ===
    elif base_uri == "p8fs://resources":
        from p8fs.providers import get_provider

        provider = get_provider()

        # Query resources directly to avoid Pydantic validation on JSON fields
        query = """
            SELECT id, name, category, content, summary, uri,
                   related_entities, created_at, updated_at
            FROM resources
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """

        results = provider.execute(query, (tenant_id, limit, offset))

        # Format results
        resources = []
        for row in results:
            # Handle related_entities - may be string, list, or None
            related_entities = row.get("related_entities", [])
            if isinstance(related_entities, str):
                # Parse JSON string or use empty list
                try:
                    import json
                    related_entities = json.loads(related_entities) if related_entities and related_entities != '{}' else []
                except:
                    related_entities = []

            resources.append({
                "id": str(row.get("id", "")),
                "name": row.get("name", ""),
                "category": row.get("category", ""),
                "content": row.get("content", "")[:500],  # Preview only
                "summary": row.get("summary", ""),
                "uri": row.get("uri", ""),
                "related_entities": related_entities,
                "created_at": str(row.get("created_at", "")),
                "updated_at": str(row.get("updated_at", ""))
            })

        return {
            "table": "resources",
            "page": page,
            "limit": limit,
            "offset": offset,
            "count": len(resources),
            "resources": resources,
            "info": "Content resources in P8FS, ordered by creation date"
        }

    # === MOMENTS RESOURCE ===
    elif base_uri == "p8fs://moments":
        from p8fs.providers import get_provider

        provider = get_provider()

        # Query moments directly to avoid Pydantic validation on JSON array fields
        query = """
            SELECT id, name, moment_type, resource_timestamp, resource_ends_timestamp,
                   summary, location, present_persons, emotion_tags, topic_tags, created_at
            FROM moments
            WHERE tenant_id = %s
            ORDER BY resource_timestamp DESC
            LIMIT %s OFFSET %s
        """

        results = provider.execute(query, (tenant_id, limit, offset))

        # Helper to parse array fields that might be strings
        def parse_array_field(value):
            if isinstance(value, str):
                try:
                    import json
                    return json.loads(value) if value and value != '{}' else []
                except:
                    return []
            return value if value is not None else []

        # Format results
        moments = []
        for row in results:
            moments.append({
                "id": str(row.get("id", "")),
                "name": row.get("name", ""),
                "moment_type": row.get("moment_type", ""),
                "start_time": str(row.get("resource_timestamp", "")),
                "end_time": str(row.get("resource_ends_timestamp", "")),
                "summary": row.get("summary", ""),
                "location": row.get("location", ""),
                "present_persons": parse_array_field(row.get("present_persons")),
                "emotion_tags": parse_array_field(row.get("emotion_tags")),
                "topic_tags": parse_array_field(row.get("topic_tags")),
                "created_at": str(row.get("created_at", ""))
            })

        return {
            "table": "moments",
            "page": page,
            "limit": limit,
            "offset": offset,
            "count": len(moments),
            "moments": moments,
            "info": "Temporal moments (meetings, events, conversations), ordered by resource timestamp"
        }

    # === ENTITIES RESOURCES ===
    elif base_uri.startswith("p8fs://entities/"):
        table_name = base_uri.replace("p8fs://entities/", "")

        if table_name not in ["resources", "moments", "files"]:
            return {"error": f"Invalid entities table: {table_name}. Options: resources, moments, files"}

        from p8fs.providers import get_provider

        provider = get_provider()

        # Query KV storage for entity keys from the specified table
        # Pattern: {tenant_id}/{entity_key}/{table_name}
        prefix = f"{tenant_id}/"

        try:
            # Scan KV for all entity keys
            entity_entries = await provider.kv.scan(prefix=prefix, limit=1000)

            # Filter for entries matching the table and extract entity names
            entities = []
            seen_entities = set()

            for entry in entity_entries:
                if not entry.get("key"):
                    continue

                key = entry["key"]
                parts = key.split("/")

                # Expected format: {tenant_id}/{entity_key}/{table_name}
                if len(parts) >= 3 and parts[2] == table_name:
                    entity_key = parts[1]

                    if entity_key not in seen_entities:
                        seen_entities.add(entity_key)

                        # Get the value to find updated_at timestamp
                        value = entry.get("value", {})
                        updated_at = value.get("updated_at", "")

                        entities.append({
                            "entity_key": entity_key,
                            "table": table_name,
                            "count": len(value.get("entity_ids", [])) if isinstance(value, dict) else 0,
                            "updated_at": updated_at
                        })

            # Sort by updated_at descending
            entities.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

            # Apply pagination
            paginated_entities = entities[offset:offset + limit]

            return {
                "table": f"entities/{table_name}",
                "page": page,
                "limit": limit,
                "offset": offset,
                "total_entities": len(entities),
                "count": len(paginated_entities),
                "entities": paginated_entities,
                "info": f"Entity keys from {table_name} table, ordered by last update"
            }

        except Exception as e:
            logger.error(f"Failed to load entities for {table_name}: {e}", exc_info=True)
            return {
                "error": f"Failed to load entities: {str(e)}",
                "table": table_name
            }

    # === S3 UPLOAD RESOURCE ===
    elif uri.startswith("p8fs://s3-upload/"):
        # Parse URI: p8fs://s3-upload/{filename} (tenant_id comes from auth context)
        filename = uri.replace("p8fs://s3-upload/", "")

        if not filename:
            return {"error": "Invalid s3-upload URI format. Expected: p8fs://s3-upload/{filename}"}

        try:
            from datetime import datetime

            # Build S3 key using P8FS convention: uploads/{YYYY}/{MM}/{DD}/{filename}
            now = datetime.utcnow()
            date_path = now.strftime("%Y/%m/%d")
            s3_key = f"uploads/{date_path}/{filename}"

            # P8FS convention: bucket = tenant_id
            bucket = tenant_id
            s3_uri = f"s3://{bucket}/{s3_key}"

            # Create S3 client
            s3_client = boto3.client(
                's3',
                endpoint_url=config.seaweedfs_s3_endpoint,
                aws_access_key_id=config.seaweedfs_access_key,
                aws_secret_access_key=config.seaweedfs_secret_key,
                region_name='us-east-1'
            )

            # Generate presigned PUT URL (valid for 1 hour)
            # SeaweedFS supports presigned URLs but has some quirks
            try:
                presigned_url = s3_client.generate_presigned_url(
                    'put_object',
                    Params={
                        'Bucket': bucket,
                        'Key': s3_key,
                        'ContentType': 'application/octet-stream'
                    },
                    ExpiresIn=3600
                )
                upload_method = "presigned_url"

            except Exception as presign_error:
                # Fallback: Return direct upload URL with auth
                logger.warning(f"Presigned URL generation failed, using direct upload: {presign_error}")
                presigned_url = f"{config.seaweedfs_s3_endpoint}/{bucket}/{s3_key}"
                upload_method = "direct_with_auth"

            return {
                "tenant_id": tenant_id,
                "filename": filename,
                "s3_path": s3_uri,
                "s3_key": s3_key,
                "bucket": bucket,
                "date_path": date_path,
                "presigned_url": presigned_url,
                "upload_method": upload_method,
                "expires_in": 3600,
                "usage": {
                    "upload": f'curl -T "{filename}" "{presigned_url}"',
                    "note": "File will be automatically indexed in P8FS after upload",
                    "upload_path": f"uploads/{date_path}/{filename}"
                },
                "info": f"Upload to s3://{bucket}/uploads/{date_path}/{filename}"
            }

        except Exception as e:
            logger.error(f"Failed to generate S3 upload URL for {tenant_id}/{filename}: {e}", exc_info=True)
            return {
                "error": "Failed to generate upload URL",
                "tenant_id": tenant_id,
                "filename": filename,
                "details": str(e)
            }

    else:
        return {"error": f"Unknown resource URI: {uri}"}


# === RESOURCE REGISTRATION FUNCTIONS ===

def register_files_resource(mcp: FastMCP):
    """Register files table resource."""

    @mcp.resource("p8fs://files/{view}")
    async def files_resource(view: str) -> str:
        """Paginated access to files table.

        URI: p8fs://files/all?page=1&limit=20

        Path Parameters:
        - view: Resource view (use "all" for default listing)

        Query Parameters:
        - page: Page number (default: 1)
        - limit: Items per page (default: 20, max: 100)

        Returns JSON with files ordered by creation date (newest first).
        """
        # TODO: Get tenant_id from auth context
        tenant_id = config.default_tenant_id
        # Build URI for load_resource (expects p8fs://files format)
        uri = "p8fs://files"
        result = await load_resource(uri, tenant_id=tenant_id)
        import json
        return json.dumps(result, indent=2)


def register_resources_resource(mcp: FastMCP):
    """Register resources table resource."""

    @mcp.resource("p8fs://resources/{view}")
    async def resources_resource(view: str) -> str:
        """Paginated access to resources table.

        URI: p8fs://resources/all?page=1&limit=20

        Path Parameters:
        - view: Resource view (use "all" for default listing)

        Query Parameters:
        - page: Page number (default: 1)
        - limit: Items per page (default: 20, max: 100)

        Returns JSON with resources ordered by creation date (newest first).
        Content field is truncated to 500 chars (preview only).
        """
        # TODO: Get tenant_id from auth context
        tenant_id = config.default_tenant_id
        # Build URI for load_resource (expects p8fs://resources format)
        uri = "p8fs://resources"
        result = await load_resource(uri, tenant_id=tenant_id)
        import json
        return json.dumps(result, indent=2)


def register_moments_resource(mcp: FastMCP):
    """Register moments table resource."""

    @mcp.resource("p8fs://moments/{view}")
    async def moments_resource(view: str) -> str:
        """Paginated access to moments table.

        URI: p8fs://moments/all?page=1&limit=20

        Path Parameters:
        - view: Resource view (use "all" for default listing)

        Query Parameters:
        - page: Page number (default: 1)
        - limit: Items per page (default: 20, max: 100)

        Returns JSON with moments ordered by start time (newest first).
        """
        # TODO: Get tenant_id from auth context
        tenant_id = config.default_tenant_id
        # Build URI for load_resource (expects p8fs://moments format)
        uri = "p8fs://moments"
        result = await load_resource(uri, tenant_id=tenant_id)
        import json
        return json.dumps(result, indent=2)


def register_entities_resource(mcp: FastMCP):
    """Register entities discovery resources."""

    @mcp.resource("p8fs://entities/{table}")
    async def entities_resource(table: str) -> str:
        """Entity keys from a specific table.

        URI: p8fs://entities/{table}?page=1&limit=50

        Tables: resources, moments, files

        Query Parameters:
        - page: Page number (default: 1)
        - limit: Items per page (default: 50, max: 100)

        Returns JSON with entity keys ordered by last update (newest first).
        Shows entity name, table, count of resources, and last updated timestamp.

        Use this to discover what entities exist before querying with LOOKUP.
        """
        # TODO: Get tenant_id from auth context
        tenant_id = config.default_tenant_id
        # Build URI for load_resource
        uri = f"p8fs://entities/{table}"
        result = await load_resource(uri, tenant_id=tenant_id)
        import json
        return json.dumps(result, indent=2)


def register_s3_upload_resource(mcp: FastMCP):
    """Register S3 upload presigned URL resource."""

    @mcp.resource("p8fs://s3-upload/{filename}")
    async def s3_upload_resource(filename: str) -> str:
        """Get presigned S3 upload URL.

        URI: p8fs://s3-upload/{filename}

        Tenant ID automatically extracted from JWT token.
        Returns presigned PUT URL for direct S3 upload.

        S3 Path Convention:
        - Bucket: {tenant_id}
        - Key: uploads/{YYYY}/{MM}/{DD}/{filename}
        - Example: s3://tenant-test/uploads/2025/11/15/document.pdf

        Workflow:
        1. Call this resource to get presigned URL
        2. Upload file: curl -T local-file.pdf "{presigned_url}"
        3. File is automatically indexed in P8FS

        Presigned URL valid for 1 hour.
        """
        # TODO: Get tenant_id from auth context (JWT token)
        tenant_id = config.default_tenant_id
        # Build URI for load_resource
        uri = f"p8fs://s3-upload/{filename}"
        result = await load_resource(uri, tenant_id=tenant_id)
        import json
        return json.dumps(result, indent=2)
