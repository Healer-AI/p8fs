"""Tests for JSON extraction utility."""

import pytest
from p8fs.utils.json_extractor import JSONExtractor


class TestJSONExtractor:
    """Test the JSONExtractor utility."""

    def test_extract_plain_json(self):
        """Test extraction of plain JSON string."""
        response = '{"key": "value", "number": 42}'
        result = JSONExtractor.extract(response)
        assert result == {"key": "value", "number": 42}

    def test_extract_from_markdown_fence_with_json_label(self):
        """Test extraction from ```json fence."""
        response = """Here's the analysis:

```json
{
  "key": "value",
  "nested": {
    "field": "data"
  }
}
```

That's all!"""
        result = JSONExtractor.extract(response)
        assert result is not None
        assert result["key"] == "value"
        assert result["nested"]["field"] == "data"

    def test_extract_from_markdown_fence_without_label(self):
        """Test extraction from ``` fence without json label."""
        response = """Analysis follows:

```
{
  "analysis_id": "test-123",
  "summary": "Test summary"
}
```
"""
        result = JSONExtractor.extract(response)
        assert result is not None
        assert result["analysis_id"] == "test-123"
        assert result["summary"] == "Test summary"

    def test_extract_with_preamble_text(self):
        """Test extraction when JSON has text preamble."""
        response = """I'll analyze this content for you.

```json
{
  "user_id": null,
  "analysis_id": "abc-123",
  "key_themes": ["theme1", "theme2"]
}
```

This completes the analysis."""
        result = JSONExtractor.extract(response)
        assert result is not None
        assert result["analysis_id"] == "abc-123"
        assert len(result["key_themes"]) == 2

    def test_extract_nested_objects(self):
        """Test extraction of deeply nested JSON."""
        response = """```json
{
  "level1": {
    "level2": {
      "level3": {
        "value": "deep"
      }
    }
  }
}
```"""
        result = JSONExtractor.extract(response)
        assert result is not None
        assert result["level1"]["level2"]["level3"]["value"] == "deep"

    def test_extract_by_braces_fallback(self):
        """Test fallback to brace matching when no fence."""
        response = """Some text before { "key": "value", "array": [1, 2, 3] } some text after"""
        result = JSONExtractor.extract(response)
        assert result is not None
        assert result["key"] == "value"
        assert result["array"] == [1, 2, 3]

    def test_extract_returns_none_for_invalid(self):
        """Test that invalid JSON returns None."""
        response = "This is just plain text with no JSON"
        result = JSONExtractor.extract(response)
        assert result is None

    def test_extract_handles_arrays(self):
        """Test extraction of JSON arrays."""
        response = '["item1", "item2", "item3"]'
        result = JSONExtractor.extract(response)
        # Extractor supports both objects and arrays
        assert result == ["item1", "item2", "item3"]

    def test_extract_real_claude_response(self):
        """Test with realistic Claude response format."""
        response = """I'll analyze this personal journal entry to extract meaningful insights.

```json
{
  "user_id": null,
  "analysis_id": "test-abc-123",
  "executive_summary": "This entry shows a busy professional balancing work and personal commitments.",
  "key_themes": [
    "work-life balance",
    "startup challenges",
    "family responsibilities"
  ],
  "goals": [
    {
      "goal": "Complete product launch",
      "category": "work",
      "timeframe": "end of month",
      "priority": "high"
    }
  ],
  "pending_tasks": [],
  "recommendations": ["Take time for self-care", "Delegate more tasks"]
}
```

This analysis captures the key elements from the journal entry."""
        result = JSONExtractor.extract(response)
        assert result is not None
        assert result["analysis_id"] == "test-abc-123"
        assert "work-life balance" in result["key_themes"]
        assert len(result["goals"]) == 1
        assert result["goals"][0]["priority"] == "high"
