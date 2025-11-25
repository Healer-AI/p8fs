# Engram Specification

## Overview

Engrams are structured memory documents in P8FS that represent captured experiences, observations, or insights. An engram is fundamentally a **Resource** with optional **attached Moments**, leveraging the same unified schema used by the dreaming worker and REM system.

**Key Concepts:**
- Engrams are saved as `Resources` (not a separate model)
- They use the graph edges schema (`InlineEdge`) for relationships
- They can have attached `Moments` for temporal segments
- Device metadata (IMEI, location, etc.) stored in resource metadata
- Saved as YAML files for human readability and version control
- Automatically chunked and embedded for semantic search

## Data Models

### Resource (Base Model)

Engrams use the standard `Resources` pydantic model:

```python
class Resources(AbstractEntityModel):
    """Generic content resources with metadata."""

    name: str                              # Resource name
    category: str | None                   # Resource category (e.g., "engram")
    content: str | None                    # Resource content for semantic search
    summary: str | None                    # Content summary for semantic search
    uri: str | None                        # Resource URI
    metadata: dict[str, Any]               # Resource metadata (device info, etc.)
    graph_paths: list[dict[str, Any]]      # Knowledge graph edges (InlineEdge objects)
    resource_timestamp: datetime | None    # Resource timestamp
    userid: str | None                     # Associated user ID
```

### InlineEdge (Graph Relationships)

Graph relationships use the `InlineEdge` model:

```python
class InlineEdge(BaseModel):
    """Inline graph edge stored within an entity's graph_paths field."""

    dst: str                    # Human-friendly label (e.g., "Daily Team Standup", "Sarah Chen", "api-docs.md")
    rel_type: str              # Relationship type (e.g., "semantic_similar", "followed_by")
    weight: float              # Relationship weight (0.0-1.0)
    properties: dict[str, Any] # Edge properties:
                               #   - dst_name: Display name (usually same as dst)
                               #   - dst_id: Target entity UUID (optional, populated by system)
                               #   - dst_entity_type: Type (e.g., "moment", "resource/engram", "person/employee")
                               #   - match_type: How relationship was determined
                               #   - confidence: Confidence score (0.0-1.0)
```

**CRITICAL DESIGN PRINCIPLE: Human-Friendly Labels**

The `dst` field contains **human-friendly labels** - whatever makes sense to humans:
- ✅ **Person names**: `"Sarah Chen"` (natural), `"sarah-chen"` (legal but potentially confusing)
- ✅ **File paths**: `"docs/setup.md"`, `"/home/user/file.txt"`
- ✅ **URIs**: `"https://example.com/api"`, `"meeting://standup/2024-11-11"`
- ✅ **Concepts**: `"API Rate Limiting Issue"`, `"Q4 Roadmap"`
- ✅ **Technical IDs**: `"resource-001"`, `"uuid-1234"` (legal, but defeats human-friendly purpose)

**What's Legal:**
ANY string is legal in the `dst` field - keys, IDs, URIs, file paths, natural language, etc. There are no technical restrictions.

**What Makes Sense:**
The system is designed for human-friendly labels because:
- Users type natural language: `"Show me everything about Sarah Chen"`
- LOOKUP queries use these labels directly: `LOOKUP "Sarah Chen"`
- The system manages label→UUID mapping internally

**Why `"sarah-chen"` is misleading for person names:**
- Technically legal, but creates confusion
- Users naturally say "Sarah Chen", not "sarah-chen"
- Using kebab-case suggests it's a file path or technical ID
- Better to use what humans actually say/type

**User Uniqueness Responsibility:**
Within a tenant's namespace, the user ensures label uniqueness. If "Sarah Chen" exists as both a person and a project, LOOKUP returns both and the LLM disambiguates based on context.

### Moment (Temporal Segments)

Attached moments use the standard `Moment` model:

```python
class Moment(AbstractEntityModel):
    """Time-bounded segment of experience."""

    name: str                              # Moment name/title
    content: str                           # Moment content/description
    summary: str | None                    # Brief summary
    category: str | None                   # Moment category
    uri: str | None                        # Source URI (can include time fragment)
    resource_timestamp: datetime | None    # Moment start time
    resource_ends_timestamp: datetime | None  # Moment end time
    moment_type: str | None                # Type: conversation, meeting, reflection, etc.
    emotion_tags: list[str]                # Emotional context tags
    topic_tags: list[str]                  # Topic tags (kebab-case)
    present_persons: list[dict]            # People present (Person objects)
    speakers: list[dict] | None            # Speaker segments
    location: str | None                   # GPS coordinates or location
    background_sounds: str | None          # Ambient sounds description
    metadata: dict[str, Any]               # Additional metadata
    graph_paths: list[dict[str, Any]]      # Knowledge graph edges
```

