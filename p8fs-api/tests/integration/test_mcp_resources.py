"""Integration tests for MCP resources with pagination and S3 uploads.

Tests all MCP resource endpoints:
- p8fs://files - Files table with pagination
- p8fs://resources - Resources table with pagination
- p8fs://moments - Moments table with pagination
- p8fs://entities/{table} - Entity discovery with pagination
- s3-upload://{filename} - Presigned S3 upload URLs
"""

import pytest
from datetime import datetime, timezone
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from p8fs_api.routers.mcp_resources import load_resource, parse_resource_uri

logger = get_logger(__name__)


@pytest.fixture
def tenant_id():
    """Get test tenant ID."""
    return config.default_tenant_id


@pytest.mark.integration
class TestResourceURIParsing:
    """Test resource URI parsing and parameter extraction."""

    def test_parse_simple_uri(self):
        """Test parsing URI without query parameters."""
        base_uri, params = parse_resource_uri("p8fs://files")

        assert base_uri == "p8fs://files"
        assert params["page"] == 1
        assert params["limit"] == 20

    def test_parse_uri_with_pagination(self):
        """Test parsing URI with pagination parameters."""
        base_uri, params = parse_resource_uri("p8fs://resources?page=3&limit=50")

        assert base_uri == "p8fs://resources"
        assert params["page"] == 3
        assert params["limit"] == 50

    def test_parse_uri_with_partial_params(self):
        """Test parsing URI with only some parameters."""
        base_uri, params = parse_resource_uri("p8fs://moments?page=2")

        assert base_uri == "p8fs://moments"
        assert params["page"] == 2
        assert params["limit"] == 20  # Default

    def test_parse_entities_uri(self):
        """Test parsing entities URI."""
        base_uri, params = parse_resource_uri("p8fs://entities/resources?limit=100")

        assert base_uri == "p8fs://entities/resources"
        assert params["page"] == 1
        assert params["limit"] == 100


@pytest.mark.integration
class TestFilesResource:
    """Test p8fs://files resource with pagination."""

    async def test_files_resource_default_pagination(self, tenant_id):
        """Test files resource with default pagination."""
        result = await load_resource("p8fs://files", tenant_id=tenant_id)

        assert result["table"] == "files"
        assert result["page"] == 1
        assert result["limit"] == 20
        assert result["offset"] == 0
        assert "files" in result
        assert "count" in result
        assert isinstance(result["files"], list)

    async def test_files_resource_custom_pagination(self, tenant_id):
        """Test files resource with custom pagination."""
        result = await load_resource("p8fs://files?page=2&limit=10", tenant_id=tenant_id)

        assert result["page"] == 2
        assert result["limit"] == 10
        assert result["offset"] == 10  # (page - 1) * limit

    async def test_files_resource_structure(self, tenant_id):
        """Test files resource returns correct structure."""
        result = await load_resource("p8fs://files?limit=5", tenant_id=tenant_id)

        if result["count"] > 0:
            file = result["files"][0]
            assert "id" in file
            assert "uri" in file
            assert "name" in file
            assert "mime_type" in file
            assert "size" in file
            assert "created_at" in file
            assert "metadata" in file

    async def test_files_resource_limit_cap(self, tenant_id):
        """Test files resource caps limit at 100."""
        result = await load_resource("p8fs://files?limit=500", tenant_id=tenant_id)

        assert result["limit"] == 100  # Capped


@pytest.mark.integration
class TestResourcesResource:
    """Test p8fs://resources resource with pagination."""

    async def test_resources_resource_default(self, tenant_id):
        """Test resources resource with defaults."""
        result = await load_resource("p8fs://resources", tenant_id=tenant_id)

        assert result["table"] == "resources"
        assert result["page"] == 1
        assert result["limit"] == 20
        assert "resources" in result
        assert isinstance(result["resources"], list)

    async def test_resources_resource_structure(self, tenant_id):
        """Test resources resource returns correct structure."""
        result = await load_resource("p8fs://resources?limit=5", tenant_id=tenant_id)

        if result["count"] > 0:
            resource = result["resources"][0]
            assert "id" in resource
            assert "name" in resource
            assert "category" in resource
            assert "content" in resource
            assert "summary" in resource
            assert "uri" in resource
            assert "related_entities" in resource
            assert "created_at" in resource
            assert "updated_at" in resource

            # Content should be truncated to 500 chars
            assert len(resource["content"]) <= 500

    async def test_resources_resource_pagination(self, tenant_id):
        """Test resources resource pagination."""
        page1 = await load_resource("p8fs://resources?page=1&limit=5", tenant_id=tenant_id)
        page2 = await load_resource("p8fs://resources?page=2&limit=5", tenant_id=tenant_id)

        assert page1["page"] == 1
        assert page1["offset"] == 0
        assert page2["page"] == 2
        assert page2["offset"] == 5


