# CPU Inference Options for macOS

## Option 1: MLX (Apple Silicon - RECOMMENDED) ⭐

**MLX** is Apple's ML framework optimized for M-series chips. It's FAST and can run 8B models smoothly.

### Install MLX

```bash
cd p8fs-ai
uv add mlx mlx-lm
```

### Usage

```python
from mlx_lm import load, generate

# Load model with automatic quantization
model, tokenizer = load("mlx-community/granite-3.1-8b-instruct-4bit")

# Generate
prompt = "Explain semantic search in one sentence:"
response = generate(model, tokenizer, prompt=prompt, max_tokens=100)
print(response)
```

### Available Granite MLX Models

- `mlx-community/granite-3.1-8b-instruct-4bit` (2GB - FAST)
- `mlx-community/granite-3.1-8b-instruct-8bit` (4GB)
- `mlx-community/granite-3.1-8b-instruct` (16GB - full precision)

**Performance**: 20-50 tokens/sec on M1/M2/M3

## Option 2: llama.cpp (Cross-Platform)

**llama.cpp** provides highly optimized CPU inference with GGUF quantization.

### Install

```bash
# Install llama-cpp-python
cd p8fs-ai
uv add llama-cpp-python
```

### Usage

```python
from llama_cpp import Llama

# Load GGUF model
llm = Llama(
    model_path="models/granite-3.1-8b-instruct-Q4_K_M.gguf",
    n_ctx=2048,
    n_threads=8,
)

# Generate
output = llm("Explain semantic search:", max_tokens=100)
print(output['choices'][0]['text'])
```

### Download GGUF Models

```bash
# Using huggingface-cli
huggingface-cli download \
  TheBloke/granite-3.1-8b-instruct-GGUF \
  granite-3.1-8b-instruct-Q4_K_M.gguf \
  --local-dir models/
```

**Performance**: 10-30 tokens/sec on CPU

## Option 3: Smaller Models (Qwen 2.5 3B)

Use smaller models that run faster on CPU:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

# Load 3B model (much faster on CPU)
model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-3B-Instruct",
    torch_dtype=torch.float32,  # CPU works better with fp32
    device_map="cpu",
)
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-3B-Instruct")
```

**Performance**: 5-15 tokens/sec on CPU

## Option 4: Ollama (Easiest Setup)

**Ollama** provides the simplest way to run models locally.

### Install

```bash
# Install Ollama
brew install ollama

# Pull Granite model
ollama pull granite3.1-dense:8b

# Or pull smaller model
ollama pull qwen2.5:3b
```

### Usage

```bash
# Direct CLI
ollama run granite3.1-dense:8b "Explain semantic search"

# Python API
pip install ollama

python -c "
import ollama
response = ollama.chat(model='granite3.1-dense:8b', messages=[
  {'role': 'user', 'content': 'Explain semantic search'}
])
print(response['message']['content'])
"
```

**Performance**: 15-40 tokens/sec (optimized GGUF backend)

## Performance Comparison

| Method | Speed (tokens/sec) | Memory | Setup Difficulty | Recommendation |
|--------|-------------------|--------|------------------|----------------|
| **MLX 4-bit** | 20-50 | 2-4GB | Easy | ⭐ Best for Apple Silicon |
| **Ollama** | 15-40 | 4-8GB | Easiest | ⭐ Best for quick testing |
| **llama.cpp** | 10-30 | 4-8GB | Medium | Good cross-platform |
| **Transformers (3B)** | 5-15 | 6-12GB | Easy | Slower but familiar |
| **Transformers (8B bf16)** | 0.1-1 | 16GB+ | Easy | ❌ Too slow |

## Recommended Approach for p8fs-ai

### Phase 1: Quick Validation (Use Ollama)

```bash
# Install Ollama
brew install ollama

# Test Granite
ollama pull granite3.1-dense:8b
ollama run granite3.1-dense:8b "Generate REM query: Find resources about machine learning"
```

### Phase 2: Integration Testing (Use MLX)

Add MLX support to model loader:

```python
# src/p8fs_ai/models/loader_mlx.py
from mlx_lm import load, generate

def load_model_mlx(model_name: str, quantization: str = "4bit"):
    """Load model with MLX for Apple Silicon."""

    # Map to MLX community models
    mlx_models = {
        "granite-3.1-8b": "mlx-community/granite-3.1-8b-instruct-4bit",
        "qwen-2.5-7b": "mlx-community/Qwen2.5-7B-Instruct-4bit",
    }

    mlx_model = mlx_models.get(model_name)
    model, tokenizer = load(mlx_model)

    return model, tokenizer

def generate_mlx(model, tokenizer, prompt: str, max_tokens: int = 256):
    """Generate with MLX model."""
    return generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=max_tokens,
        temp=0.1
    )
```

### Phase 3: Baseline Evaluation (MLX + Cloud GPU)

- Use MLX for quick local iteration
- Use cloud GPU for comprehensive benchmarking
- Compare results to ensure MLX matches GPU performance

## Quick Test Script

Create `scripts/test_granite_mlx.py`:

```python
#!/usr/bin/env python3
"""Test Granite with MLX on Apple Silicon."""

try:
    from mlx_lm import load, generate

    print("Loading Granite 3.1 8B with MLX (4-bit)...")
    model, tokenizer = load("mlx-community/granite-3.1-8b-instruct-4bit")

    print("\nTest 1: Simple completion")
    response = generate(
        model, tokenizer,
        prompt="Explain semantic search in one sentence:",
        max_tokens=64,
        verbose=True
    )
    print(f"Response: {response}")

    print("\n\nTest 2: REM query generation")
    prompt = """Generate a REM query for: Find resources about machine learning from last week

REM Query:"""
    response = generate(model, tokenizer, prompt=prompt, max_tokens=64)
    print(f"Response: {response}")

except ImportError:
    print("MLX not installed. Install with: uv add mlx mlx-lm")
```

## Bottom Line

**For immediate testing on your Mac:**

```bash
# Option A: Ollama (2 minutes to get running)
brew install ollama
ollama pull granite3.1-dense:8b
ollama run granite3.1-dense:8b "test prompt"

# Option B: MLX (5 minutes, better Python integration)
cd p8fs-ai
uv add mlx mlx-lm
uv run python -c "
from mlx_lm import load, generate
model, tokenizer = load('mlx-community/granite-3.1-8b-instruct-4bit')
print(generate(model, tokenizer, prompt='Explain REM queries:', max_tokens=100))
"
```

Both will give you ~20-40 tokens/sec, which is totally usable for development and testing!
