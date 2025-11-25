"""
OpenTelemetry utility functions for P8FS.

Provides helper functions for instrumenting LLM calls, tool executions,
and agent workflows following GenAI semantic conventions.

All operations are no-ops if OTEL is disabled or no active span exists.
"""

from typing import Optional, Any
import json

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind
from opentelemetry.trace.status import Status, StatusCode


def get_tracer(name: str = __name__):
    """Get a tracer instance."""
    return trace.get_tracer(name)


def get_current_span() -> Optional[Span]:
    """Get the current active span."""
    span = trace.get_current_span()
    if not span or not span.get_span_context().is_valid:
        return None
    return span


def set_llm_attributes(
    span: Span,
    model: str,
    provider: str,
) -> None:
    """
    Set standard LLM attributes on a span.

    Args:
        span: The span to annotate
        model: Model identifier (e.g., "gpt-4o", "claude-sonnet-4")
        provider: Provider name (e.g., "openai", "anthropic")
    """
    if not span:
        return

    # GenAI semantic conventions
    span.set_attribute("gen_ai.operation.name", "chat")
    span.set_attribute("gen_ai.provider.name", provider)
    span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("gen_ai.response.model", model)


def set_generation_attributes(
    span: Span,
    prompt: Optional[str] = None,
    completion: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    finish_reason: Optional[str] = None,
    is_streaming: bool = False,
) -> None:
    """
    Annotate span with LLM generation metadata.

    Args:
        span: The span to annotate
        prompt: Input prompt
        completion: Model output
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens
        total_tokens: Total tokens
        temperature: Sampling temperature
        max_tokens: Maximum output tokens
        finish_reason: Reason generation stopped
        is_streaming: Whether streaming was used
    """
    if not span:
        return

    if prompt:
        span.set_attribute("input.value", prompt)

    if completion:
        span.set_attribute("output.value", completion)

    if input_tokens is not None:
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)

    if output_tokens is not None:
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)

    if total_tokens is not None:
        span.set_attribute("gen_ai.usage.total_tokens", total_tokens)
    elif input_tokens is not None and output_tokens is not None:
        span.set_attribute("gen_ai.usage.total_tokens", input_tokens + output_tokens)

    if temperature is not None:
        span.set_attribute("gen_ai.request.temperature", temperature)

    if max_tokens is not None:
        span.set_attribute("gen_ai.request.max_tokens", max_tokens)

    if finish_reason:
        span.set_attribute("gen_ai.response.finish_reason", finish_reason)

    span.set_attribute("gen_ai.is_streaming", is_streaming)


def set_agent_attributes(
    span: Span,
    agent_name: Optional[str] = None,
    agent_type: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """
    Annotate span with agent-specific metadata.

    Args:
        span: The span to annotate
        agent_name: Name of the agent
        agent_type: Type/category of agent
        user_id: User identifier
        session_id: Session identifier
    """
    if not span:
        return

    if agent_name:
        span.set_attribute("agent.name", agent_name)

    if agent_type:
        span.set_attribute("agent.type", agent_type)

    if user_id:
        span.set_attribute("user.id", user_id)

    if session_id:
        span.set_attribute("session.id", session_id)


def add_span_event(
    span: Span,
    event_name: str,
    attributes: Optional[dict] = None,
) -> None:
    """
    Add a generic event to the span.

    Args:
        span: The span to annotate
        event_name: Name of the event
        attributes: Optional event attributes
    """
    if not span:
        return

    span.add_event(event_name, attributes=attributes or {})


def mark_span_as_error(span: Span, error_message: str) -> None:
    """
    Mark span as error.

    Args:
        span: The span to mark
        error_message: Error description
    """
    if not span:
        return

    span.set_status(Status(StatusCode.ERROR, error_message))


def get_current_span_id_as_hex() -> Optional[str]:
    """
    Get the current span ID in hexadecimal format.

    Returns:
        16-character hex string representing the span ID, or None if no valid span
    """
    span = get_current_span()
    if not span:
        return None

    span_id = span.get_span_context().span_id
    return format(span_id, '016x')


def get_current_trace_id_as_hex() -> Optional[str]:
    """
    Get the current trace ID in hexadecimal format.

    Returns:
        32-character hex string representing the trace ID, or None if no valid span
    """
    span = get_current_span()
    if not span:
        return None

    trace_id = span.get_span_context().trace_id
    return format(trace_id, '032x')
