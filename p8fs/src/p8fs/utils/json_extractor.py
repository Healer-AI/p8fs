"""JSON extraction utilities for parsing LLM responses.

Handles extracting JSON from various formats:
- Plain JSON strings
- Markdown fenced code blocks (```json ... ```)
- Mixed text with JSON objects
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class JSONExtractor:
    """Extract JSON from LLM responses in various formats."""

    @staticmethod
    def extract(response: str) -> Optional[dict]:
        """Extract JSON from response string.

        Tries multiple strategies:
        1. Parse as plain JSON
        2. Extract from markdown fence (```json ... ```)
        3. Find JSON object by brace matching

        Args:
            response: The text response containing JSON

        Returns:
            Parsed JSON dict or None if extraction fails
        """
        # Strategy 1: Check if response is already JSON
        try:
            result_json = json.loads(response)
            logger.info("Response is already valid JSON")
            return result_json
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from markdown fence
        # Look for ```json\n{...}\n``` or ```\n{...}\n```
        fence_start = response.find('```')
        if fence_start != -1:
            # Find the content after the opening fence
            content_start = response.find('\n', fence_start) + 1
            # Find the closing fence
            fence_end = response.find('```', content_start)
            if fence_end != -1:
                json_str = response[content_start:fence_end].strip()
                try:
                    result_json = json.loads(json_str)
                    logger.info("Extracted JSON from markdown fence")
                    return result_json
                except json.JSONDecodeError:
                    pass

        # Strategy 3: Find JSON object by braces
        first_brace = response.find('{')
        last_brace = response.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_str = response[first_brace:last_brace+1]
            try:
                result_json = json.loads(json_str)
                logger.info("Extracted JSON by finding braces")
                return result_json
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON: {json_str[:200]}")

        logger.warning("Could not extract JSON from response")
        return None
