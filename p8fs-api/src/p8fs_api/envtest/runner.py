"""Environment diagnostic runner."""

import time
from typing import List, Callable, Awaitable
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from .models import DiagnosticResult, DiagnosticStatus, EnvDiagnosticReport

logger = get_logger(__name__)


class EnvDiagnosticRunner:
    """Runs environment diagnostics and collects results."""

    def __init__(self):
        self.diagnostics: List[Callable[[], Awaitable[DiagnosticResult]]] = []
        self._register_diagnostics()

    def _register_diagnostics(self):
        """Register all available diagnostics."""
        from .diagnostics import tidb, tikv, config as config_diagnostic

        self.diagnostics.extend([
            config_diagnostic.diagnose_config_loaded,
            tidb.diagnose_tidb_connectivity,
            tikv.diagnose_tikv_kv_operations,
        ])

        if config.storage_provider == "postgresql":
            from .diagnostics import postgres
            self.diagnostics.append(postgres.diagnose_postgresql_connectivity)

    async def run_all(self) -> EnvDiagnosticReport:
        """Run all registered diagnostics and generate report."""
        logger.info(f"Running {len(self.diagnostics)} environment diagnostics...")
        start_time = time.time()

        results = []
        for diagnostic_func in self.diagnostics:
            try:
                result = await diagnostic_func()
                results.append(result)
                status_icon = "✓" if result.status == DiagnosticStatus.PASS else "✗"
                logger.info(f"{status_icon} {result.name}: {result.message}")
            except Exception as e:
                logger.error(f"Diagnostic execution failed: {diagnostic_func.__name__}: {e}")
                results.append(DiagnosticResult(
                    name=diagnostic_func.__name__,
                    status=DiagnosticStatus.ERROR,
                    message=f"Diagnostic execution failed: {str(e)}",
                    duration_ms=0
                ))

        duration_ms = (time.time() - start_time) * 1000

        passed = sum(1 for r in results if r.status == DiagnosticStatus.PASS)
        failed = sum(1 for r in results if r.status == DiagnosticStatus.FAIL)
        skipped = sum(1 for r in results if r.status == DiagnosticStatus.SKIP)
        errors = sum(1 for r in results if r.status == DiagnosticStatus.ERROR)

        report = EnvDiagnosticReport(
            environment=config.environment,
            total_diagnostics=len(results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            duration_ms=duration_ms,
            results=results
        )

        logger.info(
            f"Diagnostic Results: {passed} passed, {failed} failed, "
            f"{skipped} skipped, {errors} errors ({duration_ms:.0f}ms)"
        )

        return report
