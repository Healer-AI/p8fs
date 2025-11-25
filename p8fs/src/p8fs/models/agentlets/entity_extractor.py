"""Entity extraction agent for discovering entities in resource content."""

from typing import Any
from pydantic import BaseModel, Field
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class ExtractedEntity(BaseModel):
    """Single extracted entity."""

    entity_id: str = Field(description="Normalized entity identifier (lowercase-hyphenated)")
    entity_type: str = Field(description="Entity type: Person|Organization|Project|Concept")
    entity_name: str = Field(description="Display name of the entity")
    mentions: int = Field(default=1, description="Number of mentions in content")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence score")
    context: str = Field(description="Brief contextual description")


class EntityExtractionRequest(BaseModel):
    """Request for entity extraction from content."""

    content: str = Field(description="Text content to extract entities from")
    resource_id: str = Field(description="Resource ID for reference")
    resource_type: str | None = Field(None, description="Type of resource (transcript, document, etc.)")


class EntityExtractionResult(BaseModel):
    """Result of entity extraction."""

    entities: list[ExtractedEntity] = Field(description="Extracted entities")
    total_entities: int = Field(description="Total number of entities found")
    resource_id: str = Field(description="Source resource ID")


class EntityExtractorAgent:
    """
    Agent for extracting structured entities from resource content.

    This agent analyzes text content to identify and normalize entities including:
    - People (john-smith, jane-doe, etc.)
    - Organizations (acme-corp, tech-startup-xyz, etc.)
    - Projects (project-alpha, microservices-migration, etc.)
    - Concepts (api-design, oauth-authentication, etc.)

    Entities are normalized to lowercase-hyphenated identifiers for consistency.
    """

    system_prompt = """You are an expert entity extraction system. Your task is to identify and extract entities from text content.

Entity types to extract:
1. **Person**: Names of people (e.g., "John Smith" → john-smith)
2. **Organization**: Companies, teams, departments (e.g., "Acme Corp" → acme-corp)
3. **Project**: Named projects or initiatives (e.g., "Project Alpha" → project-alpha)
4. **Concept**: Important technical concepts or methodologies (e.g., "OAuth 2.1" → oauth-2-1)

For each entity provide:
- **entity_id**: Normalized lowercase identifier with hyphens (e.g., "sarah-chen", "project-alpha")
- **entity_type**: One of Person, Organization, Project, Concept
- **entity_name**: Original display name (e.g., "Sarah Chen", "Project Alpha")
- **mentions**: Count of how many times entity appears
- **confidence**: 0.0-1.0 score based on context clarity
- **context**: Brief description of role/relevance (e.g., "lead engineer", "client company")

Guidelines:
- Normalize entity IDs consistently (lowercase, hyphenated, no special chars)
- Only extract meaningful entities, not every mention
- Higher confidence for entities with clear context
- Combine multiple references to same entity
- Focus on entities that appear important to the content
"""

    async def extract_entities(
        self,
        request: EntityExtractionRequest,
        memory_proxy
    ) -> EntityExtractionResult:
        """
        Extract entities from content using LLM.

        Args:
            request: Extraction request with content and metadata
            memory_proxy: LLM interface for extraction

        Returns:
            EntityExtractionResult with discovered entities
        """
        prompt = f"""Extract entities from the following content:

{request.content[:3000]}  # Limit to first 3000 chars for efficiency

Identify all people, organizations, projects, and key concepts mentioned.
Return structured entity information."""

        try:
            # Use memory proxy to call LLM with structured output
            result = await memory_proxy.query(
                model=EntityExtractionResult,
                request=request,
                prompt=prompt,
                system_prompt=self.system_prompt
            )

            # Ensure resource_id is set
            result.resource_id = request.resource_id
            result.total_entities = len(result.entities)

            logger.info(
                f"Extracted {result.total_entities} entities from resource {request.resource_id}"
            )

            # Log sample entities
            if result.entities:
                sample = result.entities[:3]
                for entity in sample:
                    logger.debug(
                        f"  - {entity.entity_id} ({entity.entity_type}): {entity.entity_name}"
                    )

            return result

        except Exception as e:
            logger.error(f"Entity extraction failed for {request.resource_id}: {e}")
            # Return empty result on failure
            return EntityExtractionResult(
                entities=[],
                total_entities=0,
                resource_id=request.resource_id
            )

    def entities_to_dict_list(self, entities: list[ExtractedEntity]) -> list[dict[str, Any]]:
        """
        Convert ExtractedEntity objects to dict list for storage.

        Args:
            entities: List of ExtractedEntity objects

        Returns:
            List of dicts suitable for JSONB storage
        """
        return [entity.model_dump() for entity in entities]
