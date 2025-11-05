# Moment and Session Model Updates

## Overview
This document tracks the comprehensive updates to Moment and Session models, including new fields for speaker tracking, emotion analysis, session-moment relationships, and API context handling.

## Objectives

### 1. Moment Model Enhancements

#### A. Images Field (COMPLETED)
- **Status**: ✅ Completed
- **Field**: `images: list[str]`
- **Description**: URIs to representative images associated with moments
- **Migration**: Applied to PostgreSQL, TiDB migration created

#### B. Speakers Field (NEW)
- **Status**: 🔄 In Progress
- **Field**: `speakers: list[dict]`
- **Format**: List of speaker dictionaries with structure:
  ```python
  {
      "text": str,              # Spoken text
      "speaker_identifier": str, # Unique speaker ID (e.g., "speaker_1", "user_123")
      "timestamp": datetime,     # When this was spoken
      "emotion": str             # Detected emotion (e.g., "happy", "neutral", "stressed")
  }
  ```
- **Description**: Detailed speaker tracking within moments for conversation analysis

#### C. Key Emotions Field (NEW)
- **Status**: 🔄 In Progress
- **Field**: `key_emotions: list[str]`
- **Description**: High-level emotional context tags for the entire moment
- **Examples**: `["collaborative", "tense", "enthusiastic", "reflective"]`
- **Notes**: Distinct from `emotion_tags` which is more granular. This field captures the dominant emotions across the entire moment.

### 2. Session Model Enhancements

#### A. Moment ID Field (NEW)
- **Status**: 🔄 In Progress
- **Field**: `moment_id: str | None`
- **Description**: Optional reference to a Moment entity ID
- **Purpose**: Links chat sessions to specific moments for contextual awareness
- **Use Case**: When a user is chatting about or during a specific moment

### 3. API Context Management

#### A. X-Moment-Id Header (NEW)
- **Status**: 🔄 In Progress
- **Header**: `X-Moment-Id`
- **Description**: HTTP header to track moment context across API calls
- **Implementation**:
  - Request middleware to extract and validate `X-Moment-Id` header
  - Store in request context for downstream services
  - Automatically save to Session model when creating/updating sessions
- **Location**: p8fs-api request handling

### 4. Chat Search Enhancement

#### A. Moment-Filtered Chat Search (NEW)
- **Status**: 🔄 In Progress
- **Endpoint**: `/chats/search` or similar
- **Parameters**:
  - `query: str` - Search query text
  - `moment_id: str | None` - Optional moment ID filter
  - `limit: int` - Result limit
  - `tenant_id: str` - Tenant identifier
- **Functionality**:
  - Search chat/session content semantically
  - Filter by moment_id when provided
  - Return relevant sessions with moment context

## Database Schema Changes

### Moment Table Additions

**PostgreSQL:**
```sql
ALTER TABLE public.moments
    ADD COLUMN IF NOT EXISTS speakers JSONB,
    ADD COLUMN IF NOT EXISTS key_emotions TEXT[];

CREATE INDEX IF NOT EXISTS idx_moments_speakers_gin ON public.moments USING GIN (speakers);
CREATE INDEX IF NOT EXISTS idx_moments_key_emotions_gin ON public.moments USING GIN (key_emotions);
```

**TiDB:**
```sql
ALTER TABLE moments
    ADD COLUMN IF NOT EXISTS speakers TEXT COMMENT 'JSON array of speaker entries with text, identifier, timestamp, emotion',
    ADD COLUMN IF NOT EXISTS key_emotions TEXT COMMENT 'JSON array of key emotional context tags';
```

### Session Table Additions

**PostgreSQL:**
```sql
ALTER TABLE public.sessions
    ADD COLUMN IF NOT EXISTS moment_id UUID;

CREATE INDEX IF NOT EXISTS idx_sessions_moment_id ON public.sessions (moment_id);
```

**TiDB:**
```sql
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS moment_id VARCHAR(255);

CREATE INDEX idx_sessions_moment_id ON sessions (moment_id);
```

## Migration Strategy

### Incremental Migrations (for Production)
- **File Pattern**: `YYYYMMDD_HHMMSS_add_moment_session_fields.sql`
- **Approach**: ALTER TABLE statements only
- **Safety**: Uses `IF NOT EXISTS` for idempotency
- **Rollback**: Document includes DROP COLUMN statements (commented)

