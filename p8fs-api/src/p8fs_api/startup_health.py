"""Startup health check for P8FS API.

Runs comprehensive system checks on startup and stores results for /health endpoint.
"""

from datetime import datetime, timezone
from typing import Any

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

# Global health check state
startup_health_data: dict[str, Any] = {
    "status": "initializing",
    "timestamp": None,
    "checks": {}
}


async def run_startup_health_checks(extended: bool = False) -> dict[str, Any]:
    """Run all startup health checks and return results.

    Checks:
    - TiKV key-value operations (put/get)
    - Database record counts (resources, files, moments)
    - LLM service connectivity (only when extended=True due to cost)
    - NATS queue sizes
    - Embedding service (default provider and vector generation)

    Args:
        extended: If True, run LLM health check (has cost implications)

    Returns:
        Dictionary with health check results including:
        - status: Overall health status (healthy/degraded/unhealthy)
        - timestamp: When checks were run
        - version: API version
        - checks: Individual check results (tikv, database, llm, nats, embedding)
        - duration_ms: How long checks took to complete
    """
    logger.info(f"Running startup health checks (extended={extended})")
    start_time = datetime.now(timezone.utc)

    checks = {}

    # 1. TiKV health check
    tikv_check = await check_tikv_health()
    checks["tikv"] = tikv_check

    # 2. Database health check
    db_check = await check_database_health()
    checks["database"] = db_check

    # 3. LLM service health check (only in extended mode due to cost)
    if extended:
        llm_check = await check_llm_health()
        checks["llm"] = llm_check
    else:
        checks["llm"] = {
            "status": "skipped",
            "message": "LLM check skipped"
        }

    # 4. NATS queue health check
    nats_check = await check_nats_health()
    checks["nats"] = nats_check

    # 5. Embedding service health check
    embedding_check = await check_embedding_health()
    checks["embedding"] = embedding_check

    # Determine overall status
    all_healthy = all(
        check.get("status") == "healthy"
        for check in checks.values()
    )

    overall_status = "healthy" if all_healthy else "degraded"

    # Get API version
    from . import __version__

    result = {
        "status": overall_status,
        "version": __version__,
        "timestamp": start_time.isoformat(),
        "checks": checks,
        "duration_ms": int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
    }

    # Store in global state
    startup_health_data.update(result)

    logger.info(
        f"Startup health checks completed: {overall_status}",
        duration_ms=result["duration_ms"]
    )

    return result


async def check_tikv_health() -> dict[str, Any]:
    """Check TiKV/KV storage health by performing put/get operations."""
    try:
        from p8fs.providers import get_provider

        provider = get_provider()
        kv = provider.kv

        # Test key-value operations
        test_key = "health_check_startup"
        test_value = {"timestamp": datetime.now(timezone.utc).isoformat(), "test": "startup_health"}

        # Put
        await kv.put(test_key, test_value, ttl_seconds=60)

        # Get
        retrieved = await kv.get(test_key)

        if retrieved and retrieved.get("test") == "startup_health":
            return {
                "status": "healthy",
                "message": "TiKV put/get operations successful",
                "provider": config.storage_provider
            }
        else:
            return {
                "status": "unhealthy",
                "message": "TiKV get returned unexpected value",
                "provider": config.storage_provider
            }

    except Exception as e:
        logger.error(f"TiKV health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "message": f"TiKV error: {str(e)}",
            "error": str(e)
        }


async def check_database_health() -> dict[str, Any]:
    """Check database health by counting records in key tables."""
    try:
        from p8fs.providers import get_provider

        provider = get_provider()
        conn = provider.connect_sync()

        counts = {}

        # Count resources
        try:
            result = provider.execute(
                "SELECT COUNT(*) as count FROM resources WHERE tenant_id = %s",
                (config.tenant_id,),
                conn
            )
            counts["resources"] = result[0]["count"] if result else 0
        except Exception as e:
            logger.warning(f"Failed to count resources: {e}")
            counts["resources"] = None

        # Count files
        try:
            result = provider.execute(
                "SELECT COUNT(*) as count FROM files WHERE tenant_id = %s",
                (config.tenant_id,),
                conn
            )
            counts["files"] = result[0]["count"] if result else 0
        except Exception as e:
            logger.warning(f"Failed to count files: {e}")
            counts["files"] = None

        # Count moments
        try:
            result = provider.execute(
                "SELECT COUNT(*) as count FROM moments WHERE tenant_id = %s",
                (config.tenant_id,),
                conn
            )
            counts["moments"] = result[0]["count"] if result else 0
        except Exception as e:
            logger.warning(f"Failed to count moments: {e}")
            counts["moments"] = None

        conn.close()

        # Check if at least one count succeeded
        if any(count is not None for count in counts.values()):
            return {
                "status": "healthy",
                "message": "Database queries successful",
                "counts": counts,
                "provider": config.storage_provider
            }
        else:
            return {
                "status": "unhealthy",
                "message": "All database queries failed",
                "counts": counts
            }

    except Exception as e:
        logger.error(f"Database health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "message": f"Database error: {str(e)}",
            "error": str(e)
        }


