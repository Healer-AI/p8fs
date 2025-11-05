"""Configuration validation diagnostics."""

import time
from p8fs_cluster.config.settings import config

from ..models import DiagnosticResult, DiagnosticStatus


async def diagnose_config_loaded() -> DiagnosticResult:
    """Verify that configuration is properly loaded."""
    start_time = time.time()

    try:
        env = config.environment
        provider = config.storage_provider

        duration_ms = (time.time() - start_time) * 1000
        return DiagnosticResult(
            name="config_loaded",
            status=DiagnosticStatus.PASS,
            message=f"Config loaded: env={env}, provider={provider}",
            duration_ms=duration_ms
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return DiagnosticResult(
            name="config_loaded",
            status=DiagnosticStatus.ERROR,
            message=f"Config error: {str(e)}",
            duration_ms=duration_ms
        )
