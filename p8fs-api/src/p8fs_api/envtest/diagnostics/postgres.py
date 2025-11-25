"""PostgreSQL connectivity diagnostics."""

import time
from p8fs_cluster.config.settings import config

from ..models import DiagnosticResult, DiagnosticStatus


async def diagnose_postgresql_connectivity() -> DiagnosticResult:
    """Verify PostgreSQL connection."""
    start_time = time.time()

    try:
        import psycopg2

        conn = psycopg2.connect(
            host=config.pg_host,
            port=config.pg_port,
            user=config.pg_user,
            password=config.pg_password,
            database=config.pg_database,
            connect_timeout=5
        )
        conn.close()

        duration_ms = (time.time() - start_time) * 1000
        return DiagnosticResult(
            name="postgresql_connectivity",
            status=DiagnosticStatus.PASS,
            message=f"Connected to PostgreSQL at {config.pg_host}:{config.pg_port}",
            duration_ms=duration_ms
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return DiagnosticResult(
            name="postgresql_connectivity",
            status=DiagnosticStatus.FAIL,
            message=f"PostgreSQL connection failed: {str(e)}",
            duration_ms=duration_ms
        )