## Engram YAML Format

### Basic Engram

```yaml
kind: engram
name: "Morning Run and Reflection"
category: "diary"
summary: "Morning run and reflection on project goals"
resource_timestamp: "2025-11-16T06:30:00Z"
metadata:
  device:
    imei: "352099001761481"
    model: "iPhone 15 Pro"
    os: "iOS 18.1"
    location:
      latitude: 37.7749
      longitude: -122.4194
      accuracy: 10.5
      altitude: 52.3
content: |
  Beautiful morning run through Golden Gate Park. The weather was perfect -
  crisp air, clear skies. Spent the time thinking about the Q4 roadmap and
  how we can prioritize the mobile features. Feeling energized and ready to
  tackle the sprint planning meeting this afternoon.

graph_edges:
  - dst: "Sprint Planning Meeting"
    rel_type: "precedes"
    weight: 0.8
    properties:
      dst_name: "Sprint Planning Meeting"
      dst_id: "moment-sprint-planning-2025-11-16"
      dst_entity_type: "moment"
      match_type: "temporal_sequence"
      confidence: 0.8
```

### Engram with Attached Moments

```yaml
kind: engram
name: "Daily Team Standup"
category: "meeting"
summary: "Daily standup discussing sprint progress and blockers"
resource_timestamp: "2025-11-16T09:00:00Z"
uri: "s3://recordings/2025/11/16/standup.m4a"
metadata:
  device:
    imei: "352099001761481"
    model: "iPhone 15 Pro"
    app: "Percolate Recorder"
    version: "1.2.0"
content: |
  Daily standup meeting with the engineering team. Discussed sprint progress,
  identified two blockers, and planned pairing sessions for the afternoon.

graph_edges:
  - dst: "Q4 Roadmap Discussion"
    rel_type: "semantic_similar"
    weight: 0.75
    properties:
      dst_name: "Q4 Roadmap Discussion"
      dst_id: "resource-q4-roadmap-2025-11-15"
      dst_entity_type: "resource/meeting"
      match_type: "semantic-basic"
      similarity_score: 0.75
      confidence: 0.75

moments:
  - name: "Sprint Progress Review"
    content: "Sarah reviewed completed tickets and updated the burndown chart"
    summary: "Sprint progress update from Sarah"
    resource_timestamp: "2025-11-16T09:00:00Z"
    resource_ends_timestamp: "2025-11-16T09:05:00Z"
    uri: "s3://recordings/2025/11/16/standup.m4a#t=0,300"
    moment_type: "meeting"
    emotion_tags: ["focused", "productive"]
    topic_tags: ["sprint-progress", "burndown", "velocity"]
    present_persons:
      - id: "sarah"
        name: "Sarah Chen"
        comment: "VP Engineering"
      - id: "mike"
        name: "Mike Johnson"
        comment: "Tech Lead"
    location: "Office Conference Room A"
    background_sounds: "keyboard typing, coffee machine"
    metadata:
      meeting_section: "progress_review"
      tickets_completed: 12
      tickets_remaining: 8

  - name: "Blocker Discussion"
    content: "Mike raised two blockers: API rate limiting and database migration delays"
    summary: "Team discussed two technical blockers"
    resource_timestamp: "2025-11-16T09:05:00Z"
    resource_ends_timestamp: "2025-11-16T09:12:00Z"
    uri: "s3://recordings/2025/11/16/standup.m4a#t=300,720"
    moment_type: "problem_solving"
    emotion_tags: ["concerned", "collaborative"]
    topic_tags: ["blockers", "api-rate-limiting", "database-migration"]
    present_persons:
      - id: "sarah"
        name: "Sarah Chen"
        comment: "VP Engineering"
      - id: "mike"
        name: "Mike Johnson"
        comment: "Tech Lead"
      - id: "alex"
        name: "Alex Rodriguez"
        comment: "Backend Engineer"
    speakers:
      - text: "We're hitting rate limits on the third-party API"
        speaker_identifier: "Mike Johnson"
        timestamp: "2025-11-16T09:05:30Z"
        emotion: "concerned"
      - text: "Let's pair this afternoon to implement exponential backoff"
        speaker_identifier: "Alex Rodriguez"
        timestamp: "2025-11-16T09:06:15Z"
        emotion: "collaborative"
    metadata:
      meeting_section: "blockers"
      blocker_count: 2
      action_items:
        - "Implement API rate limiting backoff"
        - "Complete database migration testing"
    graph_edges:
      - dst: "API Rate Limiting Issue"
        rel_type: "discusses"
        weight: 0.9
        properties:
          dst_name: "API Rate Limiting Issue"
          dst_id: "resource-api-issue-2025-11-15"
          dst_entity_type: "resource/technical-doc"
          match_type: "explicit_reference"
          confidence: 0.9
```

