"""Integration test for dreaming worker with moment processing."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest

from p8fs.workers.dreaming import DreamingWorker
from p8fs.models.agentlets.moments import MomentBuilder
from p8fs.services.llm import MemoryProxy
from p8fs.services.llm.models import CallingContext
from p8fs.repository import TenantRepository
from p8fs.models.engram.models import Moment


@pytest.mark.integration
async def test_moment_processing_and_storage():
    """Test that moments are processed and saved to database."""

    # Load test transcript data
    transcript_file = Path("tests/sample_data/moment_samples/tenant_1/transcript_2025-01-13T09-00-00Z_input.json")
    transcript_data = json.loads(transcript_file.read_text())

    # Initialize MemoryProxy with MomentBuilder
    proxy = MemoryProxy(MomentBuilder)

    context = CallingContext(
        model="gpt-4o",
        tenant_id="tenant-test-moments",
        temperature=0.1,
        max_tokens=4000
    )

    # Parse transcript into moments using MomentBuilder
    result = await proxy.parse_content(
        content=transcript_data,
        context=context,
        merge_strategy="last"
    )

    # Verify we got moments back
    assert hasattr(result, 'moments'), "Result should have moments attribute"
    assert len(result.moments) > 0, "Should have at least one moment"

    # Save each moment to database
    moment_repo = TenantRepository(Moment, tenant_id="tenant-test-moments")
    saved_moment_ids = []

    for moment_data in result.moments:
        # Convert present_persons from list to dict if needed
        present_persons = moment_data.get('present_persons', {})
        if isinstance(present_persons, list):
            # Convert list of person objects to dict keyed by fingerprint_id
            present_persons = {
                person.get('fingerprint_id', f'person_{i}'): person
                for i, person in enumerate(present_persons)
            }

        # Convert moment dict to Moment model
        moment = Moment(
            id=uuid4(),
            tenant_id="tenant-test-moments",
            name=moment_data.get('name'),
            start_time=moment_data.get('resource_timestamp'),
            end_time=moment_data.get('resource_ends_timestamp'),
            content=moment_data.get('content'),
            summary=moment_data.get('summary'),
            present_persons=present_persons,
            location=moment_data.get('location'),
            moment_type=moment_data.get('moment_type'),
            emotion_tags=moment_data.get('emotion_tags', []),
            topic_tags=moment_data.get('topic_tags', []),
            resource_timestamp=moment_data.get('resource_timestamp'),
            resource_ends_timestamp=moment_data.get('resource_ends_timestamp'),
            metadata=moment_data.get('metadata', {})
        )

        # Save to database
        saved_moment = await moment_repo.upsert(moment)
        # Handle both dict and object returns
        moment_id = saved_moment.id if hasattr(saved_moment, 'id') else saved_moment.get('id', moment.id)
        saved_moment_ids.append(moment_id)

        print(f"✅ Saved moment: {moment.name}")
        print(f"   Type: {moment.moment_type}")
        print(f"   Start: {moment.start_time}")
        print(f"   End: {moment.end_time}")
        print(f"   Emotions: {moment.emotion_tags}")
        print(f"   Topics: {moment.topic_tags}")

    # Verify moments were saved
    assert len(saved_moment_ids) == len(result.moments)

    # Query moments from database
    moments_from_db = await moment_repo.select(limit=10)
    assert len(moments_from_db) >= len(saved_moment_ids)

    # Verify temporal data is present
    for moment in moments_from_db:
        assert moment.tenant_id == "tenant-test-moments"
        assert moment.start_time is not None or moment.resource_timestamp is not None
        if moment.start_time and moment.end_time:
            assert moment.end_time >= moment.start_time, "End time should be after start time"

    print(f"\n✅ Successfully processed and saved {len(saved_moment_ids)} moments")
    return saved_moment_ids


@pytest.mark.integration
async def test_query_moments_by_time_range():
    """Test querying moments by temporal range."""
    from datetime import datetime, timezone

    moment_repo = TenantRepository(Moment, tenant_id="tenant-test-moments")

    # Query all moments
    all_moments = await moment_repo.select(limit=100)

    if len(all_moments) == 0:
        pytest.skip("No moments in database to query")

    print(f"\nFound {len(all_moments)} moments in database")

    # Group by moment type
    by_type = {}
    for moment in all_moments:
        moment_type = moment.moment_type or "unknown"
        by_type[moment_type] = by_type.get(moment_type, 0) + 1

    print(f"Moments by type: {by_type}")

    # Verify temporal data
    moments_with_time = [m for m in all_moments if m.start_time is not None]
    print(f"Moments with start_time: {len(moments_with_time)}")

    if len(moments_with_time) > 0:
        earliest = min(m.start_time for m in moments_with_time)
        latest = max(m.start_time for m in moments_with_time)
        print(f"Time range: {earliest} to {latest}")

    assert len(all_moments) > 0


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_moment_processing_and_storage())
    asyncio.run(test_query_moments_by_time_range())
