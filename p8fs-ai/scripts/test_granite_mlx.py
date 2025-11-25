#!/usr/bin/env python3
"""Test Granite with MLX on Apple Silicon."""

import sys
import time

try:
    from mlx_lm import load, generate

    print("=" * 80)
    print("QWEN 2.5 CODER 7B - MLX INFERENCE (Apple Silicon)")
    print("=" * 80)

    print("\nLoading model: mlx-community/Qwen2.5-Coder-7B-Instruct-4bit")
    print("This will download ~4GB on first run...")
    start = time.time()
    model, tokenizer = load("mlx-community/Qwen2.5-Coder-7B-Instruct-4bit")
    load_time = time.time() - start
    print(f"✓ Model loaded in {load_time:.1f}s\n")

    # Test 1: Simple completion
    print("=" * 80)
    print("TEST 1: Simple Completion")
    print("=" * 80)
    prompt1 = "Explain what semantic search is in one sentence:"
    print(f"Prompt: {prompt1}\n")

    start = time.time()
    response1 = generate(
        model, tokenizer,
        prompt=prompt1,
        max_tokens=100,
        verbose=True  # Shows tokens/sec
    )
    gen_time = time.time() - start
    print(f"\nGeneration time: {gen_time:.1f}s")
    print(f"Response: {response1}\n")

    # Test 2: REM query generation
    print("=" * 80)
    print("TEST 2: REM Query Generation")
    print("=" * 80)
    prompt2 = """You are a REM query generator. Convert natural language to REM queries.

REM Syntax:
- LOOKUP <key> - Find by key
- SEARCH "<text>" IN <table> - Semantic search
- SELECT ... FROM <table> WHERE ... - SQL query

User: Find resources about machine learning from last week

REM Query:"""

    print(f"Prompt: User: Find resources about machine learning from last week\n")

    start = time.time()
    response2 = generate(
        model, tokenizer,
        prompt=prompt2,
        max_tokens=128,
        verbose=True
    )
    gen_time = time.time() - start
    print(f"\nGeneration time: {gen_time:.1f}s")
    print(f"Response: {response2}\n")

    # Test 3: Structured output (edge affinity)
    print("=" * 80)
    print("TEST 3: Edge Affinity Scoring")
    print("=" * 80)
    prompt3 = """Score the semantic affinity between these two resources (0.0-1.0):

Resource 1: "Meeting notes about Q4 planning and budget allocation"
Resource 2: "Q3 financial review and budget analysis"

Return JSON:
{
  "affinity_score": <float>,
  "reason": "<explanation>"
}

Output:"""

    print("Scoring two resource descriptions...\n")

    start = time.time()
    response3 = generate(
        model, tokenizer,
        prompt=prompt3,
        max_tokens=150,
        verbose=True
    )
    gen_time = time.time() - start
    print(f"\nGeneration time: {gen_time:.1f}s")
    print(f"Response: {response3}\n")

    print("=" * 80)
    print("ALL TESTS COMPLETED SUCCESSFULLY ✓")
    print("=" * 80)
    print("\nMLX Performance Summary:")
    print("- Model: Qwen 2.5 Coder 7B (4-bit quantized)")
    print("- Memory: ~4-5GB")
    print("- Speed: Check 'tokens/sec' in verbose output above")
    print("- Platform: Apple Silicon optimized")
    print("\nNote: Granite 3.1 MLX version not yet available.")
    print("Qwen2.5-Coder is excellent for structured output and code generation.")

except ImportError as e:
    print("❌ MLX not installed")
    print("\nInstall with:")
    print("  cd p8fs-ai")
    print("  uv add mlx mlx-lm")
    print("\nOr use Ollama instead:")
    print("  brew install ollama")
    print("  ollama pull granite3.1-dense:8b")
    sys.exit(1)

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
