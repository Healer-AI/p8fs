"""OpenAPI specification parser for P8FS

This module provides the OpenApiSpec class for parsing OpenAPI specifications
and converting them to Function entities that can be stored in the P8FS KV store.
"""

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import requests
import yaml

from p8fs_cluster.logging import get_logger
from p8fs.models.p8 import Function

from .utils import generate_short_name, map_openapi_to_function, normalize_operation_id

logger = get_logger(__name__)


class OpenApiSpec:
    """OpenAPI specification parser and processor

    This class parses OpenAPI specifications from various sources (URLs, files, dict)
    and provides methods to convert endpoints to Function entities that can be
    stored in the P8FS system.
    """

    def __init__(
        self,
        uri_or_spec: str | dict[str, Any],
        token_key: str | None = None,
        alt_host: str | None = None,
    ):
        """Initialize OpenAPI spec parser

        Args:
            uri_or_spec: OpenAPI spec as URL, file path, or dict
            token_key: Optional token key for API authentication
            alt_host: Alternative host for API invocation (e.g., for Docker/K8s)
        """
        self._spec_uri_str = ""
        self.spec = self._load_spec(uri_or_spec)
        self.token_key = token_key
        self.alt_host = alt_host

        # Extract host information
        self.host_uri = self._extract_host_uri()

        # Build operation mappings
        self._endpoint_methods = {
            op_id: (endpoint, method)
            for op_id, endpoint, method in self._iter_operations()
        }
        self.short_names = self._map_short_names()

    def _load_spec(self, uri_or_spec: str | dict[str, Any]) -> dict[str, Any]:
        """Load OpenAPI specification from various sources

        Args:
            uri_or_spec: URL, file path, or dict containing the spec

        Returns:
            Parsed OpenAPI specification as dict
        """
        if isinstance(uri_or_spec, dict):
            return uri_or_spec

        if isinstance(uri_or_spec, str):
            self._spec_uri_str = uri_or_spec

            # Load from URL
            if uri_or_spec.startswith(("http://", "https://")):
                response = requests.get(uri_or_spec)
                if response.status_code == 200:
                    try:
                        return response.json()
                    except json.JSONDecodeError:
                        return yaml.safe_load(response.text)
                else:
                    raise Exception(
                        f"Failed to fetch spec from {uri_or_spec}: {response.status_code}"
                    )

            # Load from file
            else:
                with open(uri_or_spec) as file:
                    content = file.read()
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return yaml.safe_load(content)

        raise ValueError("uri_or_spec must be a URL, file path, or dict")

    def _extract_host_uri(self) -> str:
        """Extract host URI from OpenAPI spec

        Returns:
            Base host URI for API endpoints
        """
        if self.alt_host:
            return self.alt_host

        # OpenAPI 3.0 format
        if "servers" in self.spec:
            return self.spec["servers"][0]["url"]

        # OpenAPI 2.0 (Swagger) format
        if "host" in self.spec:
            scheme = self.spec.get("schemes", ["https"])[0]
            base_path = self.spec.get("basePath", "")
            return f"{scheme}://{self.spec['host']}{base_path}"

        # Fallback to spec URI
        if self._spec_uri_str:
            parsed_url = urlparse(self._spec_uri_str)
            return f"{parsed_url.scheme}://{parsed_url.netloc}"

        return ""

    def _iter_operations(self) -> Iterator[tuple[str, str, str]]:
        """Iterate over all operations in the spec

        Yields:
            Tuple of (operation_id, endpoint, method)
        """
        for endpoint, path_item in self.spec.get("paths", {}).items():
            for method, operation in path_item.items():
                if method.lower() in [
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                ]:
                    operation_id = operation.get("operationId")
                    if operation_id:
                        yield operation_id, endpoint, method.upper()

    def _map_short_names(self) -> dict[str, str]:
        """Map short names to operation IDs

        Returns:
            Dictionary mapping short names to operation IDs
        """
        short_names = {}
        for operation_id, (endpoint, method) in self._endpoint_methods.items():
            short_name = generate_short_name(endpoint, method)
            short_names[short_name] = operation_id
        return short_names

    @property
    def spec_uri(self) -> str:
        """Get the original spec URI"""
        return self._spec_uri_str

    def get_operation_spec(self, operation_id: str) -> dict[str, Any]:
        """Get operation specification by operation ID

        Args:
            operation_id: OpenAPI operation ID

        Returns:
            Operation specification dict
        """
        endpoint, method = self._endpoint_methods[operation_id]
        return self.spec["paths"][endpoint][method.lower()]

    def get_endpoint_method(self, operation_id: str) -> tuple[str, str] | None:
        """Get endpoint and method for operation ID

        Args:
            operation_id: OpenAPI operation ID

        Returns:
            Tuple of (endpoint, method) or None if not found
        """
        return self._endpoint_methods.get(operation_id)

    def resolve_ref(self, ref: str) -> dict[str, Any]:
        """Resolve a $ref to its full JSON schema

        Args:
            ref: JSON reference string (e.g., "#/components/schemas/Pet")

        Returns:
            Resolved schema dict
        """
        parts = ref.lstrip("#/").split("/")
        resolved = self.spec
        for part in parts:
            resolved = resolved[part]
        return resolved

    def get_expanded_schema_for_endpoint(
        self, endpoint: str, method: str
    ) -> dict[str, Any]:
        """Get expanded schema for specific endpoint and method

        Args:
            endpoint: API endpoint path
            method: HTTP method

        Returns:
            Expanded schema with resolved references
        """
        method_spec = self.spec["paths"].get(endpoint, {}).get(method.lower(), {})

        # Process parameters
        parameters = []
        for param in method_spec.get("parameters", []):
            param_schema = param.get("schema", {})
            if "$ref" in param_schema:
                param_schema = self.resolve_ref(param_schema["$ref"])

            parameters.append(
                {
                    "name": param["name"],
                    "in": param["in"],
                    "description": param.get("description", ""),
                    "required": param.get("required", False),
                    "schema": param_schema,
                }
            )

        # Process request body
        request_body = None
        if "requestBody" in method_spec:
            content = method_spec["requestBody"].get("content", {})
            if "application/json" in content:
                schema = content["application/json"].get("schema", {})
                if "$ref" in schema:
                    schema = self.resolve_ref(schema["$ref"])
                request_body = schema

        # Build expanded spec
        expanded = method_spec.copy()
        expanded["parameters"] = parameters
        expanded["request_body"] = request_body

        return expanded

    def iterate_functions(
        self,
        verbs: str | list[str] | None = None,
        filter_ops: str | list[str] | None = None,
    ) -> Iterator[Function]:
        """Iterate over Function entities generated from OpenAPI spec

        Args:
            verbs: HTTP verbs to filter for (e.g., "get,post" or ["get", "post"])
            filter_ops: Operation IDs to filter for

        Yields:
            Function entities ready to be stored in P8FS
        """
        # Process filter parameters
        if isinstance(verbs, str):
            verbs = [v.strip().upper() for v in verbs.split(",")]
        elif isinstance(verbs, list):
            verbs = [v.upper() for v in verbs]

        if isinstance(filter_ops, str):
            filter_ops = [op.strip() for op in filter_ops.split(",")]

        # Map operation IDs to short names
        op_id_to_short_name = {v: k for k, v in self.short_names.items()}

        for operation_id, endpoint, method in self._iter_operations():
            # Apply filters
            if verbs and method not in verbs:
                continue
            if filter_ops and operation_id not in filter_ops:
                continue

            # Get expanded schema
            expanded_spec = self.get_expanded_schema_for_endpoint(endpoint, method)

            # Convert to function spec
            short_name = op_id_to_short_name.get(operation_id)
            function_spec = map_openapi_to_function(expanded_spec, short_name)

            # Create Function entity
            function = Function(
                name=short_name or normalize_operation_id(operation_id),
                key=operation_id,
                proxy_uri=self.host_uri,
                function_spec=function_spec,
                verb=method,
                endpoint=endpoint,
                description=expanded_spec.get("description")
                or expanded_spec.get("summary", ""),
            )

            yield function

    def get_function_by_name(self, name: str) -> Function | None:
        """Get Function entity by name

        Args:
            name: Function name (short name or operation ID)

        Returns:
            Function entity or None if not found
        """
        # Try short name first
        operation_id = self.short_names.get(name)
        if not operation_id:
            # Try operation ID directly
            operation_id = name

        if operation_id not in self._endpoint_methods:
            return None

        endpoint, method = self._endpoint_methods[operation_id]
        expanded_spec = self.get_expanded_schema_for_endpoint(endpoint, method)

        short_name = next(
            (k for k, v in self.short_names.items() if v == operation_id), None
        )
        function_spec = map_openapi_to_function(expanded_spec, short_name)

        return Function(
            name=short_name or normalize_operation_id(operation_id),
            key=operation_id,
            proxy_uri=self.host_uri,
            function_spec=function_spec,
            verb=method,
            endpoint=endpoint,
            description=expanded_spec.get("description")
            or expanded_spec.get("summary", ""),
        )

    def __getitem__(self, key: str) -> tuple[str, str]:
        """Get endpoint and method by operation ID or short name

        Args:
            key: Operation ID or short name

        Returns:
            Tuple of (endpoint, method)
        """
        if key not in self._endpoint_methods:
            if key in self.short_names:
                key = self.short_names[key]
            else:
                raise KeyError(f"Operation {key} not found")

        return self._endpoint_methods[key]

    def __repr__(self) -> str:
        return f"OpenApiSpec({self._spec_uri_str})"

    def __len__(self) -> int:
        return len(self._endpoint_methods)

    def list_operations(self) -> list[str]:
        """List all available operation IDs

        Returns:
            List of operation IDs
        """
        return list(self._endpoint_methods.keys())

    def list_short_names(self) -> list[str]:
        """List all available short names

        Returns:
            List of short names
        """
        return list(self.short_names.keys())