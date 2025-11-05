# Engram Specification

## Overview

Engrams are special structured documents that represent memory structures in P8-FS. They use a Kubernetes-like format with `kind`, `metadata`, and `spec` fields. Engrams serve as a universal format for uploading and processing various types of memory-related data.

When an Engram document is uploaded with a summary in its metadata, the system:
1. Stores the Engram itself as a Resource entity
2. Processes the spec operations (upserts, patches, associations)

## Structure

### Base Engram Format

```yaml
kind: engram   
metadata:
  name: "unique-engram-name"
  summary: "Overall summary of the engram content"
  entityType: "models.Moment"  # The target entity type
  timestamp: "2025-08-30T10:00:00Z"
  uri: "s3://bucket/path/to/original/file.wav"
  tenant-id: tenant-123 # the API or file path will also know the tenant anyway
spec:
  upserts: []     # Create or update entities
  patches: []     # Partial updates to existing entities
  associations: [] # Create relationships between entities
```

### JSON Equivalent

```json
{
  "kind": "engram",
  "metadata": {
    "name": "unique-engram-name",
    "summary": "Overall summary of the engram content",
    "entityType": "models.Moment",
    "timestamp": "2025-08-30T10:00:00Z",
    "uri": "s3://bucket/path/to/original/file.wav"
  },
  "spec": {
    "upserts": [],
    "patches": [],
    "associations": []
  }
}
```

## Entity Types

### Moment

Moments are time-bounded segments of experience, typically extracted from audio, video, or other temporal data sources.

**Required Fields (from Resource base class):**
- `tenant_id`: Tenant identifier (normally this will be )
- `content`: The content/transcription of the moment
- `uri`: Reference to the source file
- `resource_timestamp`: Start time of the moment
- `resource_ends_timestamp`: End time of the moment (could be made optional)

**Optional Fields:**
- `present_persons`: Dictionary of people present
  - Key: Fingerprint/voice ID
  - Value: `PresentPerson` object with:
    - `fingerprint_id`: Unique fingerprint/voice ID (required)
    - `user_id`: User ID if identified (optional)
    - `user_label`: Display name (optional)
- `location`: GPS coordinates or location description
- `background_sounds`: Description of ambient sounds
- `moment_type`: Type of moment (conversation, meeting, etc.)
- `emotion_tags`: List of emotional context tags
- `topic_tags`: List of topic tags

A generic `metadata` dict can be used to store anything and we can evolve the core schema over time

## Processing Flow

1. **Engram Upload**: When an Engram is uploaded (JSON/YAML) - we support both API POST and S3 file upload. S3 uploads are asynchronously processed by background workers.

### Upload Methods

#### API Upload
```bash
# Upload YAML Engram via API
curl -X POST http://localhost:8000/api/v1/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@my-engram.yaml"

# Upload JSON Engram via API
curl -X POST http://localhost:8000/api/v1/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @my-engram.json
```

#### Direct S3 Upload
Files should be uploaded to S3 following the tenant-based path convention:

```
https://s3.percolationlabs.ai/{tenant-id}/uploads/{yyyy}/{mm}/{dd}/filename.yaml
```

**Example:**
```
https://s3.percolationlabs.ai/tenant-abc123/uploads/2025/08/30/meeting-transcript.yaml
```

Note: The tenant ID serves as the S3 bucket name, providing complete isolation between tenants.

Files uploaded to S3 are automatically discovered and processed by background workers that monitor the tenant upload directories.

### Processing Steps

2. **Summary Storage**: If `metadata.summary` exists, store the Engram itself as a `models.Engram` resource - a summary will be embedded and stored for search
3. **Entity Processing**: Process spec operations in order:
   - **Upserts**: Create or update entities (entities can be resources, momements etc as per the metadata tag)
   - **Patches**: Apply partial updates (like upserts but we read and merge entities)
   - **Associations**: Create graph relationships

The processor is implemented in `src/p8fs/workers/engrams/processor.py`

## Examples

### Audio Capture with Multiple Moments

