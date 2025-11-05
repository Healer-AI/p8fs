"""Engram data models."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from ..base import AbstractEntityModel
from ..fields import DefaultEmbeddingField


class EngramMetadata(BaseModel):
    """Engram metadata."""
    name: str
    entityType: str = "engram"
    summary: str | None = None
    timestamp: datetime | None = None
    uri: str | None = None
    
    model_config = {"extra": "allow"}


class EngramPatch(BaseModel):
    """Patch operation for existing entity."""
    id: str | None = None  # Support both formats
    entityId: str | None = None
    fields: dict[str, Any] | None = None  # Support both formats  
    updates: dict[str, Any] | None = None


class EngramAssociation(BaseModel):
    """Graph association between entities."""
    # Support both formats from specification
    from_type: str | None = None
    from_id: str | None = None
    to_type: str | None = None  
    to_id: str | None = None
    relationship: str | None = None
    # Legacy format support
    fromEntityId: str | None = None
    toEntityId: str | None = None
    relationType: str | None = None
    metadata: dict[str, Any] | None = None


class EngramSpec(BaseModel):
    """Engram specification with operations."""
    upserts: list[dict[str, Any]] | None = Field(default_factory=list)
    patches: list[EngramPatch] | None = Field(default_factory=list)
    associations: list[EngramAssociation] | None = Field(default_factory=list)


class EngramDocument(BaseModel):
    """Kubernetes-like document for Engram operations."""
    kind: str | None = None
    p8Kind: str | None = None
    metadata: EngramMetadata
    spec: EngramSpec
    
    def is_engram(self) -> bool:
        """Check if document is an Engram."""
        return (self.kind == "engram") or (self.p8Kind == "engram")


class Engram(AbstractEntityModel):
    """Stored Engram entity."""
    tenant_id: str
    name: str
    summary: str | None = DefaultEmbeddingField(None, description="Engram summary for semantic search")
    content: dict[str, Any]
    processed_at: datetime
    upsert_count: int = 0
    patch_count: int = 0
    association_count: int = 0

    model_config = {
        "table_name": "engrams",
        "description": "Processed Engram documents with operations tracking"
    }


class Moment(AbstractEntityModel):
    """Time-bounded segment of content."""
    tenant_id: str
    name: str | None = Field(None, description="Moment name/title")
    content: str | None = DefaultEmbeddingField(None, description="Moment content for semantic search")
    summary: str | None = Field(None, description="Moment summary")
    present_persons: dict[str, Any] | None = Field(default_factory=dict, description="People present during this moment")
    location: str | None = Field(None, description="Location where moment occurred")
    background_sounds: str | None = Field(None, description="Background sounds description")
    moment_type: str | None = Field(None, description="Type of moment (conversation, meeting, etc.)")
    emotion_tags: list[str] | None = Field(default_factory=list, description="Emotional context tags")
    topic_tags: list[str] | None = Field(default_factory=list, description="Topic tags")
    uri: str | None = Field(None, description="Reference to source file or media")
    resource_timestamp: datetime | None = Field(None, description="Original resource timestamp")
    resource_ends_timestamp: datetime | None = Field(None, description="Original resource end timestamp")
    images: list[str] | None = Field(None, description="URIs to representative images")
    speakers: list[dict[str, Any]] | None = Field(None, description="Speaker entries with text, identifier, timestamp, emotion")
    key_emotions: list[str] | None = Field(None, description="Key emotional context tags")
    metadata: dict[str, Any] | None = Field(default_factory=dict, description="Additional metadata")

    model_config = {
        "table_name": "moments",
        "description": "Time-bounded segments of experience with rich metadata",
        "key_field": "id"
    }