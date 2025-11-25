#!/bin/bash
# P8FS API startup script with proper environment setup

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
P8FS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Set up Python path for all modules
export PYTHONPATH="$SCRIPT_DIR/src:$P8FS_ROOT/p8fs-cluster/src:$P8FS_ROOT/p8fs-core/src:$P8FS_ROOT/p8fs-node/src:$P8FS_ROOT/p8fs-auth/src:$PYTHONPATH"

# Set development mode
export P8FS_API_DEBUG=true
export P8FS_API_RELOAD=true

echo "🔧 P8FS API Development Server"
echo "📍 PYTHONPATH configured for all modules"
echo "🚀 Starting API server on port 8000..."
echo ""

# Run with uv
cd "$SCRIPT_DIR"
exec uv run python main.py