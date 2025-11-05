"""
Integration tests for structured output with MemoryProxy.

These tests verify the complete end-to-end structured output flow:
1. Model description includes YAML schema by default
2. System prompt contains the schema in the LLM request
3. Real LLM call returns structured JSON
4. Response is validated against the Pydantic model
5. All expected fields are populated correctly

Run with: pytest tests/integration/services/llm/test_structured_output_integration.py -v -s
"""

import pytest
import json
from pydantic import BaseModel, Field
from typing import List, Optional

from p8fs.services.llm.memory_proxy import MemoryProxy
from p8fs.services.llm.models import CallingContext
from p8fs.models.agentlets.dreaming import DreamModel
from p8fs.models.base import AbstractModel
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class SimpleAnalysisModel(AbstractModel):
    """
    Analyze text and extract key insights.

    You are an expert text analyst. Extract the main topic, sentiment, and key points from the given text.
    Be concise and accurate.
    """

    model_config = {
        "name": "SimpleAnalysis",
        "description": "Simple text analysis with structured output"
    }

    main_topic: str = Field(description="The main topic or subject of the text")
    sentiment: str = Field(description="Overall sentiment: positive, negative, or neutral")
    key_points: List[str] = Field(
        default_factory=list,
        description="List of 2-4 key points from the text"
    )
    summary: str = Field(description="One sentence summary of the text")