### Device Metadata Example

```yaml
kind: engram
name: "Product Feature Idea - Voice Commands"
category: "note"
summary: "Voice note about new product feature idea during commute"
resource_timestamp: "2025-11-16T08:15:00Z"
metadata:
  device:
    imei: "352099001761481"
    model: "iPhone 15 Pro"
    os: "iOS 18.1"
    app: "Percolate Voice"
    version: "2.1.0"
    location:
      latitude: 37.7749
      longitude: -122.4194
      accuracy: 10.5
      altitude: 52.3
      speed: 15.2
      heading: 180.0
    network:
      type: "cellular"
      carrier: "AT&T"
      signal_strength: -85
content: |
  Had an idea during the commute - we could add voice commands to the mobile app
  for quick note capture. Users could say "Hey Percolate, remember that..." and
  it would create an engram automatically. Would integrate with the existing
  transcription pipeline.

graph_edges:
  - dst: "Mobile App Roadmap"
    rel_type: "contributes_to"
    weight: 0.7
    properties:
      dst_name: "Mobile App Roadmap"
      dst_id: "resource-mobile-roadmap-q4"
      dst_entity_type: "resource/planning"
      match_type: "manual"
      confidence: 1.0
```

## Processing Flow

### 1. Engram Upload

Engrams can be uploaded via:

**API Upload:**
```bash
# Upload YAML engram
curl -X POST http://localhost:8000/api/v1/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@my-engram.yaml"

# Upload JSON engram
curl -X POST http://localhost:8000/api/v1/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @my-engram.json
```

**S3 Upload:**
```
s3://{tenant-bucket}/uploads/{yyyy}/{mm}/{dd}/engram-name.yaml
```

Background workers monitor upload directories and process new files automatically.

### 2. Resource Creation with Dual Indexing

The engram processor creates resources via `repository.upsert()`, which automatically performs dual indexing:

1. **Parses YAML/JSON** into structured data
2. **Creates Resource** with:
   - `name` from top-level name field
   - `category` from top-level category field (or default to "engram")
   - `content` from content field
   - `summary` from top-level summary field
   - `metadata` from metadata field (includes device info, etc.)
   - `graph_paths` from graph_edges (converted to InlineEdge dicts)
   - `resource_timestamp` from top-level resource_timestamp field
3. **Calls `repository.upsert(resource)`** which automatically:
   - **Persists to SQL table** (INSERT or UPDATE)
   - **Generates embeddings** for semantic search (vector index)
   - **Populates entity key index** for LOOKUP queries (reverse key mappings)

**Dual Indexing Contract:**

The caller (engram processor) never manages indexing directly. `upsert()` is contractually obligated to maintain both indexes:

- **Embedding Index**: Vector search on content/summary fields
- **Entity Key Index**: LOOKUP by human-friendly labels
  - PostgreSQL: Stores reverse lookups in KV + creates AGE graph nodes
  - TiDB: Stores reverse key mappings in TiKV

This abstraction ensures LOOKUP queries work immediately after upsert without additional steps.

**CRITICAL: Upsert with JSON Merge Behavior**

Engrams are **ALWAYS upserted with JSON merging**, never overwritten:

- **Graph edges are merged**, not replaced - new edges are added to existing ones
- **Metadata is merged** - new keys are added, existing keys are updated
- **Arrays (emotion_tags, topic_tags) are merged** - duplicates removed
- **Content and summary** are updated if provided
- **Timestamps** are preserved from original if not provided in update

