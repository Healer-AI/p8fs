"""P8FS API module entry point.

   #lsof -ti :8001 | xargs kill -9
   P8FS_DEBUG=true uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8001
   http://localhost:8001/auth/qr-login
      
"""

import argparse
import os
from pathlib import Path


def setup_environment():
    """Set up Python path for cross-module imports."""
    modules_root = Path(__file__).parent.parent.parent.parent
    if str(modules_root) not in os.environ.get("PYTHONPATH", ""):
        pythonpath = os.environ.get("PYTHONPATH", "")
        new_paths = [
            str(modules_root / "p8fs-cluster" / "src"),
            str(modules_root / "p8fs" / "src"),
            str(modules_root / "p8fs-node" / "src"),
            str(modules_root / "p8fs-auth" / "src"),
        ]
        for path in new_paths:
            if Path(path).exists() and path not in pythonpath:
                pythonpath = f"{path}:{pythonpath}" if pythonpath else path
        os.environ["PYTHONPATH"] = pythonpath


def main():
    """Run the P8FS API server."""
    parser = argparse.ArgumentParser(description="P8FS API Server")
    parser.add_argument(
        "--host",
        default=os.environ.get("P8FS_API_HOST", "0.0.0.0"),
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("P8FS_API_PORT", "8000")),
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development"
    )
    parser.add_argument(
        "--workers", type=int, default=1, help="Number of worker processes (default: 1)"
    )

    args = parser.parse_args()

    if args.reload:
        # Use uvicorn with reload - must use module path string
        import uvicorn

        uvicorn.run(
            "p8fs_api.main:app",
            host=args.host,
            port=args.port,
            reload=True,
            log_level="info",
        )
    else:
        # Production mode - import app and run directly
        setup_environment()
        import uvicorn

        from .main import app

        uvicorn.run(
            app, host=args.host, port=args.port, workers=args.workers, log_level="info"
        )


if __name__ == "__main__":
    main()
