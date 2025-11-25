"""Isolated integration test for MomentBuilder with fixed transcript data.

This test verifies that MomentBuilder can generate moments from known good data
without involving the database or full dreaming worker flow.
"""

import json
import pytest
from pathlib import Path

from p8fs.models.agentlets.moments import MomentBuilder
from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext


@pytest.fixture
def sample_transcript():
    """Load a sample transcript with known good data."""
    transcript_path = Path(__file__).parent.parent / "sample_data" / "moment_samples" / "tenant_1" / "transcript_2025-01-13T09-00-00Z_input.json"
    with open(transcript_path, 'r') as f:
        return json.load(f)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_moment_builder_generates_moments_from_transcript(sample_transcript):
    """Test that MomentBuilder generates at least one moment from a valid transcript.

    This is the core test to verify MomentBuilder works with real data.
    If this fails, the issue is in the MomentBuilder model itself.
    """
    proxy = MemoryProxy(MomentBuilder)
    context = CallingContext(
        model="gpt-4o",
        tenant_id="test-tenant",
        temperature=0.1,
        max_tokens=8000
    )

    # Call MomentBuilder with real LLM
    result = await proxy.parse_content(
        content=sample_transcript,
        context=context,
        merge_strategy="last"
    )

    # Debug logging
    print(f"\n=== MomentBuilder Result ===")
    print(f"Result type: {type(result)}")
    print(f"Result: {result}")
    if hasattr(result, 'model_dump'):
        result_dict = result.model_dump()
        print(f"Result dict: {json.dumps(result_dict, indent=2, default=str)}")
        print(f"Total moments: {result_dict.get('total_moments', 0)}")
        print(f"Moments count: {len(result_dict.get('moments', []))}")
        print(f"Analysis summary: {result_dict.get('analysis_summary')}")

    # Core assertions
    assert isinstance(result, MomentBuilder), "Result should be a MomentBuilder instance"
    assert hasattr(result, 'moments'), "Result should have moments attribute"
    assert isinstance(result.moments, list), "moments should be a list"

    # This is the critical test - we should get at least 1 moment from the transcript
    assert len(result.moments) > 0, f"Expected at least 1 moment, got {len(result.moments)}. Analysis: {result.analysis_summary if hasattr(result, 'analysis_summary') else 'N/A'}"

    # Verify moment structure
    for i, moment in enumerate(result.moments):
        print(f"\nMoment {i+1}: {json.dumps(moment, indent=2, default=str)}")
        assert 'name' in moment, f"Moment {i} missing 'name'"
        assert 'content' in moment, f"Moment {i} missing 'content'"
        assert 'resource_timestamp' in moment, f"Moment {i} missing 'resource_timestamp'"
        # Accept either 'moment_type' or 'type' field
        assert 'moment_type' in moment or 'type' in moment, f"Moment {i} missing 'moment_type' or 'type'"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_moment_builder_with_simple_text_data():
    """Test MomentBuilder with simple text data instead of transcript.

    This test verifies that MomentBuilder can handle different input formats.
    """
    simple_data = {
        "content": "Had a great meeting with Sarah and Jordan today about the Q4 roadmap. We discussed priorities for the product launch and identified some capacity issues with the engineering team. Overall feeling optimistic but need to address the backend performance concerns.",
        "timestamp": "2025-01-15T14:00:00Z"
    }

    proxy = MemoryProxy(MomentBuilder)
    context = CallingContext(
        model="gpt-4o",
        tenant_id="test-tenant",
        temperature=0.1,
        max_tokens=8000
    )

    result = await proxy.parse_content(
        content=simple_data,
        context=context,
        merge_strategy="last"
    )

    print(f"\n=== Simple Data Result ===")
    if hasattr(result, 'model_dump'):
        print(json.dumps(result.model_dump(), indent=2, default=str))

    assert isinstance(result, MomentBuilder)
    assert len(result.moments) > 0, f"Expected moments from simple text data, got {len(result.moments)}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_moment_builder_with_sessions_and_resources():
    """Test MomentBuilder with format similar to dreaming worker.

    This mimics how the dreaming worker passes data to MomentBuilder.
    """
    data = {
        "sessions": [
            {
                "session_id": "sess_001",
                "created_at": "2025-01-15T10:00:00Z",
                "messages": [
                    {"role": "user", "content": "I'm worried about the deadline for the project"},
                    {"role": "assistant", "content": "What's your main concern?"},
                    {"role": "user", "content": "The backend isn't ready and we launch in 2 weeks"}
                ]
            }
        ],
        "resources": [
            {
                "name": "Meeting Notes - Q4 Planning",
                "content": "Discussed Q4 roadmap with team. Key priorities: 1) Product launch 2) Team capacity 3) Backend performance",
                "created_at": "2025-01-15T09:00:00Z"
            }
        ]
    }

    proxy = MemoryProxy(MomentBuilder)
    context = CallingContext(
        model="gpt-4o",
        tenant_id="test-tenant",
        temperature=0.1,
        max_tokens=8000
    )

    result = await proxy.parse_content(
        content=data,
        context=context,
        merge_strategy="last"
    )

    print(f"\n=== Sessions+Resources Result ===")
    if hasattr(result, 'model_dump'):
        print(json.dumps(result.model_dump(), indent=2, default=str))

    assert isinstance(result, MomentBuilder)
    assert len(result.moments) > 0, f"Expected moments from sessions+resources, got {len(result.moments)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
