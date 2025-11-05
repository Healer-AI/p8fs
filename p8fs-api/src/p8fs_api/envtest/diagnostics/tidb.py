"""TiDB connectivity diagnostics."""

import time
from p8fs_cluster.config.settings import config

from ..models import DiagnosticResult, DiagnosticStatus


async def diagnose_tidb_connectivity() -> DiagnosticResult:
    """Verify TiDB connection."""
    start_time = time.time()

    try:
        import pymysql

        conn = pymysql.connect(
            host=config.tidb_host,
            port=config.tidb_port,
            user=config.tidb_user,
            database=config.tidb_database,
            connect_timeout=5
        )
        conn.close()

        duration_ms = (time.time() - start_time) * 1000
        return DiagnosticResult(
            name="tidb_connectivity",
            status=DiagnosticStatus.PASS,
            message=f"Connected to TiDB at {config.tidb_host}:{config.tidb_port}",
            duration_ms=duration_ms
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return DiagnosticResult(
            name="tidb_connectivity",
            status=DiagnosticStatus.FAIL,
            message=f"TiDB connection failed: {str(e)}",
            duration_ms=duration_ms
        )
