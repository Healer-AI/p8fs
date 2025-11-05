"""Utility functions for OpenAPI service

This module provides utility functions for converting OpenAPI specifications
to function definitions compatible with LLM function calling.
"""

from typing import Any

from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


def map_openapi_to_function(
    spec: dict[str, Any], short_name: str | None = None
) -> dict[str, Any]:
    """Map an OpenAPI endpoint spec to a function definition

    Converts an OpenAPI endpoint specification to a function definition
    that can be used with LLM function calling systems like OpenAI's.

    Args:
        spec: OpenAPI endpoint specification dictionary
        short_name: Optional short name for the function

    Returns:
        Function definition dictionary compatible with LLM systems

    Example:
        >>> spec = {
        ...     "operationId": "getCurrentWeather",
        ...     "summary": "Get current weather",
        ...     "parameters": [
        ...         {
        ...             "name": "city",
        ...             "in": "query",
        ...             "required": True,
        ...             "schema": {"type": "string"}
        ...         }
        ...     ]
        ... }
        >>> func = map_openapi_to_function(spec)
        >>> print(func['name'])
        'getCurrentWeather'
    """

    def _map_schema(schema: dict[str, Any]) -> dict[str, Any]:
        """Recursively map OpenAPI schema to function parameter schema

        Args:
            schema: OpenAPI schema dictionary

        Returns:
            Mapped schema dictionary
        """
        if "schema" in schema:
            schema = schema["schema"]

        mapped_schema = {
            "type": schema.get("type", "string"),
            "description": schema.get("description", ""),
        }

        if "enum" in schema:
            mapped_schema["enum"] = schema["enum"]

        if schema.get("type") == "array" and "items" in schema:
            mapped_schema["items"] = _map_schema(schema["items"])

        if schema.get("type") == "object" and "properties" in schema:
            mapped_schema["properties"] = {
                k: _map_schema(v) for k, v in schema["properties"].items()
            }

        return mapped_schema

    try:
        # Extract parameters from the spec
        parameters = {}
        required_params = []

        # Process query/path/header parameters
        for param in spec.get("parameters", []):
            param_name = param["name"]
            parameters[param_name] = _map_schema(param)

            if param.get("required", False):
                required_params.append(param_name)

        # Process request body if present
        request_body = spec.get("request_body")
        if request_body:
            parameters["request_body"] = request_body

            # Add required fields from request body
            if isinstance(request_body, dict) and "required" in request_body:
                required_params.extend(request_body["required"])

        # Build function definition
        function_def = {
            "name": short_name
            or spec.get("operationId")
            or spec.get("title", "unknown"),
            "description": spec.get("description") or spec.get("summary", ""),
            "parameters": {
                "type": "object",
                "properties": parameters,
                "required": required_params,
            },
        }

        return function_def

    except Exception as e:
        logger.warning(f"Failed to parse OpenAPI spec: {e}")
        logger.debug(f"Spec content: {spec}")
        raise


def normalize_operation_id(operation_id: str) -> str:
    """Normalize operation ID to a valid function name

    Args:
        operation_id: OpenAPI operation ID

    Returns:
        Normalized function name
    """
    # Remove special characters and convert to snake_case
    import re

    # Replace camelCase with snake_case
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", operation_id)
    s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)

    # Remove special characters
    normalized = re.sub(r"[^a-zA-Z0-9_]", "_", s2.lower())

    # Remove duplicate underscores
    normalized = re.sub(r"_+", "_", normalized)

    # Remove leading/trailing underscores
    normalized = normalized.strip("_")

    return normalized


def extract_endpoint_info(
    spec: dict[str, Any], endpoint: str, method: str
) -> dict[str, Any]:
    """Extract endpoint information from OpenAPI spec

    Args:
        spec: Full OpenAPI specification
        endpoint: API endpoint path
        method: HTTP method

    Returns:
        Extracted endpoint information
    """
    method_spec = spec.get("paths", {}).get(endpoint, {}).get(method.lower(), {})

    return {
        "operation_id": method_spec.get("operationId"),
        "summary": method_spec.get("summary"),
        "description": method_spec.get("description"),
        "parameters": method_spec.get("parameters", []),
        "request_body": method_spec.get("requestBody"),
        "responses": method_spec.get("responses", {}),
        "tags": method_spec.get("tags", []),
        "security": method_spec.get("security", []),
    }


def generate_short_name(endpoint: str, method: str) -> str:
    """Generate a short name from endpoint and method

    Args:
        endpoint: API endpoint path
        method: HTTP method

    Returns:
        Generated short name
    """
    # Clean up the endpoint
    clean_endpoint = endpoint.lstrip("/")
    clean_endpoint = clean_endpoint.replace("/", "_")
    clean_endpoint = clean_endpoint.replace("-", "_")
    clean_endpoint = clean_endpoint.replace("{", "")
    clean_endpoint = clean_endpoint.replace("}", "")

    # Combine with method
    short_name = f"{method.lower()}_{clean_endpoint}"

    # Normalize
    return normalize_operation_id(short_name)


def validate_function_spec(func_spec: dict[str, Any]) -> bool:
    """Validate function specification

    Args:
        func_spec: Function specification dictionary

    Returns:
        True if valid, False otherwise
    """
    required_fields = ["name", "description", "parameters"]

    for field in required_fields:
        if field not in func_spec:
            logger.error(f"Missing required field: {field}")
            return False

    # Validate parameters structure
    params = func_spec.get("parameters", {})
    if not isinstance(params, dict):
        logger.error("Parameters must be a dictionary")
        return False

    if params.get("type") != "object":
        logger.error("Parameters type must be 'object'")
        return False

    properties = params.get("properties", {})
    if not isinstance(properties, dict):
        logger.error("Parameters properties must be a dictionary")
        return False

    return True