@pytest.mark.integration
class TestMomentsResource:
    """Test p8fs://moments resource with pagination."""

    async def test_moments_resource_default(self, tenant_id):
        """Test moments resource with defaults."""
        result = await load_resource("p8fs://moments", tenant_id=tenant_id)

        assert result["table"] == "moments"
        assert result["page"] == 1
        assert result["limit"] == 20
        assert "moments" in result
        assert isinstance(result["moments"], list)

    async def test_moments_resource_structure(self, tenant_id):
        """Test moments resource returns correct structure."""
        result = await load_resource("p8fs://moments?limit=5", tenant_id=tenant_id)

        if result["count"] > 0:
            moment = result["moments"][0]
            assert "id" in moment
            assert "name" in moment
            assert "moment_type" in moment
            assert "start_time" in moment
            assert "end_time" in moment
            assert "summary" in moment
            assert "location" in moment
            assert "present_persons" in moment
            assert "emotion_tags" in moment
            assert "topic_tags" in moment
            assert "created_at" in moment

    async def test_moments_resource_ordering(self, tenant_id):
        """Test moments are ordered by start_time descending."""
        result = await load_resource("p8fs://moments?limit=10", tenant_id=tenant_id)

        if result["count"] >= 2:
            moments = result["moments"]
            # First moment should have later or equal start_time than second
            if moments[0]["start_time"] and moments[1]["start_time"]:
                time1 = datetime.fromisoformat(moments[0]["start_time"].replace('Z', '+00:00'))
                time2 = datetime.fromisoformat(moments[1]["start_time"].replace('Z', '+00:00'))
                assert time1 >= time2, "Moments should be ordered by start_time DESC"


@pytest.mark.integration
class TestEntitiesResource:
    """Test p8fs://entities/{table} resource with pagination."""

    async def test_entities_resources_table(self, tenant_id):
        """Test entities resource for resources table."""
        result = await load_resource("p8fs://entities/resources", tenant_id=tenant_id)

        assert result["table"] == "entities/resources"
        assert result["page"] == 1
        assert result["limit"] == 20
        assert "entities" in result
        assert "total_entities" in result
        assert isinstance(result["entities"], list)

    async def test_entities_moments_table(self, tenant_id):
        """Test entities resource for moments table."""
        result = await load_resource("p8fs://entities/moments", tenant_id=tenant_id)

        assert result["table"] == "entities/moments"
        assert "entities" in result

    async def test_entities_files_table(self, tenant_id):
        """Test entities resource for files table."""
        result = await load_resource("p8fs://entities/files", tenant_id=tenant_id)

        assert result["table"] == "entities/files"
        assert "entities" in result

    async def test_entities_invalid_table(self, tenant_id):
        """Test entities resource with invalid table."""
        result = await load_resource("p8fs://entities/invalid", tenant_id=tenant_id)

        assert "error" in result
        assert "invalid" in result["error"].lower()

    async def test_entities_structure(self, tenant_id):
        """Test entities resource returns correct structure."""
        result = await load_resource("p8fs://entities/resources?limit=10", tenant_id=tenant_id)

        if len(result["entities"]) > 0:
            entity = result["entities"][0]
            assert "entity_key" in entity
            assert "table" in entity
            assert "count" in entity
            assert "updated_at" in entity

    async def test_entities_pagination(self, tenant_id):
        """Test entities resource pagination."""
        page1 = await load_resource("p8fs://entities/resources?page=1&limit=10", tenant_id=tenant_id)
        page2 = await load_resource("p8fs://entities/resources?page=2&limit=10", tenant_id=tenant_id)

        assert page1["page"] == 1
        assert page1["offset"] == 0
        assert page2["page"] == 2
        assert page2["offset"] == 10

    async def test_entities_ordering(self, tenant_id):
        """Test entities are ordered by updated_at descending."""
        result = await load_resource("p8fs://entities/resources?limit=10", tenant_id=tenant_id)

        if len(result["entities"]) >= 2:
            entities = result["entities"]
            # Entities should be ordered by updated_at DESC
            if entities[0]["updated_at"] and entities[1]["updated_at"]:
                time1 = entities[0]["updated_at"]
                time2 = entities[1]["updated_at"]
                assert time1 >= time2, "Entities should be ordered by updated_at DESC"


