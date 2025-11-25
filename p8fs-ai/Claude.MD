# P8FS AI Module - Open Source Model Fine-tuning for REM

## Overview

This module focuses on fine-tuning and deploying open-source models for REM (Resource-Entity-Moment) query operations to reduce LLM token costs while maintaining high performance on three critical tasks:

1. **REM Query Generation**: Tool calling with intent detection to generate REM dialect queries from natural language
2. **Graph Edge Construction**: Semantic search of historical data to identify resource affinity and generate graph edges
3. **Moment Construction**: Temporal activity classification for experience segmentation

**Target**: Models running on <20GB GPU with performance comparable to commercial LLMs for specialized tasks.

## Model Candidates

### Primary Candidates

| Model | Parameters | Memory | Strengths | Use Cases |
|-------|-----------|---------|-----------|-----------|
| **Granite 3.1 8B Instruct** | 8B | ~16GB | Enterprise-focused, instruction following | REM query generation, tool calling |
| **Qwen 2.5 Coder 7B** | 7B | ~14GB | Code generation, structured output | SQL generation, schema understanding |
| **Qwen 2.5 Coder 32B** | 32B | ~64GB (4-bit: ~20GB) | Advanced reasoning, complex queries | Multi-step REM queries, edge reasoning |
| **DeepSeek-R1-Distill 32B** | 32B | ~64GB (4-bit: ~20GB) | Reasoning, planning | Complex moment classification |
| **Llama 3.3 70B Instruct** | 70B | ~140GB (4-bit: ~40GB) | General capability, fine-tunable | Baseline comparison (cloud only) |

### Quantization Strategy

All models will be tested with:
- **BF16/FP16**: Full precision for fine-tuning
- **INT8**: 2x memory reduction, minimal quality loss
- **INT4**: 4x memory reduction for inference
- **GPTQ/AWQ**: Advanced quantization for 32B+ models

Target: Run 32B models in 4-bit on 20GB GPU for inference.

## Three Core Tasks

### Task 1: REM Query Generation (Tool Calling)

**Objective**: Generate REM dialect queries from natural language with accurate intent detection.

**Input**: Natural language query + available tools/tables
```
User: "Find resources about machine learning from last week"
Context: {tables: [resources, moments, entities], operations: [LOOKUP, SEARCH, SQL]}
```

**Expected Output**: REM query with correct operation
```json
{
  "intent": "semantic_search",
  "query_type": "SEARCH",
  "parameters": {
    "query_text": "machine learning",
    "table_name": "resources",
    "time_filter": {"after": "2024-11-10"},
    "limit": 10
  },
  "explanation": "Using SEARCH for semantic similarity on recent resources"
}
```

**Evaluation Metrics**:
- Intent accuracy: % correct operation selection (LOOKUP vs SEARCH vs SQL)
- Query validity: % syntactically correct REM queries
- Parameter accuracy: % correct field extraction
- Execution success: % queries that execute without errors

**Dataset Requirements**:
- 1000+ natural language ’ REM query pairs
- Covers all REM operations: LOOKUP, SEARCH, SQL, FUZZY, TRAVERSE
- Includes edge cases: ambiguous queries, multi-step operations
- Generated from existing REM test suite + synthetic examples

### Task 2: Graph Edge Construction (Resource Affinity)

**Objective**: Identify semantically related resources and generate graph edges with metadata.

**Input**: Source resource + historical resources
```json
{
  "source": {
    "id": "res-123",
    "content": "Meeting notes about Q4 planning and budget allocation"
  },
  "candidates": [
    {"id": "res-100", "content": "Q3 financial review..."},
    {"id": "res-200", "content": "Team capacity planning for H2..."}
  ]
}
```