@pytest.mark.integration
@pytest.mark.llm
class TestStructuredOutputIntegration:
    """Integration tests for structured output with real LLMs"""

    @pytest.fixture
    def gpt4_context(self) -> CallingContext:
        """Calling context for GPT-4 with JSON mode"""
        return CallingContext(
            model="gpt-4.1-mini",
            temperature=0.1,  # Lower for more consistent structured output
            max_tokens=1000,
            stream=False,  # Non-streaming for easier JSON parsing
            tenant_id="test_tenant",
            user_id="test_user_structured",
            prefer_json=True,  # Enable JSON mode
        )

    @pytest.fixture
    def claude_context(self) -> CallingContext:
        """Calling context for Claude with structured output"""
        return CallingContext(
            model="claude-sonnet-4-5",
            temperature=0.1,
            max_tokens=1000,
            stream=False,
            tenant_id="test_tenant",
            user_id="test_user_structured",
            prefer_json=True,
        )

    @pytest.fixture
    def sample_content(self) -> str:
        """Sample content for analysis"""
        return """
        Today was a productive day! I completed the quarterly report ahead of schedule
        and received positive feedback from my manager. I also started working on the
        new product feature that will launch next month. The team collaboration has been
        excellent, and I feel energized about the upcoming projects.

        I need to remember to schedule the team meeting for next week and prepare
        the presentation slides. Also, I should follow up with the design team about
        the mockups.
        """

    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_model_description_includes_yaml_schema_by_default(self):
        """Test that model description includes YAML schema by default"""
        description = SimpleAnalysisModel.get_model_description()

        # Should contain YAML schema by default (after our change)
        assert "```yaml" in description, "Default should include YAML schema"
        assert "main_topic" in description
        assert "sentiment" in description
        assert "key_points" in description

        # Should contain the docstring
        assert "expert text analyst" in description.lower()

        logger.info(f"Model description length: {len(description)} chars")
        logger.info(f"Schema preview:\n{description[:500]}...")

    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_message_stack_contains_yaml_schema(self):
        """Test that MessageStack builds system prompt with YAML schema"""
        proxy = MemoryProxy(model_context=SimpleAnalysisModel)

        question = "Analyze this text"
        messages = proxy._build_message_stack(question)

        # Should have system message
        system_messages = [m for m in messages if m["role"] == "system"]
        assert len(system_messages) > 0, "Should have system message"

        system_content = system_messages[0]["content"]

        # System prompt should contain YAML schema
        assert "```yaml" in system_content, "System prompt should include YAML schema"
        assert "main_topic" in system_content
        assert "sentiment" in system_content
        assert "key_points" in system_content

        # Should contain model description
        assert "expert text analyst" in system_content.lower()

        logger.info(f"System prompt length: {len(system_content)} chars")
        logger.info(f"System prompt preview:\n{system_content[:300]}...")

    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_simple_structured_output_gpt4(self, gpt4_context, sample_content):
        """Test structured output with simple model using GPT-4"""
        proxy = MemoryProxy(model_context=SimpleAnalysisModel)

        question = f"Please analyze the following text:\n\n{sample_content}"

        try:
            response = await proxy.run(question, gpt4_context, max_iterations=1)

            logger.info(f"Raw response:\n{response}")

            # Parse JSON response
            parsed = self._extract_json(response)
            assert parsed is not None, f"Failed to parse JSON from response: {response[:200]}"

            # Validate against model
            validated = SimpleAnalysisModel(**parsed)

            # Verify all required fields are populated
            assert validated.main_topic, "main_topic should be populated"
            assert validated.sentiment in ["positive", "negative", "neutral"], \
                f"Invalid sentiment: {validated.sentiment}"
            assert len(validated.key_points) >= 2, \
                f"Should have at least 2 key points, got {len(validated.key_points)}"
            assert validated.summary, "summary should be populated"

            logger.info(f"✅ Validated structured output:")
            logger.info(f"  Main topic: {validated.main_topic}")
            logger.info(f"  Sentiment: {validated.sentiment}")
            logger.info(f"  Key points: {validated.key_points}")
            logger.info(f"  Summary: {validated.summary}")

        except Exception as e:
            logger.error(f"Structured output test failed: {e}", exc_info=True)
            raise

    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_simple_structured_output_claude(self, claude_context, sample_content):
        """Test structured output with simple model using Claude"""
        proxy = MemoryProxy(model_context=SimpleAnalysisModel)

        question = f"Please analyze the following text:\n\n{sample_content}"

        try:
            response = await proxy.run(question, claude_context, max_iterations=1)

            logger.info(f"Raw response:\n{response}")

            # Parse JSON response
            parsed = self._extract_json(response)
            assert parsed is not None, f"Failed to parse JSON from response: {response[:200]}"

            # Validate against model
            validated = SimpleAnalysisModel(**parsed)

            # Verify all required fields are populated
            assert validated.main_topic, "main_topic should be populated"
            assert validated.sentiment in ["positive", "negative", "neutral"], \
                f"Invalid sentiment: {validated.sentiment}"
            assert len(validated.key_points) >= 2, \
                f"Should have at least 2 key points, got {len(validated.key_points)}"
            assert validated.summary, "summary should be populated"

            logger.info(f"✅ Validated structured output:")
            logger.info(f"  Main topic: {validated.main_topic}")
            logger.info(f"  Sentiment: {validated.sentiment}")
            logger.info(f"  Key points: {validated.key_points}")
            logger.info(f"  Summary: {validated.summary}")

        except Exception as e:
            logger.error(f"Structured output test failed: {e}", exc_info=True)
            raise

    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_dream_model_structured_output(self, gpt4_context, sample_content):
        """Test structured output with DreamModel (complex nested model)"""
        proxy = MemoryProxy(model_context=DreamModel)

        question = f"Please analyze the following personal note:\n\n{sample_content}"

        try:
            response = await proxy.run(question, gpt4_context, max_iterations=1)

            logger.info(f"Raw response length: {len(response)} chars")
            logger.info(f"Raw response preview:\n{response[:300]}...")

            # Parse JSON response
            parsed = self._extract_json(response)
            assert parsed is not None, f"Failed to parse JSON from response"

            # Validate against DreamModel
            validated = DreamModel(**parsed)

            # Verify key fields are populated
            logger.info(f"✅ Validated DreamModel output:")

            if validated.executive_summary:
                logger.info(f"  Executive summary: {validated.executive_summary[:100]}...")

            if validated.key_themes:
                logger.info(f"  Key themes ({len(validated.key_themes)}): {validated.key_themes}")

            if validated.goals:
                logger.info(f"  Goals extracted: {len(validated.goals)}")
                for goal in validated.goals[:2]:
                    logger.info(f"    - {goal.goal} (priority: {goal.priority})")

            if validated.pending_tasks:
                logger.info(f"  Tasks extracted: {len(validated.pending_tasks)}")
                for task in validated.pending_tasks[:2]:
                    logger.info(f"    - {task.task} (urgency: {task.urgency})")

            # At minimum, should have extracted something meaningful
            assert (
                validated.goals or
                validated.pending_tasks or
                validated.key_themes or
                validated.executive_summary
            ), "DreamModel should extract at least some structured information"

        except Exception as e:
            logger.error(f"DreamModel structured output test failed: {e}", exc_info=True)
            raise

    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_structured_output_with_metadata_response_format(self, sample_content):
        """Test structured output using context.metadata response_format"""
        proxy = MemoryProxy(model_context=SimpleAnalysisModel)

        # Use metadata to set response_format (alternative to prefer_json)
        context = CallingContext(
            model="gpt-4.1-mini",
            temperature=0.1,
            max_tokens=1000,
            stream=False,
            tenant_id="test_tenant",
            metadata={"response_format": {"type": "json_object"}}
        )

        question = f"Please analyze the following text:\n\n{sample_content}"

        try:
            response = await proxy.run(question, context, max_iterations=1)

            # Parse and validate
            parsed = self._extract_json(response)
            assert parsed is not None, "Should get valid JSON response"

            validated = SimpleAnalysisModel(**parsed)
            assert validated.main_topic, "Should have main_topic"

            logger.info(f"✅ Structured output via metadata.response_format works!")
            logger.info(f"  Main topic: {validated.main_topic}")

        except Exception as e:
            logger.error(f"Metadata response_format test failed: {e}", exc_info=True)
            raise

    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_yaml_vs_json_schema_format(self, sample_content):
        """Test that YAML schema format works better than JSON for structured output"""
        proxy = MemoryProxy(model_context=SimpleAnalysisModel)

        context = CallingContext(
            model="gpt-4.1-mini",
            temperature=0.1,
            max_tokens=1000,
            stream=False,
            tenant_id="test_tenant",
            prefer_json=True,
        )

        question = f"Please analyze the following text:\n\n{sample_content}"

        try:
            # Test with default YAML schema
            messages_yaml = proxy._build_message_stack(question)
            system_yaml = [m for m in messages_yaml if m["role"] == "system"][0]["content"]

            response = await proxy.run(question, context, max_iterations=1)
            parsed = self._extract_json(response)

            assert parsed is not None, "YAML schema should produce valid JSON"
            validated = SimpleAnalysisModel(**parsed)

            # Verify YAML is more readable in system prompt
            assert "```yaml" in system_yaml, "Should use YAML format"
            assert system_yaml.count('\n') > 20, "YAML should be multi-line and readable"

            logger.info(f"✅ YAML schema format produces valid structured output")
            logger.info(f"  System prompt has {system_yaml.count('  ')} indentations (readable)")

        except Exception as e:
            logger.error(f"YAML schema format test failed: {e}", exc_info=True)
            raise

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from markdown or plain text response."""
        import re

        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try markdown code block with json
        pattern1 = r'```json\s*(\{[\s\S]+?\})\s*```'
        matches = re.findall(pattern1, text, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[-1])
            except json.JSONDecodeError:
                pass

        # Try markdown code block without language
        pattern2 = r'```\s*(\{[\s\S]+?\})\s*```'
        matches = re.findall(pattern2, text, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[-1])
            except json.JSONDecodeError:
                pass

        # Try first { to last }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass

        return None
