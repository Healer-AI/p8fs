"""Integration test for moments entity endpoints."""

import base64
import json
import os
import uuid
from datetime import datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from httpx import AsyncClient

from src.p8fs_api.main import app


@pytest.fixture
def dev_jwt_token():
    """Get development JWT token for testing."""
    # Get dev token from environment or use default for testing
    dev_token = os.getenv("P8FS_DEV_TOKEN_SECRET", "p8fs-dev-dHMZAB_dK8JR6ps-zLBSBTfBeoNdXu2KcpNywjDfD58")
    
    # Generate Ed25519 key pair
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    public_key_b64 = base64.b64encode(public_key_bytes).decode('utf-8')
    
    # Get JWT via dev endpoint
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/dev/register",
            json={
                "email": "test-moments@example.com",
                "public_key": public_key_b64,
                "device_info": {
                    "device_name": "Test Runner",
                    "device_type": "test",
                    "os_version": "Test",
                    "app_version": "test-1.0.0",
                    "platform": "pytest"
                },
            },
            headers={
                "X-Dev-Token": dev_token,
                "X-Dev-Email": "test-moments@example.com",
                "X-Dev-Code": "123456",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200, f"Failed to get dev token: {response.text}"
        token_data = response.json()
        print(f"Token response: {token_data}")  # Debug output
        
        return {
            "access_token": token_data["access_token"],
            "tenant_id": token_data.get("tenant_id"),
            "headers": {"Authorization": f"Bearer {token_data['access_token']}"}
        }


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_moments_full_flow(client: TestClient, dev_jwt_token):
    """Test full flow: create moment, get by id, get by name, search, semantic search."""
    
    headers = dev_jwt_token["headers"]
    tenant_id = dev_jwt_token["tenant_id"]
    
    # 1. Create a moment with descriptive content for semantic search
    moment_data = {
        "name": f"test-moment-{uuid.uuid4().hex[:8]}",
        "content": "A beautiful sunset over the Pacific Ocean with vibrant orange and pink colors reflecting on the calm water. Seagulls flying overhead.",
        "summary": "Sunset at the beach with stunning colors",
        "location": "Santa Monica Beach, California",
        "emotion_tags": ["peaceful", "awe-inspiring", "relaxing"],
        "topic_tags": ["nature", "sunset", "ocean", "beach"],
        "moment_type": "observation",
        "metadata": {
            "weather": "clear",
            "temperature": "72F",
            "test": True
        }
    }
    
    # Create moment via PUT
    response = client.put(
        "/api/v1/entity/moments/",
        json=moment_data,
        headers=headers
    )
    assert response.status_code == 200
    created_moment = response.json()
    assert "id" in created_moment
    assert created_moment["tenant_id"] == tenant_id
    moment_id = created_moment["id"]
    
    # 2. Get moment by ID
    response = client.get(
        f"/api/v1/entity/moments/{moment_id}",
        headers=headers
    )
    assert response.status_code == 200
    retrieved_moment = response.json()
    assert retrieved_moment["id"] == moment_id
    assert retrieved_moment["name"] == moment_data["name"]
    assert retrieved_moment["content"] == moment_data["content"]
    
    # 3. Get moment by name
    response = client.get(
        f"/api/v1/entity/moments/name/{moment_data['name']}",
        headers=headers
    )
    assert response.status_code == 200
    retrieved_by_name = response.json()
    assert retrieved_by_name["id"] == moment_id
    assert retrieved_by_name["name"] == moment_data["name"]
    
    # 4. Search without query (list all)
    response = client.get(
        "/api/v1/entity/moments/",
        headers=headers
    )
    assert response.status_code == 200
    search_results = response.json()
    assert "results" in search_results
    assert "total" in search_results
    assert search_results["entity_type"] == "moment"
    assert len(search_results["results"]) > 0
    # Check our moment is in the results
    moment_ids = [m["id"] for m in search_results["results"]]
    assert moment_id in moment_ids
    
    # 5. Search with filters
    response = client.get(
        "/api/v1/entity/moments/?moment_type=observation",
        headers=headers
    )
    assert response.status_code == 200
    filtered_results = response.json()
    assert len(filtered_results["results"]) > 0
    # All results should have moment_type = observation
    for result in filtered_results["results"]:
        assert result.get("moment_type") == "observation"
    
    # 6. Semantic search - search for ocean/beach related content
    response = client.get(
        "/api/v1/entity/moments/?query=ocean%20waves%20beach%20sunset",
        headers=headers
    )
    assert response.status_code == 200
    semantic_results = response.json()
    assert "results" in semantic_results
    assert len(semantic_results["results"]) > 0
    
    # The created moment should be in results due to semantic similarity
    # (it has ocean, beach, sunset content)
    found_moment = False
    for result in semantic_results["results"]:
        if result["id"] == moment_id:
            found_moment = True
            # Semantic search includes similarity score
            assert "similarity_score" in result
            assert result["similarity_score"] > 0.7  # Should have high similarity
            break
    assert found_moment, "Created moment not found in semantic search results"
    
    # 7. Test pagination
    response = client.get(
        "/api/v1/entity/moments/?limit=5&offset=0",
        headers=headers
    )
    assert response.status_code == 200
    paginated_results = response.json()
    assert paginated_results["limit"] == 5
    assert paginated_results["offset"] == 0
    
    # 8. Update moment via POST (alias for PUT)
    updated_data = {
        "name": moment_data["name"],
        "content": moment_data["content"],
        "summary": "Updated summary - Beautiful sunset scene",
        "metadata": {
            "weather": "clear",
            "temperature": "72F", 
            "updated": True
        }
    }
    response = client.post(
        "/api/v1/entity/moments/",
        json=updated_data,
        headers=headers
    )
    assert response.status_code == 200
    updated_moment = response.json()
    # Note: repository upsert returns operation result, not the entity
    assert updated_moment.get("success") is True or "affected_rows" in updated_moment


@pytest.mark.asyncio
async def test_moment_errors(client: AsyncClient, dev_jwt_token):
    """Test error cases for moment endpoints."""
    
    headers = dev_jwt_token["headers"]
    
    # Test get non-existent moment by ID
    response = client.get(
        f"/api/v1/entity/moments/{uuid.uuid4()}",
        headers=headers
    )
    assert response.status_code == 404
    error = response.json()
    assert "error" in error or "detail" in error
    
    # Test get non-existent moment by name
    response = client.get(
        "/api/v1/entity/moments/name/non-existent-moment-name-xyz",
        headers=headers
    )
    assert response.status_code == 404
    error = response.json()
    assert "error" in error or "detail" in error