**Expected Output**: Scored edges with relationship metadata
```json
{
  "edges": [
    {
      "from": "res-123",
      "to": "res-100",
      "type": "SEE_ALSO",
      "score": 0.85,
      "reason": "Both discuss quarterly planning and budget",
      "metadata": {"topic_overlap": ["planning", "budget", "q4"]}
    },
    {
      "from": "res-123",
      "to": "res-200",
      "type": "SEE_ALSO",
      "score": 0.72,
      "reason": "Related planning activities",
      "metadata": {"topic_overlap": ["planning", "capacity"]}
    }
  ]
}
```

**Evaluation Metrics**:
- Edge precision: % of suggested edges that are semantically valid
- Edge recall: % of valid edges identified from candidates
- Score calibration: Correlation between predicted scores and human ratings
- Metadata quality: Usefulness of extracted topics and reasoning

**Dataset Requirements**:
- 500+ resource pairs with human-annotated affinity scores
- Mix of related (SEE_ALSO) and unrelated resource pairs
- Diverse content types: diary entries, meeting notes, technical docs
- Temporal relationships: resources from different time periods

### Task 3: Moment Construction (Temporal Classification)

**Objective**: Classify temporal data into moment segments with activity type, emotions, topics, and participants.

**Input**: Transcript or temporal activity data
```
[2024-11-17 09:00] You started your morning with a team standup. Sarah mentioned the API deployment is ready. Mike had concerns about the database migration. You agreed to review the migration script before deployment.

[2024-11-17 10:30] Focused coding session working on the authentication service. Fixed the token refresh bug that was causing intermittent logouts. Felt satisfied with the progress.
```

**Expected Output**: Structured moment collection
```json
{
  "moments": [
    {
      "name": "Morning Standup with Team",
      "summary": "You discussed deployment readiness and database migration concerns",
      "content": "Team standup covering API deployment status. Sarah confirmed readiness, Mike raised migration concerns, you committed to reviewing scripts.",
      "resource_timestamp": "2024-11-17T09:00:00Z",
      "resource_ends_timestamp": "2024-11-17T09:15:00Z",
      "moment_type": "meeting",
      "emotion_tags": ["focused", "collaborative", "concerned"],
      "topic_tags": ["api-deployment", "database-migration", "team-standup"],
      "present_persons": [
        {"id": "sarah-123", "name": "Sarah", "comment": "Backend lead"},
        {"id": "mike-456", "name": "Mike", "comment": "Database engineer"}
      ]
    },
    {
      "name": "Authentication Service Debugging",
      "summary": "You fixed the token refresh bug causing logout issues",
      "content": "Focused coding session on authentication service. Successfully debugged and fixed token refresh bug.",
      "resource_timestamp": "2024-11-17T10:30:00Z",
      "resource_ends_timestamp": "2024-11-17T11:45:00Z",
      "moment_type": "problem_solving",
      "emotion_tags": ["focused", "satisfied", "productive"],
      "topic_tags": ["authentication", "bug-fix", "token-refresh"]
    }
  ]
}
```

**Evaluation Metrics**:
- Boundary accuracy: % correct moment start/end timestamps
- Type classification: % correct moment_type assignments
- Emotion accuracy: F1 score for emotion tag predictions
- Topic extraction: Precision/recall for topic tags
- Participant extraction: % correct person identification
- Summary quality: Human rating of summary usefulness (1-5 scale)

**Dataset Requirements**:
- 200+ annotated transcripts with moment boundaries
- Diverse activity types: meetings, reflection, coding, conversations
- Clear temporal markers and activity transitions
- Human-labeled emotions, topics, participants

## Experimental Framework

### Phase 1: Baseline Evaluation (Weeks 1-2)

**Objective**: Establish performance baselines for all candidate models.

#### Local Testing Setup

**Hardware Requirements**:
- GPU: 24GB VRAM minimum (RTX 3090/4090, A5000)
- RAM: 64GB system memory
- Storage: 500GB SSD for models and datasets

