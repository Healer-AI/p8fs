"""OpenTelemetry observability setup for P8FS API.

This module provides centralized configuration for OpenTelemetry instrumentation:
- Auto-instrumentation for FastAPI HTTP endpoints
- Auto-instrumentation for HTTPX client requests
- Manual instrumentation decorators for agents and custom code
- OTLP exporter configuration for sending to collector

The collector is running at: otel-collector.observability.svc.cluster.local:4317
"""

import os
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from . import __version__

logger = get_logger(__name__)

# Global tracer instance
tracer = trace.get_tracer(__name__)


def setup_observability(service_name: str | None = None) -> None:
    """Configure OpenTelemetry instrumentation for the service.

    Uses centralized configuration from p8fs_cluster.config.settings for all OTEL settings.

    Sets up:
    1. Resource with service name and version
    2. OTLP exporter to send traces to collector
    3. Trace provider with batch processor
    4. HTTP client instrumentation
    5. Logging instrumentation

    Args:
        service_name: Name of the service for traces (default: from config.otel_service_name)
    """
    try:
        # Check if tracing is enabled
        if not config.tracing_enabled:
            logger.info("OpenTelemetry tracing disabled via config")
            return

        # Use service name from config if not provided
        service_name = service_name or config.otel_service_name

        # Check if we're running in Kubernetes or locally
        if not os.path.exists("/var/run/secrets/kubernetes.io"):
            # Local development - disabled by default
            # Users must explicitly set OTEL_EXPORTER_OTLP_ENDPOINT to enable
            if "OTEL_EXPORTER_OTLP_ENDPOINT" not in os.environ:
                logger.info("Local development detected, OpenTelemetry disabled by default")
                logger.info("To enable tracing locally:")
                logger.info("  1. Port forward: kubectl port-forward -n observability svc/otel-collector 4317:4317")
                logger.info("  2. Set env var: export OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317")
                return

        # Get endpoint from centralized config
        otlp_endpoint = config.otel_exporter_otlp_endpoint

        # Create resource with service metadata from centralized config
        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_VERSION: config.otel_service_version,
            "deployment.environment": config.deployment_environment,
            "service.namespace": config.otel_service_namespace,
            "debug.mode": str(config.debug)
        })

        # Create OTLP exporter with settings from centralized config
        otlp_exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=config.otel_insecure
        )

        # Create trace provider with batch processor
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(processor)

        # Set as global trace provider
        trace.set_tracer_provider(provider)

        # Auto-instrument HTTPX client
        HTTPXClientInstrumentor().instrument()

        # Auto-instrument logging
        LoggingInstrumentor().instrument()

        logger.info(
            "OpenTelemetry initialized",
            service=service_name,
            version=config.otel_service_version,
            namespace=config.otel_service_namespace,
            otlp_endpoint=otlp_endpoint,
            environment=config.deployment_environment
        )

    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry: {e}", exc_info=True)
        # Don't fail startup if observability setup fails
        logger.warning("Continuing without OpenTelemetry instrumentation")


def instrument_fastapi(app) -> None:
    """Instrument FastAPI application with OpenTelemetry.

    This should be called after the FastAPI app is created but before it starts serving.
    Automatically traces all HTTP endpoints with:
    - HTTP method, route, status code
    - Request duration
    - Exception details

    Excludes health check endpoints to reduce trace volume:
    - /health, /ready - Kubernetes probes
    - /metrics - Prometheus metrics

    Args:
        app: FastAPI application instance
    """
    try:
        excluded_urls = "/health,/ready,/metrics"
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls=excluded_urls
        )
        logger.info(
            "FastAPI auto-instrumentation enabled",
            excluded_urls=excluded_urls
        )
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI: {e}", exc_info=True)


