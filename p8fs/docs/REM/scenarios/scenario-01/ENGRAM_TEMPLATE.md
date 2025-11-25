# Engram Template for Scenario 1

## Design Principles

### 1. Human-Friendly Labels (NOT Technical IDs)

**Person Names**: Use natural format
- ✅ `id: "Sarah Chen"`, `dst: "Sarah Chen"`
- ❌ `id: "sarah-chen"`, `dst: "person-123"`

**Concepts/Projects**: Use descriptive labels
- ✅ `dst: "API Rate Limiting Issue"`, `dst: "Q4 Roadmap"`
- ❌ `dst: "api-rate-limiting-issue"`, `dst: "project-001"`

**File Paths**: Kebab-case is fine for actual file paths
- ✅ `dst: "docs/api-reference.md"`

### 2. No dst_id in Manual Engrams

The system automatically populates `dst_id` during processing. Never include it in handwritten engrams:

```yaml
# ✅ CORRECT
graph_edges:
  - dst: "Mike Johnson"
    rel_type: "attended_by"
    weight: 1.0
    properties:
      dst_entity_type: "person/employee"
      # NO dst_id field

# ❌ WRONG
graph_edges:
  - dst: "Mike Johnson"
    properties:
      dst_id: "uuid-1234..."  # Don't include this!
```

### 3. Automatic Indexing

When engrams are processed via `repository.upsert()`, the system automatically:
1. Persists to SQL table (resources, moments, etc.)
2. Generates vector embeddings for semantic search
3. Creates graph nodes via p8.add_nodes() for LOOKUP queries
4. Populates graph edges from graph_paths field

You never need to manually manage indexing. Entity graph synchronization happens via p8.add_nodes().

## Template Structure

```yaml
kind: engram
name: "{Natural Event Name}"
category: "{meeting|note|diary|conversation}"
summary: "Brief 1-2 sentence summary of the event"
resource_timestamp: "YYYY-MM-DDTHH:MM:SSZ"
uri: "{optional-uri-to-recording-or-file}"
metadata:
  device:
    model: "{Device Model}"
    app: "{App Name}"
    version: "{App Version}"
  {additional-metadata}:
    key: "value"
content: |
  Detailed content describing what happened.

  Use natural language, full sentences, proper paragraphs.

  Include context that would help semantic search find this later.

graph_edges:
  - dst: "{Human Friendly Label}"
    rel_type: "{relationship-type}"
    weight: {0.0-1.0}
    properties:
      dst_entity_type: "{entity-type}"
      match_type: "{how-relationship-determined}"
      confidence: {0.0-1.0}

moments:
  - name: "{Moment Name}"
    content: "What happened during this segment"
    summary: "Brief summary of this moment"
    resource_timestamp: "YYYY-MM-DDTHH:MM:SSZ"
    resource_ends_timestamp: "YYYY-MM-DDTHH:MM:SSZ"
    moment_type: "{meeting|discussion|decision|planning|reflection}"
    emotion_tags: ["{emotion1}", "{emotion2}"]
    topic_tags: ["{topic-1}", "{topic-2}"]
    present_persons:
      - id: "{Person Natural Name}"
        name: "{Person Natural Name}"
        comment: "{Role or context}"
    speakers:
      - text: "What they said"
        speaker_identifier: "{Speaker Name}"
        timestamp: "YYYY-MM-DDTHH:MM:SSZ"
        emotion: "{emotion}"
    graph_edges:
      - dst: "{Entity Label}"
        rel_type: "{relationship}"
        weight: {0.0-1.0}
        properties:
          dst_entity_type: "{type}"
```

## Common Relationship Types

### Top-Level Engram Edges
- `discusses`: References/discusses an entity
- `relates_to`: General relationship
- `precedes`: Temporal sequence (this before that)
- `follows`: Temporal sequence (this after that)
- `contributes_to`: Contributes to a goal/project

### Moment Edges (within moments array)
- `attended_by`: Person attended this moment
- `discusses`: Topic/concept discussed
- `mentions`: Brief reference to entity
- `decides`: Decision made about entity

## Entity Types (dst_entity_type)

Format: `{schema}/{category}`