**Software Stack**:
```bash
# Core dependencies
uv add transformers>=4.36.0
uv add torch>=2.1.0
uv add vllm>=0.2.0
uv add datasets>=2.16.0
uv add peft>=0.7.0
uv add bitsandbytes>=0.41.0

# Evaluation
uv add scikit-learn
uv add pandas
uv add numpy

# Quantization
uv add auto-gptq
uv add autoawq
```

**Model Loading Pattern**:
```python
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import torch

def load_model(model_name: str, quantization: str = "bf16"):
    """Load model with specified quantization."""

    if quantization == "4bit":
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4"
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=bnb_config,
            device_map="auto"
        )
    elif quantization == "8bit":
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            load_in_8bit=True,
            device_map="auto"
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto"
        )

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    return model, tokenizer
```

#### Cloud Testing Setup

**Provider**: Modal Labs / RunPod / Lambda Labs

**GPU Tiers**:
- **Tier 1** (7B-8B models): A10 (24GB) - $0.60/hr
- **Tier 2** (32B models, 4-bit): A100 40GB - $1.10/hr
- **Tier 3** (70B models, 4-bit): A100 80GB - $2.00/hr

**Deployment Configuration**:
```python
# modal_deploy.py
import modal

stub = modal.Stub("p8fs-ai-eval")

image = modal.Image.debian_slim().pip_install(
    "transformers>=4.36.0",
    "torch>=2.1.0",
    "vllm>=0.2.0",
    "bitsandbytes>=0.41.0"
)

@stub.function(
    image=image,
    gpu="A100",
    timeout=3600,
    retries=2
)
def evaluate_model(model_name: str, task: str, dataset: dict):
    """Run evaluation on cloud GPU."""
    from p8fs_ai.evaluation import ModelEvaluator

    evaluator = ModelEvaluator(model_name, quantization="4bit")
    results = evaluator.evaluate(task, dataset)
    return results
```

#### Evaluation Pipeline

**Directory Structure**:
```
p8fs-ai/
   src/
      p8fs_ai/
          models/
             loader.py          # Model loading utilities
             inference.py       # Inference wrapper
             quantization.py    # Quantization configs
          evaluation/
             evaluator.py       # Main evaluation orchestrator
             metrics.py         # Task-specific metrics
             task1_rem_query.py # REM query evaluation
             task2_edges.py     # Edge construction evaluation
             task3_moments.py   # Moment classification evaluation
          datasets/
             loader.py          # Dataset loading
             generator.py       # Synthetic data generation
             annotator.py       # Human annotation helpers
          finetuning/
              trainer.py         # Fine-tuning orchestration
              lora.py            # LoRA configuration
              dpo.py             # DPO/RLHF training
   data/
      task1_rem_queries/
         train.jsonl
         val.jsonl
         test.jsonl
      task2_edges/
         train.jsonl
         val.jsonl
         test.jsonl
      task3_moments/
          train.jsonl
          val.jsonl
          test.jsonl
   benchmarks/
      baseline_results.json
      finetuned_results.json
   configs/
      models.yaml             # Model configurations
      tasks.yaml              # Task definitions
      training.yaml           # Training hyperparameters
   scripts/
       run_baseline_eval.py    # Baseline evaluation
       run_finetuning.py       # Fine-tuning script
       compare_models.py       # Model comparison

tests/
   test_task1_rem_query.py
   test_task2_edges.py
   test_task3_moments.py
```

**Baseline Evaluation Script**:
```python
# scripts/run_baseline_eval.py
from p8fs_ai.evaluation import ModelEvaluator
from p8fs_ai.datasets import load_datasets
import json

models = [
    "ibm-granite/granite-3.1-8b-instruct",
    "Qwen/Qwen2.5-Coder-7B-Instruct",
    "Qwen/Qwen2.5-Coder-32B-Instruct",  # 4-bit quantization
]

tasks = ["rem_query", "edge_construction", "moment_classification"]

results = {}

for model_name in models:
    results[model_name] = {}

    for task in tasks:
        print(f"Evaluating {model_name} on {task}...")

        evaluator = ModelEvaluator(
            model_name=model_name,
            quantization="4bit" if "32B" in model_name else "bf16"
        )

        dataset = load_datasets(task, split="test")

        task_results = evaluator.evaluate(task, dataset)
        results[model_name][task] = task_results

        print(f"  Results: {task_results['metrics']}")

# Save results
with open("benchmarks/baseline_results.json", "w") as f:
    json.dump(results, f, indent=2)
```