def trace_agent(agent_name: str | None = None):
    """Decorator to trace agent execution.

    Use this decorator on agent methods to create spans for agent operations.
    The span will include:
    - Agent name and method
    - Input parameters
    - Execution time
    - Any exceptions

    Args:
        agent_name: Optional custom agent name (default: uses class name)

    Example:
        @trace_agent("DreamAgent")
        async def analyze(self, content: str) -> dict:
            # Agent logic here
            return result
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get agent name from decorator arg or class name
            name = agent_name or (args[0].__class__.__name__ if args else func.__name__)
            span_name = f"agent.{name}.{func.__name__}"

            with tracer.start_as_current_span(span_name) as span:
                # Add agent metadata
                span.set_attribute("agent.name", name)
                span.set_attribute("agent.method", func.__name__)

                # Add input parameter count
                span.set_attribute("agent.args_count", len(args))
                span.set_attribute("agent.kwargs_count", len(kwargs))

                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("agent.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("agent.status", "error")
                    span.record_exception(e)
                    raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            name = agent_name or (args[0].__class__.__name__ if args else func.__name__)
            span_name = f"agent.{name}.{func.__name__}"

            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("agent.name", name)
                span.set_attribute("agent.method", func.__name__)
                span.set_attribute("agent.args_count", len(args))
                span.set_attribute("agent.kwargs_count", len(kwargs))

                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("agent.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("agent.status", "error")
                    span.record_exception(e)
                    raise

        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


@contextmanager
def trace_operation(operation_name: str, **attributes):
    """Context manager for tracing custom operations.

    Use this for tracing specific operations that aren't agents or HTTP requests.

    Args:
        operation_name: Name of the operation (will be prefixed with "operation.")
        **attributes: Additional attributes to add to the span

    Example:
        with trace_operation("embedding_generation", model="text-embedding-3-small"):
            embeddings = await generate_embeddings(text)
    """
    span_name = f"operation.{operation_name}"

    with tracer.start_as_current_span(span_name) as span:
        # Add custom attributes
        for key, value in attributes.items():
            span.set_attribute(key, str(value))

        try:
            yield span
            span.set_attribute("status", "success")
        except Exception as e:
            span.set_attribute("status", "error")
            span.record_exception(e)
            raise


def trace_llm_call(
    model: str,
    provider: str,
    temperature: float | None = None,
    max_tokens: int | None = None
):
    """Decorator to trace LLM API calls.

    Specialized tracing for LLM interactions with model-specific metadata.

    Args:
        model: Model name (e.g., "gpt-4", "claude-sonnet-4")
        provider: Provider name (e.g., "openai", "anthropic")
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate

    Example:
        @trace_llm_call(model="gpt-4", provider="openai", temperature=0.7)
        async def generate_response(prompt: str) -> str:
            return await client.chat.completions.create(...)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            span_name = f"llm.{provider}.{model}"

            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("llm.model", model)
                span.set_attribute("llm.provider", provider)
                if temperature is not None:
                    span.set_attribute("llm.temperature", temperature)
                if max_tokens is not None:
                    span.set_attribute("llm.max_tokens", max_tokens)

                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("llm.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("llm.status", "error")
                    span.record_exception(e)
                    raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            span_name = f"llm.{provider}.{model}"

            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("llm.model", model)
                span.set_attribute("llm.provider", provider)
                if temperature is not None:
                    span.set_attribute("llm.temperature", temperature)
                if max_tokens is not None:
                    span.set_attribute("llm.max_tokens", max_tokens)

                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("llm.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("llm.status", "error")
                    span.record_exception(e)
                    raise

        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def get_current_trace_id() -> str | None:
    """Get the current trace ID for correlation with logs.

    Returns:
        Hex string trace ID or None if no active span
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        return format(span.get_span_context().trace_id, "032x")
    return None


def get_current_span_id() -> str | None:
    """Get the current span ID for correlation with logs.

    Returns:
        Hex string span ID or None if no active span
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        return format(span.get_span_context().span_id, "016x")
    return None
