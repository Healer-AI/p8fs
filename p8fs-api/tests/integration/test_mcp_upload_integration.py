"""Integration tests for MCP upload_file tool with real services."""

import base64
import json
import os
import time
from pathlib import Path

import boto3
import pytest
from fastapi.testclient import TestClient

from p8fs_api.main import app
from p8fs_cluster.config.settings import config


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def dev_token():
    """Get or generate dev token for testing."""
    token_file = Path.home() / ".p8fs" / "auth" / "token.json"
    
    # Check if token exists and is not expired
    if token_file.exists():
        with open(token_file) as f:
            token_data = json.load(f)
            # For now, just use the existing token
            return token_data["access_token"]
    
    # If no token exists, skip the test
    pytest.skip("No dev token available. Run 'python scripts/dev/generate_dev_token.py' first")


@pytest.fixture
def auth_headers(dev_token):
    """Authorization headers with dev token."""
    return {"Authorization": f"Bearer {dev_token}"}


@pytest.fixture
def s3_client():
    """Real S3 client for verification."""
    return boto3.client(
        's3',
        endpoint_url=config.seaweedfs_s3_endpoint,
        aws_access_key_id=config.seaweedfs_access_key,
        aws_secret_access_key=config.seaweedfs_secret_key,
        region_name='us-east-1'
    )