### Phase 2: Dataset Creation (Weeks 2-3)

#### Task 1: REM Query Dataset

**Sources**:
1. **Existing REM tests**: Extract query pairs from integration tests
2. **Synthetic generation**: Use GPT-4 to generate natural language variations
3. **Real usage**: Collect queries from p8fs CLI usage logs (anonymized)

**Generation Script**:
```python
# p8fs_ai/datasets/generator.py
from openai import OpenAI
import json

client = OpenAI()

SYSTEM_PROMPT = """You are a dataset generator for REM query training.

Given a REM query example, generate 5 natural language variations that express the same intent.

Example:
REM Query: SEARCH "machine learning" IN resources LIMIT 10
Variations:
1. Find resources about machine learning
2. Show me articles related to machine learning, limit to 10
3. Search for machine learning content in my resources
4. I'm looking for information on machine learning
5. Get resources discussing machine learning topics
"""

def generate_query_variations(rem_query: str, count: int = 5) -> list[str]:
    """Generate natural language variations of a REM query."""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Generate {count} variations for: {rem_query}"}
        ]
    )

    variations = response.choices[0].message.content.strip().split("\n")
    return [v.split(". ", 1)[1] for v in variations if ". " in v]

# Example usage
base_queries = [
    "LOOKUP test-resource-1",
    'SEARCH "morning activities" IN resources',
    "SELECT * FROM resources WHERE category='diary' ORDER BY created_at DESC LIMIT 5",
    "FUZZY 'machin lerning' IN resources THRESHOLD 0.7",
]

dataset = []
for query in base_queries:
    variations = generate_query_variations(query)
    for nl_query in variations:
        dataset.append({
            "natural_language": nl_query,
            "rem_query": query,
            "intent": classify_intent(query),
            "parameters": extract_parameters(query)
        })

with open("data/task1_rem_queries/train.jsonl", "w") as f:
    for item in dataset:
        f.write(json.dumps(item) + "\n")
```

#### Task 2: Edge Construction Dataset

**Sources**:
1. **Existing resources**: Use real p8fs resources with embeddings
2. **Human annotation**: Manually label resource pairs with affinity scores
3. **Synthetic pairs**: Generate related/unrelated pairs programmatically

**Annotation Tool**:
```python
# p8fs_ai/datasets/annotator.py
import streamlit as st
from p8fs.providers import get_provider
from p8fs.providers.rem_query import REMQueryProvider

def annotation_ui():
    """Interactive annotation tool for resource pairs."""

    provider = get_provider()
    rem = REMQueryProvider(provider)

    st.title("Resource Affinity Annotation")

    # Fetch random resource
    source = fetch_random_resource(rem)
    st.subheader(f"Source: {source['name']}")
    st.text(source['content'][:500])

    # Fetch candidates
    candidates = fetch_candidate_resources(rem, exclude_id=source['id'])

    for candidate in candidates:
        st.divider()
        st.write(f"**Candidate: {candidate['name']}**")
        st.text(candidate['content'][:500])

        col1, col2, col3 = st.columns(3)

        affinity_score = col1.slider(
            "Affinity Score",
            min_value=0.0,
            max_value=1.0,
            step=0.1,
            key=f"score_{candidate['id']}"
        )

        relationship = col2.selectbox(
            "Relationship",
            ["SEE_ALSO", "PREREQUISITE", "CONTINUATION", "NONE"],
            key=f"rel_{candidate['id']}"
        )

        if col3.button("Save", key=f"save_{candidate['id']}"):
            save_annotation({
                "source_id": source['id'],
                "target_id": candidate['id'],
                "affinity_score": affinity_score,
                "relationship": relationship,
                "timestamp": datetime.now().isoformat()
            })

# Run: streamlit run p8fs_ai/datasets/annotator.py
```