This allows incremental updates to engrams without losing existing relationships or metadata.

**Example:**
```yaml
# First upload creates engram with 1 edge
kind: engram
name: "Q4 Planning Meeting"
graph_edges:
  - dst: "Project Alpha Roadmap"
    rel_type: "discusses"
    weight: 0.8

# Second upload MERGES - now has 2 edges
kind: engram
name: "Q4 Planning Meeting"
graph_edges:
  - dst: "Sarah Chen"
    rel_type: "attended_by"
    weight: 1.0
```

Result: Engram has **both** edges (Project Alpha Roadmap and Sarah Chen), not just the second one.

### 3. Attached Moments Processing

For each moment in the `moments` array:

1. **Create Moment entity** with:
   - All moment fields from YAML
   - `tenant_id` inherited from parent engram
   - Graph edges from moment.graph_edges
2. **Generate embeddings** for moment content
3. **Link to parent** engram via graph edge:
   ```python
   edge = InlineEdge(
       dst="Daily Team Standup",
       rel_type="part_of",
       weight=1.0,
       properties={
           "dst_name": "Daily Team Standup",
           "dst_id": "engram-resource-id",
           "dst_entity_type": "resource/engram",
           "match_type": "parent_child",
           "confidence": 1.0
       }
   )
   ```

### 4. Graph Edge Resolution

Graph edges are stored as InlineEdge objects in the `graph_paths` field:

- **Serialization**: InlineEdge objects → dicts → JSONB in database
- **Deserialization**: JSONB → dicts → validated by Resources model
- **Filtering**: Invalid entries (legacy string paths) automatically filtered by validator

## Implementation

### Engram Processor

```python
from p8fs.workers.engrams import EngramProcessor
from p8fs.models.p8 import Resources, Moment, InlineEdge

# Initialize processor
processor = EngramProcessor(tenant_id="tenant-123")

# Process engram YAML
with open("my-engram.yaml") as f:
    content = f.read()

result = await processor.process_engram(content, "my-engram.yaml")

# Result structure:
# {
#     "resource_id": "uuid-...",
#     "moment_ids": ["uuid-...", "uuid-..."],
#     "chunks_created": 3,
#     "embeddings_generated": 4
# }
```

### Chunking Strategy

Engrams are automatically chunked for optimal embedding:

1. **Summary chunking**: If `summary` exists, create summary chunk
2. **Content chunking**: Split long content using semantic-text-splitter
3. **Moment chunking**: Each moment is a separate chunk
4. **Chunk size**: Optimized based on model (typically 512-2048 tokens)

### Embedding Generation

Embeddings are generated for:

- Resource summary (if present)
- Resource content (if present, chunked if needed)
- Each attached moment content

Embedding provider configured via `P8FS_DEFAULT_EMBEDDING_PROVIDER`.

## Best Practices

### 1. Naming Conventions

- **Engram names**: Use natural, descriptive names that a human would use
  - Good: `"Team Standup Discussion"`, `"Morning Reflection"`, `"Q4 Planning Meeting"`
  - Bad: `"file1"`, `"recording_001"`, `"team-standup-2025-11-16"`

- **Graph edge dst labels**: Use the same natural, user-friendly names as entity labels
  - Good: `"Sprint Planning Meeting"`, `"Sarah Chen"`, `"Project Alpha Roadmap"`
  - Bad: `"uuid-1234-5678-90ab"`, `"rec001"`, `"sprint-planning-meeting"`
  - Note: LOOKUP finds ALL entities with matching labels. If multiple matches exist, the LLM resolves which is intended.

### 2. Categories

Standard categories for engrams:
- `diary`: Personal reflections
- `meeting`: Team meetings
- `note`: Quick notes and ideas
- `observation`: Environmental observations
- `conversation`: Recorded conversations
- `media`: Photos, videos with context

### 3. Device Metadata

Always include device metadata when available:

```yaml
metadata:
  device:
    imei: "device-identifier"
    model: "device-model"
    os: "operating-system"
    app: "app-name"
    version: "app-version"
    location:
      latitude: 37.7749
      longitude: -122.4194
      accuracy: 10.5
      altitude: 52.3
```

### 4. Graph Edges

