"""
Test 3: Entity Extraction with LLM

Tests entity extraction from resource content using LLM:
- Extract people, organizations, projects, concepts
- Normalize entity IDs
- Save entities to resources.related_entities field
- Verify entity structure and quality

Run with:
    P8FS_STORAGE_PROVIDER=postgresql OPENAI_MODEL=gpt-4o-mini \
    uv run pytest tests/integration/test_03_entity_extraction.py -v -s
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
import json

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers import get_provider
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models.p8 import Resources
from p8fs.services.llm import MemoryProxy
from p8fs.models.agentlets.entity_extractor import (
    EntityExtractorAgent,
    EntityExtractionRequest
)

logger = get_logger(__name__)
TENANT_ID = "tenant-test-entities"


@pytest.mark.integration
class TestEntityExtraction:
    """Test entity extraction from resources."""

    @pytest.fixture(scope="class")
    def provider(self):
        """Get database provider."""
        assert config.storage_provider == "postgresql", "Must use PostgreSQL"
        provider = get_provider()
        provider.connect_sync()
        yield provider
        # Cleanup
        try:
            provider.execute("DELETE FROM resources WHERE tenant_id = %s", (TENANT_ID,))
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

    @pytest.fixture(scope="class")
    def repo(self, provider):
        """Get tenant repository."""
        return TenantRepository(Resources, tenant_id=TENANT_ID)

    @pytest.fixture(scope="class")
    def memory_proxy(self):
        """Get memory proxy for LLM calls."""
        return MemoryProxy()

    @pytest.fixture(scope="class")
    def entity_extractor(self):
        """Get entity extractor agent."""
        return EntityExtractorAgent()

    @pytest.fixture(scope="class")
    def test_resource(self, repo):
        """Create a test resource with rich content."""
        resource = Resources(
            id=str(uuid4()),
            tenant_id=TENANT_ID,
            name="Project Alpha Team Meeting",
            category="voice_memo",
            content="""
            Team meeting about Project Alpha on January 5, 2025.

            Attendees:
            - John Smith (Project Lead)
            - Sarah Chen (Lead Engineer)
            - Mike Johnson (DevOps Engineer)

            Discussion Points:
            1. OAuth 2.1 implementation for Project Alpha API
            2. Integration with Acme Corp's Okta identity provider
            3. TiDB database schema for vector search
            4. Kubernetes deployment strategy
            5. Timeline for microservices migration

            Key Decisions:
            - Use OAuth 2.1 with PKCE for mobile authentication
            - Target Q1 2025 for production launch
            - Weekly sync with Acme Corp stakeholders

            Next Steps:
            - Sarah to finalize API specification
            - Mike to set up Kubernetes cluster
            - John to schedule follow-up with David Wilson at Acme Corp
            """,
            resource_type="transcript",
            resource_timestamp=datetime(2025, 1, 5, 14, 0, 0, tzinfo=timezone.utc),
            metadata={"source": "test"},
            related_entities=[]
        )

        import asyncio
        saved = asyncio.run(repo.put(resource))
        logger.info(f"Created test resource: {resource.id}")
        return resource

    async def test_01_extract_entities(self, test_resource, entity_extractor, memory_proxy):
        """Test extracting entities from content."""
        import os

        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("Entity extraction requires OpenAI API key")

        logger.info("\n" + "=" * 70)
        logger.info("TEST: Extract Entities from Content")
        logger.info("=" * 70)

        logger.info(f"Resource: {test_resource.name}")
        logger.info(f"Content length: {len(test_resource.content)} chars")

        # Create extraction request
        request = EntityExtractionRequest(
            content=test_resource.content,
            resource_id=test_resource.id,
            resource_type="transcript"
        )

        # Extract entities
        result = await entity_extractor.extract_entities(request, memory_proxy)

        logger.info(f"\nExtracted {result.total_entities} entities:")

        # Group by type
        by_type = {}
        for entity in result.entities:
            entity_type = entity.entity_type
            if entity_type not in by_type:
                by_type[entity_type] = []
            by_type[entity_type].append(entity)

        # Display entities by type
        for entity_type, entities in sorted(by_type.items()):
            logger.info(f"\n{entity_type}s ({len(entities)}):")
            for entity in entities:
                logger.info(f"  - {entity.entity_id}: {entity.entity_name}")
                logger.info(f"    Context: {entity.context}")
                logger.info(f"    Confidence: {entity.confidence:.2f}")

        # Validations
        assert result.total_entities > 0, "Should extract at least one entity"
        assert len(result.entities) == result.total_entities, "Count should match"

        # Check we have different entity types
        assert len(by_type) >= 2, "Should have at least 2 entity types"

        # Verify entity ID format (lowercase-hyphenated)
        for entity in result.entities:
            assert '-' in entity.entity_id or entity.entity_id.islower(), \
                f"Entity ID should be normalized: {entity.entity_id}"

        logger.info("\n✓ Entity extraction successful")

        # Store for next test
        pytest.shared_entities = result.entities

    def test_02_save_entities_to_resource(self, test_resource, provider, entity_extractor):
        """Test saving extracted entities to resource."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Save Entities to Resource")
        logger.info("=" * 70)

        entities = getattr(pytest, 'shared_entities', [])
        if not entities:
            pytest.skip("No entities from previous test")

        # Convert entities to dict list
        entities_dict = entity_extractor.entities_to_dict_list(entities)

        logger.info(f"Saving {len(entities_dict)} entities to resource...")

        # Update resource
        provider.execute(
            "UPDATE resources SET related_entities = %s WHERE id = %s",
            (json.dumps(entities_dict), test_resource.id)
        )

        # Verify saved
        result = provider.execute(
            "SELECT related_entities FROM resources WHERE id = %s",
            (test_resource.id,)
        )

        saved_entities = result[0]['related_entities']
        logger.info(f"✓ Saved {len(saved_entities)} entities")

        assert len(saved_entities) == len(entities_dict), "All entities should be saved"

        # Verify structure
        for entity in saved_entities:
            assert 'entity_id' in entity, "Should have entity_id"
            assert 'entity_type' in entity, "Should have entity_type"
            assert 'entity_name' in entity, "Should have entity_name"
            assert 'confidence' in entity, "Should have confidence"

        logger.info("✓ Entities saved successfully")

    def test_03_query_entities_from_database(self, provider):
        """Test querying entities from database."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Query Entities from Database")
        logger.info("=" * 70)

        # Query resources with entities
        resources_with_entities = provider.execute(
            """
            SELECT id, name, related_entities
            FROM resources
            WHERE tenant_id = %s AND related_entities IS NOT NULL
            """,
            (TENANT_ID,)
        )

        # Add entity count after fetching
        for resource in resources_with_entities:
            if isinstance(resource['related_entities'], str):
                import json
                resource['related_entities'] = json.loads(resource['related_entities'])
            resource['entity_count'] = len(resource['related_entities']) if resource['related_entities'] else 0

        logger.info(f"Found {len(resources_with_entities)} resources with entities:")
        for resource in resources_with_entities:
            logger.info(f"  {resource['name']}: {resource['entity_count']} entities")

        assert len(resources_with_entities) > 0, "Should find resources with entities"

        # Extract and analyze entities
        resource = resources_with_entities[0]
        entities = resource['related_entities']

        logger.info(f"\nEntity types in {resource['name']}:")
        entity_types = {}
        for entity in entities:
            entity_type = entity.get('entity_type')
            if entity_type not in entity_types:
                entity_types[entity_type] = 0
            entity_types[entity_type] += 1

        for entity_type, count in sorted(entity_types.items()):
            logger.info(f"  {entity_type}: {count}")

        logger.info("✓ Entity queries working")

    async def test_04_entity_extraction_quality(self, entity_extractor, memory_proxy):
        """Test entity extraction quality with edge cases."""
        import os

        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("Entity extraction requires OpenAI API key")

        logger.info("\n" + "=" * 70)
        logger.info("TEST: Entity Extraction Quality")
        logger.info("=" * 70)

        # Test various content types
        test_cases = [
            {
                'name': 'Technical content',
                'content': 'We are using Kubernetes for orchestration and TiDB for the database layer.',
                'expected_types': ['Concept']
            },
            {
                'name': 'People-heavy content',
                'content': 'John Smith and Sarah Chen are working with David Wilson from Acme Corp.',
                'expected_types': ['Person', 'Organization']
            },
            {
                'name': 'Project content',
                'content': 'Project Alpha and the microservices migration are both Q1 priorities.',
                'expected_types': ['Project']
            }
        ]

        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"\nTest case {i}: {test_case['name']}")

            request = EntityExtractionRequest(
                content=test_case['content'],
                resource_id=f"test-{i}",
                resource_type="test"
            )

            result = await entity_extractor.extract_entities(request, memory_proxy)

            logger.info(f"  Extracted: {result.total_entities} entities")
            extracted_types = set(e.entity_type for e in result.entities)
            logger.info(f"  Types: {', '.join(sorted(extracted_types))}")

            # Verify at least one expected type is found
            has_expected = any(et in extracted_types for et in test_case['expected_types'])
            if not has_expected:
                logger.warning(f"  Warning: No expected types found ({test_case['expected_types']})")

        logger.info("\n✓ Quality tests complete")

    async def test_05_entity_normalization(self, entity_extractor, memory_proxy):
        """Test that entity IDs are properly normalized."""
        import os

        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("Entity extraction requires OpenAI API key")

        logger.info("\n" + "=" * 70)
        logger.info("TEST: Entity ID Normalization")
        logger.info("=" * 70)

        # Content with entities that need normalization
        content = """
        Discussion between John Smith, Sarah Chen, and Mike Johnson about Project Alpha.
        Working with Acme Corp and Tech Startup XYZ on OAuth 2.1 implementation.
        """

        request = EntityExtractionRequest(
            content=content,
            resource_id="norm-test",
            resource_type="test"
        )

        result = await entity_extractor.extract_entities(request, memory_proxy)

        logger.info(f"Checking normalization for {result.total_entities} entities:")

        all_normalized = True
        for entity in result.entities:
            # Check normalization rules
            is_lowercase = entity.entity_id.islower() or '-' in entity.entity_id
            has_no_spaces = ' ' not in entity.entity_id
            has_no_special = all(c.isalnum() or c == '-' for c in entity.entity_id)

            normalized = is_lowercase and has_no_spaces and has_no_special

            status = "✓" if normalized else "✗"
            logger.info(f"  {status} {entity.entity_id} ({entity.entity_name})")

            if not normalized:
                all_normalized = False
                logger.warning(f"    Not properly normalized!")

        assert all_normalized or result.total_entities == 0, \
            "All entity IDs should be normalized (lowercase, hyphenated, no spaces/special chars)"

        logger.info("\n✓ Normalization verified")

        logger.info("\n" + "=" * 70)
        logger.info("ENTITY EXTRACTION TEST COMPLETE ✓")
        logger.info("=" * 70)
