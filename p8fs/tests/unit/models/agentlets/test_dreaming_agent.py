"""Unit tests for DreamModel."""

from datetime import datetime
import uuid

import pytest
from p8fs.models.agentlets.dreaming import (
    DreamModel, 
    DreamAnalysisMetrics,
    PersonalGoal,
    PersonalFear,
    PersonalDream,
    PendingTask,
    Appointment,
    EntityRelationship,
    UserDataBatch,
    UserDreamAnalysisRequest
)


@pytest.fixture
def sample_metrics():
    """Sample dream analysis metrics."""
    return DreamAnalysisMetrics(
        total_documents_analyzed=5,
        confidence_score=0.8,
        data_completeness=0.9
    )


@pytest.fixture
def sample_dream_model(sample_metrics):
    """Create a sample DreamModel instance."""
    return DreamModel(
        user_id="test-user-123",
        executive_summary="User is focused on career growth and personal development",
        key_themes=["career", "learning", "productivity"],
        metrics=sample_metrics
    )


def test_dream_model_creation(sample_dream_model):
    """Test DreamModel creation with basic fields."""
    assert sample_dream_model.user_id == "test-user-123"
    assert "career growth" in sample_dream_model.executive_summary
    assert len(sample_dream_model.key_themes) == 3
    assert sample_dream_model.metrics.confidence_score == 0.8


def test_dream_model_with_goals():
    """Test DreamModel with personal goals."""
    goal = PersonalGoal(
        goal="Complete Python certification",
        category="learning",
        priority="high",
        deadline="2024-06-01",
        progress_indicators=["study 2 hours daily", "complete practice tests"]
    )
    
    dream_model = DreamModel(
        user_id="test-user",
        executive_summary="Focused on skill development",
        key_themes=["learning"],
        goals=[goal],
        metrics=DreamAnalysisMetrics(
            total_documents_analyzed=1,
            confidence_score=0.9,
            data_completeness=0.8
        )
    )
    
    assert len(dream_model.goals) == 1
    assert dream_model.goals[0].goal == "Complete Python certification"
    assert dream_model.goals[0].category == "learning"


def test_dream_model_with_relationships():
    """Test DreamModel with entity relationships."""
    relationship = EntityRelationship(
        entity1="Alice",
        entity2="TechCorp",
        relationship_type="works_for",
        confidence=0.95,
        evidence="Alice mentioned her role at TechCorp in multiple conversations"
    )
    
    dream_model = DreamModel(
        user_id="test-user",
        executive_summary="User has professional connections",
        key_themes=["work", "relationships"],
        entity_relationships=[relationship],
        metrics=DreamAnalysisMetrics(
            total_documents_analyzed=3,
            confidence_score=0.85,
            data_completeness=0.9
        )
    )
    
    assert len(dream_model.entity_relationships) == 1
    assert dream_model.entity_relationships[0].relationship_type == "works_for"
    assert dream_model.entity_relationships[0].confidence == 0.95


def test_dream_analysis_metrics():
    """Test DreamAnalysisMetrics validation and defaults."""
    metrics = DreamAnalysisMetrics(
        total_documents_analyzed=10,
        confidence_score=0.75,
        data_completeness=0.6
    )
    
    assert metrics.total_documents_analyzed == 10
    assert metrics.confidence_score == 0.75
    assert metrics.data_completeness == 0.6
    assert isinstance(metrics.analysis_date, datetime)


def test_user_data_batch():
    """Test UserDataBatch model."""
    batch = UserDataBatch(
        user_profile={"name": "Test User", "role": "developer"},
        sessions=[{"id": "s1", "content": "test session"}],
        resources=[{"id": "r1", "content": "test resource"}],
        time_window_hours=48
    )
    
    assert batch.user_profile["name"] == "Test User"
    assert len(batch.sessions) == 1
    assert len(batch.resources) == 1
    assert batch.time_window_hours == 48
    assert isinstance(batch.batch_created_at, datetime)


def test_user_dream_analysis_request():
    """Test UserDreamAnalysisRequest model."""
    batch = UserDataBatch(
        user_profile={},
        sessions=[],
        resources=[]
    )
    
    request = UserDreamAnalysisRequest(
        user_id="test-user-123",
        data_batch=batch,
        analysis_depth="comprehensive",
        focus_areas=["goals", "relationships"],
        include_recommendations=True
    )
    
    assert str(request.user_id) == "test-user-123"
    assert request.analysis_depth == "comprehensive"
    assert "goals" in request.focus_areas
    assert request.include_recommendations is True


def test_personal_goal_model():
    """Test PersonalGoal model validation."""
    goal = PersonalGoal(
        goal="Learn machine learning",
        category="education",
        priority="medium",
        progress_indicators=["complete online course", "build project"]
    )
    
    assert goal.goal == "Learn machine learning"
    assert goal.category == "education"
    assert goal.priority == "medium"
    assert goal.deadline is None
    assert len(goal.progress_indicators) == 2


def test_pending_task_model():
    """Test PendingTask model."""
    task = PendingTask(
        task="Schedule dentist appointment",
        category="personal",
        urgency="soon",
        deadline="next week",
        dependencies=["find dentist contact", "check calendar"]
    )
    
    assert task.task == "Schedule dentist appointment"
    assert task.urgency == "soon"
    assert len(task.dependencies) == 2


def test_dream_model_validation():
    """Test DreamModel validation passes with minimal data."""
    # This should not raise an exception even with minimal data
    dream_model = DreamModel(
        user_id="test-user",
        executive_summary="Minimal analysis",
        key_themes=[],
        metrics=DreamAnalysisMetrics(
            total_documents_analyzed=0,
            confidence_score=0.0,
            data_completeness=0.0
        )
    )
    
    assert dream_model.user_id == "test-user"
    assert len(dream_model.goals) == 0
    assert len(dream_model.dreams) == 0