**Common Types:**
- `person/employee`
- `project/planning`
- `project/design`
- `concept/technical-issue`
- `concept/methodology`
- `resource/meeting`
- `resource/engram`

## Weight Guidelines

- `1.0`: Primary/strong relationships (attended_by, owns, part_of)
- `0.8-0.9`: Important relationships (discusses, implements, decides)
- `0.5-0.7`: Secondary relationships (relates_to, mentions)
- `0.3-0.4`: Weak relationships (references, cites)

## Example: Meeting Engram

```yaml
kind: engram
name: "Wednesday CEO Sync"
category: "meeting"
summary: "Quick sync with CEO David about Q4 launch timeline and investor demo prep"
resource_timestamp: "2024-11-13T16:00:00Z"
uri: "meeting://ceo-sync/2024-11-13"
metadata:
  device:
    model: "MacBook Pro"
    app: "Meeting Notes"
  meeting:
    duration_minutes: 15
    location: "CEO Office"
content: |
  Brief sync with David (CEO) to confirm November 30 launch date for Vitality app.

  David asked about investor demo readiness. Confirmed that onboarding flow will be
  complete by Friday, giving us two weeks buffer before investor presentation.

  Key points:
  - November 30 launch date confirmed
  - Investor demo scheduled for Nov 28
  - Need final Q4 metrics by Monday

graph_edges:
  - dst: "Launch Timeline"
    rel_type: "discusses"
    weight: 1.0
    properties:
      dst_entity_type: "project/planning"
      match_type: "explicit_reference"

  - dst: "Investor Demo"
    rel_type: "discusses"
    weight: 0.9
    properties:
      dst_entity_type: "concept/business-event"
      match_type: "explicit_reference"

moments:
  - name: "Launch Date Confirmation"
    content: "David confirmed November 30 as the official launch date for Vitality app. This gives us 17 days from today."
    summary: "Nov 30 launch date confirmed by CEO"
    resource_timestamp: "2024-11-13T16:02:00Z"
    resource_ends_timestamp: "2024-11-13T16:08:00Z"
    moment_type: "decision"
    emotion_tags: ["decisive", "committed", "focused"]
    topic_tags: ["launch-timeline", "q4-goals", "vitality-app"]
    present_persons:
      - id: "David Chen"
        name: "David Chen"
        comment: "CEO, made decision"
      - id: "Sarah Chen"
        name: "Sarah Chen"
        comment: "Product Manager, confirmed timeline"
    graph_edges:
      - dst: "David Chen"
        rel_type: "attended_by"
        weight: 1.0
        properties:
          dst_entity_type: "person/executive"
          role: "CEO"

      - dst: "Launch Timeline"
        rel_type: "decides"
        weight: 1.0
        properties:
          dst_entity_type: "project/planning"
```

## Validation Checklist

Before creating new engrams, verify:

- [ ] Person IDs use natural names (no kebab-case)
- [ ] Graph edge `dst` fields use human-friendly labels
- [ ] No `dst_id` fields in properties
- [ ] `dst_entity_type` follows schema/category format
- [ ] Timestamps are in ISO 8601 format with timezone
- [ ] Content is substantial enough for semantic search
- [ ] Emotion tags are lowercase, topic tags are kebab-case
- [ ] Weights reflect relationship strength (0.0-1.0)

## Remaining Engrams for Scenario 1

1. `wed-late-ceo-sync.yaml` - Wednesday late afternoon CEO meeting
2. `thu-morning-user-research.yaml` - Thursday user testing review
3. `thu-afternoon-devops-sync.yaml` - Thursday deployment planning
4. `thu-evening-reflection.yaml` - Thursday personal reflection
5. `fri-morning-standup.yaml` - Friday sprint progress
6. `fri-afternoon-allhands.yaml` - Friday company all-hands
7. `fri-late-oneOnone.yaml` - Friday 1-on-1 with Jamie
8. `sat-morning-testing-thoughts.yaml` - Saturday voice memo
9. `sat-afternoon-test-review.yaml` - Saturday test analysis
10. `sun-evening-weekly-reflection.yaml` - Sunday weekly summary
