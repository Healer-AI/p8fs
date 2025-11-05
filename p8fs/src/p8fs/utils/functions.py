"""Function inspection and tool generation utilities.

Required unit tests
- Important to cover function args to json output on tool types e.g. including union types and complex types

Required integration tests
- Important to integration test calling EACH dialect (google, anthropic and openai with) tools generation from these functions
- For integration tests create a shared LLM client object for each provider that can be shared by all tests

"""

import inspect
from collections.abc import Callable
from typing import Any

try:
    from docstring_manager import DocstringManager
except ImportError:
    DocstringManager = None

from .typing import TypeInspector

# Note: AbstractModel import removed to avoid circular imports
# This will be added back when implementing From_Callable.create_model_from_function


class FunctionInspector:
    """Analyze Python functions and extract metadata for tool generation."""

    def __init__(self):
        self.type_inspector = TypeInspector()

    def analyze_function(self, func: Callable) -> dict[str, Any]:
        """Analyze a function and return comprehensive metadata."""
        return self.type_inspector.analyze_function_signature(func)

    def extract_docstring_info(self, func: Callable) -> dict[str, Any]:
        """Extract structured information from function docstring.
        
        Parses docstrings to extract description, parameters, return info, and examples.
        Handles various docstring formats and section detection.
        
        Args:
            func: Function to extract docstring from
            
        Returns:
            Dict containing:
            - description: Main function description
            - parameters: Dict of parameter names to descriptions
            - returns: Return value description
            - examples: List of example usage strings
        """
        doc = func.__doc__ or ""
        lines = [line.strip() for line in doc.split("\n") if line.strip()]

        info = {"description": "", "parameters": {}, "returns": "", "examples": []}

        if not lines:
            return info

        # First line is typically the main description
        info["description"] = lines[0]

        # Parse docstring sections (simplified)
        current_section = "description"
        for line in lines[1:]:
            if line.lower().startswith("args:") or line.lower().startswith(
                "parameters:"
            ):
                current_section = "parameters"
            elif line.lower().startswith("returns:") or line.lower().startswith(
                "return:"
            ):
                current_section = "returns"
            elif line.lower().startswith("examples:") or line.lower().startswith(
                "example:"
            ):
                current_section = "examples"
            elif current_section == "returns" and line:
                info["returns"] = line
            elif current_section == "examples" and line:
                info["examples"].append(line)

        return info

    def get_function_metadata(self, func: Callable) -> dict[str, Any]:
        """Get complete metadata for a function including analysis and docs."""
        signature_info = self.analyze_function(func)
        docstring_info = self.extract_docstring_info(func)

        metadata = {
            **signature_info,
            "docstring_info": docstring_info,
            "module": func.__module__,
            "qualname": func.__qualname__,
        }

        return metadata


