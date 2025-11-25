"""TiKV KV operations diagnostics."""

import time
import json
from p8fs.providers import get_provider

from ..models import DiagnosticResult, DiagnosticStatus


async def diagnose_tikv_kv_operations() -> DiagnosticResult:
    """Diagnostic for basic KV put/get operations."""
    start_time = time.time()

    try:
        provider = get_provider()
        kv = provider.kv

        test_key = "envdiag:healthcheck"
        test_value = {"status": "ok", "timestamp": time.time()}

        await kv.put(test_key, json.dumps(test_value), ttl_seconds=60)

        retrieved = await kv.get(test_key)
        if not retrieved:
            duration_ms = (time.time() - start_time) * 1000
            return DiagnosticResult(
                name="tikv_kv_operations",
                status=DiagnosticStatus.FAIL,
                message="KV get returned None after put",
                duration_ms=duration_ms
            )

        await kv.delete(test_key)

        duration_ms = (time.time() - start_time) * 1000
        return DiagnosticResult(
            name="tikv_kv_operations",
            status=DiagnosticStatus.PASS,
            message="KV put/get/delete operations successful",
            duration_ms=duration_ms
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return DiagnosticResult(
            name="tikv_kv_operations",
            status=DiagnosticStatus.FAIL,
            message=f"KV operations failed: {str(e)}",
            duration_ms=duration_ms
        )