#### Task 3: Moment Classification Dataset

**Sources**:
1. **Transcript data**: Real diary entries, meeting notes from p8fs
2. **Synthetic generation**: Use GPT-4 to generate realistic temporal data
3. **Human annotation**: Label moment boundaries, types, emotions, topics

**Generation Template**:
```python
# Generate synthetic moment data
MOMENT_GENERATION_PROMPT = """Generate a realistic transcript for a {duration} period containing {num_moments} distinct moments.

Include:
- Clear temporal markers (timestamps, time references)
- Activity transitions (topic shifts, location changes, participant changes)
- Emotional language patterns (stress indicators, excitement, satisfaction)
- Specific topics and themes
- Participants in conversations

Moment types to include: {moment_types}

Format as chronological narrative with timestamps."""

def generate_moment_transcript(
    duration: str = "3 hours",
    num_moments: int = 4,
    moment_types: list[str] = None
) -> str:
    """Generate synthetic temporal transcript."""

    if moment_types is None:
        moment_types = ["meeting", "problem_solving", "reflection"]

    prompt = MOMENT_GENERATION_PROMPT.format(
        duration=duration,
        num_moments=num_moments,
        moment_types=", ".join(moment_types)
    )

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a realistic transcript generator."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content
```

### Phase 3: Fine-tuning (Weeks 3-5)

**Approach**: Parameter-Efficient Fine-Tuning (PEFT) using LoRA

**Why LoRA**:
- Trains only 0.1-1% of parameters
- Reduces memory requirements by 3x
- Faster training than full fine-tuning
- Multiple task-specific adapters can be swapped

**Training Configuration**:
```python
# p8fs_ai/finetuning/trainer.py
from peft import LoraConfig, get_peft_model
from transformers import TrainingArguments, Trainer
from datasets import load_dataset

def setup_lora_training(
    model,
    task_name: str,
    rank: int = 16,
    alpha: int = 32,
    dropout: float = 0.1
):
    """Configure LoRA for fine-tuning."""

    lora_config = LoraConfig(
        r=rank,                    # Rank of update matrices
        lora_alpha=alpha,          # Scaling factor
        lora_dropout=dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"]
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    return model

def train_model(
    model_name: str,
    task: str,
    output_dir: str,
    num_epochs: int = 3,
    batch_size: int = 4,
    learning_rate: float = 2e-4
):
    """Fine-tune model on task."""

    # Load base model
    base_model, tokenizer = load_model(model_name, quantization="4bit")

    # Apply LoRA
    model = setup_lora_training(base_model, task)

    # Load dataset
    dataset = load_dataset("json", data_files={
        "train": f"data/{task}/train.jsonl",
        "validation": f"data/{task}/val.jsonl"
    })

    # Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=learning_rate,
        fp16=True,
        logging_steps=10,
        save_strategy="epoch",
        evaluation_strategy="epoch",
        load_best_model_at_end=True,
        report_to="tensorboard"
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        tokenizer=tokenizer
    )

    # Train
    trainer.train()

    # Save adapter
    model.save_pretrained(f"{output_dir}/lora_adapter")
    tokenizer.save_pretrained(f"{output_dir}/lora_adapter")
```

**Multi-Task Training Strategy**:

Option 1: **Task-Specific Adapters** (Recommended)
- Train 3 separate LoRA adapters, one per task
- Swap adapters at inference time based on task
- Best performance per task

