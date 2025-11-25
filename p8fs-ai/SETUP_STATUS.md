# P8FS AI Setup Status

## Completed Tasks

### 1. Module Structure ✅
Created complete directory structure:
```
p8fs-ai/
├── src/p8fs_ai/
│   ├── models/          # Model loading utilities
│   ├── evaluation/      # Evaluation framework
│   ├── datasets/        # Dataset management
│   └── finetuning/      # Fine-tuning orchestration
├── data/                # Training datasets
├── benchmarks/          # Evaluation results
├── configs/             # Configuration files
├── scripts/             # Utility scripts
└── tests/               # Test suite
```

### 2. Dependencies Installed ✅
All core dependencies installed via `uv`:
- transformers 4.57.1
- torch 2.8.0
- datasets 4.4.1
- peft 0.18.0
- scikit-learn 1.7.2
- pandas 2.3.3
- fastapi 0.121.2
- openai 2.8.0

Note: `bitsandbytes` excluded on macOS (Linux/Windows only for quantization)

### 3. Model Utilities Created ✅
**File**: `src/p8fs_ai/models/loader.py`

Features:
- Multi-quantization support (bf16, fp16, 8bit, 4bit)
- Automatic fallback when quantization unavailable (macOS)
- Simple inference wrapper
- Parameter counting and diagnostics

### 4. Granite 3.1 8B Downloaded ✅
**Model**: ibm-granite/granite-3.1-8b-instruct
**Size**: 15GB
**Location**: `~/.cache/huggingface/hub/models--ibm-granite--granite-3.1-8b-instruct`

Model files successfully downloaded and cached.

### 5. Test Script Created ✅
**File**: `scripts/test_granite.py`

Includes three test scenarios:
1. Simple completion (semantic search explanation)
2. REM query generation (tool calling)
3. Structured output (edge affinity scoring)

## Important Notes

### macOS Limitations

The current system (macOS) has limitations for running large language models:

1. **No GPU Acceleration**: macOS doesn't support CUDA
2. **No Quantization**: bitsandbytes library unavailable
3. **CPU Performance**: 8B model on CPU is extremely slow (~minutes per inference)
4. **Memory Requirements**: 15GB+ RAM needed for bf16 inference

### Recommended Setup for Testing

**Option 1: Cloud GPU (Recommended for immediate testing)**
```bash
# Using Modal Labs
modal run scripts/test_granite_modal.py

# Using RunPod
# 1. Create A10 instance (24GB VRAM)
# 2. Clone repo and run: uv run python scripts/test_granite.py
```

**Option 2: Local GPU (Linux/Windows)**
If you have access to a system with:
- NVIDIA GPU with 16GB+ VRAM (RTX 3090/4090, A5000)
- Linux or Windows OS
- CUDA installed

Then you can run with 4-bit quantization:
```python
model, tokenizer = load_model(
    "ibm-granite/granite-3.1-8b-instruct",
    quantization="4bit"  # Reduces to ~5GB VRAM
)
```

**Option 3: Smaller Model (macOS/CPU compatible)**
For macOS testing, use smaller models:
- Granite 3B (not released yet)
- Qwen 2.5 3B Instruct
- Llama 3.2 3B Instruct

## Next Steps

### Immediate (Can do on macOS)

1. **Create Dataset Generators**
   ```bash
   # Generate REM query dataset from existing tests
   uv run python scripts/generate_rem_dataset.py
   ```

2. **Build Evaluation Framework**
   ```bash
   # Create evaluation metrics and test harness
   # Can run on small datasets without inference
   ```

3. **Setup Annotation Tool**
   ```bash
   # Streamlit app for manual dataset annotation
   uv run streamlit run src/p8fs_ai/datasets/annotator.py
   ```

### Short-term (Requires GPU)

1. **Run Baseline Evaluation**
   - Test Granite 3.1 8B on all three tasks
   - Compare with Qwen 2.5 Coder 7B
   - Generate benchmark results

2. **Fine-tune Task 1 (REM Query)**
   - Prepare training dataset
   - Train LoRA adapter
   - Evaluate improvements

3. **Deploy Inference Server**
   - Setup vLLM with LoRA adapters
   - Integrate with p8fs CLI
   - Performance testing

### Cloud GPU Pricing Reference

For budget planning:

| Provider | GPU | VRAM | Price/hr | Best For |
|----------|-----|------|----------|----------|
| Modal Labs | A10 | 24GB | $0.60 | 7B-8B models |
| RunPod | A10 | 24GB | $0.44 | Development |
| Lambda Labs | A10 | 24GB | $0.60 | Long runs |
| Modal Labs | A100 40GB | 40GB | $1.10 | 32B models (4-bit) |

**Recommendation**: Start with RunPod A10 for development ($0.44/hr = ~$10/day for full-time testing)

## Current Status Summary

**Environment**: macOS (development only)
**Model**: Granite 3.1 8B (downloaded, not tested on GPU)
**Codebase**: Ready for dataset creation and evaluation framework
**Blocking**: Need GPU access for model inference testing

## Quick Commands

```bash
# Install dependencies
cd p8fs-ai && uv sync

# Run tests (once on GPU)
uv run python scripts/test_granite.py

# Generate datasets
uv run python scripts/generate_rem_dataset.py

# Start annotation tool
uv run streamlit run src/p8fs_ai/datasets/annotator.py
```

## Questions?

- **Where is the model?** `~/.cache/huggingface/hub/models--ibm-granite--granite-3.1-8b-instruct`
- **Can I test locally?** Not practical on macOS/CPU. Use cloud GPU or Linux+NVIDIA GPU
- **What's next?** Build datasets and evaluation framework (can do on macOS), then test on GPU
- **Cost estimate?** $10-20 for initial baseline evaluation on cloud GPU
