"""OpenTelemetry instrumentation for P8FS workers.

Provides tracing and metrics for:
- Tiered router queue management
- Storage workers processing files
- Distributed tracing across NATS queues

Key feature: Trace context propagation through NATS messages enables
end-to-end tracing of file uploads through the entire pipeline.
"""

import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

_tracer = None
_meter = None
_propagator = TraceContextTextMapPropagator()


def setup_worker_observability(service_name: str) -> None:
    """Set up OpenTelemetry for workers with tracing and metrics.

    Args:
        service_name: Worker service name (e.g., "p8fs-tiered-router", "p8fs-storage-worker-small")
    """
    global _tracer, _meter

    try:
        if not config.tracing_enabled:
            logger.info("OpenTelemetry disabled via config")
            return

        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_VERSION: "1.0.0",
            "deployment.environment": config.deployment_environment,
            "service.namespace": "p8fs-workers",
        })

        otlp_trace_exporter = OTLPSpanExporter(
            endpoint=config.otel_exporter_otlp_endpoint,
            insecure=config.otel_insecure
        )

        trace_provider = TracerProvider(resource=resource)
        trace_processor = BatchSpanProcessor(otlp_trace_exporter)
        trace_provider.add_span_processor(trace_processor)
        trace.set_tracer_provider(trace_provider)
        _tracer = trace.get_tracer(__name__)

        otlp_metric_exporter = OTLPMetricExporter(
            endpoint=config.otel_exporter_otlp_endpoint,
            insecure=config.otel_insecure
        )

        metric_reader = PeriodicExportingMetricReader(
            otlp_metric_exporter,
            export_interval_millis=config.otel_metric_export_interval
        )

        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader]
        )
        metrics.set_meter_provider(meter_provider)
        _meter = metrics.get_meter(__name__)

        logger.info(
            f"OpenTelemetry initialized for {service_name}",
            service=service_name,
            otlp_endpoint=config.otel_exporter_otlp_endpoint
        )

    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry: {e}", exc_info=True)
        logger.warning("Continuing without OpenTelemetry instrumentation")


def get_tracer():
    """Get the global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer(__name__)
    return _tracer


def get_meter():
    """Get the global meter instance."""
    global _meter
    if _meter is None:
        _meter = metrics.get_meter(__name__)
    return _meter


def inject_trace_context(headers: dict[str, str] | None = None) -> dict[str, str]:
    """Inject current trace context into message headers for propagation.

    This enables distributed tracing across NATS queues - the downstream
    service can extract the context and continue the same trace.

    Args:
        headers: Existing headers dict or None

    Returns:
        Headers dict with trace context injected
    """
    if headers is None:
        headers = {}

    _propagator.inject(headers)
    return headers


def extract_trace_context(headers: dict[str, str] | None) -> Any:
    """Extract trace context from message headers.

    Args:
        headers: Message headers containing trace context

    Returns:
        Extracted trace context
    """
    if headers is None:
        return None

    return _propagator.extract(headers)


@contextmanager
def continue_trace(headers: dict[str, str] | None, span_name: str, **attributes):
    """Continue a distributed trace from message headers.

    Args:
        headers: Message headers containing trace context
        span_name: Name for the new span
        **attributes: Additional span attributes
    """
    tracer = get_tracer()
    ctx = extract_trace_context(headers)

    with tracer.start_as_current_span(span_name, context=ctx) as span:
        for key, value in attributes.items():
            span.set_attribute(key, str(value))

        try:
            yield span
            span.set_attribute("status", "success")
        except Exception as e:
            span.set_attribute("status", "error")
            span.record_exception(e)
            raise


class RouterMetrics:
    """Metrics for tiered router operations."""

    def __init__(self):
        meter = get_meter()

        self.nats_queue_size = meter.create_observable_gauge(
            name="nats.queue.size",
            description="Number of messages in NATS queue",
            unit="messages"
        )

        self.sends_queue_size = meter.create_observable_gauge(
            name="router.sends_queue.size",
            description="Number of pending sends in router",
            unit="messages"
        )

        self.messages_routed = meter.create_counter(
            name="router.messages.routed",
            description="Total messages routed to workers",
            unit="messages"
        )

        self.routing_errors = meter.create_counter(
            name="router.errors",
            description="Total routing errors",
            unit="errors"
        )

        self.routing_duration = meter.create_histogram(
            name="router.routing.duration",
            description="Time to route a message",
            unit="seconds"
        )


class WorkerMetrics:
    """Metrics for storage worker operations."""

    def __init__(self):
        meter = get_meter()

        self.files_processed = meter.create_counter(
            name="worker.files.processed",
            description="Total files processed",
            unit="files"
        )

        self.processing_errors = meter.create_counter(
            name="worker.processing.errors",
            description="Total processing errors",
            unit="errors"
        )

        self.processing_duration = meter.create_histogram(
            name="worker.processing.duration",
            description="Time to process a file",
            unit="seconds"
        )

        self.file_size_processed = meter.create_histogram(
            name="worker.file_size.processed",
            description="Size of files processed",
            unit="bytes"
        )


def trace_routing_operation(operation_name: str):
    """Decorator to trace router operations."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()
            span_name = f"router.{operation_name}"

            with tracer.start_as_current_span(span_name) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("status", "error")
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator


def trace_worker_operation(queue_name: str, **attributes):
    """Decorator to trace worker operations with context propagation."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, msg, *args, **kwargs):
            headers = msg.headers if hasattr(msg, 'headers') else None

            with continue_trace(
                headers,
                f"worker.{queue_name}.process",
                queue=queue_name,
                **attributes
            ) as span:
                start_time = time.time()

                try:
                    result = await func(self, msg, *args, **kwargs)
                    duration = time.time() - start_time
                    span.set_attribute("processing.duration", duration)
                    span.set_attribute("status", "success")
                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    span.set_attribute("processing.duration", duration)
                    span.set_attribute("status", "error")
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator


@contextmanager
def trace_file_processing(
    file_name: str,
    file_size: int,
    tenant_id: str,
    queue_name: str
):
    """Context manager for tracing file processing operations."""
    tracer = get_tracer()

    with tracer.start_as_current_span("file.process") as span:
        span.set_attribute("file.name", file_name)
        span.set_attribute("file.size", file_size)
        span.set_attribute("file.size_mb", file_size / (1024 * 1024))
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("queue.name", queue_name)

        start_time = time.time()

        try:
            yield span
            duration = time.time() - start_time
            span.set_attribute("processing.duration", duration)
            span.set_attribute("status", "success")

        except Exception as e:
            duration = time.time() - start_time
            span.set_attribute("processing.duration", duration)
            span.set_attribute("status", "error")
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            span.record_exception(e)
            raise
