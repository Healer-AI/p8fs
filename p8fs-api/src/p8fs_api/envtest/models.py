"""Models for environment diagnostic results."""

from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class DiagnosticStatus(str, Enum):
    """Diagnostic execution status."""
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


class DiagnosticResult(BaseModel):
    """Result of a single environment diagnostic."""

    name: str = Field(..., description="Diagnostic name")
    status: DiagnosticStatus = Field(..., description="Diagnostic status")
    message: str = Field(..., description="Status message or error details")
    duration_ms: float = Field(..., description="Diagnostic duration in milliseconds")
    metadata: dict = Field(default_factory=dict, description="Additional diagnostic metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EnvDiagnosticReport(BaseModel):
    """Complete environment diagnostic report."""

    environment: str = Field(..., description="Environment name (dev/staging/production)")
    total_diagnostics: int = Field(..., description="Total number of diagnostics")
    passed: int = Field(..., description="Number of passed diagnostics")
    failed: int = Field(..., description="Number of failed diagnostics")
    skipped: int = Field(..., description="Number of skipped diagnostics")
    errors: int = Field(..., description="Number of errored diagnostics")
    duration_ms: float = Field(..., description="Total duration in milliseconds")
    results: list[DiagnosticResult] = Field(..., description="Individual diagnostic results")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def success(self) -> bool:
        """Overall success status (all diagnostics passed)."""
        return self.failed == 0 and self.errors == 0
