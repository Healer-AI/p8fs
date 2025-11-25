"""Integration test for MomentBuilder model."""

import json
import pytest
from pathlib import Path
from datetime import datetime

from p8fs.models.agentlets.moments import MomentBuilder
from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext


@pytest.fixture
def sample_transcript():
    transcript_path = Path(__file__).parent.parent / "sample_data" / "moment_samples" / "tenant_1" / "transcript_2025-01-13T09-00-00Z_input.json"
    with open(transcript_path, 'r') as f:
        return json.load(f)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_moment_from_transcript(sample_transcript):
    proxy = MemoryProxy(MomentBuilder)
    context = CallingContext(
        model="claude-sonnet-4-5",
        tenant_id="test-tenant",
        temperature=0.1,
        max_tokens=8000
    )

    result = await proxy.parse_content(
        content=sample_transcript,
        context=context,
        merge_strategy="last"
    )

    assert isinstance(result, MomentBuilder)
    assert isinstance(result.moments, list)
    assert len(result.moments) > 0

    for moment in result.moments:
        assert 'name' in moment
        assert 'content' in moment
        assert 'resource_timestamp' in moment
        assert 'moment_type' in moment
        assert moment['moment_type'] in ['conversation', 'meeting', 'observation', 'reflection', 'planning', 'problem_solving', 'learning', 'social']

        if 'emotion_tags' in moment:
            assert isinstance(moment['emotion_tags'], list)

        if 'topic_tags' in moment:
            assert isinstance(moment['topic_tags'], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
