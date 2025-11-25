"""Engram data models.

Engrams are now stored as Resources (see p8fs.models.p8.Resources).
Moments are stored using the p8fs.models.p8.Moment model.

This module contains helper models for Person and Speaker data structures
used within Moments.
"""

from pydantic import BaseModel, Field


class Person(BaseModel):
    """Person present during a moment."""
    id: str = Field(..., description="Unique identifier for the person (fingerprint_id)")
    name: str = Field(..., description="Display name or label for the person")
    comment: str | None = Field(None, description="Optional comment about the person's role or context")


class Speaker(BaseModel):
    """Speaker entry with utterance details."""
    text: str = Field(..., description="What was said")
    speaker_identifier: str = Field(..., description="Identifier for the speaker")
    timestamp: str = Field(..., description="ISO timestamp of when this was said")
    emotion: str | None = Field(None, description="Detected emotion during this utterance")
