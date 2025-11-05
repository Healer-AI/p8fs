"""P8FS API Module - REST API, CLI, and MCP interfaces."""

from importlib.metadata import version, PackageNotFoundError


def _get_version() -> str:
    """Get version from package metadata."""
    try:
        return version("p8fs-api")
    except PackageNotFoundError:
        return "0.1.0"


__version__ = _get_version()