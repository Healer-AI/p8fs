# Test Transcript Data Generation for Moments Classification

## Overview

This directory contains test transcript data pairs for evaluating the Moments classification system. Moments are time-bounded segments of experience that integrate all user data sources (audio transcripts, files, images) and classify temporal periods of user activity.

## Moment Model Reference

The `Moment` model is defined in `/Users/sirsh/code/p8fs-modules/p8fs/src/p8fs/models/p8.py:886-954` as a subclass of `Resources`.

### Core Moment Fields

```python
class Moment(Resources):
    """
    Time-bounded segment of experience extracted from temporal data.
    Classifies periods of user activity, conversations, focus, presence, etc.
    """

    # Temporal boundaries
    resource_timestamp: datetime  # Start time (inherited from Resources)
    resource_ends_timestamp: datetime | None  # End time

    # Presence information
    present_persons: dict[str, Any] | None  # People present (fingerprint_id -> PresentPerson)

    # Context
    location: str | None  # GPS coordinates or location description
    background_sounds: str | None  # Ambient sounds or environment

    # Classification
    moment_type: str | None  # 'conversation', 'meeting', 'observation', 'reflection'
    emotion_tags: list[str] | None  # ['happy', 'focused', 'stressed']
    topic_tags: list[str] | None  # Topic tags extracted from content

    # Inherited from Resources
    content: str  # Main content (summary/description)
    summary: str | None  # Brief summary
    name: str  # Moment name/title
    category: str | None  # Moment category
    uri: str  # Source URI
    metadata: dict[str, Any]  # Additional metadata
```

### Present Person Structure

```python
class PresentPerson(AbstractModel):
    fingerprint_id: str  # Unique voice/fingerprint ID
    user_id: str | None  # User ID if identified
    user_label: str | None  # Display name or label
```

## What Moments Classify

Moments describe temporal segments where a user:
- **Collaborates**: Meetings with speakers 1, 2, 3
- **Plans**: Discussing future goals, projects, strategies
- **Focuses**: Deep work on specific topics or problems
- **Reflects**: Personal thoughts, journaling, processing experiences
- **Interacts**: Social conversations, networking
- **Worries**: Concerns, anxieties, problem discussions
- **Creates**: Brainstorming, ideation, creative work
- **Learns**: Taking notes, reviewing information
- **Relocates**: Moving between locations, travel planning

## Test Data Structure

Each test case consists of:

1. **Input Data** (`*_input.json`): 10-minute timestamped transcript
2. **Expected Moment** (`*_expected_moment.json`): Target classification output

### Input Transcript Format

```json
{
  "transcript_id": "unique-id",
  "duration_seconds": 600,
  "start_timestamp": "2025-01-15T09:00:00Z",
  "end_timestamp": "2025-01-15T09:10:00Z",
  "source_uri": "s3://bucket/recording.wav",
  "segments": [
    {
      "timestamp": "2025-01-15T09:00:00Z",
      "speaker_id": "speaker_0",
      "speaker_label": "User",
      "text": "Okay, let's review the Q4 roadmap...",
      "duration_seconds": 12.5
    }
  ],
  "speakers": [
    {
      "speaker_id": "speaker_0",
      "fingerprint_id": "fp_abc123",
      "user_label": "User"
    },
    {
      "speaker_id": "speaker_1",
      "fingerprint_id": "fp_def456",
      "user_label": "Sarah"
    }
  ],
  "environment": {
    "location": "37.7749,-122.4194",
    "background_sounds": "office environment, keyboard typing",
    "recording_quality": "high"
  }
}
```

### Expected Moment Format

```json
{
  "name": "Q4 Planning Discussion with Sarah",
  "content": "Strategic planning meeting discussing Q4 roadmap priorities, focusing on product launches and team capacity. User and Sarah reviewed timeline, identified blockers, and aligned on key deliverables.",
  "summary": "Q4 roadmap planning with Sarah - prioritized launches, discussed capacity",
  "category": "meeting",
  "uri": "s3://bucket/recording.wav",
  "resource_timestamp": "2025-01-15T09:00:00Z",
  "resource_ends_timestamp": "2025-01-15T09:10:00Z",
  "moment_type": "meeting",
  "emotion_tags": ["focused", "collaborative", "optimistic"],
  "topic_tags": ["q4-planning", "product-roadmap", "team-capacity"],
  "present_persons": {
    "fp_abc123": {
      "fingerprint_id": "fp_abc123",
      "user_id": "user_123",
      "user_label": "User"
    },
    "fp_def456": {
      "fingerprint_id": "fp_def456",
      "user_id": "user_456",
      "user_label": "Sarah"
    }
  },
  "location": "37.7749,-122.4194",
  "background_sounds": "office environment, keyboard typing",
  "metadata": {
    "source_type": "audio_transcript",
    "duration_minutes": 10,
    "word_count": 1247,
    "speaker_count": 2
  }
}
```

