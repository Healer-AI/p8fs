"""LLM request handling and protocol adapters."""

from typing import Any


def prepare_openai_request(request_data: dict[str, Any], model_config: dict[str, Any]) -> dict[str, Any]:
    """Prepare request data for OpenAI API."""
    api_url = model_config.get("completions_uri", "https://api.openai.com/v1/chat/completions")
    token = model_config.get("token")
    
    if not token:
        raise ValueError("No API token configured for OpenAI")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "p8fs/0.1.0"
    }
    
    return {
        "api_url": api_url,
        "headers": headers,
        "api_data": request_data
    }


def prepare_anthropic_request(request_data: dict[str, Any], model_config: dict[str, Any]) -> dict[str, Any]:
    """Prepare request data for Anthropic API."""
    api_url = model_config.get("completions_uri", "https://api.anthropic.com/v1/messages")
    token = model_config.get("token")
    version = model_config.get("anthropic-version", "2023-06-01")
    
    if not token:
        raise ValueError("No API token configured for Anthropic")
    
    headers = {
        "x-api-key": token,
        "Content-Type": "application/json",
        "anthropic-version": version,
        "User-Agent": "p8fs/0.1.0"
    }
    
    return {
        "api_url": api_url,
        "headers": headers,
        "api_data": request_data
    }


def prepare_google_request(request_data: dict[str, Any], model_config: dict[str, Any]) -> dict[str, Any]:
    """Prepare request data for Google API."""
    api_url = model_config.get("completions_uri")
    token = model_config.get("token")
    
    if not token:
        raise ValueError("No API token configured for Google")
    
    # Add API key to URL for Google
    if "?" in api_url:
        api_url += f"&key={token}"
    else:
        api_url += f"?key={token}"
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "p8fs/0.1.0"
    }
    
    return {
        "api_url": api_url,
        "headers": headers,
        "api_data": request_data
    }