@pytest.mark.integration
class TestMCPUploadIntegration:
    """Integration tests for MCP upload functionality."""
    
    def test_upload_text_file(self, client, auth_headers, s3_client):
        """Test uploading a text file through MCP."""
        # Step 1: Initialize MCP session
        init_response = client.post(
            "/api/mcp",
            headers={**auth_headers, "Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                }
            }
        )
        
        assert init_response.status_code == 200
        
        # Extract session ID from headers
        session_id = init_response.headers.get("mcp-session-id")
        assert session_id is not None
        
        # Step 2: Upload file
        test_content = f"Integration test content at {time.strftime('%Y-%m-%d %H:%M:%S')}"
        base64_content = base64.b64encode(test_content.encode()).decode()
        
        upload_response = client.post(
            "/api/mcp",
            headers={
                **auth_headers,
                "mcp-session-id": session_id,
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "upload_file",
                    "arguments": {
                        "filename": "integration_test.txt",
                        "content": base64_content,
                        "content_type": "text/plain",
                        "base64_encoded": True
                    }
                }
            }
        )
        
        assert upload_response.status_code == 200
        
        # Parse SSE response
        response_text = upload_response.text
        result_data = None
        
        for line in response_text.split('\n'):
            if line.startswith("data: "):
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                    if "result" in data:
                        result_text = data["result"]["content"][0]["text"]
                        result_data = json.loads(result_text)
                        break
                except json.JSONDecodeError:
                    continue
        
        assert result_data is not None
        assert result_data["status"] == "success"
        assert result_data["filename"] == "integration_test.txt"
        assert "s3_key" in result_data
        assert "s3_url" in result_data
        
        # Step 3: Verify file exists in S3
        s3_key = result_data["s3_key"]
        
        try:
            obj = s3_client.get_object(Bucket=config.seaweedfs_bucket, Key=s3_key)
            content = obj['Body'].read().decode('utf-8')
            assert content == test_content
            assert obj['ContentType'] == 'text/plain'
            
            # Check metadata
            metadata = obj.get('Metadata', {})
            assert metadata.get('uploaded-by') == 'mcp-tool'
            assert 'upload-timestamp' in metadata
            assert metadata.get('original-filename') == 'integration_test.txt'
            
        finally:
            # Cleanup: Delete the test file
            try:
                s3_client.delete_object(Bucket=config.seaweedfs_bucket, Key=s3_key)
            except Exception:
                pass
    
    def test_upload_binary_file(self, client, auth_headers, s3_client):
        """Test uploading a binary file (image) through MCP."""
        # Initialize session
        init_response = client.post(
            "/api/mcp",
            headers={**auth_headers, "Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                }
            }
        )
        
        session_id = init_response.headers.get("mcp-session-id")
        
        # Create a small test image (1x1 red pixel PNG)
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        )
        png_base64 = base64.b64encode(png_data).decode()
        
        # Upload image
        upload_response = client.post(
            "/api/mcp",
            headers={
                **auth_headers,
                "mcp-session-id": session_id,
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "upload_file",
                    "arguments": {
                        "filename": "test_pixel.png",
                        "content": png_base64,
                        "content_type": "image/png",
                        "base64_encoded": True
                    }
                }
            }
        )
        
        # Parse response
        response_text = upload_response.text
        result_data = None
        
        for line in response_text.split('\n'):
            if line.startswith("data: "):
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                    if "result" in data:
                        result_text = data["result"]["content"][0]["text"]
                        result_data = json.loads(result_text)
                        break
                except json.JSONDecodeError:
                    continue
        
        assert result_data is not None
        assert result_data["status"] == "success"
        assert result_data["content_type"] == "image/png"
        
        # Verify in S3
        s3_key = result_data["s3_key"]
        
        try:
            obj = s3_client.get_object(Bucket=config.seaweedfs_bucket, Key=s3_key)
            content = obj['Body'].read()
            assert content == png_data
            assert obj['ContentType'] == 'image/png'
        finally:
            # Cleanup
            try:
                s3_client.delete_object(Bucket=config.seaweedfs_bucket, Key=s3_key)
            except Exception:
                pass
    
    def test_upload_multiple_files(self, client, auth_headers, s3_client):
        """Test uploading multiple files in sequence."""
        # Initialize session
        init_response = client.post(
            "/api/mcp",
            headers={**auth_headers, "Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                }
            }
        )
        
        session_id = init_response.headers.get("mcp-session-id")
        uploaded_keys = []
        
        try:
            # Upload 3 files
            for i in range(3):
                content = f"Test file {i} content"
                base64_content = base64.b64encode(content.encode()).decode()
                
                upload_response = client.post(
                    "/api/mcp",
                    headers={
                        **auth_headers,
                        "mcp-session-id": session_id,
                        "Accept": "application/json, text/event-stream"
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": i + 2,
                        "method": "tools/call",
                        "params": {
                            "name": "upload_file",
                            "arguments": {
                                "filename": f"test_file_{i}.txt",
                                "content": base64_content,
                                "base64_encoded": True
                            }
                        }
                    }
                )
                
                # Parse response
                response_text = upload_response.text
                for line in response_text.split('\n'):
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            if "result" in data:
                                result_text = data["result"]["content"][0]["text"]
                                result_data = json.loads(result_text)
                                assert result_data["status"] == "success"
                                uploaded_keys.append(result_data["s3_key"])
                                break
                        except json.JSONDecodeError:
                            continue
            
            # Verify all files exist
            assert len(uploaded_keys) == 3
            for key in uploaded_keys:
                obj = s3_client.get_object(Bucket=config.seaweedfs_bucket, Key=key)
                assert obj is not None
                
        finally:
            # Cleanup
            for key in uploaded_keys:
                try:
                    s3_client.delete_object(Bucket=config.seaweedfs_bucket, Key=key)
                except Exception:
                    pass
    
    def test_upload_with_special_characters(self, client, auth_headers, s3_client):
        """Test uploading files with special characters in filename."""
        # Initialize session
        init_response = client.post(
            "/api/mcp",
            headers={**auth_headers, "Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                }
            }
        )
        
        session_id = init_response.headers.get("mcp-session-id")
        
        # Test filename with spaces and special characters
        filename = "test file (2024) - #1.txt"
        content = "Content with special filename"
        base64_content = base64.b64encode(content.encode()).decode()
        
        upload_response = client.post(
            "/api/mcp",
            headers={
                **auth_headers,
                "mcp-session-id": session_id,
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "upload_file",
                    "arguments": {
                        "filename": filename,
                        "content": base64_content,
                        "base64_encoded": True
                    }
                }
            }
        )
        
        # Parse response
        response_text = upload_response.text
        result_data = None
        
        for line in response_text.split('\n'):
            if line.startswith("data: "):
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                    if "result" in data:
                        result_text = data["result"]["content"][0]["text"]
                        result_data = json.loads(result_text)
                        break
                except json.JSONDecodeError:
                    continue
        
        assert result_data is not None
        assert result_data["status"] == "success"
        assert result_data["filename"] == filename
        
        # Verify the key contains the filename
        s3_key = result_data["s3_key"]
        assert filename in s3_key
        
        # Cleanup
        try:
            s3_client.delete_object(Bucket=config.seaweedfs_bucket, Key=s3_key)
        except Exception:
            pass