class ToolGenerator:
    """Generate LLM tool specifications from Python functions."""

    def __init__(self):
        self.function_inspector = FunctionInspector()
        self.type_inspector = TypeInspector()

    def generate_tool_spec(self, func: Callable) -> dict[str, Any]:
        """Generate a generic tool specification from a function."""
        metadata = self.function_inspector.get_function_metadata(func)

        spec = {
            "name": metadata["name"],
            "description": metadata["docstring_info"]["description"]
            or f"Execute {metadata['name']} function",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }

        # Convert parameters to JSON schema
        for param_name, param_info in metadata["parameters"].items():
            param_schema = self.type_inspector.get_json_schema_type(param_info["type"])

            # Add description from docstring if available
            if param_name in metadata["docstring_info"]["parameters"]:
                param_schema["description"] = metadata["docstring_info"]["parameters"][
                    param_name
                ]

            spec["parameters"]["properties"][param_name] = param_schema

            if param_info["required"]:
                spec["parameters"]["required"].append(param_name)

        return spec

    def to_openai_tool(self, func: Callable) -> dict[str, Any]:
        """Convert function to OpenAI tool format."""
        base_spec = self.generate_tool_spec(func)

        return {"type": "function", "function": base_spec}

    def to_anthropic_tool(self, func: Callable) -> dict[str, Any]:
        """Convert function to Anthropic tool format."""
        base_spec = self.generate_tool_spec(func)

        return {
            "name": base_spec["name"],
            "description": base_spec["description"],
            "input_schema": base_spec["parameters"],
        }

    def to_custom_tool(self, func: Callable, format: str = "generic") -> dict[str, Any]:
        """Convert function to custom tool format."""
        base_spec = self.generate_tool_spec(func)
        metadata = self.function_inspector.get_function_metadata(func)

        if format == "generic":
            return base_spec
        elif format == "extended":
            return {
                **base_spec,
                "metadata": {
                    "module": metadata["module"],
                    "qualname": metadata["qualname"],
                    "is_async": metadata["is_async"],
                    "return_type": str(
                        metadata.get("return_type", {}).get("type", "Any")
                    ),
                },
            }
        else:
            return base_spec

    def generate_tool_registry(
        self, functions: list[Callable]
    ) -> dict[str, dict[str, Any]]:
        """Generate a registry of tools from multiple functions.
        
        Creates a comprehensive registry with multiple format support
        for function calling across different AI providers.
        
        Args:
            functions: List of callable functions to register
            
        Returns:
            Dict mapping function names to tool specifications containing:
            - spec: Generic tool specification
            - function: Original callable function
            - openai: OpenAI-compatible tool format
            - anthropic: Anthropic-compatible tool format
        """
        registry = {}

        for func in functions:
            tool_spec = self.generate_tool_spec(func)
            registry[tool_spec["name"]] = {
                "spec": tool_spec,
                "function": func,
                "openai": self.to_openai_tool(func),
                "anthropic": self.to_anthropic_tool(func),
            }

        return registry


