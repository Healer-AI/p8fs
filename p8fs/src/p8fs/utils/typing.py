"""Type inspection utilities for Pydantic models and Python functions.

 
"""

import inspect
import types
from collections.abc import Callable
from datetime import datetime
from typing import (
    Any,
    Union,
    get_args,
    get_origin,
)
from uuid import UUID


class TypeInspector:
    """Utilities for analyzing Python types and converting to SQL types."""

    def __init__(self):
        self._type_cache = {}

    def get_origin_and_args(self, type_hint: Any) -> tuple[Any, tuple[Any, ...]]:
        """Get the origin type and arguments from a type hint."""
        origin = get_origin(type_hint)
        args = get_args(type_hint)
        return origin, args

    def is_optional_type(self, type_hint: Any) -> bool:
        """Check if a type is Optional (Union with None)."""
        origin, args = self.get_origin_and_args(type_hint)
        # Handle both typing.Union and types.UnionType (Python 3.10+)
        if origin is Union or (hasattr(types, 'UnionType') and origin is types.UnionType):
            return type(None) in args
        return False

    def get_non_none_type(self, type_hint: Any) -> Any:
        """Get the non-None type from an Optional type."""
        if not self.is_optional_type(type_hint):
            return type_hint

        origin, args = self.get_origin_and_args(type_hint)
        non_none_types = [arg for arg in args if arg is not type(None)]

        if len(non_none_types) == 1:
            return non_none_types[0]
        elif len(non_none_types) > 1:
            return Union[tuple(non_none_types)]

        return type_hint

    def is_list_type(self, type_hint: Any) -> bool:
        """Check if type is a List type."""
        # Handle bare list type
        if type_hint is list:
            return True
        origin, _ = self.get_origin_and_args(type_hint)
        return origin is list

    def is_dict_type(self, type_hint: Any) -> bool:
        """Check if type is a Dict type."""
        # Handle bare dict type
        if type_hint is dict:
            return True
        origin, _ = self.get_origin_and_args(type_hint)
        return origin is dict

    def is_union_type(self, type_hint: Any) -> bool:
        """Check if type is a Union type."""
        origin, _ = self.get_origin_and_args(type_hint)
        # Handle both typing.Union and types.UnionType (Python 3.10+)
        return origin is Union or (hasattr(types, 'UnionType') and origin is types.UnionType)

    def is_vector_type(self, type_hint: Any) -> bool:
        """Check if type represents a vector (List[float])."""
        origin, args = self.get_origin_and_args(type_hint)
        if origin is list or origin is list:
            if args and (args[0] is float or args[0] == float):
                return True
        return False

    def is_json_type(self, type_hint: Any) -> bool:
        """Check if type should be stored as JSON."""
        # Remove Optional wrapper if present
        core_type = self.get_non_none_type(type_hint)

        # Dict types are JSON
        if self.is_dict_type(core_type):
            return True

        # List types (except vector types) are JSON
        if self.is_list_type(core_type) and not self.is_vector_type(core_type):
            return True

        # Complex Union types are JSON, but exclude common database type unions
        if self.is_union_type(core_type):
            origin, args = self.get_origin_and_args(core_type)
            # Special case: UUID | str is a database type preference, not JSON
            if len(args) == 2 and UUID in args and str in args:
                return False
            # If union has more than 2 args or doesn't include None, treat as JSON
            if len(args) > 2 or type(None) not in args:
                return True

        return False

    def get_primary_union_type(self, type_hint: Any) -> Any:
        """
        Get the primary type from a Union.
        
        For database schema generation, prioritizes database-native types:
        - UUID over str (database storage preference)  
        - First non-None type otherwise
        """
        if not self.is_union_type(type_hint):
            return type_hint

        origin, args = self.get_origin_and_args(type_hint)
        non_none_args = [arg for arg in args if arg is not type(None)]
        
        # Special case: UUID | str - prioritize UUID for database schema
        if len(non_none_args) == 2 and UUID in non_none_args and str in non_none_args:
            return UUID
            
        # Otherwise return first non-None type
        for arg in args:
            if arg is not type(None):
                return arg

        return type_hint

    def python_to_sql_type(self, type_hint: Any, provider=None) -> str:
        """
        Convert Python type hint to SQL type using provider delegation.

        Args:
            type_hint: The Python type annotation to convert
            provider: SQL provider instance that handles dialect-specific mapping

        Returns:
            SQL type string appropriate for the provider's dialect

        Implementation should:
        - Delegate to provider.map_python_type(type_hint) if provider given
        - Handle Optional types by unwrapping and recursing
        - Handle Union types by using primary (first non-None) type
        - Classify types into categories: vector, json, basic, custom
        - Return 'TEXT' as safe fallback for unknown types
        - Never include dialect-specific if/else logic here
        """
        # Handle Optional types
        if self.is_optional_type(type_hint):
            core_type = self.get_non_none_type(type_hint)
            return self.python_to_sql_type(core_type, provider)

        # Handle Union types
        if self.is_union_type(type_hint):
            primary_type = self.get_primary_union_type(type_hint)
            return self.python_to_sql_type(primary_type, provider)

        # Delegate to provider if available
        if provider and hasattr(provider, "map_python_type"):
            return provider.map_python_type(type_hint)

        # Fallback to generic mapping (should be avoided in production)
        return self._get_generic_sql_type(type_hint)

    def _get_generic_sql_type(self, type_hint: Any) -> str:
        """
        Generic SQL type mapping - should only be used as fallback.

        Implementation should:
        - Provide basic type mapping without dialect specifics
        - Use safe, widely-compatible SQL types
        - Always return 'TEXT' for complex or unknown types
        """
        # Basic type mapping (generic/safe)
        type_map = {
            str: "TEXT",
            int: "BIGINT",
            float: "DOUBLE PRECISION",
            bool: "BOOLEAN",
            datetime: "TIMESTAMP",
            UUID: "TEXT",  # Safe generic representation
        }

        if type_hint in type_map:
            return type_map[type_hint]

        # Vector, JSON, and complex types default to TEXT for safety
        return "TEXT"

    def get_sql_type_constraints(
        self, type_hint: Any, field_metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """Get SQL constraints based on type and field metadata."""
        constraints = {}

        # Max length constraint for text fields
        if type_hint is str or type_hint == str:
            max_length = field_metadata.get("max_length")
            if max_length:
                constraints["max_length"] = max_length
            else:
                constraints["max_length"] = 65535  # Default TEXT max

        # Not null constraint
        if not self.is_optional_type(type_hint):
            constraints["not_null"] = True

        # Index constraint
        if field_metadata.get("indexed", False):
            constraints["indexed"] = True

        # Unique constraint
        if field_metadata.get("unique", False):
            constraints["unique"] = True

        return constraints

    def analyze_function_signature(self, func: Callable) -> dict[str, Any]:
        """Analyze a function signature and extract type information."""
        sig = inspect.signature(func)

        analysis = {
            "name": func.__name__,
            "doc": func.__doc__,
            "parameters": {},
            "return_type": None,
            "is_async": inspect.iscoroutinefunction(func),
        }

        # Analyze parameters
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            param_info = {
                "type": param.annotation if param.annotation != param.empty else Any,
                "default": param.default if param.default != param.empty else None,
                "required": param.default == param.empty,
                "kind": param.kind.name,
            }

            # Additional type analysis
            param_info["is_optional"] = self.is_optional_type(param_info["type"])
            param_info["core_type"] = self.get_non_none_type(param_info["type"])
            param_info["is_vector"] = self.is_vector_type(param_info["type"])
            param_info["is_json"] = self.is_json_type(param_info["type"])

            analysis["parameters"][param_name] = param_info

        # Analyze return type
        if sig.return_annotation != sig.empty:
            analysis["return_type"] = {
                "type": sig.return_annotation,
                "is_optional": self.is_optional_type(sig.return_annotation),
                "core_type": self.get_non_none_type(sig.return_annotation),
                "is_vector": self.is_vector_type(sig.return_annotation),
                "is_json": self.is_json_type(sig.return_annotation),
            }

        return analysis

    def extract_nested_types(self, type_hint: Any) -> list[Any]:
        """Extract all nested types from a complex type hint.
        
        Recursively traverses type annotations to extract all component types.
        Useful for analyzing complex generics like Dict[str, List[Union[int, str]]].
        
        Args:
            type_hint: Type annotation to analyze (may be complex/nested)
            
        Returns:
            List[Any]: Flat list of all component types found in the hint
            
        Example:
            For Union[Dict[str, List[int]], None] returns:
            [Union, Dict, str, List, int, NoneType]
        """
        types = []

        origin, args = self.get_origin_and_args(type_hint)

        if origin:
            types.append(origin)
            for arg in args:
                types.extend(self.extract_nested_types(arg))
        else:
            types.append(type_hint)

        return types

    def get_json_schema_type(self, type_hint: Any) -> dict[str, Any]:
        """Convert Python type to JSON Schema type definition."""
        # Handle Optional types
        if self.is_optional_type(type_hint):
            core_type = self.get_non_none_type(type_hint)
            schema = self.get_json_schema_type(core_type)
            schema["nullable"] = True
            return schema

        # Basic type mapping
        type_map = {
            str: {"type": "string"},
            int: {"type": "integer"},
            float: {"type": "number"},
            bool: {"type": "boolean"},
            datetime: {"type": "string", "format": "date-time"},
            UUID: {"type": "string", "format": "uuid"},
        }

        if type_hint in type_map:
            return type_map[type_hint]

        # List types
        if self.is_list_type(type_hint):
            origin, args = self.get_origin_and_args(type_hint)
            schema = {"type": "array"}
            if args:
                schema["items"] = self.get_json_schema_type(args[0])
            else:
                # OpenAI requires items even for untyped arrays
                schema["items"] = {"type": "string"}
            return schema

        # Dict types
        if self.is_dict_type(type_hint):
            origin, args = self.get_origin_and_args(type_hint)
            schema = {"type": "object"}
            if len(args) >= 2:
                schema["additionalProperties"] = self.get_json_schema_type(args[1])
            return schema

        # Union types
        if self.is_union_type(type_hint):
            origin, args = self.get_origin_and_args(type_hint)
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                return self.get_json_schema_type(non_none_args[0])
            else:
                return {
                    "anyOf": [self.get_json_schema_type(arg) for arg in non_none_args]
                }

        # Default for unknown types
        return {"type": "object"}


# Inspection utilities for AbstractModel
def object_namespace(o, default: str = 'public', exclude: list[str] | str = None):
    """
    Simple wrapper to get object namespace as a module but do not allow some and use public as default
    """
    exclude = exclude or ["__main__"]
    if not isinstance(exclude, list):
        exclude = [exclude]
    
    # This convention assumes that types are in a file and the container module is the namespace
    parts = o.__module__.split(".")
    # Convention
    namespace = parts[-2] if len(parts) > 1 else parts[-1]
    if namespace not in exclude:
        return namespace
    return default


def is_strict_subclass(subclass, superclass):
    """Check if subclass is a strict subclass (not the same class)"""
    try:
        if not subclass:
            return False
        return issubclass(subclass, superclass) and subclass is not superclass
    except:
        raise ValueError(
            f"failed to check {subclass}, {superclass} as a strict subclass relationship"
        )


def get_defining_class(member, cls):
    """Get the class that defines a particular method"""
    defining_class = getattr(member, "__objclass__", None)
    if defining_class:
        return defining_class

    # Handle both class and instance - get the actual class
    actual_class = cls if hasattr(cls, 'mro') else type(cls)

    for base_class in actual_class.mro():
        if member.__name__ in base_class.__dict__:
            return base_class
    return None


def get_class_and_instance_methods(cls, inheriting_from: type = None):
    """
    Inspect the methods on the type for methods

    By default only the classes methods are used or we can take anything inheriting from a base such as AbstractModel (not in)

    Args:
        cls: The class to inspect
        inheriting_from: create the excluded base from which to inherit.
        In our case we want to treat the AbstractModel as a base that does not share properties
    """
    methods = []
    class_methods = []

    def __inherits(member):
        """
        Find out if a member inherits from something we care about, not including the thing itself
        """
        if not inheriting_from:
            return True

        # We can traverse up to a point
        return is_strict_subclass(get_defining_class(member, cls), inheriting_from)

    # Get the model name using AbstractModel helper if available
    # This handles both class and instance cases properly
    if hasattr(cls, 'get_model_name'):
        model_name = cls.get_model_name()
    elif hasattr(cls, '__name__'):
        model_name = cls.__name__
    else:
        model_name = type(cls).__name__

    # Ensure model_name is not None
    if model_name is None:
        model_name = type(cls).__name__ if not hasattr(cls, '__name__') else cls.__name__

    for name, member in inspect.getmembers(cls):
        if inspect.isfunction(member) or inspect.ismethod(member):
            # Check if the method belongs to the class and not inherited
            if member.__qualname__ and member.__qualname__.startswith(model_name) or __inherits(member):
                if isinstance(member, types.FunctionType):
                    methods.append(getattr(cls, name))
                elif isinstance(member, types.MethodType):
                    class_methods.append(getattr(cls, name))

    return methods + class_methods
