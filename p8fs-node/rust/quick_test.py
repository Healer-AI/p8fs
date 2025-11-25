#!/usr/bin/env python3
"""Quick test to verify the API structure without running the server."""

import json


# Test the request/response format structure
def test_openai_format():
    print("🧪 Testing OpenAI-compatible format structures...")
    
    # Sample request format
    request = {
        "input": ["Hello, world!", "This is a test"],
        "model": "all-MiniLM-L6-v2",
        "encoding_format": "float",
        "dimensions": 384
    }
    
    # Sample expected response format
    expected_response = {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "embedding": [0.1, 0.2, 0.3],  # Mock embedding
                "index": 0
            },
            {
                "object": "embedding", 
                "embedding": [0.4, 0.5, 0.6],  # Mock embedding
                "index": 1
            }
        ],
        "model": "all-MiniLM-L6-v2",
        "usage": {
            "prompt_tokens": 6,
            "total_tokens": 6
        }
    }
    
    print("✅ Request format:")
    print(json.dumps(request, indent=2))
    
    print("\n✅ Expected response format:")
    print(json.dumps(expected_response, indent=2))
    
    print("\n🎯 Format validation:")
    print(f"- Request has 'input' field: {'input' in request}")
    print(f"- Response has 'object' field: {'object' in expected_response}")
    print(f"- Response has 'data' array: {'data' in expected_response}")
    print(f"- Response has 'usage' tracking: {'usage' in expected_response}")
    print(f"- Data items have proper structure: {all('embedding' in item and 'index' in item for item in expected_response['data'])}")
    
    return True

def test_curl_command():
    print("\n🌐 Sample curl command for testing:")
    curl_cmd = '''curl -X POST http://localhost:3000/api/v1/embeddings \\
  -H "Content-Type: application/json" \\
  -d '{
    "input": ["Hello, world!", "Test sentence"],
    "model": "all-MiniLM-L6-v2",
    "encoding_format": "float"
  }' '''
    print(curl_cmd)

if __name__ == "__main__":
    test_openai_format()
    test_curl_command()
    print("\n✅ Format validation completed!")
    print("🚀 To test the actual API, build and run the server:")
    print("   cd p8fs-node && cargo run")
    print("   Then run: python3 test_embeddings.py")