# P8FS How-To Guide

Step-by-step guide to get started with P8FS document ingestion, semantic search, and AI-powered content analysis.

## Table of Contents

- [Prerequisites](#prerequisites)
  - [1. Start Docker Services](#1-start-docker-services)
  - [2. Install P8FS with Content Processing](#2-install-p8fs-with-content-processing)
  - [3. Set API Keys](#3-set-api-keys)
  - [4. About Tenant IDs](#4-about-tenant-ids)
- [Part 1: Process Your First File](#part-1-process-your-first-file)
- [Part 2: Verify Data in Database](#part-2-verify-data-in-database)
- [Part 3: Semantic Search](#part-3-semantic-search)
- [Part 4: AI Content Analysis with DreamModel](#part-4-ai-content-analysis-with-dreammodel)
- [Part 5: MomentBuilder - Time Classification](#part-5-momentbuilder---time-classification)
- [Part 6: Dreaming Worker - Automated Insight Pipeline](#part-6-dreaming-worker---automated-insight-pipeline)
- [Part 7: Moment Processing with Email Digest](#part-7-moment-processing-with-email-digest)
- [Part 8: Custom Analysis with parse_content()](#part-8-custom-analysis-with-parse_content)
- [Part 9: Custom Agent Models](#part-9-custom-agent-models)
- [Part 10: S3 File Storage](#part-10-s3-file-storage)
- [Part 11: Storage Worker with NATS Integration](#part-11-storage-worker-with-nats-integration)
- [Part 12: API Server and Authentication Testing](#part-12-api-server-and-authentication-testing)
- [Troubleshooting](#troubleshooting)
- [Next Steps](#next-steps)

## Prerequisites

### 1. Start Docker Services

```bash
# Navigate to p8fs directory (contains docker-compose.yaml)
cd p8fs

# Start PostgreSQL with pgvector extension
docker compose up postgres -d

# Verify container is running
docker ps | grep postgres
# Should show: percolate container running on port 5438

# Return to root directory for remaining commands
cd ..
```

### 2. Install P8FS with Content Processing

```bash
# From p8fs-modules root directory
# Install with workers extras (includes p8fs-node for file processing)
uv sync --extra workers

# This installs:
# - p8fs-node: Document processing (PDF, audio, DOCX)
# - PyTorch and transformers: ML dependencies
# - Content providers: Audio transcription, document parsing
```

### 3. Set API Keys

```bash
# OpenAI API key (required for embeddings and LLM calls)
export OPENAI_API_KEY=sk-your-key-here

# Optional: Anthropic for Claude models
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 4. About Tenant IDs

P8FS uses tenant IDs to isolate data between users or projects. The default tenant ID is `tenant-test` (configured in `p8fs_cluster.config.settings`). All CLI commands use this default when `--tenant-id` is not specified. You can override it by setting:

```bash
# Override default tenant ID
export P8FS_DEFAULT_TENANT_ID=my-custom-tenant

# Or use --tenant-id flag in each command
```

In these examples, we use the default `tenant-test` for simplicity.

## Part 1: Process Your First File

### Process a Sample Document

```bash
# From p8fs-modules root directory
# Process diary sample with automatic embedding generation
# Uses default tenant-test (no --tenant-id needed)
uv run python -m p8fs.cli process \
  tests/sample_data/content/diary_sample.md

# What happens:
# 1. File is read and split into chunks
# 2. Each chunk stored as a Resource in database (tenant: tenant-test)
# 3. Embeddings automatically generated for content field
# 4. Embeddings stored in embeddings.resources_embeddings table
```

**Output:**
```
Processing: diary_sample.md (0.0 MB)
Generated and stored 1 embeddings in batch
Successfully created 2 content resources
Completed diary_sample.md in 1.5s
✅ Processed diary_sample.md
```

**See also:** For testing storage workers with cluster integration, see [Part 11: Storage Worker with NATS Integration](#part-11-storage-worker-with-nats-integration) below.

## Part 2: Verify Data in Database

### Option A: Using pgAdmin or psql

```bash
# Connect to database (from p8fs-modules directory)
docker exec percolate psql -U postgres -d app

# Check resources were created (using default tenant-test)
SELECT name, category, length(content) as content_length
FROM resources
WHERE tenant_id = 'tenant-test'
ORDER BY created_at DESC
LIMIT 5;

# Check embeddings were generated
SELECT
    r.name,
    e.field_name,
    e.embedding_provider,
    e.vector_dimension
FROM resources r
JOIN embeddings.resources_embeddings e ON r.id = e.entity_id
WHERE r.tenant_id = 'tenant-test'
LIMIT 5;

# Expected output:
#        name         | field_name | embedding_provider | vector_dimension
# --------------------+------------+--------------------+------------------
# diary_sample_chunk_0| content    | text-embedding...  |             1536
# diary_sample_chunk_1| content    | text-embedding...  |             1536
```

### Option B: Using Python

```python
# Quick verification script (uses default tenant-test)
import asyncio
from p8fs.models.p8 import Resources
from p8fs.repository import TenantRepository
from p8fs.providers import get_provider

async def check():
    # Check resources (uses default tenant-test from config)
    repo = TenantRepository(Resources, tenant_id="tenant-test")
    resources = await repo.select(limit=10)
    print(f"✅ Found {len(resources)} resources")

    # Check embeddings
    provider = get_provider()
    embeddings = provider.execute(
        "SELECT COUNT(*) as count FROM embeddings.resources_embeddings WHERE tenant_id = %s",
        ["tenant-test"]
    )
    print(f"✅ Found {embeddings[0]['count']} embeddings")

asyncio.run(check())
```

## Part 3: Semantic Search

### Using CLI Query Command

```bash
# From p8fs-modules root directory
# Search for content about daily activities (uses default tenant-test)
uv run python -m p8fs.cli query \
  --table resources \
  --hint semantic \
  --limit 3 \
  "What did I do today?"

# What happens:
# 1. Query text is embedded using same model (text-embedding-ada-002)
# 2. Vector similarity search finds closest matches in tenant-test
# 3. Results ranked by cosine similarity score
```

**Output:**
```
score        content
0.8234       Today I worked on the authentication system...
0.7891       This morning I had breakfast and then started coding...
0.7456       Later in the afternoon I reviewed pull requests...
```

### Using Python

```python
import asyncio
from p8fs.models.p8 import Resources
from p8fs.repository import TenantRepository

async def search():
    # Uses default tenant-test
    repo = TenantRepository(Resources, tenant_id="tenant-test")

    # Semantic search - finds content by meaning, not keywords
    results = await repo.query(
        query_text="What did I do today?",
        hint="semantic",  # Uses vector similarity
        limit=5,
        threshold=0.7  # Only scores >= 0.7
    )

    # Print results
    for r in results:
        print(f"Score: {r['score']:.4f}")
        print(f"Content: {r['content'][:100]}...")
        print()

asyncio.run(search())
```

## Part 4: AI Content Analysis with DreamModel

The DreamModel analyzes personal content to extract goals, dreams, fears, and insights. It can work in two modes:

1. **Direct Content Analysis**: Analyze only the provided file content
2. **Memory-Augmented Analysis**: Use built-in `search_resources` function to find relevant stored memories

### Approach 1: Analyze Provided Content Only

For analyzing only the provided content without searching for additional resources, use `parse_content()` in Python. This bypasses the agentic loop and directly processes the content.

```python
# Create file: analyze_direct.py
import asyncio
from pathlib import Path
import yaml

from p8fs.models.agentlets.dreaming import DreamModel
from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext

async def analyze_file():
    # Read content
    content = Path("tests/sample_data/content/diary_sample.md").read_text()

    # Initialize with DreamModel
    proxy = MemoryProxy(DreamModel)

    # Create context
    context = CallingContext(
        model="claude-sonnet-4-5",
        tenant_id="tenant-test",
        temperature=0.1,
        max_tokens=8000
    )

    # Parse content directly (no search_resources called)
    result = await proxy.parse_content(
        content=content,
        context=context,
        merge_strategy="last"
    )

    # Print as YAML
    print(yaml.dump(result.model_dump(), default_flow_style=False, sort_keys=False))

asyncio.run(analyze_file())
```

Run it:
```bash
uv run python analyze_direct.py
```

**What happens:**
1. DreamModel system prompt loaded
2. Content sent directly to Claude (no agentic loop, no function calls)
3. LLM extracts structured data from provided content only
4. Response validated against DreamModel Pydantic schema
5. Output formatted as YAML

**Expected Output:**
```yaml
user_id: tenant-test
analysis_id: 550e8400-e29b-41d4-a716-446655440000
executive_summary: |
  User is focused on career development and learning new technologies.
  Shows strong interest in software engineering and personal growth.
key_themes:
  - software development
  - learning
  - career growth
goals:
  - goal: Master Python and machine learning
    category: career
    priority: high
    timeline: 6 months
  - goal: Build a personal project
    category: personal
    priority: medium
    timeline: 3 months
dreams:
  - dream: Work at a top tech company
    category: career
    timeline: long-term
fears:
  - fear: Not keeping up with technology changes
    category: career
    severity: medium
pending_tasks:
  - task: Complete Python course
    due_date: 2025-12-01
    priority: high
```

### Approach 2: Memory-Augmented Analysis with search_resources

For memory-augmented analysis where DreamModel searches for relevant resources automatically, use the `eval` command with a file. The eval command enables the agentic loop, allowing the LLM to call built-in functions.

```bash
# From p8fs-modules root directory
# Let DreamModel use search_resources to find and analyze relevant content
uv run python -m p8fs.cli eval \
  --agent-model agentlets.dreaming.DreamModel \
  --file tests/sample_data/content/diary_sample.md \
  --model claude-sonnet-4-5 \
  --format yaml

# What happens:
# 1. DreamModel loaded with agentic loop enabled
# 2. LLM has access to search_resources built-in function
# 3. LLM may call search_resources to find relevant content from tenant-test
# 4. Function searches resources from last 24 hours (default)
# 5. LLM analyzes file content + retrieved resources together
# 6. Extracts goals, dreams, fears from combined data
```

**Note:** The eval command enables the agentic loop, giving the LLM access to built-in functions like `search_resources` and `query_moments`. The LLM decides when to call these functions based on the task.

**Key Differences:**

| Approach | Method | Search Behavior |
|----------|--------|-----------------|
| **`parse_content()`** | Direct processing | No agentic loop, no function calls, analyzes only provided content |
| **`eval` command** | Agentic loop | LLM can call search_resources and other built-in functions as needed |

### Save Output to File

```bash
# From p8fs-modules root directory
# Save YAML analysis to file
uv run python -m p8fs.cli eval \
  --agent-model agentlets.dreaming.DreamModel \
  --file tests/sample_data/content/diary_sample.md \
  --model claude-sonnet-4-5 \
  --format yaml \
  --output analysis.yaml

# Then view the file
cat analysis.yaml
```

## Part 5: MomentBuilder - Time Classification

MomentBuilder classifies temporal data into activity moments with emotions and context.

### Using CLI

```bash
# From p8fs-modules root directory
# Classify transcript into moments
uv run python -m p8fs.cli eval \
  --agent-model agentlets.moments.MomentBuilder \
  --file tests/sample_data/moment_samples/tenant_1/transcript_2025-01-13T09-00-00Z_input.json \
  --model claude-sonnet-4-5 \
  --format yaml

# What happens:
# 1. MomentBuilder analyzes transcript segments
# 2. Identifies distinct moments (meetings, conversations, etc.)
# 3. Extracts emotions, topics, and present persons
# 4. Returns collection of moment objects with timestamps
```

**Output:**
```yaml
moments:
  - name: Morning Standup with Team
    moment_type: meeting
    content: Team discussed progress on authentication middleware...
    summary: Quick standup covering sprint tasks and blockers
    category: work
    resource_timestamp: '2025-01-13T09:00:00Z'
    resource_ends_timestamp: '2025-01-13T09:10:12Z'
    emotion_tags:
      - focused
      - collaborative
      - energized
    topic_tags:
      - standup-meeting
      - authentication-middleware
      - rate-limiting
    present_persons:
      - fingerprint_id: fp_alex_t1
        user_label: Alex
      - fingerprint_id: fp_jordan_t1
        user_label: Jordan
    location: video_conference
analysis_summary: Single standup meeting with productive team coordination
total_moments: 1
```

## Part 6: Dreaming Worker - Automated Insight Pipeline

The dreaming worker automatically processes tenant content to extract insights, goals, dreams, fears, and actionable items. It can run in three modes:

- **direct**: Synchronous processing with immediate results
- **batch**: Asynchronous processing via OpenAI Batch API
- **completion**: Check and retrieve results from pending batch jobs

### Process Specific Tenant

```bash
# From p8fs-modules root directory
# Process tenant-test with default settings (direct mode)
uv run python -m p8fs.cli dreaming --tenant-id tenant-test

# What happens:
# 1. Collects last 24 hours of resources and sessions for tenant
# 2. Analyzes content using DreamModel via LLM
# 3. Extracts goals, dreams, fears, tasks from content
# 4. Saves results to database
# 5. Logs errors if analysis fails
```

**Expected Output:**
```
📊 Processing tenant: tenant-test
   ✅ Completed analysis: 938d396b-66de-45a2-b4ba-d59d24f024c7
   📈 Goals: 1
   💭 Dreams: 0
   😰 Fears: 1
```

**What was extracted from the analysis:**
- **Executive Summary**: "The user is currently experiencing stress related to work-life balance and an upcoming product launch. There is a need to address personal well-being and manage anxiety."
- **Key Themes**: Work-life balance, Stress and anxiety, Upcoming product launch
- **Confidence Score**: 0.85
- **Processing Time**: ~12 seconds with GPT-4o

**Verify the results in database:**
```bash
# Check job records
docker exec percolate psql -U postgres -d app -c \
  "SELECT id, tenant_id, status, mode FROM jobs WHERE tenant_id = 'tenant-test' ORDER BY created_at DESC LIMIT 5;"

# Query goals extracted from analysis
docker exec percolate psql -U postgres -d app -c \
  "SELECT goal, category, priority, timeline FROM personal_goals WHERE user_id = 'tenant-test' LIMIT 5;"

# Query fears identified
docker exec percolate psql -U postgres -d app -c \
  "SELECT fear, category, severity FROM personal_fears WHERE user_id = 'tenant-test' LIMIT 5;"

# Check audit logs for LLM calls
docker exec percolate psql -U postgres -d app -c \
  "SELECT session_id, model, total_tokens, cost FROM audit_sessions WHERE tenant_id = 'tenant-test' ORDER BY created_at DESC LIMIT 3;"
```

### Process All Active Tenants

```bash
# From p8fs-modules root directory
# Find and process all tenants with activity in last 24 hours
uv run python -m p8fs.cli dreaming

# Adjust lookback window
uv run python -m p8fs.cli dreaming --lookback-hours 48
```

**What happens:**
1. Queries database for tenants with resources or sessions in lookback period
2. Processes each active tenant sequentially
3. Shows progress for each tenant
4. Continues on errors (doesn't stop pipeline)

### Batch Mode for Async Processing

```bash
# From p8fs-modules root directory
# Submit batch job for async processing
uv run python -m p8fs.cli dreaming --mode batch --tenant-id tenant-test

# Check batch job completions
uv run python -m p8fs.cli dreaming --mode completion
```

**Batch mode workflow:**
1. `--mode batch`: Submits job to OpenAI Batch API, returns immediately with batch_id
2. Processing happens asynchronously on OpenAI's servers
3. `--mode completion`: Checks all pending jobs, retrieves completed results

### Custom Model Selection

```bash
# From p8fs-modules root directory
# Use Claude instead of GPT-4
uv run python -m p8fs.cli dreaming \
  --tenant-id tenant-test \
  --model claude-sonnet-4-5

# Use GPT-4o for faster processing
uv run python -m p8fs.cli dreaming \
  --tenant-id tenant-test \
  --model gpt-4o
```

### Pipeline Behavior

The dreaming command is designed as a robust pipeline:

- **Loops through active tenants** when no tenant-id specified
- **Continues on errors** - one tenant failure doesn't stop the pipeline
- **Saves results** to database on success
- **Logs errors** to database on failure
- **Suitable for scheduled execution** (cron, scheduled tasks)

### Scheduled Execution Example

```bash
# Add to crontab for daily processing at 3 AM
0 3 * * * cd /path/to/p8fs-modules && uv run python -m p8fs.cli dreaming --lookback-hours 24

# Or use with systemd timer for production
[Unit]
Description=P8FS Dreaming Worker
[Timer]
OnCalendar=daily
OnCalendar=03:00
[Install]
WantedBy=timers.target
```

## Part 7: Moment Processing with Email Digest

The moments processor analyzes transcripts and activity data to extract time-bounded moments with emotional context, participants, and topics. It can optionally send beautiful HTML email digests of the moments.

### Process Moments from Transcript

```bash
# From p8fs-modules root directory
# Process transcript data and extract moments
uv run python -m p8fs.cli dreaming \
  --tenant-id tenant-test-moments \
  --task moments \
  --model gpt-4o

# What happens:
# 1. Collects last 24 hours of sessions and resources for tenant
# 2. Analyzes temporal data using MomentBuilder via LLM
# 3. Classifies moments by type (meeting, conversation, reflection, etc.)
# 4. Extracts emotions, topics, and participants
# 5. Saves moments to database with temporal boundaries
```

**Expected Output:**
```
📊 Processing tenant: tenant-test-moments
   ✅ Completed moment processing: 6f947601-d575-4793-be0d-c370304419f1
   📅 Moments: 1
```

### Send Moment Email Digest

Add `--recipient-email` to send a beautiful HTML email digest:

```bash
# From p8fs-modules root directory
# Process moments and send email to specified recipient
uv run python -m p8fs.cli dreaming \
  --tenant-id tenant-test-moments \
  --task moments \
  --model gpt-4o \
  --recipient-email user@example.com

# What happens:
# 1. Processes moments as above
# 2. Builds beautiful HTML email from first moment
# 3. Sends via configured SMTP (Gmail by default)
# 4. Email includes moment details, emotions, topics, participants
```

**Expected Output:**
```
📊 Processing tenant: tenant-test-moments
   ✅ Completed moment processing: 98516172-75e8-4ac7-bd18-42f97f5ab05d
   📅 Moments: 1
   📧 Email sent to: user@example.com
```

### Email Configuration

The email service uses Gmail SMTP by default. Configure via environment variables:

```bash
# Set Gmail app password (required for email sending)
export P8FS_EMAIL_PASSWORD="your-gmail-app-password"

# Optional: Override email settings
export P8FS_EMAIL_USERNAME="your-email@gmail.com"
export P8FS_EMAIL_SENDER_NAME="Your Name"

# If not configured, emails are skipped gracefully (no errors)
```

**Note:** For Gmail, you need an [app-specific password](https://support.google.com/accounts/answer/185833) (not your regular password) due to 2FA requirements.

### Verify Moments in Database

```bash
# Check moments were saved
docker exec percolate psql -U postgres -d app -c \
  "SELECT name, moment_type, start_time, end_time FROM moments WHERE tenant_id = 'tenant-test-moments' LIMIT 5;"

# Expected output:
#        name        | moment_type |       start_time       |        end_time
# -------------------+-------------+------------------------+------------------------
# Morning Standup    | meeting     | 2025-01-13 09:00:00+00 | 2025-01-13 09:10:12+00

# Check moment details with emotions and topics
docker exec percolate psql -U postgres -d app -c \
  "SELECT name, moment_type, emotion_tags, topic_tags FROM moments WHERE tenant_id = 'tenant-test-moments' LIMIT 1;"

# Expected output includes arrays of emotions and topics:
# emotion_tags: ["focused", "collaborative", "energized"]
# topic_tags: ["standup-meeting", "authentication-middleware", "rate-limiting"]
```

### Python Example - Process and Email Moments

```python
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from p8fs.workers.dreaming import DreamingWorker
from p8fs.models.agentlets.moments import MomentBuilder
from p8fs.services.llm import MemoryProxy
from p8fs.services.llm.models import CallingContext
from p8fs.repository import TenantRepository
from p8fs.models.engram.models import Moment

async def process_and_email_moments():
    # Load transcript data
    transcript_file = Path("tests/sample_data/moment_samples/tenant_1/transcript_2025-01-13T09-00-00Z_input.json")
    transcript_data = json.loads(transcript_file.read_text())

    # Initialize MemoryProxy with MomentBuilder
    proxy = MemoryProxy(MomentBuilder)

    context = CallingContext(
        model="gpt-4o",
        tenant_id="tenant-test-moments",
        temperature=0.1,
        max_tokens=4000
    )

    # Parse transcript into moments
    result = await proxy.parse_content(
        content=transcript_data,
        context=context,
        merge_strategy="last"
    )

    print(f"✅ Parsed {len(result.moments)} moments")

    # Save moments to database
    moment_repo = TenantRepository(Moment, tenant_id="tenant-test-moments")
    saved_moments = []

    for moment_data in result.moments:
        # Convert present_persons from list to dict if needed
        present_persons = moment_data.get('present_persons', {})
        if isinstance(present_persons, list):
            present_persons = {
                person.get('fingerprint_id', f'person_{i}'): person
                for i, person in enumerate(present_persons)
            }

        # Create and save moment
        moment = Moment(
            id=uuid4(),
            tenant_id="tenant-test-moments",
            name=moment_data.get('name'),
            start_time=moment_data.get('resource_timestamp'),
            end_time=moment_data.get('resource_ends_timestamp'),
            content=moment_data.get('content'),
            summary=moment_data.get('summary'),
            present_persons=present_persons,
            location=moment_data.get('location'),
            moment_type=moment_data.get('moment_type'),
            emotion_tags=moment_data.get('emotion_tags', []),
            topic_tags=moment_data.get('topic_tags', []),
            resource_timestamp=moment_data.get('resource_timestamp'),
            resource_ends_timestamp=moment_data.get('resource_ends_timestamp'),
            metadata=moment_data.get('metadata', {})
        )

        saved_moment = await moment_repo.upsert(moment)
        saved_moments.append(moment)

    print(f"✅ Saved {len(saved_moments)} moments to database")

    # Send email
    if saved_moments:
        from p8fs.services.email import EmailService, MomentEmailBuilder

        builder = MomentEmailBuilder()
        email_html = builder.build_moment_email_html(
            moment=saved_moments[0],
            date_title="Your Daily Moments"
        )

        email_service = EmailService()
        email_service.send_email(
            subject=f"EEPIS Moments: {saved_moments[0].name}",
            html_content=email_html,
            to_addrs="user@example.com",
            text_content=f"{saved_moments[0].name}\n\n{saved_moments[0].content}"
        )

        print(f"✅ Email sent to user@example.com")

asyncio.run(process_and_email_moments())
```

### Email Template Features

The moment email includes:
- **Beautiful gradient header** with EEPIS branding
- **Moment type badge** with color-coded scheme
- **Emotion indicators** with mood icons
- **Participant badges** with person icons
- **Topic tags** in color-coded chips
- **Location information** with map icon
- **Responsive design** for mobile and desktop

**Color schemes by moment type:**
- Meeting: Blue gradient
- Observation: Red gradient
- Reflection: Purple gradient
- Conversation: Orange gradient
- Planning: Teal gradient

## Part 8: Custom Analysis with parse_content()

Use `parse_content()` in Python for programmatic structured output with automatic pagination.

### Python Example - Analyze Large Documents

```python
import asyncio
from pathlib import Path

from p8fs.models.agentlets.dreaming import DreamModel
from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext

async def analyze_document():
    # Read your content
    content = Path("tests/sample_data/content/diary_sample.md").read_text()

    # Initialize MemoryProxy with DreamModel
    # DreamModel extracts goals, dreams, fears, tasks from personal content
    proxy = MemoryProxy(DreamModel)

    # Create context with model settings
    context = CallingContext(
        model="claude-sonnet-4-5",  # Which LLM to use
        tenant_id="my-tenant",
        temperature=0.1,  # Lower for more consistent structured output
        max_tokens=8000
    )

    # Parse content with automatic pagination
    # - Content chunked if too large for context window
    # - Each chunk processed separately
    # - Results merged based on strategy
    result = await proxy.parse_content(
        content=content,
        context=context,
        merge_strategy="last"  # Use last chunk's results
    )

    # Result is a validated DreamModel instance
    print(f"Executive Summary: {result.executive_summary}")
    print(f"Goals: {len(result.goals)}")
    print(f"Dreams: {len(result.dreams)}")
    print(f"Fears: {len(result.fears)}")

    # Export to YAML
    import yaml
    output = yaml.dump(
        result.model_dump(),
        default_flow_style=False,
        sort_keys=False
    )
    Path("dream_analysis.yaml").write_text(output)
    print("\n✅ Saved to dream_analysis.yaml")

asyncio.run(analyze_document())
```

### Python Example - Batch Processing Multiple Files

```python
import asyncio
from pathlib import Path

from p8fs.models.agentlets.dreaming import DreamModel
from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext

async def batch_analyze():
    proxy = MemoryProxy(DreamModel)
    context = CallingContext(
        model="claude-sonnet-4-5",
        tenant_id="my-tenant"
    )

    # Process multiple files
    files = Path("tests/sample_data/content").glob("*.md")

    for file in files:
        print(f"Analyzing {file.name}...")
        content = file.read_text()

        # Parse each file
        result = await proxy.parse_content(
            content=content,
            context=context,
            merge_strategy="last"
        )

        # Save results
        output_file = f"analysis_{file.stem}.yaml"
        import yaml
        Path(output_file).write_text(
            yaml.dump(result.model_dump(), default_flow_style=False)
        )
        print(f"  ✅ Saved to {output_file}")

asyncio.run(batch_analyze())
```

### Python Example - Moment Classification

```python
import asyncio
import json
from pathlib import Path

from p8fs.models.agentlets.moments import MomentBuilder
from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext

async def classify_moments():
    # Load transcript data
    transcript_file = Path("tests/sample_data/moment_samples/tenant_1/transcript_2025-01-13T09-00-00Z_input.json")
    transcript_data = json.loads(transcript_file.read_text())

    # Initialize with MomentBuilder
    # MomentBuilder classifies time periods into activity moments
    proxy = MemoryProxy(MomentBuilder)

    context = CallingContext(
        model="claude-sonnet-4-5",
        tenant_id="my-tenant",
        temperature=0.1,
        max_tokens=8000
    )

    # Parse transcript into moments
    # - Automatically handles list chunking to preserve record boundaries
    # - Returns collection of moments with temporal boundaries
    result = await proxy.parse_content(
        content=transcript_data,
        context=context,
        merge_strategy="last"
    )

    # Print moment summary
    print(f"Total moments: {result.total_moments}")
    print(f"Analysis: {result.analysis_summary}\n")

    # Print each moment
    for i, moment in enumerate(result.moments, 1):
        print(f"Moment {i}: {moment['name']}")
        print(f"  Type: {moment['moment_type']}")
        print(f"  Emotions: {', '.join(moment.get('emotion_tags', []))}")
        print(f"  Topics: {', '.join(moment.get('topic_tags', []))}")
        if moment.get('present_persons'):
            persons = [p.get('user_label', 'Unknown') for p in moment['present_persons']]
            print(f"  People: {', '.join(persons)}")
        print()

    # Save to YAML
    import yaml
    Path("moments.yaml").write_text(
        yaml.dump(result.model_dump(), default_flow_style=False)
    )
    print("✅ Saved to moments.yaml")

asyncio.run(classify_moments())
```

## Part 9: Custom Agent Models

Create your own agent models for specific analysis tasks.

### Define Custom Agent

```python
from pydantic import Field
from p8fs.models.base import AbstractModel

class CodeReviewAgent(AbstractModel):
    """You are a code review expert. Analyze code for:
    - Code quality and best practices
    - Potential bugs and security issues
    - Performance optimizations
    - Documentation completeness

    Provide constructive feedback with specific examples.
    """

    # Structured output fields
    overall_score: float = Field(
        description="Overall code quality score (0-10)"
    )

    issues: list[dict] = Field(
        default_factory=list,
        description="List of issues found with severity and description"
    )

    strengths: list[str] = Field(
        default_factory=list,
        description="Positive aspects of the code"
    )

    recommendations: list[str] = Field(
        default_factory=list,
        description="Specific recommendations for improvement"
    )
```

### Use Custom Agent

```python
import asyncio
from pathlib import Path

from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext

async def review_code():
    # Your custom agent
    from my_agents import CodeReviewAgent

    # Read code to review
    code = Path("my_module.py").read_text()

    # Initialize with custom agent
    proxy = MemoryProxy(CodeReviewAgent)

    context = CallingContext(
        model="claude-sonnet-4-5",
        tenant_id="my-tenant"
    )

    # Analyze code
    review = await proxy.parse_content(
        content=code,
        context=context
    )

    # Print review
    print(f"Overall Score: {review.overall_score}/10\n")
    print("Issues:")
    for issue in review.issues:
        print(f"  [{issue['severity']}] {issue['description']}")

    print("\nStrengths:")
    for strength in review.strengths:
        print(f"  ✓ {strength}")

    print("\nRecommendations:")
    for rec in review.recommendations:
        print(f"  → {rec}")

asyncio.run(review_code())
```

## Part 10: S3 File Storage

P8FS provides S3-compatible file storage via SeaweedFS with tenant isolation. Files are organized by tenant and date: `<tenant-id>/uploads/YYYY/MM/DD/filename.ext`.

**Tip:** You can access the SeaweedFS Filer dashboard for file browsing and management:
```bash
# Port forward to access Filer UI at http://localhost:8888
kubectl port-forward -n p8fs svc/seaweedfs-filer 8888:8888
```

### S3 Credentials

Three credential types available from cluster secret `seaweedfs-s3-config`:

```bash
# Admin credentials (full access: read, write, delete, list, admin operations)
P8FS_SEAWEEDFS_ACCESS_KEY=p8fs-admin-access
P8FS_SEAWEEDFS_SECRET_KEY=r52xFgeWpX4qnJRW78QtlhlbOt7JghMHTXwaTo2vH/o=

# Application credentials (read, write, list, tagging)
P8FS_SEAWEEDFS_ACCESS_KEY=p8fs-app-access
P8FS_SEAWEEDFS_SECRET_KEY=KijA9+oe52IHSqwfatG3wJHIo4e2OJX258QqnPxLv5o=

# Read-only credentials (read, list only)
P8FS_SEAWEEDFS_ACCESS_KEY=p8fs-readonly-access
P8FS_SEAWEEDFS_SECRET_KEY=GGdAaNQj8klZYwM4z1yoe7W/SjO/uTWR3aHcQlwA894=
```

Add to `.env` file or export as environment variables.

### Upload Files

```bash
# Upload file to tenant's date-partitioned storage
# Results in: tenant-test/uploads/2025/10/11/document.pdf
uv run python -m p8fs.cli files upload document.pdf

# Upload with custom name
uv run python -m p8fs.cli files upload local.txt report.txt

# Upload to specific tenant
uv run python -m p8fs.cli files upload data.csv --tenant-id my-tenant
```

### List Files

```bash
# List files for default tenant (tenant-test)
uv run python -m p8fs.cli files list --recursive

# List for specific tenant
uv run python -m p8fs.cli files list --tenant-id my-tenant --recursive

# Limit results
uv run python -m p8fs.cli files list --recursive --limit 50
```

**Output:**
```
Path                                                Size     Modified
--------------------------------------------------------------------------------
uploads/2025/10/11/document.pdf                   1024     2025-10-11T12:13:18
uploads/2025/10/11/report.txt                      256     2025-10-11T12:15:42

2 files
```

### Download Files

```bash
# Download file (use full path from list command)
uv run python -m p8fs.cli files download uploads/2025/10/11/document.pdf

# Download to specific location
uv run python -m p8fs.cli files download uploads/2025/10/11/report.txt /tmp/report.txt
```

### Get File Info

```bash
# Get metadata for a file
uv run python -m p8fs.cli files info uploads/2025/10/11/document.pdf
```

### Delete Files

```bash
# Delete file (prompts for confirmation)
uv run python -m p8fs.cli files delete uploads/2025/10/11/old-file.txt

# Force delete without confirmation
uv run python -m p8fs.cli files delete uploads/2025/10/11/old-file.txt --force
```

## Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Restart if needed
docker compose restart postgres

# Test connection
docker exec -it percolate psql -U postgres -d app -c "SELECT version();"
```

### Missing API Keys

```bash
# Check if keys are set
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY

# Set keys for session
export OPENAI_API_KEY=sk-your-key
export ANTHROPIC_API_KEY=sk-ant-your-key

# Or add to ~/.bashrc or ~/.zshrc for persistence
```

### p8fs-node Not Installed

```bash
# If you see "p8fs-node not installed" warning:
uv sync --extra workers

# This installs content processing dependencies
```

### Embedding Generation Fails

```bash
# Check OpenAI API key is valid
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# Should return list of available models
```

### Clean Start

```bash
# Reset database completely (from p8fs directory)
cd p8fs
docker compose down -v  # ⚠️  Deletes all data!
docker compose up postgres -d

# Wait for health check
sleep 5

# Return to root directory
cd ..

# Process sample file again (uses default tenant-test)
uv run python -m p8fs.cli process \
  tests/sample_data/content/diary_sample.md
```

## Part 11: Storage Worker with NATS Integration

Test the complete workflow of uploading files to S3, publishing events to NATS, and processing them with storage workers.

### Prerequisites

```bash
# Start local PostgreSQL
cd p8fs
docker compose up postgres -d
cd ..

# Start NATS server (or port-forward to cluster)
# Option 1: Local NATS with Docker
docker run -d --name nats -p 4222:4222 -p 8222:8222 nats:latest

# Option 2: Port-forward to cluster NATS
kubectl port-forward -n p8fs svc/nats 4222:4222 &

# Ensure S3 credentials are set (defaults work without .env)
# export P8FS_SEAWEEDFS_S3_ENDPOINT=https://s3.eepis.ai
# export P8FS_SEAWEEDFS_ACCESS_KEY=p8fs-admin-access
# export P8FS_SEAWEEDFS_SECRET_KEY=r52xFgeWpX4qnJRW78QtlhlbOt7JghMHTXwaTo2vH/o=
```

### Run Complete Integration Test

The test script demonstrates the full workflow:
1. Uploads PDF file to SeaweedFS S3
2. Publishes storage event to NATS
3. Worker consumes message from NATS
4. Downloads file from S3
5. Extracts content using PDF provider
6. Saves chunked resources with embeddings to database

```bash
# Run the complete test
uv run python scripts/test_nats_worker.py
```

**Expected Output:**
```
================================================================================
NATS Storage Worker Integration Test
================================================================================
Configuration:
  NATS URL: nats://localhost:4222
  S3 Endpoint: https://s3.eepis.ai
  Storage Provider: postgresql
  Test Subject: p8fs.storage.events.test2
  Test File: tests/sample_data/content/Sample.pdf
================================================================================

📤 Step 1: Uploading Sample.pdf to SeaweedFS...
✅ Uploaded to: uploads/2025/10/11/Sample.pdf
   Size: 840,059 bytes
   Method: single_put

📋 Step 2: Setting up test stream and consumer...
✅ Created test stream

📨 Step 3: Publishing test event to NATS...
✅ Published to: p8fs.storage.events.test2
   Event: create - uploads/2025/10/11/Sample.pdf

⚙️  Step 4: Processing event from queue...
✅ Received message from queue
   Processing: uploads/2025/10/11/Sample.pdf
Downloading file from S3: uploads/2025/10/11/Sample.pdf
Downloaded to temp file: /tmp/tmpXXX.pdf (840059 bytes)
Processing: tmpXXX.pdf (0.8 MB)
Using PDFContentProvider - will extract text and structure
Created 13 chunks in 0.8s
Successfully created 13 content resources for uploads/2025/10/11/Sample.pdf
Completed tmpXXX.pdf in 7.4s
✅ Successfully processed and acknowledged message

📊 Step 5: Verifying resources in database...
✅ Files found: 2
   - diary_sample.md (3,900 bytes)
   - uploads/2025/10/11/Sample.pdf (840,059 bytes)
✅ Resources found: 15
   - tmpXXX_chunk_0 (348 chars)
   - tmpXXX_chunk_1 (509 chars)
   - tmpXXX_chunk_2 (446 chars)
   ...

================================================================================
✅ Test PASSED - Complete workflow successful!
================================================================================

What happened:
1. ✅ File uploaded to SeaweedFS S3
2. ✅ NATS stream created
3. ✅ Event published to NATS test queue
4. ✅ Worker consumed message and downloaded from S3
5. ✅ Content extracted using PDF provider
6. ✅ Resources saved to database
```

### Verify Results

```bash
# Check files in database
docker exec percolate psql -U postgres -d app -c \
  "SELECT uri, file_size FROM files WHERE tenant_id = 'tenant-test' LIMIT 5;"

# Check resources (content chunks)
docker exec percolate psql -U postgres -d app -c \
  "SELECT name, category, length(content) as size FROM resources WHERE tenant_id = 'tenant-test' LIMIT 10;"

# Check embeddings were generated
docker exec percolate psql -U postgres -d app -c \
  "SELECT COUNT(*) as count FROM embeddings.resources_embeddings WHERE tenant_id = 'tenant-test';"

# View files in S3
uv run python -m p8fs.cli files list --tenant-id tenant-test --recursive
```

### How It Works

The storage worker integration demonstrates:

1. **S3 Upload**: File uploaded to SeaweedFS with proper AWS V4 signature authentication
2. **Event Publishing**: Storage event published to NATS JetStream with file metadata
3. **Worker Consumption**: Worker pulls message from NATS queue using durable consumer
4. **S3 Download**: Worker downloads file from S3 using the s3_key from the event
5. **Content Processing**: PDF provider extracts text and structure from downloaded file
6. **Resource Storage**: Content chunks saved to database with automatic embedding generation

This workflow is the foundation for the cluster-based storage workers that process files uploaded through the API.

### Advanced: Run Worker Continuously

For development/debugging, run the worker continuously to process events as they arrive:

```bash
# Start worker listening on test queue
# (In a separate terminal)
uv run python -m p8fs.workers.storage \
  --tenant-id tenant-test \
  --subject p8fs.storage.events.test2

# Then upload and publish events from another terminal
uv run python scripts/test_nats_worker.py
```

## Part 12: API Server and Authentication Testing

Test the P8FS API server locally with OAuth device authentication, database provider selection, and complete end-to-end auth flows.

### Start API Server

**IMPORTANT**: Always check port 8001 is free and use `--reload` for development hot reload.

```bash
# Kill any existing process on port 8001
lsof -ti :8001 | xargs kill -9

# Start with PostgreSQL (default)
cd /Users/sirsh/code/p8fs-modules/p8fs-api
P8FS_DEBUG=true uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8001

# Start with TiDB provider
cd /Users/sirsh/code/p8fs-modules/p8fs-api
P8FS_DEBUG=true P8FS_STORAGE_PROVIDER=tidb uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8001
```

**Verify server is running:**
```bash
# Health check
curl http://localhost:8001/health

# API information
curl http://localhost:8001/

# OAuth discovery (OpenID Connect)
curl http://localhost:8001/.well-known/openid-configuration

# Interactive API docs
open http://localhost:8001/docs
```

### Test Device Registration with PostgreSQL

```bash
# Register a device (creates tenant + JWT tokens)
cd /Users/sirsh/code/p8fs-modules/p8fs-api
uv run python -m p8fs_api.cli.device --local register \
  --email test@example.com \
  --tenant test-tenant

# Expected output:
# ✓ Device registered successfully!
#   Tenant ID: test-tenant
#   Token saved to: /Users/username/.p8fs/auth/token.json

# Check device status
uv run python -m p8fs_api.cli.device --local status

# Test token validity
uv run python -m p8fs_api.cli.device --local ping
```

**Verify in PostgreSQL:**
```bash
# Check tenant was created
docker exec percolate psql -U postgres -d app -c \
  "SELECT tenant_id, email, active FROM tenants WHERE email='test@example.com';"

# Expected output:
#  tenant_id  |       email       | active
# -----------+-------------------+--------
#  tenant-test| test@example.com  | t
```

### Test Device Registration with TiDB

First, ensure TiDB is running and migrations are applied:

```bash
# Start TiDB container
cd /Users/sirsh/code/p8fs-modules/p8fs
docker compose up tidb -d

# Apply migrations (one-time setup)
cd ..
uv run python -c "
import pymysql
from pathlib import Path

migration = Path('p8fs/extensions/migrations/tidb/install.sql').read_text()
conn = pymysql.connect(host='localhost', port=4000, user='root', autocommit=True)
cursor = conn.cursor()

for statement in [s.strip() for s in migration.split(';') if s.strip() and not s.strip().startswith('--')]:
    try:
        cursor.execute(statement)
    except Exception as e:
        print(f'Warning: {e}')

cursor.close()
conn.close()
print('✅ TiDB migration complete')
"
```

**Start API server with TiDB:**
```bash
# Terminal 1: Start API server with TiDB provider
cd /Users/sirsh/code/p8fs-modules/p8fs-api
P8FS_DEBUG=true P8FS_STORAGE_PROVIDER=tidb uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8001
```

**Terminal 2: Test device registration:**
```bash
# Register device with TiDB
cd /Users/sirsh/code/p8fs-modules/p8fs-api
P8FS_STORAGE_PROVIDER=tidb uv run python -m p8fs_api.cli.device --local register \
  --email test@example.com \
  --tenant test-tenant

# Expected output:
# Registering device for test@example.com...
# Using server: http://localhost:8001
# Using dev registration endpoint...
# ✓ Device registered successfully!
#   Tenant ID: test-tenant
#   Token saved to: /Users/username/.p8fs/auth/token.json

# Test token validity
P8FS_STORAGE_PROVIDER=tidb uv run python -m p8fs_api.cli.device --local ping

# Expected output:
# Testing token validity...
# Using server: http://localhost:8001
# ✓ Token is valid!
#   Authenticated: True
#   User ID: dev-xxxxxxxxxxxx
#   Email: test@example.com
#   Tenant ID: tenant-test
```

**Verify in TiDB:**
```bash
# Check tenant was created in TiDB
uv run python -c "
import pymysql

conn = pymysql.connect(host='localhost', port=4000, user='root', database='public')
cursor = conn.cursor()

cursor.execute('SELECT tenant_id, email, active FROM tenants WHERE email=\"test@example.com\"')
tenant = cursor.fetchone()

print(f'Tenant ID: {tenant[0]}')
print(f'Email: {tenant[1]}')
print(f'Active: {tenant[2]}')

cursor.close()
conn.close()
"
```

### OAuth Device Authorization Flow (Recommended)

Test the complete OAuth device flow where one device (mobile) approves another (desktop). This is the **recommended** testing flow for secondary devices.

For the complete step-by-step guide with both PostgreSQL and TiDB, see:
**[`p8fs-auth/docs/dev-testing.md`](/Users/sirsh/code/p8fs-modules/p8fs-auth/docs/dev-testing.md)**

#### Quick Start

```bash
# Terminal 1: Start API server
cd /Users/sirsh/code/p8fs-modules/p8fs-api
P8FS_DEBUG=true P8FS_STORAGE_PROVIDER=tidb uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8001

# Terminal 2: Register primary device (mobile/approving device)
uv run python -m p8fs_api.cli.device --local register --email primary@test.com --tenant tenant-test

# Request device authorization (secondary/desktop device)
uv run python -m p8fs_api.cli.device --local --device-id desktop-001 request-access
# Output: User Code: 4256-97FA

# Approve with primary device (hyphen optional!)
uv run python -m p8fs_api.cli.device --local approve 4256-97FA

# Poll for token (secondary device)
uv run python -m p8fs_api.cli.device --local --device-id desktop-001 poll

# Verify authentication (secondary device)
uv run python -m p8fs_api.cli.device --local --device-id desktop-001 ping
# ✓ Token is valid! Authenticated: True
```

**End state:** Secondary device has a valid JWT token and can make authenticated API requests with automatic token refresh support (when using full OAuth flow, not dev endpoint).

**What happens:**
1. Primary device registers and gets JWT token
2. Secondary device requests authorization → receives `device_code` and `user_code` (e.g., "4256-97FA")
3. Primary device approves using user code with Ed25519 signature (device-bound auth)
4. Server verifies signature, generates access token, updates KV storage (status=approved)
5. Secondary device polls `/oauth/token` → receives JWT access token
6. Secondary device can now make authenticated API requests

### Database Connection with DBeaver

**TiDB Connection:**
1. Open DBeaver → New Connection → MySQL
2. Configure:
   - Server Host: `localhost`
   - Port: `4000`
   - Database: `public`
   - Username: `root`
   - Password: (empty)
3. Test Connection → OK
4. Browse tables:
   - `public` schema: tenants, resources, agents, etc.
   - `embeddings` database: resources_embeddings, agents_embeddings, etc.

**PostgreSQL Connection:**
1. Open DBeaver → New Connection → PostgreSQL
2. Configure:
   - Server Host: `localhost`
   - Port: `5438`
   - Database: `app`
   - Username: `postgres`
   - Password: `postgres`
3. Test Connection → OK
4. Browse tables:
   - `public` schema: tenants, resources, agents, etc.
   - `embeddings` schema: resources_embeddings, agents_embeddings, etc.

### Testing JWT Token Authentication

After registering a device, test that JWT tokens work correctly:

#### Test 1: Ping with Valid Token (CLI)

```bash
# Use CLI device command to ping (uses stored token automatically)
cd /Users/sirsh/code/p8fs-modules/p8fs-api
uv run python -m p8fs_api.cli.device --local ping

# Expected output:
# Testing token validity...
# Using server: http://localhost:8001
# ✓ Token is valid!
#   Authenticated: True
#   User ID: dev-xxxxxxxxxxxx
#   Email: test@example.com
#   Tenant ID: tenant-test
```

#### Test 2: Direct HTTP Request with Token

```bash
# Extract token and save to file
python3 -c "import json; print(json.load(open('~/.p8fs/auth/token.json'.replace('~', '$HOME')))['access_token'])" > /tmp/token.txt

# Use token to authenticate
TOKEN=$(cat /tmp/token.txt)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8001/oauth/ping

# Actual response (200 OK):
{"authenticated":true,"user_id":"dev-xxxxxxxxxxxx","email":"test@example.com","tenant_id":"tenant-test"}
```

#### Test 3: Unauthorized Requests (403/401)

```bash
# Test 3a: No token provided
curl http://localhost:8001/oauth/ping

# Actual response (403 Forbidden):
{"error":"http_error_403","message":"Not authenticated","details":null,"request_id":null}

# Test 3b: Invalid token format
curl -H "Authorization: Bearer invalid-token-here" http://localhost:8001/oauth/ping

# Actual response (401 Unauthorized):
{"error":"http_error_401","message":"AUTH_INVALID_TOKEN: Token validation failed: Not enough segments","details":null,"request_id":null}
```

**Key Takeaways:**
- ✅ Valid JWT token → 200 OK with user info
- ❌ No token → 403 Forbidden ("Not authenticated")
- ❌ Invalid token → 401 Unauthorized ("Token validation failed")
- 🔒 All protected endpoints require `Authorization: Bearer <token>` header

#### Note on Token Refresh

The dev registration endpoint (used with `--local`) issues tokens **without refresh tokens** for quick testing. These tokens expire after 24 hours (`expires_in: 86400` seconds).

For production workflows with refresh token support, use the standard OAuth device flow instead of the dev endpoint.

### Provider Comparison

| Feature | PostgreSQL | TiDB |
|---------|-----------|------|
| **Port** | 5438 | 4000 |
| **Protocol** | PostgreSQL | MySQL |
| **Vector Type** | `vector(1536)` via pgvector | `VECTOR(1536)` native (v8.0+) |
| **Schemas** | PostgreSQL schemas | MySQL databases |
| **Graph** | Apache AGE extension | Not available |
| **Use Case** | Development, testing | Production, distributed |

### Common Issues

**Port already in use:**
```bash
# Find process using port 8001
lsof -ti :8001

# Kill the process
lsof -ti :8001 | xargs kill -9
```

**Database connection failed:**
```bash
# Check containers are running
docker ps | grep -E 'percolate|tidb'

# Restart if needed
cd /Users/sirsh/code/p8fs-modules/p8fs
docker compose restart postgres
# OR
docker compose restart tidb
```

**TiDB migrations not applied:**
```bash
# Verify tables exist
uv run python -c "import pymysql; conn = pymysql.connect(host='localhost', port=4000, user='root', database='public'); cursor = conn.cursor(); cursor.execute('SHOW TABLES'); print('Tables:', len(cursor.fetchall())); cursor.close(); conn.close()"

# If no tables, reapply migrations (see TiDB setup section above)
```

**Token expired:**
```bash
# Register new device
cd /Users/sirsh/code/p8fs-modules/p8fs-api
uv run python -m p8fs_api.cli.device --local register --email test@example.com --tenant test-tenant

# Or refresh existing token (if refresh_token available)
uv run python -m p8fs_api.cli.device --local refresh
```

### Full Documentation

For complete API server documentation including:
- All environment variables
- Hot reload development workflow
- Production deployment
- MCP server configuration
- Detailed troubleshooting

See: `/Users/sirsh/code/p8fs-modules/p8fs-api/docs/local-development.md`

## Next Steps

- **Process your own documents**: Replace sample files with your documents
- **Create custom agents**: Define agents for your specific analysis needs
- **Build workflows**: Chain multiple agents for complex analysis pipelines
- **Deploy workers**: Set up scheduled workers for automatic processing
- **Scale with TiDB**: Switch to TiDB for production deployment
- **Test API authentication**: Start API server and test device registration flows

See full documentation in `docs/` directory for advanced features.
