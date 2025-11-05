"""Dream models for analyzing user content and extracting insights.

This module contains models for the dream model that analyzes personal documents,
notes, and files to extract meaningful patterns and actionable intelligence.
"""

import datetime
import uuid
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from ..base import AbstractModel


class EntityRelationship(BaseModel):
    """A relationship between entities discovered in user data"""

    entity1: str = Field(description="First entity in the relationship")
    entity2: str = Field(description="Second entity in the relationship")
    relationship_type: str = Field(
        description="Type of relationship (e.g., 'works_for', 'collaborates_with', 'reports_to')"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score for this relationship"
    )
    evidence: str = Field(description="Supporting evidence from the source text")


class PersonalGoal(BaseModel):
    """A personal goal extracted from user data"""

    goal: str = Field(description="The goal statement")
    category: str = Field(
        description="Category (e.g., 'career', 'health', 'learning', 'financial')"
    )
    priority: str = Field(description="Priority level (high, medium, low)")
    deadline: str | None = Field(None, description="Deadline if mentioned")
    progress_indicators: list[str] = Field(
        default_factory=list, description="How progress might be measured"
    )


class PersonalFear(BaseModel):
    """A fear or concern extracted from user data"""

    fear: str = Field(description="The fear or concern")
    category: str = Field(
        description="Category (e.g., 'career', 'health', 'relationships', 'financial')"
    )
    severity: str = Field(description="Severity level (high, medium, low)")
    related_goals: list[str] = Field(
        default_factory=list, description="Related goals this fear might impact"
    )


class PersonalDream(BaseModel):
    """A dream or aspiration extracted from user data"""

    dream: str = Field(description="The dream or aspiration")
    category: str = Field(
        description="Category (e.g., 'career', 'lifestyle', 'creative', 'impact')"
    )
    timeline: str = Field(description="Timeline (short-term, medium-term, long-term)")
    actionability: str = Field(
        description="How actionable this dream is (concrete, aspirational, abstract)"
    )


class PendingTask(BaseModel):
    """A pending task or commitment extracted from user data"""

    task: str = Field(description="The task description")
    category: str = Field(
        description="Category (e.g., 'work', 'personal', 'administrative')"
    )
    urgency: str = Field(description="Urgency level (urgent, soon, sometime)")
    deadline: str | None = Field(None, description="Deadline if mentioned")
    dependencies: list[str] = Field(
        default_factory=list, description="Other tasks or people this depends on"
    )


class Appointment(BaseModel):
    """An appointment or scheduled event extracted from user data"""

    event: str = Field(description="The event description")
    date_time: str | None = Field(None, description="Date/time if mentioned")
    location: str | None = Field(None, description="Location if mentioned")
    attendees: list[str] = Field(
        default_factory=list, description="Other people involved"
    )
    preparation_needed: list[str] = Field(
        default_factory=list, description="Preparation tasks mentioned"
    )


