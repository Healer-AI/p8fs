"""Unit tests for health endpoints."""

from fastapi.testclient import TestClient
from p8fs_api.main import app

client = TestClient(app)


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_health_check(self):
        """Test main health check endpoint."""
        response = client.get("/health")
        
        if response.status_code != 200:
            print(f"Health check error: {response.status_code} - {response.text}")
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data
        assert "services" in data
        assert data["version"] == "0.1.0"
    
    def test_readiness_check(self):
        """Test Kubernetes readiness probe."""
        response = client.get("/ready")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "ready"
    
    def test_liveness_check(self):
        """Test Kubernetes liveness probe."""
        response = client.get("/live")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "alive"
        assert "timestamp" in data