### Full Schema Regeneration (for Documentation)
- **Command**: `uv run python -m p8fs.models.p8 --provider postgres --plan`
- **Purpose**: Complete reference schema for new deployments
- **Location**: `extensions/migrations/{postgres,tidb}/install.sql`

## Implementation Checklist

- [x] Create documentation (this file)
- [ ] Update Moment model in `p8fs/src/p8fs/models/p8.py`
  - [ ] Add `speakers: list[dict]` field
  - [ ] Add `key_emotions: list[str]` field
  - [ ] Update docstrings
- [ ] Update Session model in `p8fs/src/p8fs/models/p8.py`
  - [ ] Add `moment_id: str | None` field
  - [ ] Update docstrings
- [ ] Create incremental migration scripts
  - [ ] PostgreSQL: `20251018_HHMMSS_add_moment_session_fields.sql`
  - [ ] TiDB: `20251018_HHMMSS_add_moment_session_fields.sql`
- [ ] Regenerate full schema scripts
  - [ ] PostgreSQL: `install.sql`
  - [ ] TiDB: `install.sql`
- [ ] Apply migrations to PostgreSQL
- [ ] Apply migrations to TiDB
- [ ] Implement X-Moment-Id context handling in p8fs-api
  - [ ] Request middleware
  - [ ] Context storage
  - [ ] Session integration
- [ ] Create chat search endpoint with moment_id filter
  - [ ] Endpoint implementation
  - [ ] Tests

## Model Changes Reference

### Before (Moment)
```python
class Moment(Resources):
    # ... existing fields ...
    topic_tags: list[str] | None = Field(...)
    images: list[str] | None = Field(...)
```

### After (Moment)
```python
class Moment(Resources):
    # ... existing fields ...
    topic_tags: list[str] | None = Field(...)
    images: list[str] | None = Field(...)
    speakers: list[dict[str, Any]] | None = Field(...)
    key_emotions: list[str] | None = Field(...)
```

### Before (Session)
```python
class Session(AbstractEntityModel):
    # ... existing fields ...
    userid: str | None = Field(...)
```

### After (Session)
```python
class Session(AbstractEntityModel):
    # ... existing fields ...
    userid: str | None = Field(...)
    moment_id: str | None = Field(...)
```

## Testing Strategy

1. **Model Validation**
   - Unit tests for Pydantic models
   - Validate speaker dictionary structure
   - Test optional fields

2. **Migration Testing**
   - Apply to local PostgreSQL
   - Apply to local TiDB
   - Verify schema with `\d` commands

3. **API Testing**
   - Test X-Moment-Id header extraction
   - Test session creation with moment_id
   - Test chat search with moment filter

4. **Integration Testing**
   - End-to-end flow: moment creation → session linking → chat search

## Rollback Plan

If migrations need to be rolled back:

```sql
-- PostgreSQL Rollback
ALTER TABLE public.moments DROP COLUMN IF EXISTS speakers;
ALTER TABLE public.moments DROP COLUMN IF EXISTS key_emotions;
ALTER TABLE public.sessions DROP COLUMN IF EXISTS moment_id;

-- TiDB Rollback
ALTER TABLE moments DROP COLUMN IF EXISTS speakers;
ALTER TABLE moments DROP COLUMN IF EXISTS key_emotions;
ALTER TABLE sessions DROP COLUMN IF EXISTS moment_id;
```

## Notes

- Speaker tracking enables conversation analysis and multi-party moment reconstruction
- Key emotions provide quick emotional context without parsing all speakers
- Session-moment linking enables contextual chat experiences
- X-Moment-Id header allows moment context to flow through API calls
- Chat search filtering by moment enables moment-specific conversation retrieval

## Timeline

- **Start**: 2025-10-18 14:30
- **Model Updates**: In Progress
- **Migration Generation**: Pending
- **Migration Application**: Pending
- **API Implementation**: Pending
- **Testing**: Pending
- **Completion Target**: TBD

## Related Files

- Models: `/Users/sirsh/code/p8fs-modules/p8fs/src/p8fs/models/p8.py`
- Migrations: `/Users/sirsh/code/p8fs-modules/p8fs/extensions/migrations/{postgres,tidb}/`
- API: `/Users/sirsh/code/p8fs-modules/p8fs-api/src/p8fs_api/`