@pytest.mark.integration
class TestS3UploadResource:
    """Test s3-upload://{filename} resource with presigned URLs."""

    async def test_s3_upload_resource_structure(self, tenant_id):
        """Test S3 upload resource returns correct structure."""
        result = await load_resource("s3-upload://test-document.pdf", tenant_id=tenant_id)

        # Should not have error
        assert "error" not in result or not result.get("error")

        # Check required fields
        assert result["tenant_id"] == tenant_id
        assert result["filename"] == "test-document.pdf"
        assert "s3_path" in result
        assert "s3_key" in result
        assert "bucket" in result
        assert "date_path" in result
        assert "presigned_url" in result
        assert "upload_method" in result
        assert "expires_in" in result
        assert "usage" in result

    async def test_s3_upload_resource_path_convention(self, tenant_id):
        """Test S3 upload uses correct P8FS path convention."""
        result = await load_resource("s3-upload://document.pdf", tenant_id=tenant_id)

        # Bucket should be tenant_id
        assert result["bucket"] == tenant_id

        # S3 key should follow uploads/{YYYY}/{MM}/{DD}/{filename}
        s3_key = result["s3_key"]
        assert s3_key.startswith("uploads/")

        # Extract date path
        parts = s3_key.split("/")
        assert len(parts) == 5  # uploads / YYYY / MM / DD / filename
        assert parts[0] == "uploads"
        assert parts[4] == "document.pdf"

        # Verify date format
        now = datetime.utcnow()
        expected_date_path = now.strftime("%Y/%m/%d")
        assert result["date_path"] == expected_date_path

        # S3 path should be correct
        expected_s3_path = f"s3://{tenant_id}/uploads/{expected_date_path}/document.pdf"
        assert result["s3_path"] == expected_s3_path

    async def test_s3_upload_resource_presigned_url(self, tenant_id):
        """Test presigned URL generation."""
        result = await load_resource("s3-upload://test.txt", tenant_id=tenant_id)

        presigned_url = result["presigned_url"]
        assert presigned_url.startswith("http")

        # Should contain bucket and key
        assert tenant_id in presigned_url or result["s3_key"] in presigned_url

        # Check upload method
        assert result["upload_method"] in ["presigned_url", "direct_with_auth"]

    async def test_s3_upload_resource_usage_instructions(self, tenant_id):
        """Test usage instructions are provided."""
        result = await load_resource("s3-upload://document.pdf", tenant_id=tenant_id)

        usage = result["usage"]
        assert "upload" in usage
        assert "curl" in usage["upload"]
        assert "document.pdf" in usage["upload"]
        assert "note" in usage
        assert "upload_path" in usage

    async def test_s3_upload_resource_empty_filename(self, tenant_id):
        """Test S3 upload with empty filename."""
        result = await load_resource("s3-upload://", tenant_id=tenant_id)

        assert "error" in result
        assert "Invalid" in result["error"]

    async def test_s3_upload_resource_special_chars(self, tenant_id):
        """Test S3 upload with special characters in filename."""
        result = await load_resource("s3-upload://My Document (2024).pdf", tenant_id=tenant_id)

        # Should handle special characters
        assert result["filename"] == "My Document (2024).pdf"
        assert "My Document (2024).pdf" in result["s3_key"]


@pytest.mark.integration
class TestResourceErrors:
    """Test error handling for invalid resource URIs."""

    async def test_unknown_resource_uri(self, tenant_id):
        """Test unknown resource URI."""
        result = await load_resource("unknown://invalid", tenant_id=tenant_id)

        assert "error" in result
        assert "Unknown resource" in result["error"]

    async def test_malformed_pagination(self, tenant_id):
        """Test malformed pagination parameters."""
        # Invalid page number should default
        result = await load_resource("p8fs://files?page=invalid", tenant_id=tenant_id)

        # Should handle gracefully (either error or default to page 1)
        assert "error" in result or result.get("page") in [1, "invalid"]


@pytest.mark.integration
async def test_all_resources_integration(tenant_id):
    """Integration test for all resources working together."""
    logger.info("=" * 70)
    logger.info("TESTING ALL MCP RESOURCES")
    logger.info("=" * 70)

    # Test files resource
    logger.info("Testing p8fs://files...")
    files = await load_resource("p8fs://files?limit=5", tenant_id=tenant_id)
    assert files["table"] == "files"
    logger.info(f"✓ Files resource: {files['count']} files found")

    # Test resources resource
    logger.info("Testing p8fs://resources...")
    resources = await load_resource("p8fs://resources?limit=5", tenant_id=tenant_id)
    assert resources["table"] == "resources"
    logger.info(f"✓ Resources resource: {resources['count']} resources found")

    # Test moments resource
    logger.info("Testing p8fs://moments...")
    moments = await load_resource("p8fs://moments?limit=5", tenant_id=tenant_id)
    assert moments["table"] == "moments"
    logger.info(f"✓ Moments resource: {moments['count']} moments found")

    # Test entities resource
    logger.info("Testing p8fs://entities/resources...")
    entities = await load_resource("p8fs://entities/resources?limit=10", tenant_id=tenant_id)
    assert entities["table"] == "entities/resources"
    logger.info(f"✓ Entities resource: {entities['total_entities']} entities found")

    # Test S3 upload resource
    logger.info("Testing s3-upload://test.pdf...")
    upload = await load_resource("s3-upload://test.pdf", tenant_id=tenant_id)
    assert upload["tenant_id"] == tenant_id
    assert upload["upload_method"] in ["presigned_url", "direct_with_auth"]
    logger.info(f"✓ S3 upload resource: {upload['upload_method']} method")

    logger.info("=" * 70)
    logger.info("ALL MCP RESOURCES WORKING CORRECTLY")
    logger.info("=" * 70)
