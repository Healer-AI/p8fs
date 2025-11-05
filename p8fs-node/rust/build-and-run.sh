#!/bin/bash

# Build and run script for p8fs-node

set -e

echo "🔨 Building p8fs-node Docker image..."

# Build the Docker image
docker build -t p8fs-node:latest .

echo "✅ Build complete!"

echo "🚀 Starting p8fs-node API server..."

# Run the container
docker run -d \
  --name p8fs-node-api \
  --rm \
  -p 3000:3000 \
  -e EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2 \
  -e EMBEDDING_DIMENSIONS=384 \
  -e RUST_LOG=info \
  p8fs-node:latest

echo "⏳ Waiting for server to start..."
sleep 30

echo "🧪 Testing API..."

# Test the API
curl -X POST http://localhost:3000/api/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": ["Hello world", "Test sentence"],
    "model": "all-MiniLM-L6-v2",
    "encoding_format": "float"
  }' | jq '.' || echo "⚠️  jq not installed, showing raw response"

echo -e "\n✅ API is running!"
echo "📊 Container status:"
docker ps | grep p8fs-node

echo -e "\n🔗 API endpoints:"
echo "  - Embeddings: http://localhost:3000/api/v1/embeddings"
echo "  - Content: http://localhost:3000/api/v1/content/process"
echo "  - Health: http://localhost:3000/"

echo -e "\n🛑 To stop:"
echo "  docker stop p8fs-node-api"