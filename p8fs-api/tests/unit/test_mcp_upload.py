"""Unit tests for MCP upload_file tool."""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from p8fs_api.main import app
from p8fs_cluster.config.settings import config


@pytest.fixture
def mock_s3_client():
    """Mock S3 client for testing."""
    mock_client = MagicMock()
    mock_client.put_object = MagicMock()
    return mock_client


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def valid_token():
    """Valid JWT token for testing."""
    return "test-jwt-token"


@pytest.fixture
def auth_headers(valid_token):
    """Valid authorization headers for testing."""
    return {"Authorization": f"Bearer {valid_token}"}


@pytest.fixture
def mcp_session_id():
    """Mock MCP session ID."""
    return "test-session-123"


class TestMCPUploadFile:
    """Test cases for MCP upload_file tool."""
    
    @patch('p8fs_api.middleware.auth.get_current_user')
    @patch('boto3.client')
    def test_upload_file_success(self, mock_boto3, mock_get_current_user, client, auth_headers, mcp_session_id, mock_s3_client):
        """Test successful file upload with base64 content."""
        # Mock auth verification
        from p8fs_api.middleware.auth import User
        mock_get_current_user.return_value = User(
            id="test-user-id",
            email="test@example.com",
            tenant_id="test-tenant"
        )
        
        # Mock S3 client
        mock_boto3.return_value = mock_s3_client
        
        # Test data
        test_content = "Hello, test file!"
        base64_content = base64.b64encode(test_content.encode()).decode()
        
        # Make request
        response = client.post(
            "/api/mcp",
            headers={**auth_headers, "mcp-session-id": mcp_session_id},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "upload_file",
                    "arguments": {
                        "filename": "test.txt",
                        "content": base64_content,
                        "content_type": "text/plain",
                        "base64_encoded": True
                    }
                }
            }
        )
        
        assert response.status_code == 200
        
        # Parse SSE response
        response_text = response.text
        result_data = None
        
        for line in response_text.split('\n'):
            if line.startswith("data: "):
                data_str = line[6:]
                data = json.loads(data_str)
                if "result" in data:
                    result_text = data["result"]["content"][0]["text"]
                    result_data = json.loads(result_text)
                    break
        
        assert result_data is not None
        assert result_data["status"] == "success"
        assert result_data["filename"] == "test.txt"
        assert result_data["content_type"] == "text/plain"
        assert result_data["size"] == len(test_content.encode())
        assert "s3_key" in result_data
        assert "s3_url" in result_data
        assert "timestamp" in result_data
        
        # Verify S3 client was called
        mock_s3_client.put_object.assert_called_once()
        call_args = mock_s3_client.put_object.call_args[1]
        assert call_args["Bucket"] == config.seaweedfs_bucket
        assert call_args["Body"] == test_content.encode()
        assert call_args["ContentType"] == "text/plain"
    
    @patch('p8fs_api.middleware.auth.get_current_user')
    @patch('boto3.client')
    def test_upload_file_non_base64(self, mock_boto3, mock_get_current_user, client, auth_headers, mcp_session_id, mock_s3_client):
        """Test file upload with plain text content."""
        # Mock auth verification
        from p8fs_api.middleware.auth import User
        mock_get_current_user.return_value = User(
            id="test-user-id",
            email="test@example.com",
            tenant_id="test-tenant"
        )
        
        # Mock S3 client
        mock_boto3.return_value = mock_s3_client
        
        test_content = "Plain text content"
        
        response = client.post(
            "/api/mcp",
            headers={**auth_headers, "mcp-session-id": mcp_session_id},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "upload_file",
                    "arguments": {
                        "filename": "plain.txt",
                        "content": test_content,
                        "content_type": "text/plain",
                        "base64_encoded": False
                    }
                }
            }
        )
        
        assert response.status_code == 200
        
        # Verify S3 client received UTF-8 encoded content
        call_args = mock_s3_client.put_object.call_args[1]
        assert call_args["Body"] == test_content.encode('utf-8')
    
    @patch('p8fs_api.middleware.auth.get_current_user')
    def test_upload_file_invalid_base64(self, mock_get_current_user, client, auth_headers, mcp_session_id):
        """Test handling of invalid base64 content."""
        # Mock auth verification
        from p8fs_api.middleware.auth import User
        mock_get_current_user.return_value = User(
            id="test-user-id",
            email="test@example.com",
            tenant_id="test-tenant"
        )
        
        invalid_base64 = "not-valid-base64!@#$"
        
        response = client.post(
            "/api/mcp",
            headers={**auth_headers, "mcp-session-id": mcp_session_id},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "upload_file",
                    "arguments": {
                        "filename": "test.txt",
                        "content": invalid_base64,
                        "base64_encoded": True
                    }
                }
            }
        )
        
        assert response.status_code == 200
        
        # Parse response
        response_text = response.text
        result_data = None
        
        for line in response_text.split('\n'):
            if line.startswith("data: "):
                data_str = line[6:]
                data = json.loads(data_str)
                if "result" in data:
                    result_text = data["result"]["content"][0]["text"]
                    result_data = json.loads(result_text)
                    break
        
        assert result_data is not None
        assert result_data["status"] == "error"
        assert "Failed to decode base64" in result_data["message"]
    
    @patch('p8fs_api.middleware.auth.get_current_user')
    @patch('boto3.client')
    def test_upload_file_s3_error(self, mock_boto3, mock_get_current_user, client, auth_headers, mcp_session_id, mock_s3_client):
        """Test handling of S3 upload errors."""
        # Mock auth verification
        from p8fs_api.middleware.auth import User
        mock_get_current_user.return_value = User(
            id="test-user-id",
            email="test@example.com",
            tenant_id="test-tenant"
        )
        
        # Mock S3 client with error
        mock_s3_client.put_object.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}},
            'PutObject'
        )
        mock_boto3.return_value = mock_s3_client
        
        test_content = base64.b64encode(b"test").decode()
        
        response = client.post(
            "/api/mcp",
            headers={**auth_headers, "mcp-session-id": mcp_session_id},
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "upload_file",
                    "arguments": {
                        "filename": "test.txt",
                        "content": test_content,
                        "base64_encoded": True
                    }
                }
            }
        )
        
        assert response.status_code == 200
        
        # Parse response
        response_text = response.text
        result_data = None
        
        for line in response_text.split('\n'):
            if line.startswith("data: "):
                data_str = line[6:]
                data = json.loads(data_str)
                if "result" in data:
                    result_text = data["result"]["content"][0]["text"]
                    result_data = json.loads(result_text)
                    break
        
        assert result_data is not None
        assert result_data["status"] == "error"
        assert "Failed to upload to S3" in result_data["message"]
    
    def test_upload_file_requires_auth(self, client):
        """Test that upload_file requires authentication."""
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "upload_file",
                    "arguments": {
                        "filename": "test.txt",
                        "content": "dGVzdA==",
                        "base64_encoded": True
                    }
                }
            }
        )
        
        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "invalid_token"
    
    @patch('p8fs_api.middleware.auth.get_current_user')
    @patch('boto3.client')
    def test_upload_file_auto_content_type(self, mock_boto3, mock_get_current_user, client, auth_headers, mcp_session_id, mock_s3_client):
        """Test auto-detection of content type."""
        # Mock auth verification
        from p8fs_api.middleware.auth import User
        mock_get_current_user.return_value = User(
            id="test-user-id",
            email="test@example.com",
            tenant_id="test-tenant"
        )
        
        # Mock S3 client
        mock_boto3.return_value = mock_s3_client
        
        test_content = base64.b64encode(b"test").decode()
        
        # Test various file extensions
        test_cases = [
            ("document.pdf", "application/pdf"),
            ("image.png", "image/png"),
            ("script.js", "application/javascript"),
            ("data.json", "application/json"),
        ]
        
        for filename, expected_type in test_cases:
            # Reset mock
            mock_s3_client.put_object.reset_mock()
            
            response = client.post(
                "/api/mcp",
                headers={**auth_headers, "mcp-session-id": mcp_session_id},
                json={
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "upload_file",
                        "arguments": {
                            "filename": filename,
                            "content": test_content,
                            "base64_encoded": True
                        }
                    }
                }
            )
            
            assert response.status_code == 200
            
            # Verify content type was set correctly
            call_args = mock_s3_client.put_object.call_args[1]
            assert call_args["ContentType"] == expected_type
    
    @patch('p8fs_api.middleware.auth.get_current_user')
    @patch('boto3.client')
    def test_upload_file_metadata(self, mock_boto3, mock_get_current_user, client, auth_headers, mcp_session_id, mock_s3_client):
        """Test that proper metadata is set on uploaded files."""
        # Mock auth verification
        from p8fs_api.middleware.auth import User
        mock_get_current_user.return_value = User(
            id="test-user-id",
            email="test@example.com",
            tenant_id="test-tenant"
        )
        
        # Mock S3 client
        mock_boto3.return_value = mock_s3_client
        
        test_content = base64.b64encode(b"test").decode()
        
        response = client.post(
            "/api/mcp",
            headers={**auth_headers, "mcp-session-id": mcp_session_id},
            json={
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "upload_file",
                    "arguments": {
                        "filename": "metadata_test.txt",
                        "content": test_content,
                        "base64_encoded": True
                    }
                }
            }
        )
        
        assert response.status_code == 200
        
        # Verify metadata was set
        call_args = mock_s3_client.put_object.call_args[1]
        metadata = call_args["Metadata"]
        
        assert metadata["uploaded-by"] == "mcp-tool"
        assert "upload-timestamp" in metadata
        assert metadata["original-filename"] == "metadata_test.txt"