Use appropriate relationship types:

- `semantic_similar`: Semantic similarity (from dreaming worker)
- `precedes`: Temporal sequence
- `follows`: Temporal sequence (reverse)
- `part_of`: Parent-child relationship
- `discusses`: References/discusses another entity
- `relates_to`: General relationship
- `contributes_to`: Contributes to a goal/project

### 5. Moments Best Practices

- **Granularity**: Each moment should be 15 minutes to 2 hours
- **Present persons**: Always include when known
- **Emotion tags**: 2-4 tags per moment (e.g., "focused", "excited", "concerned")
- **Topic tags**: 3-7 specific tags (e.g., "api-design", "sprint-planning", "q4-roadmap")
- **Speakers**: Include for conversations with timestamps
- **Location**: GPS coordinates or descriptive location

### 6. URI Conventions

- **Full URIs**: Always use complete URIs
  - `s3://bucket/path/to/file.m4a`
  - `seaweedfs://uploads/2025/11/16/recording.wav`

- **Time fragments**: Use RFC 5147 for media fragments
  - `s3://bucket/file.m4a#t=0,300` (0-5 minutes)
  - `s3://bucket/file.m4a#t=300,720` (5-12 minutes)

### 7. Content Quality

- **Summaries**: Write clear, searchable summaries (1-3 sentences)
- **Content**: Include full context for semantic search
- **Timestamps**: Always use ISO 8601 format
- **Metadata**: Include relevant context for filtering and analysis

## Examples

### Personal Diary Entry

```yaml
kind: engram
name: "Evening Reflection on Work-Life Balance"
category: "diary"
summary: "Evening reflection on work-life balance and weekend plans"
resource_timestamp: "2025-11-16T20:30:00Z"
metadata:
  device:
    model: "MacBook Pro"
    app: "Percolate Desktop"
    version: "1.0.5"
content: |
  Reflecting on the week - felt a bit overwhelmed with the sprint deadlines
  but managed to ship the API improvements on time. Team collaboration was
  excellent, especially the pairing session with Alex on the rate limiting fix.

  Looking forward to the weekend - planning to disconnect and spend time with
  family. Need to maintain better work-life boundaries going forward.

moments:
  - name: "Work Reflection"
    content: "Felt overwhelmed with sprint deadlines but proud of API improvements shipped"
    summary: "Mixed feelings about work week - stress but accomplishment"
    resource_timestamp: "2025-11-16T20:30:00Z"
    resource_ends_timestamp: "2025-11-16T20:35:00Z"
    moment_type: "reflection"
    emotion_tags: ["stressed", "proud", "accomplished", "relieved"]
    topic_tags: ["work-life-balance", "sprint-delivery", "api-improvements"]

  - name: "Weekend Planning"
    content: "Planning to disconnect and focus on family time this weekend"
    summary: "Weekend plans focused on rest and family"
    resource_timestamp: "2025-11-16T20:35:00Z"
    resource_ends_timestamp: "2025-11-16T20:37:00Z"
    moment_type: "planning"
    emotion_tags: ["hopeful", "anticipatory", "calm"]
    topic_tags: ["weekend-plans", "family-time", "work-life-balance"]
    present_persons:
      - id: "self"
        name: "Me"
        comment: "Personal reflection"
```

### Voice Memo During Commute

```yaml
kind: engram
name: "Commute Idea - Voice Activation"
category: "note"
summary: "Product idea for voice-activated note capture"
resource_timestamp: "2025-11-16T08:15:00Z"
uri: "s3://recordings/2025/11/16/commute-voice-memo.m4a"
metadata:
  device:
    imei: "352099001761481"
    model: "iPhone 15 Pro"
    app: "Percolate Voice"
    location:
      latitude: 37.7749
      longitude: -122.4194
      speed: 45.5
content: |
  Voice command feature for mobile app - "Hey Percolate, remember that..."
  Creates engrams automatically from voice input. Would be perfect for
  capturing ideas during commutes like this one.

graph_edges:
  - dst: "Mobile App Feature Roadmap"
    rel_type: "contributes_to"
    weight: 0.8
    properties:
      dst_name: "Mobile App Feature Roadmap"
      dst_id: "resource-mobile-roadmap-q4"
      dst_entity_type: "resource/planning"
      match_type: "manual"
      confidence: 1.0
```