Option 2: **Multi-Task Single Model**
- Train one adapter on combined dataset
- Add task prefix to prompts (e.g., "[REM_QUERY]", "[EDGE]", "[MOMENT]")
- Simpler deployment

**Training Schedule**:
```
Week 3: Fine-tune Qwen 2.5 Coder 7B on Task 1 (REM queries)
Week 4: Fine-tune on Tasks 2 & 3
Week 5: Multi-task training experiments, hyperparameter tuning
```

### Phase 4: Deployment & Optimization (Week 6)

**Inference Server**: vLLM for high-throughput serving

**Server Setup**:
```python
# p8fs_ai/server.py
from vllm import LLM, SamplingParams
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# Load model with vLLM
llm = LLM(
    model="Qwen/Qwen2.5-Coder-7B-Instruct",
    tensor_parallel_size=1,
    gpu_memory_utilization=0.9,
    dtype="bfloat16"
)

class QueryRequest(BaseModel):
    task: str  # "rem_query", "edge", "moment"
    input: str
    max_tokens: int = 512

@app.post("/generate")
def generate(request: QueryRequest):
    """Generate output for specified task."""

    # Load task-specific LoRA adapter
    # (vLLM supports LoRA adapters via adapter registry)

    sampling_params = SamplingParams(
        temperature=0.1,
        top_p=0.95,
        max_tokens=request.max_tokens
    )

    outputs = llm.generate([request.input], sampling_params)

    return {
        "task": request.task,
        "output": outputs[0].outputs[0].text,
        "tokens": len(outputs[0].outputs[0].token_ids)
    }

# Run: uvicorn p8fs_ai.server:app --host 0.0.0.0 --port 8000
```

**Integration with p8fs**:
```python
# p8fs/src/p8fs/services/llm/local_model.py
from p8fs_cluster.config.settings import config
import requests

class LocalModelService:
    """Client for local fine-tuned models."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def generate_rem_query(self, natural_language: str) -> dict:
        """Generate REM query from natural language."""

        response = requests.post(
            f"{self.base_url}/generate",
            json={
                "task": "rem_query",
                "input": natural_language,
                "max_tokens": 256
            }
        )

        return response.json()["output"]

    def score_edge_affinity(self, source: str, target: str) -> float:
        """Score affinity between two resources."""

        prompt = f"Source: {source}\n\nTarget: {target}\n\nAffinity score (0-1):"

        response = requests.post(
            f"{self.base_url}/generate",
            json={
                "task": "edge",
                "input": prompt,
                "max_tokens": 50
            }
        )

        # Parse score from output
        return parse_score(response.json()["output"])

    def classify_moments(self, transcript: str) -> list[dict]:
        """Extract moments from temporal data."""

        response = requests.post(
            f"{self.base_url}/generate",
            json={
                "task": "moment",
                "input": transcript,
                "max_tokens": 2048
            }
        )

        return parse_moments(response.json()["output"])
```

**Optimization Techniques**:
1. **Speculative Decoding**: Use small draft model to speed up generation
2. **Continuous Batching**: Process multiple requests concurrently
3. **KV Cache Optimization**: Reuse cached keys/values for common prompts
4. **Quantization**: Deploy 4-bit quantized models for inference

## Success Metrics

### Performance Targets

**Task 1: REM Query Generation**
- Intent accuracy: >90%
- Query validity: >95%
- Execution success: >90%
- Latency: <500ms per query

**Task 2: Edge Construction**
- Edge precision: >80%
- Edge recall: >70%
- Score calibration: >0.7 Pearson correlation
- Latency: <200ms per pair

**Task 3: Moment Classification**
- Boundary accuracy: >85%
- Type classification: >80%
- Emotion F1: >0.75
- Topic precision: >0.80
- Latency: <2s for 1 hour transcript

### Cost Comparison

**Current**: GPT-4 via OpenAI API
- REM query: $0.001 per query (100 tokens @ $0.01/1K)
- Edge scoring: $0.002 per pair (200 tokens)
- Moment classification: $0.05 per hour transcript (5K tokens)
- **Monthly cost** (10K queries, 5K pairs, 100 hours): ~$350

