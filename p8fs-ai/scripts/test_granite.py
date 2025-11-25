#!/usr/bin/env python3
"""Test script for Granite 3.1 8B model."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from p8fs_ai.models.loader import load_model, generate_text


def test_rem_query_generation():
    """Test REM query generation capability."""

    prompt = """You are a REM query generator. Given a natural language query, generate a REM query.

REM Query Syntax:
- LOOKUP <key> - Find entity by key
- SEARCH "<query text>" IN <table> - Semantic search
- SELECT ... FROM <table> WHERE ... - SQL query
- FUZZY '<text>' IN <table> THRESHOLD <0.0-1.0> - Fuzzy search

User: Find resources about machine learning from last week

REM Query:"""

    print("=" * 80)
    print("TEST: REM Query Generation")
    print("=" * 80)
    print(f"\nPrompt:\n{prompt}\n")

    model, tokenizer = load_model(
        "ibm-granite/granite-3.1-8b-instruct",
        quantization="bf16"  # Use bf16 on macOS (4bit requires bitsandbytes/Linux)
    )

    output = generate_text(
        model,
        tokenizer,
        prompt,
        max_new_tokens=128,
        temperature=0.1
    )

    print(f"Generated Output:\n{output}\n")
    print("=" * 80)


def test_simple_completion():
    """Test simple text completion."""

    prompt = "Explain what a semantic search is in one sentence:"

    print("\n" + "=" * 80)
    print("TEST: Simple Completion")
    print("=" * 80)
    print(f"\nPrompt: {prompt}\n")

    model, tokenizer = load_model(
        "ibm-granite/granite-3.1-8b-instruct",
        quantization="bf16"  # Use bf16 on macOS (4bit requires bitsandbytes/Linux)
    )

    output = generate_text(
        model,
        tokenizer,
        prompt,
        max_new_tokens=64,
        temperature=0.7
    )

    print(f"Generated Output:\n{output}\n")
    print("=" * 80)


def test_structured_output():
    """Test structured JSON output."""

    prompt = """Given two resources, score their affinity (0.0-1.0) based on semantic similarity.

Resource 1: "Meeting notes about Q4 planning and budget allocation for the engineering team"
Resource 2: "Q3 financial review and budget analysis"

Output JSON format:
{
  "affinity_score": <float>,
  "reason": "<explanation>"
}

Output:"""

    print("\n" + "=" * 80)
    print("TEST: Structured Output (Edge Affinity)")
    print("=" * 80)
    print(f"\nPrompt:\n{prompt}\n")

    model, tokenizer = load_model(
        "ibm-granite/granite-3.1-8b-instruct",
        quantization="bf16"  # Use bf16 on macOS (4bit requires bitsandbytes/Linux)
    )

    output = generate_text(
        model,
        tokenizer,
        prompt,
        max_new_tokens=128,
        temperature=0.1
    )

    print(f"Generated Output:\n{output}\n")
    print("=" * 80)


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("GRANITE 3.1 8B INSTRUCT - MODEL TESTING")
    print("=" * 80 + "\n")

    # Run tests
    try:
        test_simple_completion()
        test_rem_query_generation()
        test_structured_output()

        print("\n" + "=" * 80)
        print("ALL TESTS COMPLETED")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
