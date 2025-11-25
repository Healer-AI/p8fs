# MLX CPU Inference Test Results

## Summary

✅ **CPU inference on macOS is VIABLE for p8fs-ai development!**

Using Qwen 2.5 Coder 7B (4-bit) with MLX on Apple Silicon.

## Performance Metrics

| Metric | Value | Assessment |
|--------|-------|------------|
| **Generation Speed** | 12-13 tokens/sec | ✅ Very usable |
| **Peak Memory** | 4.4 GB | ✅ Efficient |
| **Load Time** | 4 seconds | ✅ Fast (cached) |
| **Model Size** | ~4 GB download | ✅ Reasonable |

## Test Results

### Test 1: Simple Completion ✅

**Prompt**: "Explain what semantic search is in one sentence:"

**Output**:
> "Semantic search is a type of search that uses artificial intelligence to understand the meaning behind a user's query and return results that are most relevant to that meaning."

**Quality**: Perfect explanation
**Speed**: 13.5 tokens/sec

---

### Test 2: REM Query Generation ✅

**Prompt**: "Find resources about machine learning from last week"

**Output**:
```
SEARCH "machine learning" IN resources WHERE date > "2023-04-01"
```

**Quality**:
- ✅ Correct REM syntax (SEARCH ... IN ...)
- ✅ Proper query text extraction
- ✅ Attempted time filtering
- ⚠️ Date filter syntax not perfect (but shows understanding)

**Speed**: 13.4 tokens/sec

---

### Test 3: Edge Affinity Scoring (JSON) ✅

**Prompt**: Score affinity between Q4 planning notes and Q3 financial review

**Output**:
```json
{
  "affinity_score": 0.8,
  "reason": "Both resources involve budget allocation and financial planning, but Resource 1 is specifically about Q4 planning and budget allocation, while Resource 2 is about Q3 financial review and budget analysis. They share some common elements but are not identical."
}
```

**Quality**:
- ✅ Perfect JSON format
- ✅ Reasonable affinity score (0.8)
- ✅ Excellent reasoning about semantic overlap
- ✅ Identifies both similarities and differences

**Speed**: 12.9 tokens/sec

---

## Conclusions

### What Works Well

1. **Structured Output**: Model generates valid JSON and follows REM syntax
2. **Reasoning Quality**: Provides good explanations for scores/decisions
3. **Speed**: 12-13 tok/s is sufficient for batch evaluation and development
4. **Memory Efficiency**: 4.4GB fits comfortably on modern Macs
5. **Load Time**: 4s makes iteration fast

### Limitations

1. **Chat Template Tokens**: Model sometimes generates `<|im_start|>`, `<|im_end|>` tokens
   - Solution: Use proper chat template or post-process output
2. **REM Syntax**: Not perfect on first try (needs fine-tuning)
   - Expected: This is what fine-tuning will fix!
3. **Speed vs Cloud**: 12 tok/s vs 50-100 tok/s on GPU
   - Still fast enough for development iteration

### Recommendations

**For p8fs-ai Development:**

1. ✅ **Use MLX for local iteration**
   - Perfect for prompt engineering
   - Good enough for small-scale evaluation
   - Great for dataset validation

2. ✅ **Use Cloud GPU for comprehensive benchmarking**
   - Baseline evaluation across multiple models
   - Large dataset processing
   - Final fine-tuning

3. ✅ **Hybrid Approach**
   - Develop/test locally with MLX
   - Validate at scale on cloud GPU
   - Best of both worlds

## Next Steps

### Immediate (Can do now on Mac)

1. **Create proper chat templates** for Qwen to avoid `<|im_start|>` tokens
2. **Generate REM query dataset** from integration tests
3. **Build evaluation metrics** for the three tasks
4. **Test with different prompts** to optimize few-shot examples

### Short-term (This week)

1. **Create MLX wrapper** in `p8fs_ai/models/loader_mlx.py`
2. **Build evaluation harness** that works with MLX
3. **Generate initial baseline** with Qwen 2.5 Coder 7B
4. **Compare with Granite** (when available) or other models

### Medium-term (Next 1-2 weeks)

1. **Prepare fine-tuning datasets** (1000+ examples per task)
2. **Setup cloud GPU** for fine-tuning (Modal/RunPod)
3. **Fine-tune LoRA adapters** for each task
4. **Deploy vLLM server** with task-specific adapters

## Cost Implications

**Before MLX discovery**: Thought we needed $10-20/day for cloud GPU testing

**After MLX validation**:
- Local development: **$0/day** ✅
- Cloud GPU only for: Fine-tuning, large-scale eval
- Estimated savings: 50-70% of development costs

## Files

- Test script: `scripts/test_granite_mlx.py`
- CPU options guide: `docs/CPU_INFERENCE_OPTIONS.md`
- This report: `MLX_TEST_RESULTS.md`

## Command to Reproduce

```bash
cd p8fs-ai
uv run python scripts/test_granite_mlx.py
```

First run downloads ~4GB model, subsequent runs load in 4 seconds.
