"""
OpenInference span kinds for Phoenix integration.

These span kinds help categorize operations in Phoenix UI for better observability.
"""

from enum import Enum
from typing import Optional
from opentelemetry.trace import Span


class OpenInferenceSpanKind(str, Enum):
    """
    Span kinds following OpenInference semantic conventions for LLM tracing.

    These are used by Phoenix and other observability tools to categorize spans.
    """
    AGENT = "AGENT"
    LLM = "LLM"
    TOOL = "TOOL"
    CHAIN = "CHAIN"
    RETRIEVER = "RETRIEVER"
    EMBEDDING = "EMBEDDING"
    RERANKER = "RERANKER"


def set_span_kind(span: Span, kind: OpenInferenceSpanKind) -> None:
    """
    Set OpenInference span kind attribute.

    Args:
        span: The span to annotate
        kind: OpenInference span kind
    """
    if not span:
        return

    span.set_attribute("openinference.span.kind", kind.value)
