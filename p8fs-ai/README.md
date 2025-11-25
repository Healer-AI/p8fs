# P8FS AI Module

Fine-tuning and deployment of open-source models for REM operations.

See [Claude.MD](Claude.MD) for detailed design and implementation plan.

## Quick Start

```bash
# Install dependencies
uv sync

# Run Granite model test
uv run python scripts/test_granite.py
```

## Tasks

1. **REM Query Generation**: Tool calling with intent detection
2. **Graph Edge Construction**: Semantic search for resource affinity
3. **Moment Construction**: Temporal activity classification

## Models

- Granite 3.1 8B Instruct
- Qwen 2.5 Coder 7B/32B
- DeepSeek-R1-Distill 32B
