#!/bin/bash
# Run OpenAI integration tests with proper environment setup

echo "🚀 Running OpenAI Integration Tests"
echo "=================================="

# Check if OpenAI key is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Error: OPENAI_API_KEY environment variable not set"
    echo "Please set: export OPENAI_API_KEY=your-api-key"
    exit 1
fi

echo "✅ OpenAI API key found"

# Set storage provider
export P8FS_STORAGE_PROVIDER=${P8FS_STORAGE_PROVIDER:-tidb}
export P8FS_TIDB_HOST=${P8FS_TIDB_HOST:-localhost}
export P8FS_TIDB_PORT=${P8FS_TIDB_PORT:-4000}
export P8FS_TIDB_USER=${P8FS_TIDB_USER:-root}
export P8FS_TIDB_PASSWORD=${P8FS_TIDB_PASSWORD:-}
export P8FS_TIDB_DATABASE=${P8FS_TIDB_DATABASE:-public}

echo "📦 Storage Provider: $P8FS_STORAGE_PROVIDER"
echo "🗄️  Database: $P8FS_TIDB_DATABASE"

# Run tests
echo ""
echo "Running integration tests..."
echo ""

# Change to project root
cd /Users/sirsh/code/p8fs-modules/p8fs

# Run with pytest
python -m pytest tests/integration/test_dreaming_openai_integration.py -v -s

echo ""
echo "✨ Integration tests complete!"