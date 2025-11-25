"""
Function handler for LLM function calls.

This module provides a registry and execution system for functions that can be
called by language models during conversations. It includes support for:
- Runtime function abstraction from callables
- Extracting functions from classes
- Auto-generating OpenAI function schemas from Python signatures
"""

import asyncio
import inspect
import typing
import uuid
from collections.abc import Callable
from typing import Any

from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)
import sys

# Python 3.11+ has UTC, earlier versions need timezone.utc
if sys.version_info >= (3, 11):
    from datetime import UTC
else:
    from datetime import timezone
    UTC = timezone.utc

from p8fs.models.base import AbstractModel
from p8fs.models.base import Function


class RuntimeFunction(Function):
    """A wrapper for handling library functions at runtime"""

    fn: Callable | None = None

    def __call__(self, *args, **kwargs):
        """
        Convenience to call any function via its proxy
        Emulates the percolate pattern: F('paris') or F(**kwargs)
        """
        # Handle positional arguments by converting to keyword arguments
        if args:
            # Get function signature to map positional args to parameter names
            if self.fn:
                sig = inspect.signature(self.fn)
                params = list(sig.parameters.keys())
                # Skip 'self' if present
                if params and params[0] == 'self':
                    params = params[1:]
                
                # Map positional args to keyword args
                for i, arg in enumerate(args):
                    if i < len(params):
                        kwargs[params[i]] = arg
        
        # Check if this is a proxy function that needs special handling
        if self.proxy_uri and self.proxy_uri != "lib":
            return self._handle_proxy_call(**kwargs)
        
        # Handle direct function calls
        return self._execute_direct(**kwargs)
    
    def _handle_proxy_call(self, **kwargs):
        """
        Handle proxy-based function calls (agent, OpenAPI, etc.)
        Emulates percolate's get_proxy(proxy_uri).invoke(self, **kwargs) pattern
        """
        from p8fs.services.llm.memory_proxy import MemoryProxy
        
        # Check if this is an agent proxy (similar to p8agent/ pattern)
        if "agent/" in self.proxy_uri or "Agent" in self.proxy_uri:
            # Load the agent and invoke
            try:
                # Extract agent name from proxy URI
                if "/" in self.proxy_uri:
                    agent_name = self.proxy_uri.split("/")[-1]
                else:
                    agent_name = self.proxy_uri
                
                # Try to load the model/agent
                from p8fs.utils.inspection import load_entity
                model_context = load_entity(agent_name)
                
                if model_context:
                    # Create memory proxy with the agent context
                    proxy = MemoryProxy(model_context)
                    # Use the function name as the method to call
                    if hasattr(proxy, self.name):
                        method = getattr(proxy, self.name)
                        return method(**kwargs)
                    else:
                        # Fall back to running the agent with the question
                        question = kwargs.get('question') or kwargs.get('query') or str(kwargs)
                        return proxy.run(question)
                
            except Exception as e:
                logger.warning(f"Agent proxy call failed for {self.proxy_uri}: {e}")
        
        # OpenAPI proxy handling (stub for now)
        elif "http" in self.proxy_uri or "https" in self.proxy_uri:
            # TODO: Implement OpenAPI service proxy
            logger.warning(f"OpenAPI proxy not yet implemented: {self.proxy_uri}")
            return {"error": "OpenAPI proxy not implemented", "proxy_uri": self.proxy_uri}
        
        # Default fallback to direct execution
        return self._execute_direct(**kwargs)
    
    def _execute_direct(self, **kwargs):
        """Execute the wrapped function directly - handles bound/unbound methods transparently"""
        if not self.fn:
            raise ValueError(f"No callable function attached to {self.name}")
        
        # Handle different types of callables transparently
        if inspect.ismethod(self.fn):
            # Bound method - just call with kwargs
            return self.fn(**kwargs)
        
        elif inspect.isfunction(self.fn):
            # Unbound function - check if it needs 'self'
            sig = inspect.signature(self.fn)
            params = list(sig.parameters.keys())
            
            if params and params[0] == 'self':
                # This is an unbound instance method - we need to create an instance
                # Get the class from the function's qualified name
                func_qualname = getattr(self.fn, '__qualname__', '')
                if '.' in func_qualname:
                    class_name = func_qualname.split('.')[0]
                    func_module = inspect.getmodule(self.fn)
                    if func_module and hasattr(func_module, class_name):
                        cls = getattr(func_module, class_name)
                        # Create instance and bind method
                        instance = cls()
                        bound_method = getattr(instance, self.fn.__name__)
                        return bound_method(**kwargs)
                
                raise ValueError(f"Cannot call unbound method {self.name} - unable to create instance")
            else:
                # Regular function - call directly
                return self.fn(**kwargs)
        
        else:
            # Some other callable - try direct call
            return self.fn(**kwargs)

    model_config = {
        "arbitrary_types_allowed": True
    }


