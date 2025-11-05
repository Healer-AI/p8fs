"""Unit tests for moment creation with actual LLM response examples."""

import pytest
from datetime import datetime
from uuid import uuid4

from p8fs.models.engram.models import Moment


class TestMomentCreation:
    """Test moment creation with real LLM response patterns."""

    def test_moment_from_llm_response_with_all_fields(self):
        """Test creating a Moment from a complete LLM response."""
        # This is an actual response from gpt-4.1-mini
        llm_response = {
            "name": "Morning Reflection on Product Launch Anxiety",
            "content": "The user reflected on feelings of anxiety about the upcoming product launch, noting unresolved backend performance issues mentioned by Sarah in a 1:1 meeting. They planned to schedule time with the engineering team to address these concerns and set weekly goals including finalizing marketing materials, completing an investor deck, and exploring an ML certification course.",
            "summary": "Personal reflection on launch anxiety and weekly goal setting.",
            "moment_type": "reflection",
            "emotion_tags": ["anxious", "worried", "focused"],
            "topic_tags": ["product-launch", "backend-performance-issues", "weekly-goals", "marketing-materials", "investor-deck", "ml-certification"],
            "present_persons": [
                {"user_label": "User", "user_id": None, "fingerprint_id": None},
                {"user_label": "Sarah", "user_id": None, "fingerprint_id": None}
            ],
            "location": "Home or personal space (implied)",
            "background_sounds": "None noted",
            "resource_timestamp": "2024-03-18T08:00:00Z",
            "resource_ends_timestamp": "2024-03-18T08:15:00Z"
        }

        # Convert present_persons from list to dict as the worker does
        present_persons = llm_response.get('present_persons', {})
        if isinstance(present_persons, list):
            present_persons = {
                person.get('fingerprint_id') or f'person_{i}': person
                for i, person in enumerate(present_persons)
            }

        # Create Moment instance
        moment = Moment(
            id=uuid4(),
            tenant_id="tenant-test",
            name=llm_response.get('name') or "Untitled Moment",
            content=llm_response.get('content') or llm_response.get('summary') or "",
            summary=llm_response.get('summary'),
            present_persons=present_persons,
            location=llm_response.get('location'),
            moment_type=llm_response.get('moment_type'),
            emotion_tags=llm_response.get('emotion_tags', []),
            topic_tags=llm_response.get('topic_tags', []),
            resource_timestamp=datetime.fromisoformat(llm_response['resource_timestamp'].replace('Z', '+00:00')),
            resource_ends_timestamp=datetime.fromisoformat(llm_response['resource_ends_timestamp'].replace('Z', '+00:00')),
            metadata=llm_response.get('metadata', {})
        )

        assert moment.name == "Morning Reflection on Product Launch Anxiety"
        assert moment.moment_type == "reflection"
        assert len(moment.emotion_tags) == 3
        assert len(moment.topic_tags) == 6
        assert isinstance(moment.present_persons, dict)
        assert moment.resource_timestamp is not None
        assert moment.resource_ends_timestamp is not None

    def test_moment_from_minimal_llm_response(self):
        """Test creating a Moment when LLM returns minimal fields."""
        # Simulates LLM returning only required content + time region
        llm_response = {
            "content": "User had a brief conversation about weekend plans.",
            "resource_timestamp": "2024-03-18T14:00:00Z",
            "resource_ends_timestamp": "2024-03-18T14:05:00Z"
        }

        # Create Moment with defaults
        moment = Moment(
            id=uuid4(),
            tenant_id="tenant-test",
            name=llm_response.get('name') or "Untitled Moment",  # Should default
            content=llm_response.get('content') or "",
            summary=llm_response.get('summary'),  # Can be None
            present_persons=llm_response.get('present_persons') or {},
            location=llm_response.get('location'),
            moment_type=llm_response.get('moment_type'),
            emotion_tags=llm_response.get('emotion_tags', []),
            topic_tags=llm_response.get('topic_tags', []),
            resource_timestamp=datetime.fromisoformat(llm_response['resource_timestamp'].replace('Z', '+00:00')),
            resource_ends_timestamp=datetime.fromisoformat(llm_response['resource_ends_timestamp'].replace('Z', '+00:00')),
            metadata={}
        )

        assert moment.name == "Untitled Moment"  # Default applied
        assert moment.content == "User had a brief conversation about weekend plans."
        assert moment.summary is None  # Can be None
        assert moment.moment_type is None  # Can be None
        assert moment.emotion_tags == []
        assert moment.topic_tags == []
        assert moment.resource_timestamp is not None
        assert moment.resource_ends_timestamp is not None

    def test_moment_fallback_content_from_summary(self):
        """Test that content falls back to summary if not provided."""
        llm_response = {
            "summary": "Quick check-in meeting",
            "resource_timestamp": "2024-03-18T10:00:00Z",
            "resource_ends_timestamp": "2024-03-18T10:10:00Z"
        }

        moment = Moment(
            id=uuid4(),
            tenant_id="tenant-test",
            name="Untitled Moment",
            content=llm_response.get('content') or llm_response.get('summary') or "",
            summary=llm_response.get('summary'),
            present_persons={},
            resource_timestamp=datetime.fromisoformat(llm_response['resource_timestamp'].replace('Z', '+00:00')),
            resource_ends_timestamp=datetime.fromisoformat(llm_response['resource_ends_timestamp'].replace('Z', '+00:00')),
            metadata={}
        )

        assert moment.content == "Quick check-in meeting"  # Fallback worked
        assert moment.summary == "Quick check-in meeting"

    def test_all_actual_llm_moments(self):
        """Test all 4 moments from actual LLM response."""
        # These are ALL 4 actual responses from gpt-4.1-mini for the diary sample
        llm_moments = [
            {
                "name": "Morning Reflection on Product Launch Anxiety",
                "content": "The user reflected on feelings of anxiety about the upcoming product launch...",
                "summary": "Personal reflection on launch anxiety and weekly goal setting.",
                "moment_type": "reflection",
                "emotion_tags": ["anxious", "worried", "focused"],
                "topic_tags": ["product-launch", "backend-performance-issues", "weekly-goals"],
                "resource_timestamp": "2024-03-18T08:00:00Z",
                "resource_ends_timestamp": "2024-03-18T08:15:00Z"
            },
            {
                "name": "Coffee Meeting with Alex from Google",
                "content": "The user met with Alex from Google for coffee to discuss potential collaboration...",
                "summary": "Networking coffee meeting about open source collaboration.",
                "moment_type": "conversation",
                "emotion_tags": ["excited", "optimistic"],
                "topic_tags": ["open-source-collaboration", "career-growth", "networking"],
                "resource_timestamp": "2024-03-18T10:30:00Z",
                "resource_ends_timestamp": "2024-03-18T11:00:00Z"
            },
            {
                "name": "Productive Work Day and Team Concerns",
                "content": "The user completed the marketing copy and received positive feedback...",
                "summary": "Work accomplishments mixed with technical debt concerns.",
                "moment_type": "reflection",
                "emotion_tags": ["productive", "worried"],
                "topic_tags": ["marketing-copy", "technical-debt", "team-capacity", "funding"],
                "resource_timestamp": "2024-03-19T09:00:00Z",
                "resource_ends_timestamp": "2024-03-19T17:00:00Z"
            },
            {
                "name": "Dinner with Mom",
                "content": "The user had dinner with their mother, who is recovering well from surgery...",
                "summary": "Family time supporting mom after surgery.",
                "moment_type": "social",
                "emotion_tags": ["caring", "responsible"],
                "topic_tags": ["family-time", "caregiving", "health"],
                "resource_timestamp": "2024-03-19T18:30:00Z",
                "resource_ends_timestamp": "2024-03-19T20:00:00Z"
            }
        ]

        moments = []
        for llm_moment in llm_moments:
            moment = Moment(
                id=uuid4(),
                tenant_id="tenant-test",
                name=llm_moment.get('name') or "Untitled Moment",
                content=llm_moment.get('content') or "",
                summary=llm_moment.get('summary'),
                present_persons={},
                location=llm_moment.get('location'),
                moment_type=llm_moment.get('moment_type'),
                emotion_tags=llm_moment.get('emotion_tags', []),
                topic_tags=llm_moment.get('topic_tags', []),
                resource_timestamp=datetime.fromisoformat(llm_moment['resource_timestamp'].replace('Z', '+00:00')),
                resource_ends_timestamp=datetime.fromisoformat(llm_moment['resource_ends_timestamp'].replace('Z', '+00:00')),
                metadata={}
            )
            moments.append(moment)

        assert len(moments) == 4
        assert moments[0].moment_type == "reflection"
        assert moments[1].moment_type == "conversation"
        assert moments[2].moment_type == "reflection"
        assert moments[3].moment_type == "social"

        # Verify all have required fields
        for moment in moments:
            assert moment.name is not None
            assert moment.content is not None
            assert moment.resource_timestamp is not None
            assert moment.resource_ends_timestamp is not None