async def check_llm_health() -> dict[str, Any]:
    """Check LLM service health with a simple test query."""
    try:
        # Check if OpenAI API key is set
        openai_key = getattr(config, 'openai_api_key', None)
        if not openai_key:
            return {
                "status": "degraded",
                "message": "LLM API key not configured",
                "note": "Set OPENAI_API_KEY to enable LLM checks"
            }

        from p8fs.services.llm.memory_proxy import MemoryProxy
        from p8fs.services.llm.models import CallingContext
        from p8fs.utils.inspection import load_entity

        # Load p8-system agent
        agent_class = load_entity("p8-system")
        agent_instance = agent_class(
            id="health-check-agent",
            name="p8-system",
            description="Health check instance",
            spec={"source": "health-check", "type": "agent"}
        )

        # Create calling context
        context = CallingContext(
            model="gpt-4.1-nano",
            temperature=0,
            max_tokens=5,
            prefers_streaming=False,
            tenant_id=config.tenant_id,
            user_id="health-check"
        )

        # Test with MemoryProxy and p8-system agent
        async with MemoryProxy(model_context=agent_instance) as memory_proxy:
            response = await memory_proxy.run("Respond with 'yes'", context)

        # Check if we got a response
        if response and len(response) > 0:
            return {
                "status": "healthy",
                "message": "LLM service responded successfully",
                "model": "gpt-4.1-nano",
                "response": response[:50]  # First 50 chars
            }
        else:
            return {
                "status": "unhealthy",
                "message": "LLM service returned empty response"
            }

    except Exception as e:
        logger.warning(f"LLM health check failed: {e}", exc_info=True)
        return {
            "status": "degraded",
            "message": f"LLM not available: {str(e)}",
            "note": "This is expected if LLM API keys are not configured"
        }


async def check_nats_health() -> dict[str, Any]:
    """Check NATS health by querying queue sizes."""
    try:
        from p8fs.services.nats.client import NATSClient

        # Try to connect to NATS
        nats_client = NATSClient([config.nats_url])

        try:
            await nats_client.connect()

            # Get queue statistics for known worker queues
            queue_sizes = {}

            # List of NATS streams to check (tiered storage router)
            worker_queues = [
                "P8FS_STORAGE_EVENTS",        # Main queue
                "P8FS_STORAGE_EVENTS_SMALL",  # Small files
                "P8FS_STORAGE_EVENTS_MEDIUM", # Medium files
                "P8FS_STORAGE_EVENTS_LARGE"   # Large files
            ]

            for queue_name in worker_queues:
                try:
                    # Get stream info for queue
                    stream_info = await nats_client.get_stream_info(queue_name)
                    if stream_info:
                        total_messages = stream_info.get("messages", 0)

                        # Get consumer info to check unprocessed messages
                        consumer_name = queue_name.replace("P8FS_STORAGE_EVENTS", "").lower().strip("_") or "default"
                        consumer_name = f"{consumer_name}-workers" if consumer_name != "default" else "storage-workers"

                        try:
                            consumer_info = await nats_client.get_consumer_info(queue_name, consumer_name)
                            unprocessed = consumer_info.get("num_pending", 0)
                        except Exception as consumer_error:
                            logger.debug(f"Failed to get consumer info for {queue_name}/{consumer_name}: {consumer_error}")
                            unprocessed = None

                        queue_sizes[queue_name] = {
                            "messages": total_messages,
                            "unprocessed": unprocessed,
                            "bytes": stream_info.get("bytes", 0)
                        }
                except Exception as e:
                    logger.debug(f"Queue {queue_name} not found or inaccessible: {e}")
                    queue_sizes[queue_name] = {"error": str(e)}

            # Don't call close() - NATS client doesn't have this method
            # The connection will be cleaned up automatically

            return {
                "status": "healthy",
                "message": "NATS connection successful",
                "url": config.nats_url,
                "queue_sizes": queue_sizes
            }

        except Exception as e:
            logger.warning(f"NATS connection failed: {e}")
            return {
                "status": "degraded",
                "message": f"NATS connection error: {str(e)}",
                "url": config.nats_url
            }

    except Exception as e:
        logger.warning(f"NATS health check failed: {e}")
        return {
            "status": "degraded",
            "message": f"NATS not available: {str(e)}",
            "note": "This is expected if NATS is not configured"
        }


async def check_embedding_health() -> dict[str, Any]:
    """Check embedding service health by generating a test embedding."""
    try:
        from p8fs.config.embedding import get_default_embedding_provider
        from p8fs.services.llm import get_embedding_service

        # Get default embedding provider
        default_provider = get_default_embedding_provider()

        # Get embedding service
        embedding_service = get_embedding_service()

        # Test embedding generation with a simple phrase
        test_text = "health check"
        embeddings = embedding_service.encode_batch([test_text], default_provider)

        # Check if we got valid embeddings
        if embeddings and len(embeddings) > 0 and len(embeddings[0]) > 0:
            return {
                "status": "healthy",
                "message": "Embedding service generated embeddings successfully",
                "provider": default_provider,
                "vector_dimension": len(embeddings[0]),
                "test_text": test_text
            }
        else:
            return {
                "status": "unhealthy",
                "message": "Embedding service returned empty embeddings",
                "provider": default_provider
            }

    except Exception as e:
        logger.warning(f"Embedding health check failed: {e}", exc_info=True)
        return {
            "status": "degraded",
            "message": f"Embedding service not available: {str(e)}",
            "note": "This may indicate missing dependencies or configuration"
        }


def get_startup_health_data() -> dict[str, Any]:
    """Get the cached startup health check data."""
    return startup_health_data
