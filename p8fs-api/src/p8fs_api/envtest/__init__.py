"""Environment diagnostics module for cluster validation.

This module provides diagnostics that validate connectivity and
functionality of services in the cluster environment. Diagnostics can be run:

1. Via CLI: uv run python -m p8fs_api.cli.envdiag
2. Via API endpoint: GET /envdiag (when P8FS_ENVDIAG_ENABLED=true)
3. In test pod: kubectl apply -f manifests/envdiag-pod.yaml

Use cases:
- Pre-deployment validation
- Troubleshooting cluster connectivity issues
- Verifying configuration after changes
- Testing TiKV gRPC operations from within cluster
"""

from .runner import EnvDiagnosticRunner
from .models import DiagnosticResult, DiagnosticStatus

__all__ = ["EnvDiagnosticRunner", "DiagnosticResult", "DiagnosticStatus"]