class FunctionHandler:
    """
    Handles registration and execution of functions for LLM function calls.

    This class maintains a registry of available functions and handles their
    execution when called by language models.
    """

    def __init__(self):
        """Initialize the function handler."""
        self._functions: dict[str, Callable | RuntimeFunction] = {}
        self._function_schemas: dict[str, dict[str, Any]] = {}
        self._runtime_functions: dict[str, RuntimeFunction] = {}
        logger.debug("Initialized FunctionHandler")

    def register(self, name: str, func: Callable, schema: dict[str, Any] | None = None):
        """
        Register a function for LLM calls.

        Args:
            name: Function name as it will be called by the LLM
            func: The callable function
            schema: Optional OpenAI function schema
        """
        self._functions[name] = func

        if schema:
            self._function_schemas[name] = schema
        else:
            # Auto-generate basic schema from function signature
            self._function_schemas[name] = self._generate_schema(name, func)

        logger.info(f"Registered function: {name}")

    def unregister(self, name: str):
        """
        Unregister a function.

        Args:
            name: Function name to unregister
        """
        if name in self._functions:
            del self._functions[name]
            del self._function_schemas[name]
            logger.info(f"Unregistered function: {name}")

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        """
        Execute a registered function.

        Args:
            name: Function name
            arguments: Function arguments as a dictionary

        Returns:
            Function result

        Raises:
            ValueError: If function is not registered
        """
        if name not in self._functions:
            raise ValueError(f"Function '{name}' is not registered")

        func_or_runtime = self._functions[name]

        try:
            # Use the RuntimeFunction object directly via its __call__ method
            # This ensures proper handling of bound/unbound methods, proxy calls, etc.
            if isinstance(func_or_runtime, RuntimeFunction):
                # Call the RuntimeFunction's __call__ method with arguments
                if inspect.iscoroutinefunction(func_or_runtime.fn):
                    # If the underlying function is async, we need to await it
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: func_or_runtime(**arguments)
                    )
                else:
                    # For sync functions, call directly or in executor
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: func_or_runtime(**arguments)
                    )
            else:
                # Handle raw callables (legacy support)
                func = func_or_runtime
                if inspect.iscoroutinefunction(func):
                    result = await func(**arguments)
                else:
                    # Run sync function in executor to avoid blocking
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, lambda: func(**arguments))

            logger.info(f"Executed function '{name}' successfully")
            return result

        except Exception as e:
            logger.error(f"Error executing function '{name}': {e}")
            raise

    def get_schemas(self) -> list[dict[str, Any]]:
        """
        Get all registered function schemas for LLM tools parameter.

        Returns:
            List of function schemas in OpenAI format
        """
        return list(self._function_schemas.values())

    def get_function_names(self) -> list[str]:
        """
        Get list of registered function names.

        Returns:
            List of function names
        """
        return list(self._functions.keys())

    def _generate_schema(self, name: str, func: Callable) -> dict[str, Any]:
        """
        Generate a basic OpenAI function schema from function signature.

        Args:
            name: Function name
            func: The function

        Returns:
            Basic function schema
        """
        sig = inspect.signature(func)
        parameters = {}
        required = []

        for param_name, param in sig.parameters.items():
            # Skip self, cls, *args, **kwargs
            if param_name in ["self", "cls"] or param.kind in [
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ]:
                continue

            # Basic type mapping
            param_type = "string"  # Default
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == list:
                    param_type = "array"
                elif param.annotation == dict:
                    param_type = "object"

            parameters[param_name] = {
                "type": param_type,
                "description": f"Parameter {param_name}",
            }

            # Check if required (no default value)
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": name,
                "description": func.__doc__ or f"Function {name}",
                "parameters": {
                    "type": "object",
                    "properties": parameters,
                    "required": required,
                },
            },
        }

    def add_function(self, function: Callable | Function):
        """
        Add a function to the stack of functions given to the LLM.

        Args:
            function: A callable function or Function type
        """
        EXCLUDED_SYSTEM_FUNCTIONS = ["get_model_functions"]

        if not isinstance(function, Function):
            # Convert callable to RuntimeFunction
            function = self.from_callable(function)

        if function.name not in self._functions:
            # Only add non-private methods
            if (
                not function.name.startswith("_")
                and function.name not in EXCLUDED_SYSTEM_FUNCTIONS
            ):
                self._functions[function.name] = function
                self._runtime_functions[function.name] = function
                self._function_schemas[function.name] = function.function_spec
                logger.debug(f"Added function {function.name}")

    def add_from_class(self, cls: type, inheriting_from: type | None = None):
        """
        Extract and add callable methods from a class.

        Args:
            cls: The class to extract methods from
            inheriting_from: Optional base class to filter methods
        """
        methods = self._get_class_and_instance_methods(cls, inheriting_from)
        for method in methods:
            self.add_function(method)

    @classmethod
    def from_callable(
        cls,
        fn: Callable,
        remove_untyped: bool = True,
        proxy_uri: str | None = None,
        alias: str | None = None,
    ) -> RuntimeFunction:
        """
        Construct a RuntimeFunction from a callable.

        Args:
            fn: The callable function
            remove_untyped: Whether to remove untyped parameters
            proxy_uri: Optional proxy URI
            alias: Optional function name alias

        Returns:
            RuntimeFunction instance
        """

        def process_properties(properties: dict, remove_untyped_params: bool):
            """Process and clean up property definitions"""
            untyped = []

            # Get function signature to check for type annotations
            sig = inspect.signature(fn)
            type_hints = typing.get_type_hints(fn)

            for key, details in properties.items():
                # Remove unnecessary fields
                for remove_field in ["title", "default"]:
                    if remove_field in details:
                        details.pop(remove_field)

                # Handle anyOf types
                if "anyOf" in details:
                    new_list = [t for t in details["anyOf"] if t.get("type") != "null"]
                    if len(new_list) >= 1:
                        details["type"] = new_list[0]["type"]
                        details.pop("anyOf")
                    else:
                        details.pop("anyOf")
                        details["oneOf"] = new_list

                # Recursively process nested properties
                if "properties" in details:
                    process_properties(details["properties"], remove_untyped_params)

                # Mark untyped parameters for removal if requested
                # A parameter is considered untyped if it has no type annotation in the original function
                if remove_untyped_params and key in sig.parameters:
                    param = sig.parameters[key]
                    if (
                        param.annotation == inspect.Parameter.empty
                        and key not in type_hints
                    ):
                        untyped.append(key)

            # Remove untyped parameters only if remove_untyped is True
            if remove_untyped_params:
                for key in untyped:
                    properties.pop(key)

        def _map_schema(schema: dict) -> dict:
            """Map pydantic schema to OpenAI function spec"""
            p = dict(schema)
            if "properties" in p:
                process_properties(p["properties"], remove_untyped)

            name = p.pop("title", fn.__name__)
            desc = p.pop("description", fn.__doc__ or "No description provided")

            return {"name": alias or name, "parameters": p, "description": desc}

        # Determine proxy URI
        if not proxy_uri:
            proxy_uri = (
                fn.__self__.__class__.__name__ if hasattr(fn, "__self__") else "lib"
            )
            if not isinstance(proxy_uri, str):
                proxy_uri = str(proxy_uri)

        # Create pydantic model from function and get schema
        try:
            model = AbstractModel.create_model_from_function(fn)
            schema = model.model_json_schema()
            # If schema has no properties, fall back to manual generation
            if not schema.get("properties"):
                schema = cls._generate_pydantic_schema(fn)
        except:
            # Fallback to manual schema generation
            schema = cls._generate_pydantic_schema(fn)

        spec = _map_schema(schema)
        key = spec["name"] if not proxy_uri else f"{proxy_uri}.{spec['name']}"
        id_md5_uuid = uuid.uuid3(uuid.NAMESPACE_DNS, key)

        # Create OpenAI-style function spec
        function_spec = {"type": "function", "function": spec}

        return RuntimeFunction(
            id=str(id_md5_uuid),
            name=spec["name"],
            key=key,
            endpoint=spec["name"],
            verb="get",
            proxy_uri=proxy_uri,
            function_spec=function_spec,
            description=spec["description"],
            fn=fn,
        )

    @staticmethod
    def _generate_pydantic_schema(fn: Callable) -> dict:
        """
        Generate a pydantic-style schema from function signature.

        Args:
            fn: The function to analyze

        Returns:
            Schema dictionary
        """
        sig = inspect.signature(fn)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            # Skip special parameters
            if param_name in ["self", "cls"] or param.kind in [
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ]:
                continue

            # Basic type mapping
            param_info = {"type": "string"}  # Default

            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_info["type"] = "integer"
                elif param.annotation == float:
                    param_info["type"] = "number"
                elif param.annotation == bool:
                    param_info["type"] = "boolean"
                elif (
                    param.annotation == list
                    or getattr(param.annotation, "__origin__", None) == list
                ):
                    param_info["type"] = "array"
                elif (
                    param.annotation == dict
                    or getattr(param.annotation, "__origin__", None) == dict
                ):
                    param_info["type"] = "object"
                elif param.annotation == str:
                    param_info["type"] = "string"

            properties[param_name] = param_info

            # Check if required (no default value)
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {
            "title": fn.__name__,
            "description": fn.__doc__ or f"Function {fn.__name__}",
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _get_class_and_instance_methods(
        self, cls: type, inheriting_from: type | None = None
    ) -> list[Callable]:
        """
        Extract methods from a class, optionally filtering by inheritance.

        Args:
            cls: The class to inspect
            inheriting_from: Optional base class filter

        Returns:
            List of callable methods
        """
        methods = []

        def is_strict_subclass(subclass, superclass):
            """Check if subclass strictly inherits from superclass"""
            try:
                if not subclass:
                    return False
                return issubclass(subclass, superclass) and subclass is not superclass
            except:
                return False

        def get_defining_class(member, cls):
            """Get the class that defines a member"""
            defining_class = getattr(member, "__objclass__", None)
            if defining_class:
                return defining_class

            for base_class in cls.mro():
                if member.__name__ in base_class.__dict__:
                    return base_class
            return None

        def inherits_from_base(member):
            """Check if member inherits from the specified base"""
            if not inheriting_from:
                return True

            defining_class = get_defining_class(member, cls)
            return is_strict_subclass(defining_class, inheriting_from)

        # Inspect all members of the class
        for name, member in inspect.getmembers(cls):
            if inspect.isfunction(member) or inspect.ismethod(member):
                # Check if method belongs to the class or inherits appropriately
                if member.__qualname__.startswith(cls.__name__) or inherits_from_base(
                    member
                ):
                    # Get the actual method from the class
                    method = getattr(cls, name)
                    if callable(method) and not name.startswith("_"):
                        methods.append(method)

        return methods

    @classmethod
    def create_with_defaults(cls) -> "FunctionHandler":
        """
        Create a function handler with some default utility functions.

        Returns:
            FunctionHandler with default functions registered
        """
        handler = cls()

        # Register some default utility functions
        async def get_current_time() -> str:
            """Get the current UTC time."""
            from datetime import datetime

            return datetime.now(UTC).isoformat()

        handler.register(
            "get_current_time",
            get_current_time,
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get the current UTC time",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        )

        return handler