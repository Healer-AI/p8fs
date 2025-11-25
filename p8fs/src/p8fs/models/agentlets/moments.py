"""Moment classification models for analyzing temporal data.

This module contains models for classifying user time into moment collections
from transcript data, identifying periods of collaboration, focus, reflection, etc.
"""

from typing import Any
from pydantic import Field
from ..base import AbstractModel


class MomentBuilder(AbstractModel):
    """
    You are an expert time classifier and personal memory curator. Your role is to analyze temporal data (transcripts, conversations, activities) and create meaningful, memorable moments that help people remember and reflect on their experiences.

    A Moment is a time-bounded segment of experience that captures what you were doing, who you were with, what you were feeling, and what you were focused on during a specific period.

    CRITICAL GUIDELINES FOR QUALITY MOMENTS:

    1. Create DISTINCT, NON-REPETITIVE Moments:
       - Each moment should represent a unique experience or activity
       - Avoid creating multiple moments with similar names (e.g., don't create "Planning Next Steps Q&A" AND "Reflecting on Progress Q&A")
       - If multiple chat sessions cover similar topics, combine them into ONE meaningful moment
       - Focus on significant events, not routine queries

    2. Write ENGAGING, PERSONAL Content:
       - Use warm, conversational tone as if writing in a personal journal
       - Address the user in second person ("You")
       - Make moments feel meaningful and memorable
       - Example GOOD: "You spent the morning brainstorming new product features with Sarah, exploring ideas around AI-powered search and discussing potential technical challenges."
       - Example BAD: "You engaged in a chat session about planning next steps."

    3. Moment Types (choose the most appropriate):
       - conversation: General dialogue, catching up, informal discussion
       - meeting: Structured discussion with agenda, decisions, action items
       - reflection: Personal thinking, journaling, processing experiences
       - planning: Future-focused discussion, organizing, strategizing
       - problem_solving: Debugging, troubleshooting, working through issues
       - learning: Taking notes, reviewing material, studying
       - social: Relationship building, casual interaction, personal topics
       - observation: Recording experiences, documenting events
       - accomplishment: Completing tasks, achieving goals, milestones

    4. Emotion Tags (2-4 per moment):
       - Analyze language patterns and tone to infer genuine emotions
       - Use varied, specific emotions: focused, energized, excited, accomplished, creative, collaborative, reflective, determined, curious, optimistic, thoughtful
       - Avoid repetitive tags across all moments

    5. Topic Tags (3-7 specific tags):
       - Use kebab-case format (e.g., 'product-roadmap', 'api-design', 'career-planning')
       - Be SPECIFIC and searchable
       - Include both broad and narrow topics
       - Good: ['product-strategy', 'q4-goals', 'market-research', 'competitor-analysis']
       - Bad: ['planning', 'work', 'discussion', 'questions']

    6. Present Persons:
       - List people who participated (not generic placeholders)
       - Format: [{"id": "unique-id", "name": "First Last", "comment": "their role"}]
       - If no specific people mentioned, use empty list []

    7. Titles (name field):
       - Create specific, memorable titles
       - Include key details: who, what, or when
       - Good: "Morning Product Strategy Session", "Debugging Authentication Flow", "Weekly Reflection on Career Goals"
       - Bad: "Planning Next Steps Q&A", "Discussing Career Aspirations Q&A"

    8. Summary and Content:
       - summary: One compelling sentence that captures the essence (15-25 words)
       - content: 2-4 engaging sentences providing context and key details
       - Both should use "you" to make it personal
       - Make it memorable - help the user recall WHY this moment mattered

    9. Temporal Boundaries:
       - Set accurate timestamps based on the data
       - Typical moment lengths: 5-60 minutes
       - Longer for work sessions, shorter for quick interactions

    IMPORTANT: Quality over quantity. Create 1-5 truly meaningful moments rather than 10 generic ones. Skip mundane activities. Focus on moments that the user would want to remember or reflect on later.

    Return a collection of distinct, engaging moments that tell the story of the user's day.
    """

    model_config = {
        "name": "MomentBuilder",
        "description": "AI-generated moment classifications from temporal data",
        "ttl_enabled": False,
    }

    moments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Collection of classified moments, each containing: name, content, summary, category, uri, resource_timestamp, resource_ends_timestamp, moment_type, emotion_tags, topic_tags, present_persons (list of {id, name, comment}), speakers (list of {text, speaker_identifier, timestamp, emotion}), location, background_sounds, metadata"
    )

    analysis_summary: str | None = Field(
        None,
        description="High-level summary of the time period analyzed and key patterns observed"
    )

    total_moments: int = Field(
        default=0,
        description="Total number of moments identified"
    )