## Test Case Categories

### 1. Collaborative Meetings
- **Scenario**: Multi-person meetings, planning sessions, reviews
- **Key Features**: Multiple speakers, turn-taking, decision-making
- **Example**: `meeting_planning_001_input.json`

### 2. Solo Planning
- **Scenario**: Individual reflection, voice notes, planning
- **Key Features**: Single speaker, future-focused, organizing thoughts
- **Example**: `solo_planning_001_input.json`

### 3. Problem Solving
- **Scenario**: Debugging, troubleshooting, working through issues
- **Key Features**: Analytical language, iterative thinking, solution finding
- **Example**: `problem_solving_001_input.json`

### 4. Social Conversations
- **Scenario**: Casual discussions, catching up, relationship building
- **Key Features**: Multiple speakers, personal topics, emotional expression
- **Example**: `social_conversation_001_input.json`

### 5. Learning Sessions
- **Scenario**: Taking notes, reviewing material, studying
- **Key Features**: Information processing, summarizing, question-asking
- **Example**: `learning_session_001_input.json`

### 6. Anxiety/Worry Processing
- **Scenario**: Expressing concerns, working through anxiety
- **Key Features**: Emotional language, problem anticipation, self-soothing
- **Example**: `worry_processing_001_input.json`

## Generating Test Data

### Manual Creation

1. Create realistic 10-minute transcript with temporal flow
2. Include speaker metadata and environmental context
3. Generate corresponding Moment classification
4. Validate required fields are present

### LLM-Assisted Generation

```python
# Example: Generate test case using LLM
prompt = """
Generate a realistic 10-minute transcript and corresponding Moment classification for:
- Scenario: Team standup meeting with 3 engineers
- Context: Discussing sprint progress and blockers
- Emotional tone: Focused but slightly stressed
- Include: Realistic dialogue, speaker transitions, timing
"""
```

### Validation Checklist

- [ ] Transcript duration ~600 seconds (10 minutes)
- [ ] Timestamps are sequential and realistic
- [ ] Speaker IDs are consistent throughout
- [ ] Environment data is included
- [ ] Moment classification captures key themes
- [ ] emotion_tags reflect actual emotional content
- [ ] topic_tags are specific and relevant
- [ ] present_persons matches speakers in transcript

## Usage in Evaluation

### Running Eval Tests

```python
from p8fs.evaluation.moments import MomentClassifier

# Load test cases
test_input = load_json("meeting_planning_001_input.json")
expected = load_json("meeting_planning_001_expected_moment.json")

# Run classification
classifier = MomentClassifier()
result = classifier.classify(test_input)

# Compare result vs expected
score = evaluate_moment_match(result, expected)
```

### Evaluation Metrics

1. **Content Accuracy**: Summary captures key points
2. **Temporal Accuracy**: Timestamps and duration correct
3. **Presence Accuracy**: All speakers identified
4. **Classification Accuracy**: moment_type matches scenario
5. **Emotion Detection**: emotion_tags align with tone
6. **Topic Extraction**: topic_tags cover main themes

## Best Practices

### Transcript Realism

- Use natural speech patterns (filler words, pauses, interruptions)
- Include realistic timing (people speak at varying speeds)
- Add environmental details (background sounds, location changes)
- Model real conversation dynamics (turn-taking, overlaps)

### Moment Classification

- Write summaries that a human would find useful
- Choose emotion_tags that reflect actual emotional content
- Select topic_tags that enable later search/retrieval
- Ensure moment_type accurately describes the activity

### Diversity

Generate test cases covering:
- Various speaker counts (1-5)
- Different emotional tones
- Multiple environments (office, home, outdoors)
- Various activity types
- Different time-of-day contexts

## File Naming Convention

```
{scenario}_{type}_{number}_{input|expected_moment}.json

Examples:
- meeting_planning_001_input.json
- meeting_planning_001_expected_moment.json
- solo_reflection_002_input.json
- solo_reflection_002_expected_moment.json
```

## Future Enhancements

- Multi-modal inputs (transcript + image uploads + file metadata)
- Longer duration moments (30min, 1hr)
- Cross-reference with user's uploaded files/documents
- Location transition detection
- Recurring moment pattern recognition
