#!/usr/bin/env python3
"""Test script for p8fs-node embedding API compatibility."""

import time

import requests


def test_embedding_api():
    """Test the embedding API with OpenAI-compatible format."""
    
    base_url = "http://localhost:3000/api/v1"
    
    print("🧪 Testing p8fs-node embedding API...")
    
    # Test data
    test_cases = [
        {
            "name": "Single sentence",
            "input": ["Hello, world!"],
            "expected_count": 1
        },
        {
            "name": "Multiple sentences", 
            "input": [
                "The quick brown fox jumps over the lazy dog.",
                "Machine learning is transforming how we work with text.",
                "Embeddings capture semantic meaning in vector space."
            ],
            "expected_count": 3
        },
        {
            "name": "Empty and short text",
            "input": ["", "Hi", "A"],
            "expected_count": 3
        }
    ]
    
    for test_case in test_cases:
        print(f"\n📝 Testing: {test_case['name']}")
        
        payload = {
            "input": test_case["input"],
            "model": "all-MiniLM-L6-v2",
            "encoding_format": "float"
        }
        
        try:
            response = requests.post(
                f"{base_url}/embeddings",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify OpenAI-compatible structure
                assert "object" in data and data["object"] == "list"
                assert "data" in data
                assert "model" in data
                assert "usage" in data
                
                # Verify data structure
                assert len(data["data"]) == test_case["expected_count"]
                
                for i, item in enumerate(data["data"]):
                    assert item["object"] == "embedding"
                    assert item["index"] == i
                    assert isinstance(item["embedding"], list)
                    assert len(item["embedding"]) > 0  # Should have dimensions
                
                # Verify usage tracking
                assert "prompt_tokens" in data["usage"]
                assert "total_tokens" in data["usage"]
                
                print(f"✅ Success: {len(data['data'])} embeddings generated")
                print(f"   Model: {data['model']}")
                print(f"   Dimensions: {len(data['data'][0]['embedding'])}")
                print(f"   Tokens: {data['usage']['total_tokens']}")
                
            else:
                print(f"❌ Failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Connection error: {e}")
        except Exception as e:
            print(f"❌ Test failed: {e}")

def test_health_check():
    """Test the health check endpoint."""
    
    print("\n💚 Testing health check...")
    
    try:
        response = requests.get("http://localhost:3000/", timeout=5)
        if response.status_code == 200:
            print("✅ Health check passed")
        else:
            print(f"⚠️ Health check returned: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check failed: {e}")

if __name__ == "__main__":
    print("Starting API tests...")
    print("Make sure the server is running: cargo run")
    print("Waiting 5 seconds for server startup...")
    time.sleep(5)
    
    test_health_check()
    test_embedding_api()
    
    print("\n🎉 All tests completed!")