```yaml
kind: engram
metadata:
  name: "meeting-2025-08-30-10am"
  summary: "Team standup meeting discussing Q4 roadmap with 3 participants"
  entityType: "models.Moment"
  timestamp: "2025-08-30T10:00:00Z"
  uri: "s3://p8fs-audio/meetings/2025-08-30/standup.wav"
spec:
  upserts:
    - id: "moment-1"
      tenant_id: "tenant-123"
      name: "Opening discussion"
      content: "John opened the meeting by reviewing yesterday's progress"
      summary: "Review of previous day's accomplishments"
      resource_timestamp: "2025-08-30T10:00:00Z"
      resource_ends_timestamp: "2025-08-30T10:05:00Z"
      uri: "s3://p8fs-audio/meetings/2025-08-30/standup.wav#t=0,300"
      present_persons:
        "voice_fp_john123": 
          fingerprint_id: "voice_fp_john123"
          user_id: "user-john-doe"
          user_label: "John Doe"
        "voice_fp_jane456":
          fingerprint_id: "voice_fp_jane456"
          user_id: "user-jane-smith"
          user_label: "Jane Smith"
      location: "37.7749,-122.4194"
      background_sounds: "Office ambience, keyboard typing"
      metadata:
        meeting_type: "standup"
        department: "engineering"
    
    - id: "moment-2"
      tenant_id: "tenant-123"
      name: "Roadmap discussion"
      content: "Jane presented the Q4 roadmap focusing on mobile features"
      summary: "Q4 roadmap presentation and discussion"
      resource_timestamp: "2025-08-30T10:05:00Z"
      resource_ends_timestamp: "2025-08-30T10:15:00Z"
      uri: "s3://p8fs-audio/meetings/2025-08-30/standup.wav#t=300,900"
      present_persons:
        "voice_fp_john123": 
          fingerprint_id: "voice_fp_john123"
          user_id: "user-john-doe"
          user_label: "John Doe"
        "voice_fp_jane456":
          fingerprint_id: "voice_fp_jane456"
          user_id: "user-jane-smith"
          user_label: "Jane Smith"
        "voice_fp_mike789":
          fingerprint_id: "voice_fp_mike789"
          user_id: "user-mike-johnson"
          user_label: "Mike Johnson"
      location: "37.7749,-122.4194"
      background_sounds: "Whiteboard markers, occasional laughter"
      metadata:
        topics: ["mobile", "Q4", "roadmap"]
        action_items: 3

  associations:
    - from_type: "models.Moment"
      from_id: "moment-1"
      to_type: "models.Moment"
      to_id: "moment-2"
      relationship: "followed_by"
    
    - from_type: "models.Moment"
      from_id: "moment-1"
      to_type: "models.User"
      to_id: "user-john-doe"
      relationship: "speaker"
```

### Patch Example - Update Existing Moment

```yaml
kind: engram
metadata:
  name: "moment-update-transcript"
  entityType: "models.Moment"
spec:
  patches:
    - id: "moment-1"
      tenant_id: "tenant-123"
      fields:
        content: "John opened the meeting by reviewing yesterday's progress. He mentioned the API deployment was successful."
        metadata:
          transcription_quality: "high"
          transcription_service: "whisper"
```

### Daily Summary Engram

```yaml
kind: engram
metadata:
  name: "daily-summary-2025-08-30"
  summary: |
    Daily summary for August 30, 2025:
    - 3 meetings (2.5 hours total)
    - 5 important conversations
    - Key topics: Q4 planning, API deployment, mobile features
    - Action items: 7 total, 3 high priority
  entityType: "models.Engram"
  timestamp: "2025-08-30T23:59:59Z"
spec:
  associations:
    - from_type: "models.Engram"
      from_id: "daily-summary-2025-08-30"
      to_type: "models.Moment"
      to_id: "moment-1"
      relationship: "summarizes"
    - from_type: "models.Engram"
      from_id: "daily-summary-2025-08-30"
      to_type: "models.Moment"
      to_id: "moment-2"
      relationship: "summarizes"
```

## Implementation Notes

### Handler Registration

Handlers are registered based on the `kind` field:

```python
handlers = {
    "engram": process_engram,
    "resource": process_resource,
    # Add more handlers as needed
}
```

### Usage Example

```python
from p8fs.workers.engrams import EngramProcessor

# Initialize processor
processor = EngramProcessor(tenant_id="tenant-123")

# Process an Engram file
with open("my-engram.yaml", "r") as f:
    content = f.read()
    
results = await processor.process(content, "my-engram.yaml")
print(f"Processed engram: {results['engram_id']}")
print(f"Created {len(results['upserts'])} entities")
```

## Best Practices

1. **Unique IDs**: Always provide unique IDs for entities to prevent duplicates - tenant itself should be part of the hash
2. **Tenant Isolation**: Always include `tenant_id` for multi-tenant support
3. **S3 Path Convention**: Follow the standard path structure when uploading to S3:
   - `https://s3.percolationlabs.ai/{tenant-id}/uploads/{yyyy}/{mm}/{dd}/filename.yaml`
   - Tenant IDs follow the convention `tenant-{hash}` (e.g., `tenant-abc123`)
   - The tenant ID serves as the S3 bucket name, providing complete isolation between tenants
   - This ensures proper tenant isolation and chronological organization
   - Background workers automatically monitor these paths for processing
4. **URI References**: Use full URIs for file references (S3, SeaweedFS, etc.) - moments are usually processed from other resources like WAV files therefore you should preserve that link - The engram or the individual moments may link to one or more files 
5. **Timestamps**: Use ISO 8601 format for all timestamps
6. **Person Identification**: Use consistent fingerprint/voice IDs across moments
7. **Metadata**: Include relevant metadata for searching and filtering
8. **Summary Quality**: Provide meaningful summaries for better searchability
9. **File Organization**: Use descriptive filenames that include context (e.g., `meeting-standup-2025-08-30.yaml` rather than `file1.yaml`)