class FunctionHandler:
    """Runtime handler for executing functions as tools."""

    def __init__(self):
        self.registry = {}
        self.tool_generator = ToolGenerator()

    def register(
        self, name: str, func: Callable, schema: dict[str, Any] | None = None
    ) -> None:
        """Register a function as an available tool."""
        if schema is None:
            schema = self.tool_generator.generate_tool_spec(func)

        self.registry[name] = {
            "function": func,
            "schema": schema,
            "metadata": self.tool_generator.function_inspector.get_function_metadata(
                func
            ),
        }

    def register_function(self, func: Callable, name: str | None = None) -> None:
        """Register a function using its name or provided name."""
        function_name = name or func.__name__
        self.register(function_name, func)

    def get_tool_schemas(self, format: str = "openai") -> list[dict[str, Any]]:
        """Get all registered tool schemas in specified format."""
        schemas = []

        for name, info in self.registry.items():
            if format == "openai":
                schema = self.tool_generator.to_openai_tool(info["function"])
            elif format == "anthropic":
                schema = self.tool_generator.to_anthropic_tool(info["function"])
            else:
                schema = info["schema"]

            schemas.append(schema)

        return schemas

    def has_function(self, name: str) -> bool:
        """Check if a function is registered."""
        return name in self.registry

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute a registered function with given arguments."""
        if name not in self.registry:
            raise ValueError(f"Function '{name}' not found in registry")

        func = self.registry[name]["function"]
        metadata = self.registry[name]["metadata"]

        # Validate arguments against schema
        self._validate_arguments(name, arguments)

        # Execute function
        if metadata["is_async"]:
            return await func(**arguments)
        else:
            return func(**arguments)

    def _validate_arguments(self, name: str, arguments: dict[str, Any]) -> None:
        """Validate arguments against function schema."""
        schema = self.registry[name]["schema"]
        required_params = schema["parameters"].get("required", [])
        properties = schema["parameters"].get("properties", {})

        # Check required parameters
        for required_param in required_params:
            if required_param not in arguments:
                raise ValueError(
                    f"Missing required parameter '{required_param}' for function '{name}'"
                )

        # Check for unknown parameters
        for arg_name in arguments:
            if arg_name not in properties:
                raise ValueError(
                    f"Unknown parameter '{arg_name}' for function '{name}'"
                )

    def get_function_info(self, name: str) -> dict[str, Any] | None:
        """Get information about a registered function."""
        return self.registry.get(name)

    def list_functions(self) -> list[str]:
        """List all registered function names."""
        return list(self.registry.keys())

    def clear_registry(self) -> None:
        """Clear all registered functions."""
        self.registry.clear()


class From_Callable:
    """Create callable functions from Python callables with rich typing information extraction."""
    
    def __init__(self, fn: Callable):
        """
        Initialize From_Callable with function analysis.
        
        Args:
            fn: The callable to analyze and wrap
        """
        self.fn = fn
        self.type_inspector = TypeInspector()
        self.docstring_manager = DocstringManager() if DocstringManager else None
        
        # Extract comprehensive function metadata
        self.metadata = self._extract_function_metadata()
        self.schema = self._generate_function_schema()
    
    def _extract_function_metadata(self) -> dict[str, Any]:
        """
        Extract comprehensive metadata from the function.
        
        Returns:
            Dictionary with function name, signature, docstring info, and type analysis
        """
        metadata = {
            'name': self.fn.__name__,
            'module': getattr(self.fn, '__module__', None),
            'qualname': getattr(self.fn, '__qualname__', None),
            'doc': self.fn.__doc__,
            'is_async': inspect.iscoroutinefunction(self.fn),
            'signature': None,
            'parameters': {},
            'return_type': None,
            'docstring_info': {}
        }
        
        # Get function signature
        try:
            sig = inspect.signature(self.fn)
            metadata['signature'] = str(sig)
            
            # Analyze each parameter
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                    
                param_info = {
                    'name': param_name,
                    'annotation': param.annotation if param.annotation != param.empty else Any,
                    'default': param.default if param.default != param.empty else None,
                    'kind': param.kind.name,
                    'required': param.default == param.empty
                }
                
                # Add type analysis
                param_info.update(self._analyze_parameter_type(param_info['annotation']))
                
                metadata['parameters'][param_name] = param_info
            
            # Analyze return type
            if sig.return_annotation != sig.empty:
                metadata['return_type'] = {
                    'annotation': sig.return_annotation,
                    **self._analyze_parameter_type(sig.return_annotation)
                }
        
        except Exception as e:
            # If signature inspection fails, record the error but continue
            metadata['signature_error'] = str(e)
        
        # Extract docstring information
        if self.docstring_manager and self.fn.__doc__:
            try:
                metadata['docstring_info'] = self.docstring_manager.extract(self.fn.__doc__)
            except Exception:
                # Fallback to basic docstring parsing
                metadata['docstring_info'] = self._parse_docstring_basic(self.fn.__doc__)
        else:
            metadata['docstring_info'] = self._parse_docstring_basic(self.fn.__doc__ or "")
        
        return metadata
    
    def _analyze_parameter_type(self, type_annotation: Any) -> dict[str, Any]:
        """
        Analyze a parameter type annotation for detailed type information.
        
        Args:
            type_annotation: The type annotation to analyze
            
        Returns:
            Dictionary with type analysis results
        """
        analysis = {
            'type_str': str(type_annotation),
            'is_optional': self.type_inspector.is_optional_type(type_annotation),
            'is_union': self.type_inspector.is_union_type(type_annotation),
            'is_list': self.type_inspector.is_list_type(type_annotation),
            'is_dict': self.type_inspector.is_dict_type(type_annotation),
            'is_vector': self.type_inspector.is_vector_type(type_annotation),
            'is_json': self.type_inspector.is_json_type(type_annotation)
        }
        
        # Get core type (unwrap Optional)
        if analysis['is_optional']:
            analysis['core_type'] = self.type_inspector.get_non_none_type(type_annotation)
        else:
            analysis['core_type'] = type_annotation
        
        # Get JSON schema representation
        try:
            analysis['json_schema'] = self.type_inspector.get_json_schema_type(type_annotation)
        except Exception:
            analysis['json_schema'] = {'type': 'object'}
        
        return analysis
    
    def _parse_docstring_basic(self, docstring: str) -> dict[str, Any]:
        """
        Basic docstring parsing as fallback when docstring_manager is not available.
        
        Args:
            docstring: The function docstring
            
        Returns:
            Dictionary with parsed docstring information
        """
        if not docstring:
            return {'description': '', 'parameters': {}, 'returns': '', 'examples': []}
        
        lines = [line.strip() for line in docstring.split('\n') if line.strip()]
        
        info = {
            'description': lines[0] if lines else '',
            'parameters': {},
            'returns': '',
            'examples': []
        }
        
        # Simple parsing - first line is description
        # More sophisticated parsing would be handled by docstring_manager
        
        return info
    
    def _generate_function_schema(self) -> dict[str, Any]:
        """
        Generate function schema manually from metadata.
        
        Returns:
            JSON schema for the function
        """
        return self._generate_pydantic_schema()
    
    def _generate_pydantic_schema(self) -> dict[str, Any]:
        """
        Generate Pydantic-compatible schema from function metadata.
        
        Returns:
            JSON schema for the function parameters
        """
        schema = {
            'type': 'object',
            'properties': {},
            'required': []
        }
        
        # Add function description
        if self.metadata['docstring_info'].get('description'):
            schema['description'] = self.metadata['docstring_info']['description']
        
        # Process each parameter
        for param_name, param_info in self.metadata['parameters'].items():
            # Use the JSON schema from type analysis
            param_schema = param_info.get('json_schema', {'type': 'object'})
            
            # Add parameter description from docstring
            docstring_info = self.metadata['docstring_info'].get('parameters', {})
            if param_name in docstring_info:
                param_schema['description'] = docstring_info[param_name]
            
            schema['properties'][param_name] = param_schema
            
            # Add to required if parameter has no default
            if param_info['required']:
                schema['required'].append(param_name)
        
        return schema
    
    def to_openai_tool(self) -> dict[str, Any]:
        """
        Convert to OpenAI tool format.
        
        Returns:
            OpenAI tool specification
        """
        return {
            'type': 'function',
            'function': {
                'name': self.metadata['name'],
                'description': self.metadata['docstring_info'].get('description', ''),
                'parameters': self.schema
            }
        }
    
    def to_anthropic_tool(self) -> dict[str, Any]:
        """
        Convert to Anthropic tool format.
        
        Returns:
            Anthropic tool specification
        """
        return {
            'name': self.metadata['name'],
            'description': self.metadata['docstring_info'].get('description', ''),
            'input_schema': self.schema
        }
    
    def to_google_tool(self) -> dict[str, Any]:
        """
        Convert to Google tool format.
        
        Returns:
            Google tool specification
        """
        return {
            'function_declarations': [{
                'name': self.metadata['name'],
                'description': self.metadata['docstring_info'].get('description', ''),
                'parameters': self.schema
            }]
        }
    
    def __call__(self, *args, **kwargs):
        """
        Make the wrapper callable - delegates to the original function.
        
        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result of calling the original function
        """
        return self.fn(*args, **kwargs)
    
    def get_metadata(self) -> dict[str, Any]:
        """
        Get complete function metadata.
        
        Returns:
            Dictionary with all extracted metadata
        """
        return self.metadata
    
    def get_schema(self) -> dict[str, Any]:
        """
        Get function parameter schema.
        
        Returns:
            JSON schema for function parameters
        """
        return self.schema
    
    def validate_call_args(self, **kwargs) -> dict[str, Any]:
        """
        Validate call arguments against the function schema.
        
        Args:
            **kwargs: Arguments to validate
            
        Returns:
            Validated and type-converted arguments
            
        Raises:
            ValueError: If validation fails
        """
        validated_args = {}
        
        # Check required parameters
        for param_name in self.schema.get('required', []):
            if param_name not in kwargs:
                raise ValueError(f"Missing required parameter: {param_name}")
        
        # Validate each provided argument
        for param_name, value in kwargs.items():
            if param_name not in self.metadata['parameters']:
                raise ValueError(f"Unknown parameter: {param_name}")
            
            # Basic type validation could be added here
            validated_args[param_name] = value
        
        return validated_args
    
    def call(self, **kwargs):
        """
        Call the function with validated arguments.
        
        Args:
            **kwargs: Arguments to pass to the function
            
        Returns:
            Result of calling the function
        """
        validated_args = self.validate_call_args(**kwargs)
        return self.fn(**validated_args)
    
    async def call_async(self, **kwargs):
        """
        Call the function asynchronously with validated arguments.
        
        Args:
            **kwargs: Arguments to pass to the function
            
        Returns:
            Result of calling the function
        """
        validated_args = self.validate_call_args(**kwargs)
        if self.is_async:
            return await self.fn(**validated_args)
        else:
            return self.fn(**validated_args)
    
    @property
    def is_async(self) -> bool:
        """Check if the function is async."""
        return self.metadata.get('is_async', False)
