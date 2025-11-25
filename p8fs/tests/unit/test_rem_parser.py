"""
Unit tests for REM Query Parser.

Tests parsing of REM query strings into query plans.
"""

import pytest
from p8fs.query.rem_parser import REMQueryParser
from p8fs.providers.rem_query import QueryType, LookupParameters


class TestREMQueryParser:
    """Test REM query parser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = REMQueryParser(default_table="resources", tenant_id="tenant-test")

    def test_parse_single_key_lookup(self):
        """Test parsing LOOKUP with single key."""
        plan = self.parser.parse("LOOKUP test-resource-1")

        assert plan.query_type == QueryType.LOOKUP
        assert isinstance(plan.parameters, LookupParameters)
        assert plan.parameters.key == "test-resource-1"
        assert plan.parameters.table_name == "resources"

    def test_parse_multiple_keys_lookup(self):
        """Test parsing LOOKUP with comma-separated keys."""
        plan = self.parser.parse("LOOKUP key1, key2, key3")

        assert plan.query_type == QueryType.LOOKUP
        assert isinstance(plan.parameters, LookupParameters)
        assert plan.parameters.key == ["key1", "key2", "key3"]
        assert plan.parameters.table_name == "resources"

    def test_parse_multiple_keys_with_quotes(self):
        """Test parsing LOOKUP with quoted keys."""
        plan = self.parser.parse('LOOKUP "key1", "key2", "key3"')

        assert plan.query_type == QueryType.LOOKUP
        assert plan.parameters.key == ["key1", "key2", "key3"]

    def test_parse_multiple_keys_mixed_quotes(self):
        """Test parsing LOOKUP with mixed quote styles."""
        plan = self.parser.parse("LOOKUP 'key1', key2, \"key3\"")

        assert plan.query_type == QueryType.LOOKUP
        assert plan.parameters.key == ["key1", "key2", "key3"]

    def test_parse_single_key_with_table(self):
        """Test parsing LOOKUP with table:key format."""
        plan = self.parser.parse("LOOKUP moments:my-moment")

        assert plan.query_type == QueryType.LOOKUP
        assert plan.parameters.key == "my-moment"
        assert plan.parameters.table_name == "moments"

    def test_parse_get_alias(self):
        """Test parsing GET as alias for LOOKUP."""
        plan = self.parser.parse("GET test-resource-1")

        assert plan.query_type == QueryType.LOOKUP
        assert plan.parameters.key == "test-resource-1"

    def test_parse_multiple_keys_with_spaces(self):
        """Test parsing LOOKUP with spaces around commas."""
        plan = self.parser.parse("LOOKUP key1 , key2 , key3")

        assert plan.query_type == QueryType.LOOKUP
        assert plan.parameters.key == ["key1", "key2", "key3"]

    def test_parse_uuid_keys(self):
        """Test parsing LOOKUP with UUID keys."""
        uuid1 = "550e8400-e29b-41d4-a716-446655440000"
        uuid2 = "550e8400-e29b-41d4-a716-446655440001"

        plan = self.parser.parse(f"LOOKUP {uuid1}, {uuid2}")

        assert plan.query_type == QueryType.LOOKUP
        assert plan.parameters.key == [uuid1, uuid2]

    def test_parse_empty_keys_filtered(self):
        """Test that empty keys are filtered out."""
        plan = self.parser.parse("LOOKUP key1, , key2")

        assert plan.query_type == QueryType.LOOKUP
        assert plan.parameters.key == ["key1", "key2"]

    def test_parse_single_key_after_comma_split(self):
        """Test that single key after filtering stays as string."""
        plan = self.parser.parse("LOOKUP key1")

        assert plan.query_type == QueryType.LOOKUP
        assert plan.parameters.key == "key1"
        assert isinstance(plan.parameters.key, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
