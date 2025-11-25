#!/bin/bash

# Run all tests for p8fs-node Rust implementation

echo "🧪 Running p8fs-node tests..."

cd "$(dirname "$0")"

echo "📦 Running unit tests..."
cargo test --lib --verbose

echo "🔧 Running integration tests..."
cargo test --test '*' --verbose

echo "🚀 Running all tests (including ignored ones)..."
cargo test --verbose -- --ignored

echo "✅ All tests completed!"