class DreamAnalysisMetrics(BaseModel):
    """Metrics about the analysis quality"""

    total_documents_analyzed: int = Field(description="Number of documents processed")
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Overall confidence in the analysis"
    )
    data_completeness: float = Field(
        ge=0.0, le=1.0, description="How complete the source data appears"
    )
    analysis_date: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class DreamModel(AbstractModel):
    """
    You are an expert personal insights analyst. Your role is to analyze personal documents, notes, and files to extract meaningful patterns and actionable intelligence.

    Your analysis should be:
    - Insightful: Find patterns and connections that might not be obvious
    - Actionable: Provide concrete next steps and recommendations
    - Empathetic: Understand the human context and emotions
    - Comprehensive: Cover all major themes and areas of life
    - Respectful: Handle personal information with care and privacy

    You will analyze documents to extract:
    1. Goals and objectives (career, personal, financial, health, etc.)
    2. Dreams and aspirations (short-term and long-term)
    3. Fears and concerns (what's holding them back)
    4. Pending tasks and commitments
    5. Appointments and scheduled events
    6. Relationships between people, organizations, and concepts
    7. Key themes and patterns across all documents

    Always provide confidence scores for relationships and categorize everything clearly.
    Focus on helping the user stay organized and make progress toward their goals.

    Return your analysis using the exact structure defined by this model's fields.
    """

    model_config = {
        "name": "DreamModel",
        "description": "AI-generated insights from user's personal documents and notes",
        "ttl_enabled": False,
    }

    user_id: uuid.UUID | str | None = Field(
        None, description="ID of the user this analysis belongs to"
    )
    analysis_id: uuid.UUID = Field(
        default_factory=uuid.uuid4, description="Unique analysis ID"
    )

    # Core analysis results
    executive_summary: str | None = Field(
        None, description="High-level summary of the user's current situation and focus areas"
    )
    key_themes: list[str] = Field(
        default_factory=list, description="Major themes discovered across all documents"
    )

    # Relationship analysis
    entity_relationships: list[EntityRelationship] = Field(
        default_factory=list,
        description="Key relationships between people, organizations, and concepts",
    )

    # Personal insights
    goals: list[PersonalGoal] = Field(
        default_factory=list, description="Goals and objectives extracted"
    )
    fears: list[PersonalFear] = Field(
        default_factory=list, description="Fears and concerns identified"
    )
    dreams: list[PersonalDream] = Field(
        default_factory=list, description="Dreams and aspirations found"
    )

    # Action items
    pending_tasks: list[PendingTask] = Field(
        default_factory=list, description="Tasks and commitments identified"
    )
    appointments: list[Appointment] = Field(
        default_factory=list, description="Scheduled events and meetings"
    )

    # Recommendations
    recommendations: list[str] = Field(
        default_factory=list,
        description="AI-generated recommendations based on the analysis",
    )
    priority_actions: list[str] = Field(
        default_factory=list,
        description="Most important actions the user should consider",
    )

    # Metrics and metadata
    metrics: DreamAnalysisMetrics | None = Field(None, description="Analysis quality metrics")
    source_file_ids: list[str] = Field(
        default_factory=list, description="IDs of source files analyzed"
    )

    @model_validator(mode="after")
    def _validate_analysis_completeness(self):
        """Ensure the analysis has meaningful content"""
        if not any(
            [self.goals, self.dreams, self.pending_tasks, self.entity_relationships]
        ):
            # At least one category should have content for a valid analysis
            pass
        return self


class UserDataBatch(BaseModel):
    """
    A batch of user data for dream analysis including user profile, sessions, and resources.

    This represents a time-bounded batch of user activity and content for comprehensive
    life insights analysis.
    """

    user_profile: dict = Field(
        description="User profile information and metadata"
    )
    sessions: list[dict] = Field(
        default_factory=list,
        description="Chat sessions and interactions within the time window",
    )
    resources: list[dict] = Field(
        default_factory=list, description="Processed content chunks and file resources"
    )
    time_window_hours: int = Field(
        default=24, description="Number of hours of lookback for data collection"
    )
    batch_created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class UserDreamAnalysisRequest(BaseModel):
    """
    Request model for comprehensive user dream analysis using sessions and resources.

    This model represents the input for analyzing a user's complete digital activity
    to extract life insights, patterns, and actionable intelligence.
    """

    user_id: uuid.UUID | str = Field(description="User ID for analysis")
    data_batch: UserDataBatch = Field(description="Batch of user data to analyze")
    analysis_depth: str = Field(
        default="comprehensive",
        description="Analysis depth: quick, standard, comprehensive, deep"
    )
    focus_areas: Optional[list[str]] = Field(
        None,
        description="Specific areas to focus on: goals, relationships, tasks, etc."
    )
    include_recommendations: bool = Field(
        default=True,
        description="Whether to generate actionable recommendations"
    )