**Target**: Fine-tuned open source model (self-hosted)
- GPU cost: $0.60/hr (A10) × 720 hrs = $432/month
- All tasks unlimited
- **Break-even**: ~1000 API calls/day
- **Savings at scale**: 10x+ reduction in cost

### Quality Gates

**Deployment Criteria**:
- [ ] All metrics meet or exceed targets
- [ ] Latency <2x GPT-4 baseline
- [ ] Cost <50% of GPT-4 at target load
- [ ] Model size <20GB quantized
- [ ] No regressions on test set

## Development Workflow

### Environment Setup

```bash
# Clone and setup
cd p8fs-modules
mkdir -p p8fs-ai/src/p8fs_ai

# Install dependencies
cd p8fs-ai
uv add transformers torch vllm datasets peft bitsandbytes
uv add scikit-learn pandas numpy
uv add fastapi uvicorn
uv add streamlit  # For annotation tool

# Download models
uv run python -c "from transformers import AutoModel; AutoModel.from_pretrained('ibm-granite/granite-3.1-8b-instruct')"
```

### Testing

```bash
# Run baseline evaluation
uv run python scripts/run_baseline_eval.py --model granite-3.1-8b --task rem_query

# Run fine-tuning
uv run python scripts/run_finetuning.py --model granite-3.1-8b --task rem_query --epochs 3

# Compare models
uv run python scripts/compare_models.py --baseline baseline_results.json --finetuned finetuned_results.json
```

### Continuous Integration

```yaml
# .github/workflows/model_eval.yml
name: Model Evaluation

on:
  push:
    paths:
      - 'p8fs-ai/**'
      - 'data/**'

jobs:
  eval:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd p8fs-ai
          uv sync

      - name: Run tests
        run: |
          cd p8fs-ai
          uv run pytest tests/ -v

      - name: Evaluate baseline (CPU only in CI)
        run: |
          cd p8fs-ai
          uv run python scripts/run_baseline_eval.py --device cpu --quick
```

## Next Steps

### Immediate (Week 1)
1. Create p8fs-ai module structure
2. Set up baseline evaluation pipeline
3. Generate initial datasets for Task 1 (REM queries)
4. Run baseline eval on Granite 3.1 8B and Qwen 2.5 Coder 7B

### Short-term (Weeks 2-3)
1. Complete all three task datasets
2. Build annotation tool for Task 2
3. Run comprehensive baseline evaluation on all models
4. Identify best base model per task

### Medium-term (Weeks 4-6)
1. Fine-tune top 2 models on each task
2. Deploy vLLM inference server
3. Integrate with p8fs CLI for testing
4. Optimize latency and throughput

### Long-term (Months 2-3)
1. Collect real usage data to refine datasets
2. Implement multi-task training
3. Explore distillation from GPT-4 to smaller models
4. Deploy to production with KEDA autoscaling

## References

### Model Documentation
- Granite 3.1: https://huggingface.co/ibm-granite/granite-3.1-8b-instruct
- Qwen 2.5 Coder: https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct
- DeepSeek-R1: https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B

### Fine-tuning Resources
- LoRA: https://arxiv.org/abs/2106.09685
- QLoRA: https://arxiv.org/abs/2305.14314
- vLLM: https://github.com/vllm-project/vllm

### REM System Documentation
- REM CLI Guide: `/Users/sirsh/code/p8fs-modules/docs/rem-query-cli-guide.md`
- REM Contract: `/Users/sirsh/code/p8fs-modules/p8fs/claude/scratch/rem_contract_summary.md`
- ResourceEdgeBuilder: `p8fs/src/p8fs/models/agentlets/resource_edge_builder.py`
- MomentBuilder: `p8fs/src/p8fs/models/agentlets/moments.py`
