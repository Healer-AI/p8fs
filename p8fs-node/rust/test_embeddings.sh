#!/bin/bash

# Test script for p8fs-node embedding API

echo "🧪 Testing p8fs-node embedding API..."

# Start the server in the background
echo "🚀 Starting server..."
cd "$(dirname "$0")/p8fs-node"
cargo run &
SERVER_PID=$!

# Wait for server to start
sleep 10

echo "📡 Testing embedding API..."

# Test OpenAI-compatible embedding request
curl -X POST http://localhost:3000/api/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": ["Hello world", "This is a test sentence"],
    "model": "all-MiniLM-L6-v2",
    "encoding_format": "float"
  }' | jq '.'

# Test single input
echo -e "\n📝 Testing single input..."
curl -X POST http://localhost:3000/api/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": ["The quick brown fox jumps over the lazy dog"],
    "model": "all-MiniLM-L6-v2"
  }' | jq '.data[0].embedding | length'

# Test health endpoint
echo -e "\n💚 Testing health endpoint..."
curl -X GET http://localhost:3000/

echo -e "\n🛑 Stopping server..."
kill $SERVER_PID

echo "✅ Tests completed!"